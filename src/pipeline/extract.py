import json
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import httpx
import yaml
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


# Make sure all required weather variables are listed here
# The order of variables in hourly or daily is important to assign them correctly below

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

def load_config(path="config/locations.yaml"):
	with open(path, encoding="utf-8") as f:
		return yaml.safe_load(f)

def is_temporary_error(exc):
	if isinstance(exc, httpx.HTTPStatusError):
		return exc.response.status_code in (429,500,502,503,504)
	return isinstance(exc, httpx.TransportError)

@retry(
		retry=retry_if_exception(is_temporary_error),
		stop=stop_after_attempt(4),
		wait=wait_exponential(min=1, max=20),
		reraise=True,
)

def fetch_forecast(location, variables):
	params = {
	"latitude": location["latitude"],
	"longitude": location["longitude"],
	"hourly": ",".join(variables),
	"timezone": "UTC",
	}
	response = httpx.get(FORECAST_URL, params=params, timeout=30)
	response.raise_for_status()
	return params, response.json()

def content_hash(body):
	stable = {k: v for k,v in body.items() if k != "generationtime_ms"}
	return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()[:16]

def save_bronze(location_id, params, body, fetched_at, data_dir="data"):
	folder = Path(data_dir) / "bronze" / "forecast" / f"ingest_date={fetched_at:%Y-%m-%d}"
	path = folder / f"{location_id}_{content_hash(body)}.json"

	if path.exists():
		return None

	record = {
		"_meta": { 
			"source": "forecast",
			"location_id": location_id,
			"url": FORECAST_URL,
			"params": params,
			"fetched_at_utc": fetched_at.isoformat()
		},
		"response": body,
	}
	folder.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(record, indent=2), encoding="utf-8")
	return path

def main():
    cfg = load_config()
    failures = 0

    for location in cfg["locations"]:
        try:
            params, body = fetch_forecast(location, cfg["variables"])
        except httpx.HTTPError as exc:
            print(f"{location['id']}: FAILED ({exc})")
            failures += 1
            continue  # one city failing shouldn't stop the others

        path = save_bronze(location["id"], params, body, datetime.now(timezone.utc))
        if path:
            print(f"{location['id']}: saved {path}")
        else:
            print(f"{location['id']}: unchanged, skipped")

    print(f"Done with {failures} failure(s).")


if __name__=="__main__":
	main()