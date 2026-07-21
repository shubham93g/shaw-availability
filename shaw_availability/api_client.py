from __future__ import annotations

import logging
import time

import requests

from . import config

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Any network, HTTP-status, or JSON-shape failure from the Shaw API."""


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(config.HEADERS)
    return session


def get_show_times(session: requests.Session, date: str) -> list[dict]:
    params = {"date": date, **config.FIXED_SHOW_TIME_PARAMS}
    url = config.BASE_URL + config.SHOW_TIMES_PATH
    data = _request_json(session, url, params)
    if not isinstance(data, list):
        raise ApiError(f"get_show_times: expected a list, got {type(data).__name__}")
    return data


def get_layouts(session: requests.Session, performance_id: int) -> list[dict]:
    params = {"performanceId": performance_id}
    url = config.BASE_URL + config.LAYOUTS_PATH
    data = _request_json(session, url, params)
    if not isinstance(data, list):
        raise ApiError(f"get_layouts: expected a list, got {type(data).__name__}")
    return data


def _request_json(session: requests.Session, url: str, params: dict) -> object:
    response = _request_with_retry(session, url, params)
    try:
        return response.json()
    except ValueError as exc:
        raise ApiError(f"invalid JSON from {url}: {exc}") from exc


def _request_with_retry(session: requests.Session, url: str, params: dict) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(config.MAX_RETRIES + 1):
        try:
            response = session.get(
                url, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            last_error = exc
            _throttle()
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF_SECONDS[attempt])
                continue
            raise ApiError(f"request to {url} failed: {exc}") from exc

        _throttle()

        if response.status_code >= 500:
            last_error = ApiError(f"{url} returned {response.status_code}")
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF_SECONDS[attempt])
                continue
            raise last_error

        if response.status_code >= 400:
            raise ApiError(f"{url} returned {response.status_code}: {response.text[:200]}")

        return response

    raise ApiError(f"request to {url} failed after retries: {last_error}")


def _throttle() -> None:
    time.sleep(config.REQUEST_DELAY_SECONDS)
