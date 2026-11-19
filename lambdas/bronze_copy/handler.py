"""Copy one station's raw source files into the bronze/ layer of our bucket, unchanged.

Source layout: <folder>/<station_id> - <station name>/<DD-MM-YYYY>/<file>
Bronze layout: bronze/<same key as in the source>

Station folder names are NFD-normalized, so the station is selected by its numeric ID, never by name.
Files that already exist in bronze are skipped, so running the copy again changes nothing (idempotent).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import boto3

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

BRONZE_PREFIX = "bronze/"
ENV_VARS = ("SOURCE_BUCKET", "TARGET_BUCKET", "STATION_ID", "CITY_NAME", "SOURCE_FOLDERS")


@dataclass(frozen=True)
class Config:
    source_bucket: str
    target_bucket: str
    station_id: str
    city_name: str
    source_folders: tuple[str, ...]


def load_config(env=os.environ) -> Config:
    """Read the configuration from environment variables; nothing about the city lives in the code."""
    missing = [name for name in ENV_VARS if not env.get(name, "").strip()]
    if missing:
        raise ValueError(f"Missing environment variables: {', '.join(missing)}")
    folders = tuple(f.strip().strip("/") for f in env["SOURCE_FOLDERS"].split(",") if f.strip())
    if not folders:
        raise ValueError("SOURCE_FOLDERS has no folder names")
    config = Config(
        source_bucket=env["SOURCE_BUCKET"].strip(),
        target_bucket=env["TARGET_BUCKET"].strip(),
        station_id=env["STATION_ID"].strip(),
        city_name=env["CITY_NAME"].strip(),
        source_folders=folders,
    )
    if config.source_bucket == config.target_bucket:
        raise ValueError("TARGET_BUCKET must differ from SOURCE_BUCKET; the source is read-only")
    return config


def _list_prefixes(s3, bucket: str, prefix: str) -> list[str]:
    paginator = s3.get_paginator("list_objects_v2")
    out: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        out.extend(p["Prefix"] for p in page.get("CommonPrefixes", []))
    return out


def _list_keys(s3, bucket: str, prefix: str) -> list[str]:
    paginator = s3.get_paginator("list_objects_v2")
    out: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        out.extend(o["Key"] for o in page.get("Contents", []))
    return sorted(out)


def find_station_prefix(s3, bucket: str, folder: str, station_id: str) -> str:
    """Return the station's folder prefix (e.g. 'pollution/<id> - <name>/') by its numeric ID.

    Same logic as src/s3_source.find_city_prefix, kept here so the Lambda package needs only boto3.
    """
    for prefix in _list_prefixes(s3, bucket, f"{folder}/"):
        name = prefix[len(folder) + 1 :].rstrip("/")
        if name.split(" - ", 1)[0] == station_id:
            return prefix
    raise ValueError(f"Station {station_id} not found in s3://{bucket}/{folder}/")


def copy_source(s3, source_bucket: str, target_bucket: str, folder: str, station_id: str) -> dict[str, int]:
    """Copy all files of one station from one source folder to bronze/, skipping files already there."""
    station_prefix = find_station_prefix(s3, source_bucket, folder, station_id)
    existing = set(_list_keys(s3, target_bucket, BRONZE_PREFIX + station_prefix))

    copied = skipped = 0
    for key in _list_keys(s3, source_bucket, station_prefix):
        target_key = BRONZE_PREFIX + key
        if target_key in existing:
            skipped += 1
            continue
        # Server-side copy: the data never passes through the Lambda.
        s3.copy_object(Bucket=target_bucket, Key=target_key, CopySource={"Bucket": source_bucket, "Key": key})
        copied += 1

    log.info("%s: copied %d, skipped %d", folder, copied, skipped)
    return {"copied": copied, "skipped": skipped}


def handler(event, context, s3=None) -> dict[str, dict[str, int]]:
    """Lambda entry point. The event is ignored; everything comes from environment variables."""
    config = load_config()
    s3 = s3 or boto3.client("s3")
    log.info("Copying station %s (%s) folders %s to bronze", config.station_id, config.city_name, config.source_folders)
    return {
        folder: copy_source(s3, config.source_bucket, config.target_bucket, folder, config.station_id)
        for folder in config.source_folders
    }
