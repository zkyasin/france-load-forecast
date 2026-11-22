"""Command-line interface."""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx
import pandas as pd

from france_load_forecast import (
    backtest,
    conformal,
    correction,
    decomposition,
    forecast,
    model,
    odre,
    outlook,
    publish,
    warehouse,
)
from france_load_forecast.agent import agent, note, tools


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


def realtime_note(con: duckdb.DuckDBPyConnection, history: pd.DataFrame) -> str:
    """Which days come from real-time data, and the revision added to them."""
    realtime = pd.DatetimeIndex(history.index[history["source"] == "realtime"])
    if realtime.empty:
        return "all days are consolidated"
    revision_gw, days = warehouse.mean_revision(con)
    return (
        f"days from {realtime[0]:%Y-%m-%d} are real-time data raised by {revision_gw:.2f} GW,"
        f" the revision measured on {days} days"
    )


def read_backtest(data_dir: Path) -> pd.DataFrame | None:
    """The backtest results, or None after a message if they are missing."""
    path = data_dir / "backtest.csv"
    if not path.exists():
        print(f"{path} is missing: run `flf backtest` first", file=sys.stderr)
        return None
    return pd.read_csv(path, parse_dates=["origin", "month"])


def run_forecast(data_dir: Path, config: Path) -> int:
    """Forecast monthly energy over the current month and the 11 after, with a P10-P90 band
    calibrated on the backtest errors. Days already measured replace the forecast."""
    past_forecasts = read_backtest(data_dir)
    if past_forecasts is None:
        return 1

    spec = model.load_spec(config)
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        history = model.daily_frame(con, spec.smoothing)
        observed = model.load_after(con, history.index[-1])
        note = realtime_note(con, history)
    fitted = model.fit_recent(history, spec)
    summary = outlook.table(fitted, history, observed, past_forecasts)

    start = pd.Timestamp(summary.index[0])
    last_measured = observed.index[-1] if not observed.empty else history.index[-1]
    years = forecast.complete_years(pd.DatetimeIndex(history.index))
    print(
        f"monthly energy in TWh: model up to {start - pd.Timedelta(days=1):%Y-%m-%d},"
        f" measured load up to {last_measured:%Y-%m-%d}"
    )
    print(note)
    print(f"P50 over {len(years)} weather years, P10-P90 from backtest errors before {start:%Y-%m}")
    summary.index = pd.DatetimeIndex(summary.index).strftime("%Y-%m")
    print(summary.drop(columns="horizon").to_string(float_format=lambda value: f"{value:.1f}"))
    ahead = summary.iloc[-12:]
    print(f"total P50 from {ahead.index[0]}: {ahead['p50'].sum():.1f} TWh")
    return 0


def run_backtest(data_dir: Path, config: Path, first: str) -> int:
    """Forecast from each month since `first` with the data known then, and score the forecasts."""
    spec = model.load_spec(config)
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        frame = model.daily_frame(con, spec.smoothing)
    # Past forecasts are scored against consolidated data only.
    history = frame[frame["source"] == "consolidated"]
    results = backtest.run(history, spec, backtest.monthly_origins(history, first))
    results.to_csv(data_dir / "backtest.csv", index=False)

    recent = results[results["origin"] >= backtest.RECENT_ORIGINS]
    for label, part in (("all origins", results), ("origins since 2023", recent)):
        print(f"mean absolute percentage error of monthly energy, {label}")
        print(backtest.accuracy(part).to_string(float_format=lambda value: f"{value:.2f}"))
    for first_origin in (conformal.FIRST_BAND_ORIGIN, backtest.RECENT_ORIGINS):
        coverage = conformal.online_coverage(results, first_origin)
        shares = ", ".join(f"{name} {100 * share:.0f} %" for name, share in coverage.items())
        print(f"P10-P90 coverage, origins since {first_origin:%Y}: {shares}")
    return 0


def decompose(data_dir: Path, config: Path, months: int) -> int:
    """Explain the energy of the last complete months against the forecast made at their start and
    against the same month a year earlier."""
    spec = model.load_spec(config)
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        history = model.daily_frame(con, spec.smoothing)
        print(realtime_note(con, history))
    recent = decomposition.recent_months(history, months)
    latest = model.fit_recent(history, spec)
    views = {
        "the forecast made at the start of the month": decomposition.against_forecast(
            history, spec, recent
        ),
        "the same month a year earlier": decomposition.against_year_before(latest, history, recent),
    }
    for reference, table in views.items():
        table.index = pd.DatetimeIndex(table.index).strftime("%Y-%m")
        print(f"monthly energy in TWh, against {reference}")
        print(table.to_string(float_format=lambda value: f"{value:.2f}"))
    return 0


def run_publish(data_dir: Path, config: Path, out: Path) -> int:
    """Write the weekly bundle of JSON files."""
    past_forecasts = read_backtest(data_dir)
    if past_forecasts is None:
        return 1

    spec = model.load_spec(config)
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        history = model.daily_frame(con, spec.smoothing)
        observed = model.load_after(con, history.index[-1])
        rte = correction.rte_monthly(con)
        revision = warehouse.mean_revision(con)
    published = datetime.now(UTC).date()
    files = publish.build(history, observed, spec, past_forecasts, rte, revision, published)
    publish.write(files, out)
    print(f"{', '.join(files)} written to {out}")
    return 0


def load_agent(
    bundle_dir: Path, agent_config: Path, facts: Path
) -> tuple[tools.Bundle, dict[str, dict[str, object]], agent.AgentConfig] | None:
    """The bundle, the facts and the agent's configuration, or None after a message if the bundle
    is missing."""
    if not (bundle_dir / "meta.json").exists():
        print(f"no bundle in {bundle_dir}: run `flf publish` first", file=sys.stderr)
        return None
    return tools.load_bundle(bundle_dir), tools.load_facts(facts), agent.load_config(agent_config)


def report(answer: agent.Answer) -> None:
    for call in answer.tool_calls:
        print(f"tool {call['name']} {json.dumps(call['args'], ensure_ascii=False)}")
    if not answer.verified:
        print(answer.text, file=sys.stderr)
        print(f"not shown: {answer.problem}", file=sys.stderr)


def run_ask(question: str, bundle_dir: Path, agent_config: Path, facts: Path) -> int:
    """Answer a question with the agent, with its tool calls and the check of its numbers."""
    loaded = load_agent(bundle_dir, agent_config, facts)
    if loaded is None:
        return 1
    bundle, fact_texts, config = loaded
    if len(question) > config.max_question_chars:
        print(f"questions are limited to {config.max_question_chars} characters", file=sys.stderr)
        return 1
    answer = agent.ask(question, bundle, fact_texts, agent.chat_model(config), config)
    report(answer)
    print(answer.text if answer.verified else agent.REFUSAL)
    return 0 if answer.verified else 1


def run_note(month: str, bundle_dir: Path, agent_config: Path, facts: Path, out: Path) -> int:
    """Write the note on a month, if every number of its reading has a source."""
    loaded = load_agent(bundle_dir, agent_config, facts)
    if loaded is None:
        return 1
    bundle, fact_texts, config = loaded
    text, reading = note.write(month, bundle, fact_texts, agent.chat_model(config), config)
    report(reading)
    if not reading.verified:
        return 1
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{month}.md"
    path.write_text(text, encoding="utf-8")
    print(f"{path} written")
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
    decompose_parser = commands.add_parser(
        "decompose", parents=[model_options], help="explain the energy gaps of recent months"
    )
    decompose_parser.add_argument(
        "--months", type=int, default=12, help="number of recent complete months"
    )
    publish_parser = commands.add_parser(
        "publish", parents=[model_options], help="write the weekly bundle of JSON files"
    )
    publish_parser.add_argument("--out", type=Path, default=Path("data/bundle"))
    agent_options = argparse.ArgumentParser(add_help=False)
    agent_options.add_argument("--bundle", type=Path, default=Path("data/bundle"))
    agent_options.add_argument("--agent-config", type=Path, default=Path("config/agent.toml"))
    agent_options.add_argument("--facts", type=Path, default=Path("config/facts.toml"))
    ask_parser = commands.add_parser(
        "ask", parents=[agent_options], help="answer a question with the agent"
    )
    ask_parser.add_argument("question")
    note_parser = commands.add_parser(
        "note", parents=[agent_options], help="write the note on a month with the agent"
    )
    note_parser.add_argument("month", help="month as YYYY-MM")
    note_parser.add_argument("--out", type=Path, default=Path("notes"))
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
    if args.command == "decompose":
        return decompose(args.data_dir, args.config, args.months)
    if args.command == "publish":
        return run_publish(args.data_dir, args.config, args.out)
    if args.command == "ask":
        return run_ask(args.question, args.bundle, args.agent_config, args.facts)
    if args.command == "note":
        return run_note(args.month, args.bundle, args.agent_config, args.facts, args.out)
    parser.error(f"unknown command {args.command}")
