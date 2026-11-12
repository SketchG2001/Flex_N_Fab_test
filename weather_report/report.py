from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, StyleSheet1, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from reportlab.platypus.flowables import Flowable

from .analysis import format_value
from .api import Location
from .errors import AppError

PRIMARY = colors.HexColor("#17445c")
SECONDARY = colors.HexColor("#526875")
ROW_BACKGROUND = colors.HexColor("#f0f5f7")
BORDER = colors.HexColor("#cbd5db")
MARGIN_X = 1.8 * cm
MARGIN_TOP = 1.5 * cm
MARGIN_BOTTOM = 1.7 * cm
CHART_WIDTH = 16 * cm
CHART_HEIGHT = 6.05 * cm
_CHART_MISSING = "A chart image is missing. Please generate the report again."
_CHART_UNREADABLE = "A chart image could not be read. Please generate the report again."
_NO_QUALITY_NOTES = "All requested daily values are present; no duplicates found."


def _build_styles() -> StyleSheet1:
    """Create the PDF text styles. Called by generate_report."""
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("SmallText", parent=styles["BodyText"], fontSize=8.5, leading=12))
    styles["Title"].textColor = PRIMARY
    styles["Title"].alignment = TA_CENTER
    styles["Heading2"].textColor = PRIMARY
    styles["BodyText"].spaceAfter = 6
    return styles


def _paragraph(text: object, styles: StyleSheet1, style: str = "BodyText") -> Paragraph:
    """Make one PDF paragraph with special characters escaped. Called while the report is assembled."""
    return Paragraph(escape(str(text)), styles[style])


def _build_summary_table(analysis: dict[str, Any], styles: StyleSheet1) -> Table:
    """Build the weather statistics table. Called by _build_summary_section."""
    rows: list[list[Any]] = [["Metric", "Value", "Valid days", "Extreme date"]]
    for item in analysis["statistics"]:
        label = item["label"] + (" (partial)" if item["partial"] else "")
        rows.append([
            _paragraph(label, styles, "SmallText"),
            _paragraph(format_value(item["value"], item["unit"]), styles, "SmallText"),
            f"{item['valid_days']}/{analysis['days']}",
            item["date"] or "-",
        ])
    table = Table(rows, colWidths=[6.9 * cm, 3.2 * cm, 2.3 * cm, 3.6 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ROW_BACKGROUND, colors.white]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, BORDER),
    ]))
    return table


def _build_summary_section(
    analysis: dict[str, Any], notes: list[str], styles: StyleSheet1,
) -> list[Flowable]:
    """Add the summary, observations, methodology, and data-quality notes. Called by generate_report."""
    story: list[Flowable] = [
        _paragraph("Weather summary", styles, "Heading2"),
        _build_summary_table(analysis, styles),
        Spacer(1, 0.25 * cm),
        _paragraph("Observations and conclusions", styles, "Heading2"),
    ]
    story.extend(_paragraph(text, styles, "SmallText") for text in analysis["observations"])
    story.extend([
        _paragraph("Methodology and source", styles, "Heading2"),
        _paragraph(
            "Period averages are arithmetic means of available daily means. Extremes use daily "
            "maximum/minimum values; ties show the first date. Totals sum available daily amounts. "
            "Rainfall excludes snow; total precipitation includes rain, showers and snow. "
            "Values are rounded only for display.",
            styles,
            "SmallText",
        ),
        _paragraph(
            "Source: Open-Meteo Historical Weather API (Best Match), using gridded historical "
            "reanalysis/model data, not direct city-station observations. Days follow the API's "
            "resolved local timezone. Data may be revised by the provider. Weather data: CC BY 4.0. "
            "Geocoding: Open-Meteo / GeoNames.",
            styles,
            "SmallText",
        ),
        _paragraph("https://open-meteo.com/en/docs/historical-weather-api", styles, "SmallText"),
        _paragraph("Data quality", styles, "Heading2"),
        _paragraph(
            "Missing values are not filled or interpolated. Partial statistics use only valid days; "
            "partial rainfall totals are not complete-period totals. Missing chart values are gaps, "
            "not zero rainfall. N/A means no valid values.",
            styles,
            "SmallText",
        ),
    ])
    story.extend(
        _paragraph(note, styles, "SmallText") for note in (notes or [_NO_QUALITY_NOTES])
    )
    return story


def _chart_image(path: Path) -> Image:
    """Fit one chart image on the page without stretching it. Called by _build_chart_section."""
    if not path.is_file():
        raise AppError(_CHART_MISSING)
    try:
        return Image(str(path), width=CHART_WIDTH, height=CHART_HEIGHT, kind="proportional", lazy=0)
    except (OSError, ValueError) as exc:
        raise AppError(_CHART_UNREADABLE) from exc


def _build_chart_section(charts: list[Path], styles: StyleSheet1) -> list[Flowable]:
    """Add the chart heading and images. Called by generate_report."""
    if not charts:
        return []
    heading = _paragraph("Daily weather visualizations", styles, "Heading1")
    blocks: list[Flowable] = []
    for index, chart in enumerate(charts):
        parts: list[Flowable] = [_chart_image(chart), Spacer(1, 0.3 * cm)]
        if index == 0:
            parts.insert(0, heading)
        blocks.append(KeepTogether(parts))
    return blocks


def _draw_footer(canvas: Canvas, document: SimpleDocTemplate) -> None:
    """Draw the report name and page number. Called on each page of generate_report."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(SECONDARY)
    canvas.drawString(MARGIN_X, 1.1 * cm, "Historical Weather Analysis | Open-Meteo")
    canvas.drawRightString(A4[0] - MARGIN_X, 1.1 * cm, f"Page {document.page}")
    canvas.restoreState()


def generate_report(
    path: Path,
    location: Location,
    start: date,
    end: date,
    timezone: str,
    generated_at: datetime,
    analysis: dict[str, Any],
    notes: list[str],
    charts: list[Path],
) -> None:
    """Write the historical weather PDF. Called by build_report."""
    styles = _build_styles()
    story: list[Flowable] = [
        _paragraph("Historical Weather Report", styles, "Title"),
        _paragraph(location.label, styles, "Heading2"),
        _paragraph(f"{start} to {end} (inclusive) | {analysis['days']} days", styles),
        _paragraph(
            f"Coordinates: {location.latitude:.5f}, {location.longitude:.5f} | "
            f"Local-day timezone: {timezone}",
            styles,
            "SmallText",
        ),
        _paragraph(f"Generated: {generated_at:%Y-%m-%d %H:%M:%S %Z}", styles, "SmallText"),
        Spacer(1, 0.25 * cm),
    ]
    story.extend(_build_summary_section(analysis, notes, styles))
    story.extend(_build_chart_section(charts, styles))
    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=MARGIN_X,
        leftMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=f"Historical Weather - {location.label}",
        author="Historical Weather Report",
    )
    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
