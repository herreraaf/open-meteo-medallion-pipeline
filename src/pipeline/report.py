"""Report: build a self-contained HTML dashboard from the Gold tables.

Reads only Gold, never Silver or Bronze. Output: data/report/dashboard.html,
one file with plotly.js embedded, so it opens offline in any browser.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import plotly.express as px

log = logging.getLogger(__name__)

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Open-Meteo forecast dashboard</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 1100px;
          padding: 0 1rem; color: #222; }}
  h1 {{ margin-bottom: 0.2rem; }}
  .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 2rem; }}
  section {{ margin-bottom: 3rem; }}
</style>
</head>
<body>
<h1>Open-Meteo forecast dashboard</h1>
<div class="meta">Forecast fetched {data_as_of} · generated {generated_at} · run {run_id}</div>
<section><h2>Hourly temperature forecast</h2>{map}</section>
<section><h2>Daily temperature range</h2>{temperature}</section>
<section><h2>Daily precipitation</h2>{precipitation}</section>
</body>
</html>
"""


def load_gold(gold_dir):
    """Read both Gold tables into DataFrames, with timestamps in UTC."""
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    try:
        hourly = con.sql(f"""
            SELECT *, strftime(valid_time_utc, '%Y-%m-%d %H:%M UTC') AS hour
            FROM read_parquet('{(gold_dir / "hourly_forecast.parquet").as_posix()}')
            ORDER BY valid_time_utc, location_id
        """).df()
        daily = con.sql(f"""
            SELECT *
            FROM read_parquet('{(gold_dir / "daily_summary.parquet").as_posix()}')
            ORDER BY date_utc, location_id
        """).df()
    finally:
        con.close()
    return hourly, daily


def map_figure(hourly):
    """Cities colored by temperature, with a slider to move through the hours."""
    fig = px.scatter_geo(
        hourly,
        lat="latitude",
        lon="longitude",
        color="temperature_2m",
        hover_name="location_id",
        hover_data={"precipitation": ":.1f", "wind_speed_10m": ":.1f",
                    "latitude": False, "longitude": False},
        animation_frame="hour",
        # Fixed color range across all hours, so colors are comparable between frames.
        range_color=(hourly["temperature_2m"].min(), hourly["temperature_2m"].max()),
        color_continuous_scale="RdYlBu_r",
        labels={"temperature_2m": "Temp (°C)", "precipitation": "Rain (mm)",
                "wind_speed_10m": "Wind (km/h)", "hour": "Hour"},
        projection="natural earth",
    )
    fig.update_traces(marker=dict(size=16, line=dict(width=1, color="white")))

    # Zoom to the configured cities, with some margin around them.
    pad = 8
    fig.update_geos(
        lataxis_range=[max(hourly["latitude"].min() - pad, -90), min(hourly["latitude"].max() + pad, 90)],
        lonaxis_range=[hourly["longitude"].min() - pad, hourly["longitude"].max() + pad],
        showcountries=True, showland=True, landcolor="#f2efe9",
    )
    fig.update_layout(height=600, margin=dict(l=0, r=0, t=10, b=0))
    return fig


def temperature_figure(daily):
    """Daily min and max temperature per city."""
    long = daily.melt(
        id_vars=["location_id", "date_utc"],
        value_vars=["temp_min", "temp_max"],
        var_name="measure",
        value_name="temperature",
    )
    fig = px.line(
        long, x="date_utc", y="temperature", color="location_id", line_dash="measure",
        markers=True,
        labels={"date_utc": "Date (UTC)", "temperature": "°C", "location_id": "City", "measure": ""},
    )
    fig.update_layout(height=420, margin=dict(t=10))
    return fig


def precipitation_figure(daily):
    """Total daily precipitation per city."""
    fig = px.bar(
        daily, x="date_utc", y="precipitation_total", color="location_id", barmode="group",
        labels={"date_utc": "Date (UTC)", "precipitation_total": "mm", "location_id": "City"},
    )
    fig.update_layout(height=420, margin=dict(t=10))
    return fig


def run(cfg, run_id=None, data_dir="data"):
    """Write the dashboard HTML from Gold. Returns counts."""
    data_dir = Path(data_dir)
    hourly, daily = load_gold(data_dir / "gold")
    if hourly.empty:
        raise ValueError("gold hourly_forecast is empty; nothing to report")

    figures = [map_figure(hourly), temperature_figure(daily), precipitation_figure(daily)]
    # Embed plotly.js only once (with the first figure), so the file works offline.
    map_html, temperature_html, precipitation_html = (
        fig.to_html(full_html=False, include_plotlyjs=(i == 0)) for i, fig in enumerate(figures)
    )

    html = PAGE.format(
        map=map_html,
        temperature=temperature_html,
        precipitation=precipitation_html,
        data_as_of=hourly["forecast_fetched_at_utc"].max().strftime("%Y-%m-%d %H:%M UTC"),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        run_id=run_id or "-",
    )

    out = data_dir / "report" / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(out)
    log.info("dashboard written to %s", out)

    # int(): pandas returns numpy integers, which can't be written to runs.jsonl as JSON.
    return {
        "failed": 0,
        "cities": int(hourly["location_id"].nunique()),
        "hours": int(hourly["hour"].nunique()),
    }