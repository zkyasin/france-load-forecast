"""Command-line interface."""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx
import pandas as pd

from france_load_forecast import backtest, correction, forecast, model, odre, warehouse


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


def correct(data_dir: Path, config: Path) -> int:
    """Compare the climate-corrected consumption with RTE's corrected series."""
    spec = model.load_spec(config)
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        frame = model.daily_frame(con, spec.smoothing)
        rte = correction.rte_monthly(con)
    fitted = model.fit(frame, spec)
    corrected = correction.corrected_load(fitted, frame)
    annual = correction.annual_comparison(frame["load_gw"], corrected, rte)

    print("annual energy in TWh, against RTE's monthly series")
    print(annual.to_string(float_format=lambda value: f"{value:.2f}"))
    gaps = annual["corrected_gap_pct"].abs()
    print(f"corrected energy gap: {gaps.mean():.2f} % on average, {gaps.max():.2f} % at most")
    return 0


def run_forecast(data_dir: Path, config: Path) -> int:
    """Forecast monthly energy over the 12 months after the last consolidated day."""
    spec = model.load_spec(config)
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        history = model.daily_frame(con, spec.smoothing)
    fitted = model.fit(history, spec)
    dates = pd.DatetimeIndex(history.index)
    years = forecast.complete_years(dates)
    paths = forecast.paths(fitted, history, history, years)

    summary = pd.DataFrame(
        {
            "p10": paths.quantile(0.1, axis=1),
            "p50": paths.median(axis=1),
            "p90": paths.quantile(0.9, axis=1),
        }
    )
    summary.index = pd.DatetimeIndex(summary.index).strftime("%Y-%m")
    print(f"monthly energy in TWh, from data up to {dates[-1].date()}")
    print(f"P10 and P90 over the weather of {years[0]}-{years[-1]} only")
    print(summary.to_string(float_format=lambda value: f"{value:.1f}"))
    print(f"total P50: {summary['p50'].sum():.1f} TWh")
    return 0


# Origins from 2023 come after the 2022 energy crisis.
RECENT_ORIGINS = pd.Timestamp("2023-01-01")


def run_backtest(data_dir: Path, config: Path, first: str) -> int:
    """Forecast from each month since `first` with the data known then, and score the forecasts."""
    spec = model.load_spec(config)
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        history = model.daily_frame(con, spec.smoothing)
    results = backtest.run(history, spec, backtest.monthly_origins(history, first))
    results.to_csv(data_dir / "backtest.csv", index=False)

    recent = results[results["origin"] >= RECENT_ORIGINS]
    for label, part in (("all origins", results), ("origins since 2023", recent)):
        print(f"mean absolute percentage error of monthly energy, {label}")
        print(backtest.accuracy(part).to_string(float_format=lambda value: f"{value:.2f}"))
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
    model_options = argparse.ArgumentParser(add_help=False, parents=[common])
    model_options.add_argument("--config", type=Path, default=Path("config/model.toml"))
    commands.add_parser("fit", parents=[model_options], help="fit the daily load model")
    commands.add_parser(
        "correct",
        parents=[model_options],
        help="compare the climate-corrected consumption with RTE's corrected series",
    )
    commands.add_parser(
        "forecast", parents=[model_options], help="forecast monthly energy over 12 months"
    )
    backtest_parser = commands.add_parser(
        "backtest", parents=[model_options], help="score forecasts made from past months"
    )
    backtest_parser.add_argument("--first", default="2016-01-01", help="first origin")
    args = parser.parse_args(argv)

    if args.command == "ingest":
        return ingest(args.data_dir)
    if args.command == "fit":
        return fit(args.data_dir, args.config)
    if args.command == "correct":
        return correct(args.data_dir, args.config)
    if args.command == "forecast":
        return run_forecast(args.data_dir, args.config)
    if args.command == "backtest":
        return run_backtest(args.data_dir, args.config, args.first)
    parser.error(f"unknown command {args.command}")
