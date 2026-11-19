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
    client = boto3.client("secretsmanager", region_name="eu-north-1", aws_access_key_id="x", aws_secret_access_key="x")
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


VALID = {"for_date": "2022-04-15", "info": [{"name": "Novi Sad", "estimated_no_people": 1234}]}


@pytest.mark.parametrize("status", [301, 401, 403, 500, 503])
@pytest.mark.parametrize(
    "body",
    [
        f"error, got {TOKEN}",
        # Token split by a 300-char truncation boundary must not leak either.
        "x" * 290 + TOKEN,
    ],
)
def test_fetch_estimate_http_error_never_includes_response_body(status, body, caplog):
    session = FakeSession(FakeResponse(status, None, text=body))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(tourist_api.TouristApiError) as exc:
            tourist_api.fetch_estimate(URL, "2022-04-15", TOKEN, session=session)
    assert str(status) in str(exc.value)
    for part in (TOKEN, TOKEN[:10], "super-secret"):
        assert part not in str(exc.value)
        assert part not in caplog.text


@pytest.mark.parametrize("bad_token", ["abc\nSECRETPART", "abc\rSECRETPART", " leading", "", "tab\tSECRETPART"])
def test_fetch_estimate_rejects_invalid_token_without_echoing_it(bad_token):
    session = FakeSession(FakeResponse(200, VALID))
    with pytest.raises(tourist_api.TouristApiError) as exc:
        tourist_api.fetch_estimate(URL, "2022-04-15", bad_token, session=session)
    assert session.calls == []
    assert "SECRETPART" not in str(exc.value)


def test_fetch_estimate_wraps_transport_errors_without_details():
    import requests

    class Boom:
        def get(self, url, **kwargs):
            raise requests.exceptions.InvalidHeader(f"bad header value: 'Bearer {TOKEN}'")

    with pytest.raises(tourist_api.TouristApiError) as exc:
        tourist_api.fetch_estimate(URL, "2022-04-15", TOKEN, session=Boom())
    assert TOKEN not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


@pytest.mark.parametrize("url", ["http://example.com/", "ftp://example.com/", "https:///nohost", "example.com"])
def test_fetch_estimate_requires_https_url(url):
    session = FakeSession(FakeResponse(200, VALID))
    with pytest.raises(ValueError, match="HTTPS"):
        tourist_api.fetch_estimate(url, "2022-04-15", TOKEN, session=session)
    assert session.calls == []


def test_fetch_estimate_disables_redirects():
    session = FakeSession(FakeResponse(200, VALID))
    tourist_api.fetch_estimate(URL, "2022-04-15", TOKEN, session=session)
    assert session.calls[0][1]["allow_redirects"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"for_date": "2022-04-16", "info": VALID["info"]},  # wrong date
        {"for_date": "2022-04-15"},  # missing info
        {"for_date": "2022-04-15", "info": "x"},  # info not a list
        {"for_date": "2022-04-15", "info": [{"name": "Novi Sad"}]},  # missing count
        {"for_date": "2022-04-15", "info": [{"name": 1, "estimated_no_people": 1}]},
        {"for_date": "2022-04-15", "info": [{"name": "A", "estimated_no_people": "12"}]},
        {"for_date": "2022-04-15", "info": [{"name": "A", "estimated_no_people": True}]},
        {"for_date": "2022-04-15", "info": [{"name": "A", "estimated_no_people": -1}]},
        ["not", "a", "dict"],
    ],
)
def test_fetch_estimate_rejects_unexpected_payload(payload):
    session = FakeSession(FakeResponse(200, payload))
    with pytest.raises(tourist_api.TouristApiError):
        tourist_api.fetch_estimate(URL, "2022-04-15", TOKEN, session=session)


def test_fetch_estimate_rejects_non_json_body():
    class NotJson(FakeResponse):
        def json(self):
            raise ValueError("Expecting value")

    session = FakeSession(NotJson(200, None, text="<html>"))
    with pytest.raises(tourist_api.TouristApiError, match="JSON"):
        tourist_api.fetch_estimate(URL, "2022-04-15", TOKEN, session=session)
