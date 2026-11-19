import unicodedata

import boto3
import pytest
from moto import mock_aws

from lambdas.bronze_copy import handler

REGION = "eu-north-1"
SOURCE = "source-bucket"
TARGET = "target-bucket"
# Folder names in the real bucket are NFD-normalized ("C" + combining acute accent).
NS = unicodedata.normalize("NFD", "35120 - Ćirila i Metodija, Novi Sad, Serbia")
BG = unicodedata.normalize("NFD", "1297 - Dorćol 2, Beograd, Serbia")
# Starts with "35120" but is a different station; it must never match.
LOOKALIKE = "351200 - Somewhere Else, Serbia"

NS_KEYS = [
    f"pollution/{NS}/30-03-2022/file-a",
    f"pollution/{NS}/30-03-2022/file-b",
    f"pollution/{NS}/31-03-2022/file-c",
]
OTHER_KEYS = [f"pollution/{BG}/30-03-2022/file-x", f"pollution/{LOOKALIKE}/30-03-2022/file-y"]


@pytest.fixture
def s3(monkeypatch):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SECURITY_TOKEN", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        for bucket in (SOURCE, TARGET):
            client.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
        for key in NS_KEYS + OTHER_KEYS:
            client.put_object(Bucket=SOURCE, Key=key, Body=f"csv,for\n{key},1\n".encode())
        yield client


def _keys(client, bucket, prefix=""):
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
    return sorted(o["Key"] for page in pages for o in page.get("Contents", []))


def _body(client, bucket, key):
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def test_copies_every_station_file_into_bronze_unchanged(s3):
    result = handler.copy_source(s3, SOURCE, TARGET, "pollution", "35120")

    assert result == {"copied": 3, "skipped": 0}
    assert _keys(s3, TARGET) == sorted(f"bronze/{k}" for k in NS_KEYS)
    for key in NS_KEYS:
        assert _body(s3, TARGET, f"bronze/{key}") == _body(s3, SOURCE, key)


def test_other_stations_are_not_copied(s3):
    handler.copy_source(s3, SOURCE, TARGET, "pollution", "35120")

    copied = _keys(s3, TARGET)
    assert not any(BG in k or LOOKALIKE in k for k in copied)


def test_second_run_copies_nothing(s3):
    handler.copy_source(s3, SOURCE, TARGET, "pollution", "35120")
    etags = {k: s3.head_object(Bucket=TARGET, Key=k)["ETag"] for k in _keys(s3, TARGET)}

    result = handler.copy_source(s3, SOURCE, TARGET, "pollution", "35120")

    assert result == {"copied": 0, "skipped": 3}
    assert {k: s3.head_object(Bucket=TARGET, Key=k)["ETag"] for k in _keys(s3, TARGET)} == etags


def test_only_new_source_files_are_copied_on_rerun(s3):
    handler.copy_source(s3, SOURCE, TARGET, "pollution", "35120")
    new_key = f"pollution/{NS}/01-04-2022/file-d"
    s3.put_object(Bucket=SOURCE, Key=new_key, Body=b"new")

    result = handler.copy_source(s3, SOURCE, TARGET, "pollution", "35120")

    assert result == {"copied": 1, "skipped": 3}
    assert _body(s3, TARGET, f"bronze/{new_key}") == b"new"


def test_source_bucket_is_not_modified(s3):
    before = {k: s3.head_object(Bucket=SOURCE, Key=k)["ETag"] for k in _keys(s3, SOURCE)}

    handler.copy_source(s3, SOURCE, TARGET, "pollution", "35120")

    assert {k: s3.head_object(Bucket=SOURCE, Key=k)["ETag"] for k in _keys(s3, SOURCE)} == before


def test_unknown_station_raises(s3):
    with pytest.raises(ValueError, match="Station 99999 not found"):
        handler.copy_source(s3, SOURCE, TARGET, "pollution", "99999")
