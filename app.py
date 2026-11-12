from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any

import streamlit as st

from weather_report.analysis import format_value
from weather_report.api import Location
from weather_report.cache import load_cities, load_weather
from weather_report.errors import AppError
from weather_report.service import build_report, validate_dates

logger = logging.getLogger(__name__)

DEFAULT_CITY = ""
DEFAULT_COUNTRY = "IN"
MIN_HISTORY_DATE = date(1940, 1, 1)

Report = dict[str, Any]


def show_error(error: Exception, fallback: str) -> None:
    """Log an error and show a safe message. Called when search, generation, or display fails."""
    logger.exception("Weather application operation failed")
    st.error(str(error) if isinstance(error, AppError) else fallback)


def configure_page() -> None:
    """Set the Streamlit page title and layout. Called by main."""
    st.set_page_config(page_title="Historical Weather Report", page_icon="🌦️", layout="wide")


def show_intro() -> None:
    """Show the page title and short introduction. Called by main."""
    st.title("Historical weather reports")
    st.write("Explore a city's weather history and download a PDF report with the processed data.")


def show_sidebar() -> tuple[str, str, bool]:
    """Collect the city search and return whether it was submitted. Called by main."""
    with st.sidebar:
        st.header("1. Find a city")
        with st.form("city_search"):
            city = st.text_input("City", value=DEFAULT_CITY, max_chars=100)
            country = st.text_input(
                "Country code (optional)",
                value=DEFAULT_COUNTRY,
                max_chars=2,
                help="Two-letter country code, for example IN. Leave blank to search globally.",
            )
            search = st.form_submit_button("Find city", type="primary")
        st.caption("City searches are cached for 24 hours; weather data for 1 hour.")
        st.caption("Recent historical data may be incomplete. Use an older completed period for your report.")
    return city, country, bool(search)


def find_cities(city: str, country: str) -> None:
    """Search for cities and store the matches. Called by main."""
    # A new search must not leave an older location or report visible after failure.
    st.session_state.pop("locations", None)
    st.session_state.pop("report", None)
    try:
        with st.spinner("Finding matching cities..."):
            st.session_state["locations"] = load_cities(city.strip().casefold(), country.strip().upper())
    except Exception as exc:
        show_error(exc, "We couldn't complete the city search. Please try again.")


def show_report_form(locations: list[Location]) -> tuple[Location, date, date, bool]:
    """Let the user pick a location and date range. Called by main."""
    st.subheader("2. Choose a location and date range")
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    previous_month_end = today.replace(day=1) - timedelta(days=1)
    with st.form("report_request"):
        location = st.selectbox(
            "Matching locations",
            locations,
            format_func=lambda item: (
                f"{item.label} ({item.latitude:.5f}, {item.longitude:.5f}) · ID {item.id}"
            ),
        )
        start_column, end_column = st.columns(2)
        with start_column:
            start = st.date_input(
                "Start date",
                previous_month_end.replace(day=1),
                min_value=MIN_HISTORY_DATE,
                max_value=yesterday,
            )
        with end_column:
            end = st.date_input(
                "End date (inclusive)",
                previous_month_end,
                min_value=MIN_HISTORY_DATE,
                max_value=yesterday,
            )
        generate = st.form_submit_button("Generate report", type="primary")
    return location, start, end, bool(generate)


def generate_report(location: Location, start: date, end: date) -> Report:
    """Load weather and return a report ready to display. Called by generate_report_for_user."""
    validate_dates(start, end)
    weather = load_weather(location, start, end)
    report = build_report(location, start, end, weather["payload"])
    return {
        **report,
        "fetched_at": weather["fetched_at"],
        "from_cache": weather["from_cache"],
    }


def generate_report_for_user(location: Location, start: date, end: date) -> None:
    """Build a report and store it, or show an error. Called by main."""
    st.session_state.pop("report", None)
    try:
        # Reject bad dates before the spinner so a validation error does not leave a loading placeholder.
        validate_dates(start, end)
        with st.spinner("Loading weather and building your report..."):
            st.session_state["report"] = generate_report(location, start, end)
    except Exception as exc:
        show_error(exc, "We couldn't generate your report. Please try again.")


def show_report_header(report: Report) -> None:
    """Show the location, dates, and report times. Called by show_report."""
    location = report["location"]
    st.subheader(f"Report: {location.label}")
    st.caption(
        f"{report['start']} to {report['end']} (inclusive) · {report['timezone']} · "
        f"Coordinates: {location.latitude:.5f}, {location.longitude:.5f}"
    )
    st.caption(
        f"Weather fetched: {report['fetched_at']:%Y-%m-%d %H:%M:%S UTC} · "
        f"Report generated: {report['generated_at']:%Y-%m-%d %H:%M:%S UTC}"
    )


def show_data_source(report: Report) -> None:
    """Show whether the weather came from cache or a new request. Called by show_report."""
    # Reports already open during a code update may not have the new status yet.
    if report.get("from_cache") is True:
        st.info(
            "Weather data source: Cache. This report reused saved weather data; "
            "no new Open-Meteo weather API request was made for this report."
        )
    elif report.get("from_cache") is False:
        st.success(
            "Weather data source: Fresh API response. This report fetched weather data "
            "from Open-Meteo and saved it in the cache."
        )
    else:
        st.info(
            "Generate the report again to see whether its weather data came from cache or a fresh API request."
        )


def show_downloads(report: Report) -> None:
    """Show the PDF and CSV download buttons. Called by show_report."""
    pdf_column, csv_column = st.columns(2)
    with pdf_column:
        st.download_button(
            "Download PDF report",
            report["pdf"],
            file_name=f"{report['stem']}.pdf",
            mime="application/pdf",
            on_click="ignore",
            type="primary",
        )
    with csv_column:
        st.download_button(
            "Download processed CSV",
            report["csv"],
            file_name=f"{report['stem']}.csv",
            mime="text/csv",
            on_click="ignore",
        )


def show_statistics(report: Report) -> None:
    """Show the weather summary metrics. Called by show_report."""
    columns = st.columns(3)
    analysis = report["analysis"]
    for index, item in enumerate(analysis["statistics"]):
        with columns[index % len(columns)]:
            st.metric(item["label"], format_value(item["value"], item["unit"]))
            detail = f"{item['valid_days']}/{analysis['days']} valid days"
            if item["date"]:
                detail += f" · {item['date']} (first if tied)"
            if item["partial"]:
                detail += " · Partial data"
            st.caption(detail)
    if report["notes"]:
        st.warning("Some data were missing, invalid, or duplicated. See the data-quality details below.")


def show_report_tabs(report: Report) -> None:
    """Show charts, daily data, and observations. Called by show_report."""
    charts_tab, data_tab, notes_tab = st.tabs(["Charts", "Daily data", "Observations & data quality"])
    with charts_tab:
        for image in report["images"]:
            st.image(image, width="stretch")
    with data_tab:
        st.dataframe(report["frame"], hide_index=True, width="stretch")
        st.caption("Temperatures: °C · Humidity: % · Rainfall/precipitation: mm. Empty values are missing, not zero.")
    with notes_tab:
        for observation in report["analysis"]["observations"]:
            st.write(observation)
        st.subheader("Data quality")
        for note in report["notes"] or ["All requested daily values are present; no duplicates found."]:
            st.write(note)
        st.info(
            "Averages use available daily means. Missing values are not filled. Partial rainfall totals "
            "are not complete-period totals. Rainfall excludes snow; total precipitation includes it. "
            "Historical values are gridded reanalysis/model estimates, not direct city-station observations."
        )


def show_report(report: Report) -> None:
    """Show one saved report. Called by show_saved_report."""
    show_report_header(report)
    show_data_source(report)
    show_downloads(report)
    show_statistics(report)
    show_report_tabs(report)


def show_saved_report() -> None:
    """Show the report stored in the session. Called by main."""
    if "report" not in st.session_state:
        return
    st.divider()
    report_container = st.empty()
    try:
        with report_container.container():
            show_report(st.session_state["report"])
    except Exception as exc:
        report_container.empty()
        st.session_state.pop("report", None)
        show_error(exc, "We couldn't display your report. Please generate it again.")


def show_source_information() -> None:
    """Show the Open-Meteo source line and link. Called by main."""
    st.caption("Source: Open-Meteo Historical Weather API (Best Match), CC BY 4.0. Geocoding: Open-Meteo / GeoNames.")
    st.link_button("About the weather data", "https://open-meteo.com/en/docs/historical-weather-api")


def main() -> None:
    """Run the Streamlit page. Called when the app starts."""
    configure_page()
    show_intro()
    city, country, search = show_sidebar()
    if search:
        find_cities(city, country)

    locations = st.session_state.get("locations")
    if not locations:
        st.info("Start by searching for a city in the sidebar.")
    else:
        location, start, end, generate = show_report_form(locations)
        if generate:
            generate_report_for_user(location, start, end)

    show_saved_report()
    show_source_information()


if __name__ == "__main__":
    main()
