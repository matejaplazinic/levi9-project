"""Tourist estimation API client.

GET <url>?date=YYYY-MM-DD with a bearer token stored in AWS Secrets Manager.
Response: {"for_date": "...", "info": [{"name": "...", "estimated_no_people": ...}, ...]}
The token is only held in memory and never logged or included in error messages.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import requests

log = logging.getLogger(__name__)

DEFAULT_URL = "https://c4frojrhvq24ycydp5s2xxiytq0qjzop.lambda-url.eu-north-1.on.aws/"
SECRET_ID = "tourist_estimate_token"
SECRET_REGION = "eu-north-1"


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


def fetch_estimate(url: str, date: str, token: str, session=requests, timeout: float = 15) -> dict:
    """Make exactly one GET call and return the parsed JSON response."""
    validate_date(date)
    log.info("Calling tourist API for date=%s", date)
    resp = session.get(
        url,
        params={"date": date},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        body = (resp.text or "")[:300].replace(token, "***")
        raise TouristApiError(f"Tourist API returned HTTP {resp.status_code}: {body}")
    return resp.json()
