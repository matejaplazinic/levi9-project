"""Tourist estimation API client.

GET <url>?date=YYYY-MM-DD with a bearer token stored in AWS Secrets Manager.
Response: {"for_date": "...", "info": [{"name": "...", "estimated_no_people": ...}, ...]}
The token is only held in memory and never logged or included in error messages.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

DEFAULT_URL = "https://c4frojrhvq24ycydp5s2xxiytq0qjzop.lambda-url.eu-north-1.on.aws/"
SECRET_ID = "tourist_estimate_token"
SECRET_REGION = "eu-north-1"
_TOKEN_RE = re.compile(r"[\x21-\x7e]+")


class TouristApiError(RuntimeError):
    pass


def get_token(secretsmanager, secret_id: str = SECRET_ID) -> str:
    """Read the bearer token. Supports a plain-string secret or a JSON object with one value."""
    raw = secretsmanager.get_secret_value(SecretId=secret_id)["SecretString"].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(parsed, dict):
        if len(parsed) != 1:
            raise TouristApiError(
                f"Secret {secret_id} is JSON with {len(parsed)} keys ({', '.join(parsed)}); expected one."
            )
        return str(next(iter(parsed.values()))).strip()
    if isinstance(parsed, str):
        return parsed.strip()
    raise TouristApiError(f"Secret {secret_id} has an unsupported format.")


def validate_date(value: str) -> str:
    """Accept only YYYY-MM-DD (zero-padded, real calendar date)."""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date {value!r}, expected YYYY-MM-DD") from None
    if parsed.strftime("%Y-%m-%d") != value:
        raise ValueError(f"Invalid date {value!r}, expected YYYY-MM-DD")
    return value


def validate_url(url: str) -> str:
    """Only HTTPS URLs with a host are allowed, so the token is never sent in clear text."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"Tourist API URL must be an HTTPS URL with a host, got {url!r}")
    return url


def _check_token(token: str) -> None:
    # Visible ASCII only: rejects CR/LF, spaces and control characters that would make
    # requests raise InvalidHeader with the full header value in its message.
    if not _TOKEN_RE.fullmatch(token or ""):
        raise TouristApiError("Token from Secrets Manager contains invalid characters (value not shown).")


def _validate_payload(payload: object, date: str) -> dict:
    if not isinstance(payload, dict):
        raise TouristApiError("Unexpected response: top-level JSON is not an object.")
    if payload.get("for_date") != date:
        raise TouristApiError(f"Unexpected response: for_date={payload.get('for_date')!r}, requested {date!r}.")
    info = payload.get("info")
    if not isinstance(info, list):
        raise TouristApiError("Unexpected response: 'info' is missing or not a list.")
    for i, item in enumerate(info):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise TouristApiError(f"Unexpected response: info[{i}].name is missing or not a string.")
        count = item.get("estimated_no_people")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise TouristApiError(f"Unexpected response: info[{i}].estimated_no_people is not a non-negative integer.")
    return payload


def fetch_estimate(url: str, date: str, token: str, session=requests, timeout: float = 15) -> dict:
    """Make exactly one GET call (no redirects) and return the validated JSON response.

    Error messages never contain the response body or request headers.
    """
    validate_date(date)
    validate_url(url)
    _check_token(token)
    log.info("Calling tourist API for date=%s", date)
    try:
        resp = session.get(
            url,
            params={"date": date},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.RequestException as e:
        raise TouristApiError(f"Tourist API request failed ({type(e).__name__}).") from None
    if resp.status_code != 200:
        raise TouristApiError(f"Tourist API returned HTTP {resp.status_code}.")
    try:
        payload = resp.json()
    except ValueError:
        raise TouristApiError("Tourist API returned a body that is not valid JSON.") from None
    return _validate_payload(payload, date)
