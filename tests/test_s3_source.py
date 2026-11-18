import io
import unicodedata
from pathlib import Path

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from src import s3_source

BUCKET = "levi9-praksa-2026-data"
# Folder names in the real bucket are NFD-normalized ("C" + combining acute accent).
NS_NAME = unicodedata.normalize("NFD", "35120 - Ćirila i Metodija, Novi Sad, Serbia")
BG_NAME = unicodedata.normalize("NFD", "1297 - Dorćol 2, Beograd, Serbia")


@pytest.fixture
def s3():
    client = boto3.client(
        "s3", region_name="eu-north-1", aws_access_key_id="x", aws_secret_access_key="x"
    )
    with Stubber(client) as stub:
        yield client, stub


def _prefixes(*names):
    return {"CommonPrefixes": [{"Prefix": n} for n in names]}


def test_find_city_prefix_matches_station_id_with_nfd_name(s3):
    client, stub = s3
    stub.add_response(
        "list_objects_v2",
        _prefixes(f"pollution/{BG_NAME}/", f"pollution/{NS_NAME}/"),
        {"Bucket": BUCKET, "Prefix": "pollution/", "Delimiter": "/"},
    )
    assert s3_source.find_city_prefix(client, BUCKET, "pollution", "35120") == f"pollution/{NS_NAME}/"


def test_find_city_prefix_does_not_match_id_prefix(s3):
    client, stub = s3
    # "1297" must not match a station like "12970 - ..."
    stub.add_response(
        "list_objects_v2",
        _prefixes("pollution/12970 - Other, City/"),
        {"Bucket": BUCKET, "Prefix": "pollution/", "Delimiter": "/"},
    )
    with pytest.raises(ValueError, match="1297"):
        s3_source.find_city_prefix(client, BUCKET, "pollution", "1297")


def test_list_day_keys_picks_earliest_day_chronologically(s3):
    client, stub = s3
    prefix = f"weather/{NS_NAME}/"
    # Lexical order would pick 01-04-2022; chronological earliest is 30-03-2022.
    stub.add_response(
        "list_objects_v2",
        _prefixes(f"{prefix}01-04-2022/", f"{prefix}30-03-2022/", f"{prefix}31-03-2022/"),
        {"Bucket": BUCKET, "Prefix": prefix, "Delimiter": "/"},
    )
    stub.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": f"{prefix}30-03-2022/b"}, {"Key": f"{prefix}30-03-2022/a"}]},
        {"Bucket": BUCKET, "Prefix": f"{prefix}30-03-2022/"},
    )
    day, keys = s3_source.list_day_keys(client, BUCKET, prefix)
    assert day == "30-03-2022"
    assert keys == [f"{prefix}30-03-2022/a", f"{prefix}30-03-2022/b"]


def test_list_day_keys_uses_given_day(s3):
    client, stub = s3
    prefix = f"weather/{NS_NAME}/"
    stub.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": f"{prefix}15-04-2022/a"}]},
        {"Bucket": BUCKET, "Prefix": f"{prefix}15-04-2022/"},
    )
    assert s3_source.list_day_keys(client, BUCKET, prefix, day="15-04-2022") == (
        "15-04-2022",
        [f"{prefix}15-04-2022/a"],
    )


def test_local_path_uses_station_id_and_csv_extension(tmp_path):
    key = f"pollution/{NS_NAME}/01-04-2022/levi9-hack9-pollution-firehose-2-xyz"
    assert s3_source.local_path(tmp_path, "pollution", "35120", key) == (
        tmp_path / "pollution" / "35120" / "01-04-2022" / "levi9-hack9-pollution-firehose-2-xyz.csv"
    )


def test_download_files_respects_limit(s3, tmp_path):
    client, stub = s3
    keys = [f"pollution/{NS_NAME}/01-04-2022/f{i}" for i in range(4)]
    for k in keys[:2]:
        body = "name,x\nčš,1\n".encode("utf-8")
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(body), len(body))},
            {"Bucket": BUCKET, "Key": k},
        )
    paths = s3_source.download_files(client, BUCKET, "pollution", "35120", keys, limit=2, root=tmp_path)
    assert len(paths) == 2
    assert all(isinstance(p, Path) and p.exists() for p in paths)
    assert paths[0].read_text(encoding="utf-8") == "name,x\nčš,1\n"
    stub.assert_no_pending_responses()
