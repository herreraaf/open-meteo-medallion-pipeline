"""Silver -> Gold: analysis-ready tables for the dashboard, built with DuckDB SQL.

Tables (both use each city's most recent forecast snapshot):
  hourly_forecast   one row per (location_id, valid_time_utc), future hours only
  daily_summary     one row per (location_id, date_utc)

Gold is fully rebuilt from Silver on every run.
"""

from pathlib import Path
import duckdb

LATEST_SNAPSHOT= """
SELECT *
FROM read_parquet('{silver}')
QUALIFY fetched_at_utc = max(fetched_at_utc) OVER (PARTITION BY location_id)
"""

GOLD_TABLES = {
    "hourly_forecast": """
        SELECT
            location_id,
            latitude,
            longitude,
            valid_time_utc,
            temperature_2m,
            precipitation,
            wind_speed_10m,
            fetched_at_utc AS forecast_fetched_at_utc
        FROM latest
        WHERE lead_hours >= 0
        ORDER BY location_id, valid_time_utc
""",
"daily_summary": """
        SELECT
            location_id,
            any_value(latitude)                 AS latitude,
            any_value(longitude)                AS longitude,
            CAST(valid_time_utc AS DATE)        AS date_utc,
            round(min(temperature_2m), 1)       AS temp_min,
            round(max(temperature_2m), 1)       AS temp_max,
            round(avg(temperature_2m), 1)       AS temp_avg,
            round(sum(precipitation), 1)        AS precipitation_total,
            round(max(wind_speed_10m), 1)       AS wind_max,
            count(*)                            AS hours   -- completeness: should be 24
        FROM latest
        GROUP BY location_id, date_utc
        ORDER BY location_id, date_utc
    """,
}

def write_parquet(con, query, out):
    tmp = out.with_name(out.name + ".tmp")
    con.execute(f"COPY ({query}) TO '{tmp.as_posix()}' (FORMAT PARQUET)")
    tmp.replace(out)
    return con.execute(f"SELECT count(*) FROM read_parquet('{out.as_posix()}')").fetchone()[0]

def run(cfg, rund_id=None, data_dir="data"):
    data_dir = Path(data_dir)
    silver = data_dir / "silver" / "forecast_hourly.parquet"
    if not silver.exists():
        raise FileNotFoundError(f"{silver} not found, run the silver step first")

    gold_dir = data_dir / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute(f"CREATE VIEW latest AS {LATEST_SNAPSHOT.format(silver=silver.as_posix())}")

    stats = {"failed": 0}
    try:
        for name, query in GOLD_TABLES.items():
            stats[f"{name}_rows"] = write_parquet(con, query, gold_dir / f"{name}.parquet")
    finally:
        con.close()
    return stats