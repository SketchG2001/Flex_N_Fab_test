from datetime import date, datetime, timezone
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from .analysis import analyze
from .api import Location
from .charts import create_charts
from .errors import AppError
from .processing import prepare_data
from .report import generate_report


def validate_dates(start: date, end: date) -> None:
    """Reject a reversed, too-early, or unfinished date range. Called before a report is built."""
    if start > end:
        raise AppError("Start date must be on or before end date.")
    if start < date(1940, 1, 1):
        raise AppError("Historical data starts on 1940-01-01. Choose a later start date.")
    if end >= datetime.now(timezone.utc).date():
        raise AppError("Choose dates before today (UTC). Recent archive data may be incomplete.")


def build_report(location: Location, start: date, end: date, payload: dict) -> dict:
    """Turn weather data into the PDF, charts, and CSV. Called by generate_report."""
    frame, notes = prepare_data(payload, start, end)
    analysis = analyze(frame)
    generated_at = datetime.now(timezone.utc)
    local_timezone = payload.get("timezone", "unknown")
    slug = re.sub(r"[^a-z0-9]+", "_", location.label.split(",")[0].lower()).strip("_") or "city"
    stem = f"{slug}_{location.id}_{start}_{end}"
    with TemporaryDirectory(prefix="weather_") as temporary:
        work = Path(temporary)
        charts = create_charts(frame, work)
        generate_report(
            work / "report.pdf", location, start, end, local_timezone,
            generated_at, analysis, notes, charts,
        )
        pdf = (work / "report.pdf").read_bytes()
        images = [chart.read_bytes() for chart in charts]
    return {
        "location": location, "start": start, "end": end, "timezone": local_timezone,
        "generated_at": generated_at, "stem": stem, "frame": frame,
        "analysis": analysis, "notes": notes, "images": images, "pdf": pdf,
        "csv": frame.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8"),
    }
