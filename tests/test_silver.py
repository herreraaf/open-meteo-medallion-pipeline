import shutil
from pathlib import Path
from pipeline import bronze_to_silver
import pyarrow.parquet as pq

SILVER = "silver/forecast_hourly.parquet"
REAL_FIXTURE = Path(__file__).parent / "fixtures" / "forecast_brisbane.json"


def test_silver_parses_a_real_api_response(tmp_path, cfg):
    folder = tmp_path / "bronze" / "forecast" / "ingest_date=2026-10-03"
    folder.mkdir(parents=True)
    shutil.copy(REAL_FIXTURE, folder / REAL_FIXTURE.name)

    stats = bronze_to_silver.run(cfg, data_dir=tmp_path)
    rows = pq.read_table(tmp_path / SILVER).to_pylist()

    assert stats["failed"] == 0
    assert len(rows) == 168                              # 7 days × 24 hours
    assert all(r["location_id"] == "brisbane" for r in rows)
    assert all(-50 < r["temperature_2m"] < 60 for r in rows if r["temperature_2m"] is not None)