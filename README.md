# Historical Weather Data Analysis

A Python application built for the FlexNfab Python Developer assessment. It uses
Streamlit to retrieve historical weather from Open-Meteo, analyze daily measurements,
and generate a downloadable PDF report and processed CSV.

## Features

- Search for a city and select the correct location from matching results.
- Choose an inclusive start and end date.
- Analyze temperature, relative humidity, rainfall, and total precipitation.
- View temperature trends, daily rainfall, and humidity charts.
- Download a PDF containing statistics, charts, observations, and data-quality notes.
- Download the processed daily data as CSV.
- Reuse API responses through caching and display whether weather came from cache
  or a fresh API request.

## Setup and execution

Python 3.12 is recommended. An internet connection is needed for requests that are
not already cached. No API key is needed for this assignment.

Run these commands from the project root in Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

If the environment is already activated, run `python -m streamlit run app.py`.

On macOS or Linux:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Open the URL printed by Streamlit, normally [http://localhost:8501](http://localhost:8501).
Stop the application with `Ctrl+C` in the terminal.

## Using the application

1. Enter a city in the sidebar, such as **Kolkata**. Optionally enter a two-letter
   country code, such as **IN**, and click **Find city**.
2. Select the correct location. State, country, coordinates, and location ID help
   distinguish cities with the same name.
3. Choose the start and end dates and click **Generate report**.
4. Review the statistics and the **Charts**, **Daily data**, and
   **Observations & data quality** tabs.
5. Use **Download PDF report** and **Download processed CSV** to save the results.

For example, select Kolkata, India, for **1-31 October 2026**. Both dates are
included. Dates default to the previous completed month. Dates before 1940,
reversed ranges, and today/future dates are rejected using the UTC calendar date.
Very recent historical data may be incomplete.

## Application architecture

Streamlit runs the Python application on the server. The page calls the backend
modules directly, with each module responsible for one part of the workflow.

```text
app.py                     Streamlit page and request coordination
weather_report/
    __init__.py            Package definition
    api.py                 Open-Meteo requests and city geocoding
    cache.py               Cached city searches and weather responses
    service.py             Date validation and report assembly
    processing.py          Daily DataFrame creation and data validation
    analysis.py            Statistics and weather observations
    charts.py              Matplotlib chart generation
    report.py              ReportLab PDF generation
    errors.py              User-facing application error type
.streamlit/
    config.toml            Theme and browser error-display settings
requirements.txt           Python dependencies
.gitignore                 Local/generated file exclusions
README.md                  Setup and project documentation
```

### Request workflow

1. **City search:** `app.py` submits the city and country to `cache.load_cities()`.
   A cache miss calls `api.search_cities()`, which converts geocoding results into
   `Location` objects. The page displays the matches in a dropdown.
2. **Weather retrieval:** after date validation, `cache.load_weather()` returns a
   cached response or calls `api.fetch_weather()` for the selected coordinates and
   dates. All required daily variables are requested together.
3. **Processing:** `service.build_report()` passes the response to
   `processing.prepare_data()`, which returns a cleaned Pandas table and quality notes.
4. **Analysis:** `analysis.analyze()` calculates the statistics and observations once.
   The frontend and PDF use these same results.
5. **Report generation:** `charts.create_charts()` creates the three images, and
   `report.generate_report()` builds the PDF. The service also prepares CSV bytes
   and returns the completed report bundle.
6. **Display and download:** the frontend stores the bundle in `st.session_state`,
   displays it, and serves the downloads. Temporary chart and PDF files are removed
   after their contents are read into memory.

`app.py` separates input forms, generation, and display into small functions.
Shared field definitions, calculations, HTTP handling, and report assembly avoid
repeated logic. The application uses Streamlit's built-in caching and session state.

## Caching

- **City searches:** cached for 24 hours, with a maximum of 128 entries.
- **Weather responses:** cached for one hour, with a maximum of 64 entries.
- Weather cache entries match the selected location and **exact start/end dates**.
  Requesting 10-25 October after caching 1-31 October makes a separate API request;
  repeating 10-25 October can then use its own cached entry.
- The caches are held in server memory and may be shared across browser sessions.
  Restarting the server clears them. Failed network/API requests are not cached.
- Each **Generate report** submission rebuilds the PDF and charts using the available
  weather response. Downloads reuse the generated files in session state.

The page shows **Cache** or **Fresh API response**, along with the original weather
fetch time and the report generation time. The status belongs to that report's
request; it does not imply a new API call on every page rerun.

## Statistics and data quality

The application calculates average temperature, highest and lowest temperatures,
average relative humidity, total rainfall, maximum daily rainfall, and total
precipitation. Extreme dates use the first date if values tie.

- Temperature and humidity averages use available daily mean values.
- Rainfall and precipitation totals sum available daily measurements. Rainfall
  excludes snow; total precipitation includes it.
- A straight-line fit describes the daily mean temperature trend when at least
  three valid days are available. Observations also describe rainy days and the
  humidity range. The trend describes the selected period, not a forecast.
- Missing dates are restored, and missing measurements remain missing. Statistics
  show valid-day coverage; partial totals are labeled, and entirely missing metrics
  display `N/A`.
- Identical duplicates are removed; conflicting dates, invalid units, and inconsistent
  measurements are rejected. Nonnumeric and infinite measurements become missing
  with a quality note.

## Reports and exported data

The PDF includes the selected city, coordinates, timezone, date range, UTC generation
moment, summary statistics, observations, data-quality notes, and all three charts.
Download filenames include the city, location ID, and selected dates.

The CSV contains one row per requested local date:

- `date`: calendar date in `YYYY-MM-DD` format.
- `temperature_max_c`, `temperature_min_c`, `temperature_mean_c`: Celsius temperatures.
- `humidity_mean_pct`: mean relative humidity in percent.
- `rainfall_mm`, `precipitation_mm`: daily amounts in millimetres.

Missing CSV values are empty cells. CSV measurements retain their precision;
displayed statistics are rounded to two decimal places.

For submission, save one generated PDF and CSV in a `samples/` directory and include
those files with the source code, this README, `requirements.txt`, and the GitHub
repository link. Sample PDF and CSV files are not excluded by `.gitignore`.

## Error handling and data source

Requests use connection/read timeouts and up to two retries for transient failures.
Timeouts, connection failures, rate limits, and invalid responses have friendly
messages. Expected failures use `AppError`; unexpected failures receive a safe
fallback. Technical details are logged in the Streamlit server terminal. A failed
submission clears the previous report, and a failed preview is removed.

Data comes from the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
using its default Best Match dataset and local-day timezone. City lookup uses the
[Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api).
Historical values are gridded reanalysis/model estimates and may be revised by the
provider. Weather data attribution: Open-Meteo, CC BY 4.0; geocoding uses GeoNames.
