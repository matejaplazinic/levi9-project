import re
import unicodedata
from pathlib import Path

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


WEATHER_KEYS = [f"weather/{NS}/30-03-2022/file-w1", f"weather/{NS}/30-03-2022/file-w2"]
ENV = {
    "SOURCE_BUCKET": SOURCE,
    "TARGET_BUCKET": TARGET,
    "STATION_ID": "35120",
    "CITY_NAME": "Novi Sad",
    "SOURCE_FOLDERS": "pollution, weather",
}


@pytest.fixture
def lambda_env(monkeypatch, s3):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    for key in WEATHER_KEYS:
        s3.put_object(Bucket=SOURCE, Key=key, Body=b"weather")
    return s3


def test_handler_copies_all_configured_folders(lambda_env):
    result = handler.handler({}, None, s3=lambda_env)

    assert result == {"pollution": {"copied": 3, "skipped": 0}, "weather": {"copied": 2, "skipped": 0}}
    assert _keys(lambda_env, TARGET, "bronze/pollution/") == sorted(f"bronze/{k}" for k in NS_KEYS)
    assert _keys(lambda_env, TARGET, "bronze/weather/") == sorted(f"bronze/{k}" for k in WEATHER_KEYS)


def test_handler_second_run_copies_nothing(lambda_env):
    handler.handler({}, None, s3=lambda_env)

    result = handler.handler({}, None, s3=lambda_env)

    assert result == {"pollution": {"copied": 0, "skipped": 3}, "weather": {"copied": 0, "skipped": 2}}


def test_handler_creates_its_own_client_when_none_given(lambda_env, monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)

    assert handler.handler({}, None)["weather"]["copied"] == 2


def test_load_config_parses_folders():
    config = handler.load_config({**ENV, "SOURCE_FOLDERS": " pollution/ ,weather,, "})

    assert config.source_folders == ("pollution", "weather")
    assert config.station_id == "35120"


@pytest.mark.parametrize("name", handler.ENV_VARS)
def test_load_config_names_missing_variable(name):
    env = {k: v for k, v in ENV.items() if k != name}

    with pytest.raises(ValueError, match=name):
        handler.load_config(env)


def test_load_config_rejects_empty_folder_list():
    with pytest.raises(ValueError, match="SOURCE_FOLDERS"):
        handler.load_config({**ENV, "SOURCE_FOLDERS": " , "})


def test_load_config_refuses_to_write_into_source_bucket():
    with pytest.raises(ValueError, match="read-only"):
        handler.load_config({**ENV, "TARGET_BUCKET": SOURCE})


def test_lambda_code_has_no_hardcoded_city_or_station():
    root = Path(handler.__file__).resolve().parent
    offenders = [p.name for p in root.rglob("*.py") if re.search(r"35120|Novi Sad", p.read_text(encoding="utf-8"))]
    assert offenders == []
