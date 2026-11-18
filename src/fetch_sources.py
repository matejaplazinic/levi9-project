"""CLI: download sample pollution/weather files for one station and call the tourist API once.

Example:
    py -m src.fetch_sources --profile mateja --station 35120 --files 5 --tourist-date 2022-04-15
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, SSOError, TokenRetrievalError

from src import s3_source, tourist_api

BUCKET = "levi9-praksa-2026-data"
BUCKET_REGION = "eu-north-1"
SOURCES = ("pollution", "weather")

log = logging.getLogger("fetch_sources")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", default=os.environ.get("AWS_PROFILE"), help="AWS SSO profile (default: $AWS_PROFILE)")
    p.add_argument("--bucket", default=BUCKET)
    p.add_argument("--station", default="35120", help="Station ID (default: 35120, Novi Sad)")
    p.add_argument("--files", type=int, default=5, help="Files per source (default: 5)")
    p.add_argument("--day", help="Day folder DD-MM-YYYY (default: earliest available)")
    p.add_argument("--tourist-date", default="2022-04-15", help="YYYY-MM-DD (default: 2022-04-15)")
    p.add_argument("--tourist-url", default=os.environ.get("TOURIST_API_URL", tourist_api.DEFAULT_URL))
    p.add_argument("--out", type=Path, default=Path("data/raw"), help="Output folder (default: data/raw)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--skip-tourist", action="store_true", help="Only download S3 files")
    mode.add_argument("--only-tourist", action="store_true", help="Only call the tourist API")
    args = p.parse_args(argv)
    if args.files < 1:
        p.error("--files must be >= 1")
    try:
        if args.day is not None:
            s3_source.validate_day(args.day)
        if not args.skip_tourist:
            tourist_api.validate_date(args.tourist_date)
            tourist_api.validate_url(args.tourist_url)
    except ValueError as e:
        p.error(str(e))
    return args


def download_sources(session: boto3.Session, args: argparse.Namespace) -> list[Path]:
    s3 = session.client("s3", region_name=BUCKET_REGION)
    all_paths: list[Path] = []
    for source in SOURCES:
        prefix = s3_source.find_city_prefix(s3, args.bucket, source, args.station)
        day, keys = s3_source.list_day_keys(s3, args.bucket, prefix, args.day)
        log.info("%s: %d files on %s, downloading %d", source, len(keys), day, min(args.files, len(keys)))
        all_paths += s3_source.download_files(s3, args.bucket, source, args.station, keys, args.files, args.out)
    return all_paths


def call_tourist(session: boto3.Session, args: argparse.Namespace) -> Path:
    sm = session.client("secretsmanager", region_name=tourist_api.SECRET_REGION)
    token = tourist_api.get_token(sm)
    payload = tourist_api.fetch_estimate(args.tourist_url, args.tourist_date, token)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    target = args.out / "tourist" / f"{args.tourist_date}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    args = parse_args(argv)

    session = boto3.Session(profile_name=args.profile)
    try:
        if not args.only_tourist:
            for path in download_sources(session, args):
                print(path.as_posix())
        if not args.skip_tourist:
            saved = call_tourist(session, args)
            log.info("Tourist response saved to %s", saved.as_posix())
    except (TokenRetrievalError, SSOError, NoCredentialsError) as e:
        log.error(
            "AWS login missing or expired (%s). Run: aws sso login --profile %s",
            type(e).__name__,
            args.profile or "<profile>  (or pass --profile / set AWS_PROFILE)",
        )
        return 2
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in {"ExpiredToken", "ExpiredTokenException", "UnrecognizedClientException"}:
            log.error("AWS session expired. Run: aws sso login --profile %s", args.profile)
        else:
            log.error("AWS error: %s", e)
        return 2
    except (ValueError, tourist_api.TouristApiError) as e:
        log.error("%s", e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
