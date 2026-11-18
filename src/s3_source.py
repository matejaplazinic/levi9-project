"""Read pollution/weather CSV files for a single station from the source S3 bucket.

Bucket layout: <source>/<station_id> - <station name>/<DD-MM-YYYY>/<file without extension>
Station folder names are NFD-normalized, so stations are selected by numeric ID, not by name.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

DAY_FORMAT = "%d-%m-%Y"


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


def find_city_prefix(s3, bucket: str, source: str, station_id: str) -> str:
    """Return the full S3 prefix of a station folder (e.g. 'pollution/35120 - .../') by its ID."""
    for prefix in _list_prefixes(s3, bucket, f"{source}/"):
        folder = prefix[len(source) + 1 :].rstrip("/")
        if folder.split(" - ", 1)[0] == station_id:
            return prefix
    raise ValueError(f"Station {station_id} not found in s3://{bucket}/{source}/")


def list_day_keys(s3, bucket: str, city_prefix: str, day: str | None = None) -> tuple[str, list[str]]:
    """Return (day, sorted keys) for the given DD-MM-YYYY day, or for the earliest available day."""
    if day is None:
        days = [p[len(city_prefix) :].rstrip("/") for p in _list_prefixes(s3, bucket, city_prefix)]
        if not days:
            raise ValueError(f"No day folders under s3://{bucket}/{city_prefix}")
        day = min(days, key=lambda d: datetime.strptime(d, DAY_FORMAT))
    else:
        datetime.strptime(day, DAY_FORMAT)  # validate format early
    return day, _list_keys(s3, bucket, f"{city_prefix}{day}/")


def local_path(root: Path, source: str, station_id: str, key: str) -> Path:
    """Local target path: <root>/<source>/<station_id>/<day>/<file>.csv (no accents or spaces)."""
    day, filename = key.split("/")[-2:]
    return Path(root) / source / station_id / day / f"{filename}.csv"


def download_files(
    s3, bucket: str, source: str, station_id: str, keys: list[str], limit: int, root: Path
) -> list[Path]:
    """Download at most `limit` objects and return their local paths."""
    paths: list[Path] = []
    for key in keys[:limit]:
        target = local_path(root, source, station_id, key)
        target.parent.mkdir(parents=True, exist_ok=True)
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        target.write_bytes(body)
        log.info("Downloaded s3://%s/%s", bucket, key)
        paths.append(target)
    return paths
