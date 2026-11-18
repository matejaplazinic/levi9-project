import json

import pytest

from src import fetch_sources, s3_source, tourist_api


@pytest.mark.parametrize(
    "argv",
    [
        ["--day", "1-4-2022", "--skip-tourist"],
        ["--day", "2022-04-01", "--skip-tourist"],
        ["--tourist-url", "http://example.com/"],
        ["--tourist-date", "15-04-2022"],
    ],
)
def test_parse_args_rejects_bad_input(argv):
    with pytest.raises(SystemExit) as exc:
        fetch_sources.parse_args(argv)
    assert exc.value.code == 2


def test_parse_args_skips_tourist_validation_when_skipped():
    args = fetch_sources.parse_args(["--skip-tourist", "--tourist-url", "http://x", "--day", "01-04-2022"])
    assert args.day == "01-04-2022"


@pytest.fixture
def no_aws(monkeypatch):
    class FakeSession:
        def __init__(self, profile_name=None):
            pass

        def client(self, *a, **k):
            return object()

    monkeypatch.setattr(fetch_sources.boto3, "Session", FakeSession)


def test_main_fails_when_day_has_no_s3_files(no_aws, monkeypatch, tmp_path):
    monkeypatch.setattr(s3_source, "find_city_prefix", lambda *a: "pollution/35120 - X/")

    def empty_day(*a):
        raise ValueError("No files for 01-01-2022 under s3://bucket/pollution/35120 - X/")

    monkeypatch.setattr(s3_source, "list_day_keys", empty_day)
    rc = fetch_sources.main(["--day", "01-01-2022", "--skip-tourist", "--out", str(tmp_path)])
    assert rc != 0


def test_main_does_not_overwrite_saved_response_on_bad_payload(no_aws, monkeypatch, tmp_path):
    saved = tmp_path / "tourist" / "2022-04-15.json"
    saved.parent.mkdir(parents=True)
    good = {"for_date": "2022-04-15", "info": [{"name": "Novi Sad", "estimated_no_people": 19628}]}
    saved.write_text(json.dumps(good), encoding="utf-8")

    class Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"for_date": "2022-04-16"}

    monkeypatch.setattr(tourist_api, "get_token", lambda sm: "tok")
    monkeypatch.setattr(tourist_api.requests, "get", lambda *a, **k: Resp())
    rc = fetch_sources.main(["--only-tourist", "--tourist-date", "2022-04-15", "--out", str(tmp_path)])
    assert rc != 0
    assert json.loads(saved.read_text(encoding="utf-8")) == good
