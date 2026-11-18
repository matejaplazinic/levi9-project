import json
import logging

import boto3
import pytest
from botocore.stub import Stubber

from src import tourist_api

TOKEN = "super-secret-token-123"
URL = "https://example.lambda-url.eu-north-1.on.aws/"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


@pytest.fixture
def sm():
    client = boto3.client(
        "secretsmanager", region_name="eu-north-1", aws_access_key_id="x", aws_secret_access_key="x"
    )
    with Stubber(client) as stub:
        yield client, stub


@pytest.mark.parametrize(
    "secret_string",
    [TOKEN, f"  {TOKEN}\n", json.dumps({"tourist_estimate_token": TOKEN}), json.dumps({"token": TOKEN})],
)
def test_get_token_supports_plain_and_json_secret(sm, secret_string):
    client, stub = sm
    stub.add_response(
        "get_secret_value",
        {"SecretString": secret_string},
        {"SecretId": "tourist_estimate_token"},
    )
    assert tourist_api.get_token(client, "tourist_estimate_token") == TOKEN


def test_get_token_rejects_ambiguous_json(sm):
    client, stub = sm
    stub.add_response(
        "get_secret_value",
        {"SecretString": json.dumps({"a": "value-one-xyz", "b": "value-two-xyz"})},
        {"SecretId": "tourist_estimate_token"},
    )
    with pytest.raises(tourist_api.TouristApiError) as exc:
        tourist_api.get_token(client, "tourist_estimate_token")
    assert "value-one-xyz" not in str(exc.value) and "value-two-xyz" not in str(exc.value)


@pytest.mark.parametrize("bad", ["15-04-2022", "2022/04/15", "2022-4-15", "2022-02-30", ""])
def test_validate_date_rejects_bad_format(bad):
    with pytest.raises(ValueError):
        tourist_api.validate_date(bad)


def test_fetch_estimate_sends_single_get_with_date_and_bearer():
    payload = {"for_date": "2022-04-15", "info": [{"name": "Novi Sad", "estimated_no_people": 1234}]}
    session = FakeSession(FakeResponse(200, payload))
    result = tourist_api.fetch_estimate(URL, "2022-04-15", TOKEN, session=session)
    assert result == payload
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == URL
    assert kwargs["params"] == {"date": "2022-04-15"}
    assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert kwargs["timeout"] > 0


def test_fetch_estimate_validates_date_before_calling():
    session = FakeSession(FakeResponse(200, {}))
    with pytest.raises(ValueError):
        tourist_api.fetch_estimate(URL, "15-04-2022", TOKEN, session=session)
    assert session.calls == []


@pytest.mark.parametrize("status", [401, 403, 500])
def test_fetch_estimate_http_error_is_clear_and_hides_token(status, caplog):
    session = FakeSession(FakeResponse(status, None, text=f"error, got {TOKEN}"))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(tourist_api.TouristApiError) as exc:
            tourist_api.fetch_estimate(URL, "2022-04-15", TOKEN, session=session)
    assert str(status) in str(exc.value)
    assert TOKEN not in str(exc.value)
    assert TOKEN not in caplog.text
