"""Command-line interface with automation-friendly exit codes."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import psycopg

from daily_sales_etl.config import Settings
from daily_sales_etl.database import SalesRepository, apply_schema
from daily_sales_etl.pipeline import run_pipeline
from daily_sales_etl.transform import InputError

EXIT_SUCCESS = 0
EXIT_INPUT_ERROR = 2
EXIT_DATABASE_ERROR = 3
EXIT_UNEXPECTED_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load a daily sales CSV into PostgreSQL")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="validate and load one CSV file")
    run.add_argument("--input", required=True, type=Path)
    run.add_argument("--quarantine-dir", type=Path, default=Path("data/quarantine"))

    init = subparsers.add_parser("init-db", help="apply the idempotent database schema")
    init.add_argument("--schema", type=Path, default=Path("sql/init.sql"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        settings = Settings.from_environment()
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        if args.command == "init-db":
            apply_schema(settings.database_url, args.schema)
            logging.info("database schema applied")
        else:
            result = run_pipeline(args.input, args.quarantine_dir, SalesRepository(settings.database_url))
            print(
                f"run_id={result.run_id} input={result.input_count} "
                f"loaded={result.loaded_count} rejected={result.rejected_count}"
            )
        return EXIT_SUCCESS
    except (InputError, FileNotFoundError) as exc:
        logging.error("input error: %s", exc)
        return EXIT_INPUT_ERROR
    except psycopg.Error as exc:
        logging.error("database error: %s", exc)
        return EXIT_DATABASE_ERROR
    except Exception:
        logging.exception("unexpected pipeline error")
        return EXIT_UNEXPECTED_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
