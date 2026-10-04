import argparse
import sys
import logging
import os
import time

from pipeline import extract

log = logging.getLogger("pipeline")

def setup_logging():
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)sZ %(levelname)-7s%(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

# What each step runs (functions; note: no parentheses after extract.run)
STEPS = {
    "extract": extract.run,
}

# What each step does (text for --help)
STEP_DESCRIPTIONS = {
    "extract": "fetch data from Open-Meteo into bronze",
}

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
    parser.add_argument("command", choices=["run", *STEPS], metavar="command")
    args = parser.parse_args(argv)
    setup_logging()

    cfg = extract.load_config()
    steps = list(STEPS) if args.command == "run" else [args.command]

    for name in steps:
        log.info("step '%s' started", name)
        failures = STEPS[name](cfg)
        if failures:
            log.error("step '%s' had %d failure(s); stopping the pipeline", name, failures)
            return 1

    log.info("pipeline finished successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
