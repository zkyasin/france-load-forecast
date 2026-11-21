"""Command-line interface."""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx

from france_load_forecast import odre, warehouse


def ingest(data_dir: Path) -> int:
    """Download today's exports, rebuild the warehouse and run the data checks."""
    today = datetime.now(UTC).date().isoformat()
    files = {}
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        for source in warehouse.SOURCES:
            path = data_dir / "raw" / source.dataset / f"{today}.csv"
            odre.download_export(
                client, source.dataset, path, select=source.select, where=source.where
            )
            files[source.table] = path

    with duckdb.connect(data_dir / "warehouse.duckdb") as con:
        warehouse.build(con, files)
        for table, rows, first, last in warehouse.summarize(con):
            print(f"{table:<18} {rows:>8} rows  {first} to {last}")
        failures = warehouse.run_checks(con)

    for failure in failures:
        print(f"check failed: {failure}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", type=Path, default=Path("data"))

    parser = argparse.ArgumentParser(
        prog="flf", description="Forecast and analyse French electricity consumption."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "ingest", parents=[common], help="download the ODRÉ exports and rebuild the warehouse"
    )
    args = parser.parse_args(argv)

    if args.command == "ingest":
        return ingest(args.data_dir)
    parser.error(f"unknown command {args.command}")
