from dataclasses import dataclass
from datetime import date
import logging
import re
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import NewConnectionError, TimeoutError as HTTPTimeoutError

from .errors import AppError
from .processing import FIELDS

logger = logging.getLogger(__name__)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_DATA_UNAVAILABLE = "The weather service could not provide this data. Try another location or date range."
_HTTP_STATUS_MESSAGES = {
    400: _DATA_UNAVAILABLE,
    404: _DATA_UNAVAILABLE,
    422: _DATA_UNAVAILABLE,
    429: "The weather service is receiving too many requests. Please wait a minute and try again.",
}


@dataclass(frozen=True)
class Location:
    id: int
    label: str
    latitude: float
    longitude: float


def create_session() -> requests.Session:
    """Create the HTTPS session used for Open-Meteo requests. Called by load_cities and _cached_weather."""
    session = requests.Session()
    retries = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=False,
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def _is_timeout(error: Exception) -> bool:
    """Return whether a request failed because it timed out. Called by _request_error_message."""
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, (requests.Timeout, HTTPTimeoutError)) and not isinstance(current, NewConnectionError):
            return True
        nested = (getattr(current, "reason", None), current.__cause__, current.__context__, *current.args)
        pending.extend(item for item in nested if isinstance(item, BaseException))
    return False


def _request_error_message(exc: requests.RequestException) -> str:
    """Turn a failed HTTP request into a short message. Called by get_json."""
    if _is_timeout(exc):
        return "The weather service took too long to respond. Please try again in a moment."
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        if status in _HTTP_STATUS_MESSAGES:
            return _HTTP_STATUS_MESSAGES[status]
        if status is not None and status >= 500:
            return "The weather service is temporarily unavailable. Please try again shortly."
        return "The weather service could not complete the request. Please try again later."
    if isinstance(exc, requests.exceptions.SSLError):
        return "A secure connection to the weather service could not be established. Please try again later."
    if isinstance(exc, requests.ConnectionError):
        return "Could not connect to the weather service. Check your internet connection and try again."
    return "The weather service could not be reached. Please try again later."


def get_json(
    session: requests.Session,
    url: str,
    params: dict[str, str | int | float],
) -> dict[str, Any]:
    """Fetch one JSON object from Open-Meteo. Called by search_cities and fetch_weather."""
    try:
        response = session.get(url, params=params, timeout=(5, 30))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise AppError(_request_error_message(exc)) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError("The weather service returned data we could not read. Please try again later.") from exc
    if not isinstance(payload, dict):
        raise AppError("The weather service returned an unexpected response. Please try again later.")
    if payload.get("error"):
        logger.warning("Weather provider rejected the request: %s", payload.get("reason", "No reason supplied"))
        raise AppError(_DATA_UNAVAILABLE)
    return payload


def _parse_locations(results: list[Any], place: str) -> list[Location]:
    """Turn geocoding records into locations, exact city name first. Called by search_cities."""

    parsed: list[tuple[str, Location]] = []
    try:
        for item in results:
            if not isinstance(item, dict):
                raise ValueError("Invalid location record.")
            label = ", ".join(
                str(item[key]) for key in ("name", "admin1", "country") if item.get(key)
            )
            parsed.append((
                str(item.get("name", "")),
                Location(
                    int(item["id"]), label,
                    float(item["latitude"]), float(item["longitude"]),
                ),
            ))
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("City search returned an invalid location. Please try again later.") from exc
    if not parsed:
        raise AppError("No matching city was found. Check the spelling or try another country code.")
    target = place.casefold()
    parsed.sort(key=lambda item: item[0].casefold() != target)
    return [location for _, location in parsed]


def search_cities(session: requests.Session, city: str, country: str = "") -> list[Location]:
    """Search Open-Meteo for matching cities. Called by load_cities."""
    city, country = city.strip(), country.strip().upper()
    place = city.split(",")[0].strip()
    if len(place) < 2:
        raise AppError("Enter a city name with at least two characters.")
    if country and not re.fullmatch(r"[A-Z]{2}", country):
        raise AppError("Country must be a two-letter code, such as IN, or left blank.")
    params: dict[str, str | int] = {"name": city, "count": 10, "language": "en"}
    if country:
        params["countryCode"] = country
    results = get_json(session, GEOCODING_URL, params).get("results", [])
    if not isinstance(results, list):
        raise AppError("City search returned data we could not read. Please try again later.")
    return _parse_locations(results, place)


def fetch_weather(
    session: requests.Session, location: Location, start: date, end: date,
) -> dict[str, Any]:
    """Download daily historical weather for one location. Called by _cached_weather."""
    return get_json(session, ARCHIVE_URL, {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": ",".join(FIELDS),
        "timezone": "auto",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    })
