import pyarrow.parquet as pq

from pipeline import bronze_to_silver, silver_to_gold


def build_gold(bronze_dir, cfg):
    bronze_to_silver.run(cfg, data_dir=bronze_dir)
    return silver_to_gold.run(cfg, data_dir=bronze_dir)


def read(bronze_dir, name):
    return pq.read_table(bronze_dir / "gold" / f"{name}.parquet").to_pylist()


def test_daily_summary_uses_latest_snapshot(bronze_dir, cfg):
    build_gold(bronze_dir, cfg)
    brisbane = [r for r in read(bronze_dir, "daily_summary") if r["location_id"] == "brisbane"]

    # The 12:00 snapshot has base temperature 22.0; the older one (20.0) must be ignored.
    assert all(r["temp_min"] == 22.0 for r in brisbane)
    assert all(r["temp_max"] == 33.5 for r in brisbane)    # 22.0 + 23 × 0.5


def test_daily_summary_aggregates(bronze_dir, cfg):
    build_gold(bronze_dir, cfg)
    rows = read(bronze_dir, "daily_summary")

    assert len(rows) == 2 * 2                               # 2 cities × 2 days
    assert all(r["hours"] == 24 for r in rows)              # every day complete
    assert all(round(r["precipitation_total"], 1) == 4.8 for r in rows)   # 24 × 0.2


def test_hourly_forecast_excludes_past_hours(bronze_dir, cfg):
    build_gold(bronze_dir, cfg)
    rows = read(bronze_dir, "hourly_forecast")

    brisbane = [r for r in rows if r["location_id"] == "brisbane"]
    perth = [r for r in rows if r["location_id"] == "perth"]
    assert len(brisbane) == 48 - 12                         # fetched at 12:00
    assert len(perth) == 48 - 6                             # fetched at 06:00