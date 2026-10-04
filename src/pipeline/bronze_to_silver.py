"""Bronze -> Silver: flatten raw forecast JSON into a typed Parquet table."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

log = logging.getLogger(__name__)

def silver_schema(variables):
    return pa.schema(
        [
            ("location_id", pa.string()),
            ("fetched_at_utc", pa.timestamp("us", tz="UTC")),
            ("valid_time_utc", pa.timestamp("us", tz="UTC")),
            ("lead_hours", pa.float64()),
        ]
    + [(var, pa.float64()) for var in variables]
    + [
        ("latitude", pa.float64()),
        ("longitude", pa.float64()),
        ("run_id", pa.string()),
        ("source_file", pa.string()),
        ]
    )

def flatten_file(path, variables):
    record = json.loads(path.read_text(encoding="utf-8"))
    meta, response = record["_meta"], record["response"]
    hourly = response["hourly"]
    times = hourly["time"]

    requested = meta["params"]["hourly"].split(",")
    missing = [v for v in requested if v not in hourly]
    if missing:
        raise ValueError(f"missing requested variables {missing}")
    wrong_lenth = [v for v in requested if len(hourly[v]) != len(times)]
    if wrong_lenth:
        raise ValueError(f"variables with wrong number of values: {wrong_lenth}")

    fetched_at = datetime.fromisoformat(meta["fetched_at_utc"])
    rows = []
    for i, t in enumerate(times):
        valid_time = datetime.strptime(t, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        row = {
            "location_id": meta["location_id"],
            "fetched_at_utc": fetched_at,
            "valid_time_utc": valid_time,
            "lead_hours": round((valid_time - fetched_at).total_seconds() / 3600, 2)
        }
        # Variables this file didn't request (e.g. added to the config later) become null.
        for var in variables:
            row[var] = hourly[var][i] if var in hourly else None
        row.update(
            latitude=response["latitude"],
            longitude=response["longitude"],
            run_id=meta.get("run_id"),        # older files may not have one
            source_file=path.as_posix(),
        )
        rows.append(row)
    return rows

def run(cfg, run_id=None, data_dir="data"):
    data_dir = Path(data_dir)
    files = sorted((data_dir / "bronze" / "forecast").glob("*/*.json"))
    stats = {"files_read": 0, "rows_written": 0, "failed": 0}
    rows = []

    for path in files: 
        try:
            rows.extend(flatten_file(path, cfg["variables"]))
            stats["files_read"] += 1
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            log.error("rejected %s: %s", path, exc)
            stats["failed"] += 1
    unique = {}
    for row in rows:
        unique[(row["location_id"], row["fetched_at_utc"], row["valid_time_utc"])] = row
    rows = sorted(unique.values(),
                  key=lambda r: (r["location_id"], r["fetched_at_utc"], r["valid_time_utc"]))

    table = pa.Table.from_pylist(rows, schema=silver_schema(cfg["variables"]))

    out = data_dir / "silver" / "forecast_hourly.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    pq.write_table(table, tmp)
    tmp.replace(out)     #atomic

    stats["rows_written"] = table.num_rows
    return stats