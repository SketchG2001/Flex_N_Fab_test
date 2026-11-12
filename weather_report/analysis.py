import numpy as np
import pandas as pd


STATISTICS = (
    ("Average temperature", "temperature_mean_c", "mean", "°C"),
    ("Highest temperature", "temperature_max_c", "max", "°C"),
    ("Lowest temperature", "temperature_min_c", "min", "°C"),
    ("Average relative humidity", "humidity_mean_pct", "mean", "%"),
    ("Total rainfall", "rainfall_mm", "sum", "mm"),
    ("Maximum daily rainfall", "rainfall_mm", "max", "mm"),
    ("Total precipitation", "precipitation_mm", "sum", "mm"),
)


def format_value(value, unit) -> str:
    """Format a statistic for display, or N/A when it is missing. Called by the PDF and the statistics panel."""
    return "N/A" if pd.isna(value) else f"{value:.2f} {unit}"


def _calculate_value(series: pd.Series, operation: str):
    """Calculate a mean, sum, minimum, or maximum. Called by _build_statistics."""
    if operation == "sum":
        return series.sum(min_count=1)

    return getattr(series, operation)()


def _build_statistics(frame: pd.DataFrame) -> tuple[list[dict], list[str]]:
    """Build the summary rows and extreme-value sentences. Called by analyze."""
    statistics = []
    observations = []

    for label, column, operation, unit in STATISTICS:
        series = frame[column]
        valid_days = int(series.count())
        value = _calculate_value(series, operation)

        day = None

        if valid_days and operation in ("min", "max"):
            index = series.idxmin() if operation == "min" else series.idxmax()
            day = frame.loc[index, "date"].date().isoformat()

            observations.append(
                f"{label}: {format_value(value, unit)} "
                f"on {day} (first date if tied)."
            )

        statistics.append(
            {
                "label": label,
                "value": value,
                "unit": unit,
                "valid_days": valid_days,
                "date": day,
                "partial": valid_days < len(frame),
            }
        )

    return statistics, observations


def _build_temperature_trend(frame: pd.DataFrame) -> str:
    """Describe the daily mean temperature slope for this period. Called by analyze."""
    valid = frame["temperature_mean_c"].notna()
    valid_days = int(valid.sum())

    if valid_days < 3:
        return "Fewer than three valid daily means: no temperature trend fitted."

    first_date = frame["date"].min()
    elapsed = (
        frame.loc[valid, "date"] - first_date
    ).dt.days.to_numpy()

    slope = float(
        np.polyfit(
            elapsed,
            frame.loc[valid, "temperature_mean_c"],
            1,
        )[0]
    )

    direction = (
        "upward"
        if slope > 0
        else "downward"
        if slope < 0
        else "flat"
    )

    return (
        f"Daily mean temperature has a {direction} fitted slope of "
        f"{slope:+.3f} °C/day across {valid_days} valid days. "
        "This describes this period only; it is not a forecast or evidence "
        "of long-term climate change."
    )


def _build_additional_observations(frame: pd.DataFrame) -> list[str]:
    """Add rainfall and humidity sentences when those values exist. Called by analyze."""
    observations = []

    rainfall = frame["rainfall_mm"]

    if rainfall.notna().any():
        observations.append(
            f"Rainfall was greater than 0 mm on "
            f"{int((rainfall > 0).sum())} of "
            f"{int(rainfall.count())} days with rainfall data."
        )

    humidity = frame["humidity_mean_pct"]

    if humidity.notna().any():
        observations.append(
            f"Daily mean relative humidity ranged from "
            f"{humidity.min():.2f}% to {humidity.max():.2f}% "
            "on available days."
        )

    return observations


def analyze(frame: pd.DataFrame) -> dict:
    """Summarize one daily weather table. Called by build_report."""
    statistics, observations = _build_statistics(frame)

    observations.append(_build_temperature_trend(frame))
    observations.extend(_build_additional_observations(frame))

    return {
        "statistics": statistics,
        "observations": observations,
        "days": len(frame),
    }