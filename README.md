# Open-Meteo Medallion Pipeline

A local, end-to-end data pipeline built on the [Open-Meteo](https://open-meteo.com/) weather API
using a **medallion architecture** (Bronze → Silver → Gold). It ingests weather data for a
configurable set of locations, stores the raw responses, and is designed to transform them into
clean, analysis-ready datasets queryable with SQL.

> **Status:** Bronze ingestion is implemented and tested. Silver and Gold layers are in progress
> (see [Roadmap](#roadmap)).

---

## Architecture

```
Open-Meteo API
      │  extract (retries, timeouts)
      ▼
┌─────────────┐
│   Bronze    │  Raw API responses as JSON, exactly as received, plus request metadata.
│             │  Append-only, never modified. Partitioned by source and ingest date.
└─────────────┘
      │  (planned) clean, flatten, validate, deduplicate
      ▼
┌─────────────┐
│   Silver    │  Typed, UTC-normalized Parquet tables with a defined grain.
└─────────────┘
      │  (planned) aggregate
      ▼
┌─────────────┐
│    Gold     │  Aggregated, analysis-ready tables (use case to be defined).
└─────────────┘
      │
      ▼
   DuckDB / SQL
```

**Why keep every layer on disk?** Each layer can be rebuilt from the one before it. If a
transformation has a bug, it can be fixed and Silver and Gold regenerated from Bronze, without
calling the API again. Bronze also preserves data the API will never return again, such as
earlier versions of a forecast.

---

## Quick start (Docker)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPO.git
cd YOUR-REPO
docker compose build
docker compose run --rm pipeline
```

Output is written to `data/` on your machine:

```
data/bronze/forecast/ingest_date=2026-10-03/brisbane_3f9a1c2b7e4d5a60.json
```

Run it again: unchanged data is skipped, so reruns never create duplicates.

### Commands

```bash
docker compose run --rm pipeline                                   # full pipeline
docker compose run --rm pipeline python -m pipeline.cli extract    # one step
docker compose run --rm pipeline python -m pipeline.cli --help     # list commands
```

The pipeline exits with code `0` on success and `1` if any step fails, so it can be used by
schedulers or CI.

---

## Running locally (without Docker)

Requires Python 3.12+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
python -m pipeline.cli run
```

Run commands from the project root: the config and data paths are relative to it.

---

## Configuration

The pipeline's scope is defined in [`config/locations.yaml`](config/locations.yaml), not in code:

| Setting | Current value |
|---|---|
| Locations | Brisbane, Sydney, Melbourne, Perth, Gold Coast |
| Variables | `temperature_2m`, `precipitation`, `wind_speed_10m` |
| Forecast horizon | 7 days, hourly |

Adding a city or variable is a config change only. With Docker Compose, `config/` is mounted
into the container, so changes apply on the next run without rebuilding the image.

The current locations and variables are a starting set; the scope will be refined once the
analytical use case for the Gold layer is defined.

---

## Design decisions

**Idempotent ingestion.** Each Bronze file is named after a SHA-256 hash of its content. If a
rerun fetches identical data, the file already exists and the write is skipped. If the data has
changed (forecasts are updated several times a day), the new version is saved alongside the old
one, so Bronze keeps a full history of what the API returned over time. The response field
`generationtime_ms` changes on every call, so it is excluded from the hash.

**Atomic writes.** Files are written to a temporary `.tmp` file and then renamed. A crash
mid-write can never leave a partial `.json` file in Bronze.

**Raw means raw.** Bronze stores the API response untouched, with request metadata (URL,
parameters, fetch time) kept in a separate `_meta` block. Structural validation happens in the
Bronze → Silver step, so problematic responses are kept as evidence rather than discarded.

**Retries for temporary errors only.** Timeouts, connection errors, rate limits (429) and server
errors (5xx) are retried with exponential backoff. Other client errors fail immediately, since
retrying a bad request cannot succeed. One failing location does not stop the others.

**UTC everywhere.** All data is requested in UTC so every location shares one clock. Conversion
to local time is left to the presentation layer.

**No HTTP cache.** Open-Meteo's examples use a response cache, but in a pipeline a cache can
silently return stale data. Bronze already serves as the persistent record of every response.

**Right-sized technology.** The data volume is small (a few thousand rows per run), so local
files, Parquet and DuckDB are the appropriate tools. At larger scale, the same layered design
maps onto object storage with Delta Lake or Iceberg and Spark.

---

## Project structure

```
├── config/
│   └── locations.yaml      # pipeline scope: locations, variables
├── src/pipeline/
│   ├── cli.py              # single entry point: run all steps or one
│   └── extract.py          # API → Bronze
├── tests/
│   └── test_extract.py
├── data/                   # generated by the pipeline (not in git)
├── Dockerfile
├── compose.yaml
├── pyproject.toml
└── requirements.txt
```

---

## Tests

```powershell
pytest -v
```

Tests run without network access and write only to temporary folders. They currently cover
content hashing and Bronze idempotency.

---

## Roadmap

- [x] Bronze: forecast ingestion with retries, idempotency and atomic writes
- [x] Single CLI entry point, Docker setup
- [ ] Define the analytical use case for the Gold layer
- [ ] Silver: flattened, typed, deduplicated Parquet tables with data quality checks
- [ ] Gold: aggregated tables for the chosen use case
- [ ] Run tracking (audit log per pipeline run)
- [ ] CI with GitHub Actions

---

## AI usage

AI tools were used throughout this project for design discussions, code drafting and review.
Material conversations are documented in [`docs/ai_evidence/`](docs/ai_evidence/).