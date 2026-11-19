"""Copy one station's raw source files into the bronze/ layer of our bucket, unchanged.

Source layout: <folder>/<station_id> - <station name>/<DD-MM-YYYY>/<file>
Bronze layout: bronze/<same key as in the source>

Station folder names are NFD-normalized, so the station is selected by its numeric ID, never by name.
Files that already exist in bronze are skipped, so running the copy again changes nothing (idempotent).
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import boto3
from botocore.config import Config as BotoConfig

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

BRONZE_PREFIX = "bronze/"
MAX_WORKERS = 16
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
    More than one folder with the same ID (e.g. after a station rename) is an error, not a silent pick.
    """
    matches = [
        prefix
        for prefix in _list_prefixes(s3, bucket, f"{folder}/")
        if prefix[len(folder) + 1 :].rstrip("/").split(" - ", 1)[0] == station_id
    ]
    if not matches:
        raise ValueError(f"Station {station_id} not found in s3://{bucket}/{folder}/")
    if len(matches) > 1:
        raise ValueError(f"Station {station_id} has {len(matches)} folders in s3://{bucket}/{folder}/")
    return matches[0]


def copy_source(s3, source_bucket: str, target_bucket: str, folder: str, station_id: str) -> dict[str, int]:
    """Copy all files of one station from one source folder to bronze/, skipping files already there."""
    station_prefix = find_station_prefix(s3, source_bucket, folder, station_id)
    existing = set(_list_keys(s3, target_bucket, BRONZE_PREFIX + station_prefix))

    source_keys = _list_keys(s3, source_bucket, station_prefix)
    to_copy = [key for key in source_keys if BRONZE_PREFIX + key not in existing]

    def copy(key: str) -> None:
        # Server-side copy: the data never passes through the Lambda.
        s3.copy_object(Bucket=target_bucket, Key=BRONZE_PREFIX + key, CopySource={"Bucket": source_bucket, "Key": key})

    # One copy takes ~80 ms, almost all of it waiting on S3, so threads cut ~4,100 copies from ~5.5 min to seconds.
    # map() hands every copy to the pool up front; on a failure the pool still finishes the other copies, then list()
    # re-raises the error. Only the failed files are missing, and the next run copies just those.
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        list(pool.map(copy, to_copy))

    result = {"copied": len(to_copy), "skipped": len(source_keys) - len(to_copy)}
    log.info("%s: copied %d, skipped %d", folder, result["copied"], result["skipped"])
    return result


def client_config() -> BotoConfig:
    # One HTTP connection per copy thread (the default pool has only 10), and standard retries with backoff
    # so an occasional S3 SlowDown/503 under 16 parallel copies does not abort the run.
    return BotoConfig(max_pool_connections=MAX_WORKERS, retries={"mode": "standard", "max_attempts": 10})


def handler(event, context, s3=None) -> dict[str, dict[str, int]]:
    """Lambda entry point. The event is ignored; everything comes from environment variables."""
    config = load_config()
    s3 = s3 or boto3.client("s3", config=client_config())
    log.info("Copying station %s (%s) folders %s to bronze", config.station_id, config.city_name, config.source_folders)
    return {
        folder: copy_source(s3, config.source_bucket, config.target_bucket, folder, config.station_id)
        for folder in config.source_folders
    }
