"""Shared test data: a small, fake Bronze folder built without calling the API."""

from datetime import datetime, timedelta, timezone

import pytest

from pipeline.extract import save_bronze

VARIABLES = ["temperature_2m", "precipitation", "wind_speed_10m"]
DAY = datetime(2026, 10, 3, tzinfo=timezone.utc)


def make_response(base_temp, lat=-27.47, lon=153.03, hours=48):
    """A fake Open-Meteo response: 48 hourly values starting at DAY 00:00 UTC.

    Temperature rises 0.5 °C per hour within each day, so the expected
    min/max per day are easy to compute: base_temp and base_temp + 11.5.
    """
    times = [(DAY + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
    return {
        "latitude": lat,
        "longitude": lon,
        "generationtime_ms": 0.5,
        "hourly": {
            "time": times,
            "temperature_2m": [base_temp + (h % 24) * 0.5 for h in range(hours)],
            "precipitation": [0.2] * hours,
            "wind_speed_10m": [10.0] * hours,
        },
    }


@pytest.fixture
def cfg():
    return {"variables": list(VARIABLES)}


@pytest.fixture
def bronze_dir(tmp_path):
    """Bronze with three files: Brisbane fetched twice (06:00 and 12:00), Perth once (06:00)."""
    params = {"hourly": ",".join(VARIABLES)}
    save_bronze("brisbane", params, make_response(20.0), DAY.replace(hour=6),
                data_dir=tmp_path, run_id="run1")
    save_bronze("brisbane", params, make_response(22.0), DAY.replace(hour=12),
                data_dir=tmp_path, run_id="run2")
    save_bronze("perth", params, make_response(15.0, lat=-31.95, lon=115.86), DAY.replace(hour=6),
                data_dir=tmp_path, run_id="run1")
    return tmp_path