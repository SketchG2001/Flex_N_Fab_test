from datetime import date, datetime, timezone
from uuid import uuid4
import streamlit as st
from .api import Location, create_session, fetch_weather, search_cities


@st.cache_data(ttl=86400, max_entries=128, show_spinner=False)
def load_cities(city: str, country: str) -> list[Location]:
    """Search cities and reuse the result for 24 hours. Called by find_cities."""
    with create_session() as session:
        return search_cities(session, city, country)


@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)
def _cached_weather(location: Location, start: date, end: date, _request_id: str) -> dict:
    """Fetch weather and reuse it for one hour. Called by load_weather."""
    with create_session() as session:
        payload = fetch_weather(session, location, start, end)
    return {
        "payload": payload, "fetched_at": datetime.now(timezone.utc),
        "request_id": _request_id,
    }


def load_weather(location: Location, start: date, end: date) -> dict:
    """Return weather and whether this call reused the cache. Called by generate_report."""
    request_id = uuid4().hex
    weather = _cached_weather(location, start, end, _request_id=request_id)
    return {
        "payload": weather["payload"], "fetched_at": weather["fetched_at"],
        "from_cache": weather["request_id"] != request_id,
    }
