from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from .errors import AppError


FIELDS = {
    "temperature_2m_max": "temperature_max_c",
    "temperature_2m_min": "temperature_min_c",
    "temperature_2m_mean": "temperature_mean_c",
    "relative_humidity_2m_mean": "humidity_mean_pct",
    "rain_sum": "rainfall_mm",
    "precipitation_sum": "precipitation_mm",
}
_UNITS = {
    field: "°C" if field.startswith("temperature") else "%" if "humidity" in field else "mm"
    for field in FIELDS
}
_RAIN_TOLERANCE_MM = 0.1


def _normalize_numeric_columns(frame: pd.DataFrame) -> list[str]:
    """Turn measurements into numbers and note values that cannot be used. Called by prepare_data."""
    notes = []
    for column in FIELDS.values():
        original = frame[column]
        numeric = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & (numeric.isna() | ~np.isfinite(numeric))
        if invalid.any():
            notes.append(f"{column}: {int(invalid.sum())} invalid value(s) treated as missing.")
        frame[column] = numeric.replace([np.inf, -np.inf], np.nan)
    return notes


def _validate_measurements(frame: pd.DataFrame) -> None:
    """Reject impossible humidity, rainfall, and temperature values. Called by prepare_data."""
    humidity = frame["humidity_mean_pct"]
    if (humidity.notna() & ~humidity.between(0, 100)).any():
        raise AppError("Humidity data is outside the valid range. Try another date range or try again later.")

    rainfall = frame["rainfall_mm"]
    precipitation = frame["precipitation_mm"]
    negative = (rainfall.notna() & (rainfall < 0)) | (precipitation.notna() & (precipitation < 0))
    if negative.any():
        raise AppError("The weather service returned invalid rainfall values. Try another date range or try again later.")

    low = frame["temperature_min_c"]
    mean = frame["temperature_mean_c"]
    high = frame["temperature_max_c"]
    inconsistent = (
        (low.notna() & high.notna() & (low > high))
        | (mean.notna() & low.notna() & (mean < low))
        | (mean.notna() & high.notna() & (mean > high))
    )
    if inconsistent.any():
        raise AppError("The weather service returned inconsistent temperatures. Try another date range or try again later.")

    both_present = rainfall.notna() & precipitation.notna()
    if (both_present & (rainfall > precipitation + _RAIN_TOLERANCE_MM)).any():
        raise AppError("Rainfall and total precipitation data are inconsistent. Try another date range or try again later.")


def prepare_data(payload: dict[str, Any], start: date, end: date) -> tuple[pd.DataFrame, list[str]]:
    """Turn the API payload into one row per requested day. Called by build_report."""
    if start > end:
        raise AppError("Start date must be on or before end date.")
    daily = payload.get("daily")
    if not isinstance(daily, dict) or not isinstance(daily.get("time"), list):
        raise AppError("The weather service returned incomplete data. Please try again later.")
    dates = daily["time"]
    if not dates:
        raise AppError("No weather data is available for this period. Try a different date range.")
    units = payload.get("daily_units", {})
    for field in FIELDS:
        values = daily.get(field)
        if not isinstance(values, list) or len(values) != len(dates):
            raise AppError("The weather service returned incomplete measurements. Please try again later.")
        if not isinstance(units, dict) or units.get(field) != _UNITS[field]:
            raise AppError("The weather service returned unsupported measurement units. Please try again later.")

    frame = pd.DataFrame({"date": dates, **{column: daily[field] for field, column in FIELDS.items()}})
    try:
        frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="raise")
    except (ValueError, TypeError) as exc:
        raise AppError("The weather service returned invalid dates. Please try again later.") from exc
    if frame["date"].isna().any():
        raise AppError("The weather service returned incomplete dates. Please try again later.")
    outside = (frame["date"] < pd.Timestamp(start)) | (frame["date"] > pd.Timestamp(end))
    if outside.any():
        raise AppError("The weather service returned data outside your selected dates. Please try again later.")

    notes = _normalize_numeric_columns(frame)
    before = len(frame)
    frame = frame.drop_duplicates()
    removed = before - len(frame)
    if removed:
        notes.append(f"Removed {removed} identical duplicate record(s).")
    if frame["date"].duplicated().any():
        raise AppError("The weather service returned conflicting daily records. Try another date range or try again later.")
    _validate_measurements(frame)

    frame = frame.set_index("date").reindex(pd.date_range(start, end, name="date"))
    if frame.isna().all().all():
        raise AppError("No usable weather measurements are available for this period. Try a different date range.")
    for column in FIELDS.values():
        missing = int(frame[column].isna().sum())
        if missing:
            notes.append(f"{column}: {missing} of {len(frame)} requested days missing.")
    return frame.reset_index(), notes
