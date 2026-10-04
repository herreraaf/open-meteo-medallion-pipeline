import argparse
import hashlib
import json
import sys
import logging
import os
import time
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pipeline import extract

log = logging.getLogger("pipeline")
CONFIG_PATH = "config/locations.yaml"
RUNS_FILE = Path("data/_runs/runs.jsonl")

# What each step runs (functions; note: no parentheses after extract.run)
STEPS = {
    "extract": extract.run,
}

# What each step does (text for --help)
STEP_DESCRIPTIONS = {
    "extract": "fetch data from Open-Meteo into bronze",
}

#-------logging---------------------------------------------------------------------------------------#

class RunIdFilter(logging.Filter):
    run_id = "-"

    def filter(self, record):
        record.run_id = self.run_id
        return True

run_id_filter = RunIdFilter()

def setup_logging():
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        level = os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)sZ %(levelname)-7s [%(run_id)s] %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(run_id_filter)
    logging.getLogger("httpx").setLevel(logging.WARNING)

#------------- run tracking -----------------------------------------------------------------------------#

def new_run_id():
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"

def git_commit():
    """Which version of the code is running. None if git isn't available (e.g. in Docker)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None

def config_hash():
    return hashlib.sha256(Path(CONFIG_PATH).read_bytes()).hexdigest()[:12]

def write_run_record(record):
    RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

#-----------------------main---------------------------------------------------------------------------------#

def main(argv=None):
    commands = "\n".join(
        ["  run        run all steps in order"]
        + [f"  {name:<10} {desc}" for name, desc in STEP_DESCRIPTIONS.items()]
    )
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Open-Meteo medallion pipeline.",
        epilog=f"commands:\n{commands}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=["run", *STEPS], metavar="command",
                        help="one of the commands listed below")
    args = parser.parse_args(argv)

    setup_logging()
    run_id = new_run_id()
    run_id_filter.run_id = run_id
    started = datetime.now(timezone.utc)

    # Record the start first: if the process is killed, this "started"
    # record without a matching "finished" one shows the run crashed.
    write_run_record({
        "run_id": run_id,
        "event": "started",
        "started_at": started.isoformat(),
        "command": args.command,
        "git_commit": git_commit(),
        "config_sha256": config_hash(),
    })
    log.info("run started: command=%s", args.command)

    steps = list(STEPS) if args.command == "run" else [args.command]
    step_stats = {}
    status, error = "success", None

    try:
        cfg = extract.load_config(CONFIG_PATH)
        for name in steps:
            log.info("step '%s' started", name)
            stats = STEPS[name](cfg, run_id)
            step_stats[name] = stats
            log.info("step '%s' finished: %s", name, stats)

            if stats.get("failed"):
                status = "failed"
                error = f"step '{name}' had {stats['failed']} failure(s)"
                log.error("%s; stopping the pipeline", error)
                break
    except Exception as exc:  # anything unexpected still gets recorded
        status, error = "failed", repr(exc)
        log.exception("pipeline crashed")
    finally:
        finished = datetime.now(timezone.utc)
        duration = round((finished - started).total_seconds(), 2)
        write_run_record({
            "run_id": run_id,
            "event": "finished",
            "finished_at": finished.isoformat(),
            "status": status,
            "duration_s": duration,
            "steps": step_stats,
            "error": error,
        })

    log.info("run %s in %.1fs", status, duration)
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())