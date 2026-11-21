"""Command-line interface."""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx
import pandas as pd

from france_load_forecast import model, odre, warehouse


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


def fit(data_dir: Path, config: Path) -> int:
    """Fit the daily model on the warehouse and print its main estimates."""
    spec = model.load_spec(config)
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        frame = model.daily_frame(con, spec.smoothing)
    fitted = model.fit(frame, spec)
    results = fitted.results

    winter = frame.loc[pd.DatetimeIndex(frame.index).month.isin([12, 1, 2]), "temperature_smooth"]
    at = pd.Series([0.0, 5.0, 10.0, 15.0])
    residual_sd = results.resid[results.loglikelihood_burn :].std()
    print(f"{frame.index[0].date()} to {frame.index[-1].date()}, {len(frame)} days")
    print(f"one-day-ahead error sd {residual_sd:.2f} GW, AR(1) {results.params['ar.L1']:.2f}")
    print(
        f"winter gradient {model.thermosensitivity(fitted, winter).mean():.2f} GW/°C"
        " (December to February)"
    )
    for temperature, gradient in zip(at, model.thermosensitivity(fitted, at), strict=True):
        print(f"  {gradient:.2f} GW/°C at {temperature:.0f} °C")
    print("structural level, yearly mean (GW):")
    level = fitted.level
    for year, mean in level.groupby(pd.DatetimeIndex(level.index).year).mean().items():
        print(f"  {year} {mean:.1f}")
    return 0


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
    fit_parser = commands.add_parser("fit", parents=[common], help="fit the daily load model")
    fit_parser.add_argument("--config", type=Path, default=Path("config/model.toml"))
    args = parser.parse_args(argv)

    if args.command == "ingest":
        return ingest(args.data_dir)
    if args.command == "fit":
        return fit(args.data_dir, args.config)
    parser.error(f"unknown command {args.command}")
