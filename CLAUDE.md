# Project context

## Goal
Data Engineer take-home: an end-to-end medallion pipeline (Bronze/Silver/Gold)
on the Open-Meteo API. Must run locally with one command (Docker).
Deadline: In 3 days. Reviewers clone the repo and follow the README.

## Principles
- Production-minded but NOT over-engineered. Prefer small, correct, tested code.
- Every layer is persisted and rebuildable from the previous one.
- Reruns must be idempotent. All timestamps in UTC.
- Bronze stores raw API responses untouched; validation happens in Silver.

## Stack
Python 3.12, httpx + tenacity, PyYAML, PyArrow (Silver), DuckDB (Gold),
Docker + compose, pytest. No Spark, Airflow, cloud services or databases.

## Structure
- config/locations.yaml   pipeline scope (locations, variables)
- src/pipeline/cli.py     single entry point: run all steps or one
- src/pipeline/*.py       one module per layer
- data/                   generated output, never committed

## Working agreement
- Explain the approach before writing code; propose options for design choices.
- One small change at a time; I run and verify before continuing.
- Don't add files, dependencies or features I didn't ask for.
- Keep answers concise. Flag assumptions explicitly.

## Commands
- Run:   docker compose run --rm pipeline
- Tests: pytest -v

## Before changing the design
Read docs/decisions.md. Don't reverse a recorded decision without saying so
explicitly and explaining why.