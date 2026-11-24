"""Command-line interface."""

import argparse
import json
import re
import sys
import time
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx
import pandas as pd

from france_load_forecast import (
    backtest,
    bundle,
    climate,
    conformal,
    correction,
    decomposition,
    forecast,
    model,
    odre,
    outlook,
    publish,
    scenarios,
    stations,
    warehouse,
)
from france_load_forecast.agent import agent, evaluate, note, tools


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


# What a month of each target of the model is, and its unit.
MONTHLY_NAMES = {"load_gw": ("monthly energy", "TWh"), "peak_gw": ("monthly peak", "GW")}


def backtest_path(data_dir: Path, spec: model.ModelSpec) -> Path:
    return data_dir / f"backtest-{spec.model_id}.csv"


def read_backtest(data_dir: Path, spec: model.ModelSpec) -> pd.DataFrame | None:
    """The backtest results of a model, or None after a message if they are missing."""
    path = backtest_path(data_dir, spec)
    if not path.exists():
        print(f"{path} is missing: run `flf backtest` with the same config first", file=sys.stderr)
        return None
    return pd.read_csv(path, parse_dates=["origin", "month"])


def run_forecast(data_dir: Path, config: Path, rebuilt: Path) -> int:
    """Forecast monthly energy, or peak, over the current month and the 11 after, with a P10-P90
    band calibrated on the backtest errors. Days already measured replace the forecast."""
    spec = model.load_spec(config)
    past_forecasts = read_backtest(data_dir, spec)
    if past_forecasts is None:
        return 1

    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        history = model.daily_frame(con, spec.smoothing)
        observed = model.load_after(con, history.index[-1], spec.target)
        note = realtime_note(con, history)
    fitted = model.fit_recent(history, spec)
    weather = climate.since_1950(history, climate.read_rebuilt(rebuilt))
    summary = outlook.table(fitted, history, weather, observed, past_forecasts)

    start = pd.Timestamp(summary.index[0])
    last_measured = observed.index[-1] if not observed.empty else history.index[-1]
    years = forecast.years_before(weather, start)
    name, unit = MONTHLY_NAMES[spec.target]
    print(
        f"{name} in {unit}: model up to {start - pd.Timedelta(days=1):%Y-%m-%d},"
        f" measured load up to {last_measured:%Y-%m-%d}"
    )
    print(note)
    print(
        f"P50 over the weather of {years[0]} to {years[-1]} in today's climate,"
        f" P10-P90 from backtest errors before {start:%Y-%m}"
    )
    summary.index = pd.DatetimeIndex(summary.index).strftime("%Y-%m")
    print(summary.drop(columns="horizon").to_string(float_format=lambda value: f"{value:.1f}"))
    if spec.target == "load_gw":
        ahead = summary.iloc[-12:]
        print(f"total P50 from {ahead.index[0]}: {ahead['p50'].sum():.1f} TWh")
    return 0


def run_backtest(data_dir: Path, config: Path, first: str, rebuilt: Path) -> int:
    """Forecast from each month since `first` with the data known then, and score the forecasts."""
    spec = model.load_spec(config)
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        frame = model.daily_frame(con, spec.smoothing)
    # Past forecasts are scored against consolidated data only.
    history = frame[frame["source"] == "consolidated"]
    weather = climate.since_1950(history, climate.read_rebuilt(rebuilt))
    results = backtest.run(history, weather, spec, backtest.monthly_origins(history, first))
    results.to_csv(backtest_path(data_dir, spec), index=False)

    recent = results[results["origin"] >= backtest.RECENT_ORIGINS]
    name, _ = MONTHLY_NAMES[spec.target]
    for label, part in (("all origins", results), ("origins since 2023", recent)):
        print(f"mean absolute percentage error of {name}, {label}")
        print(backtest.accuracy(part).to_string(float_format=lambda value: f"{value:.2f}"))
    for first_origin in (conformal.FIRST_BAND_ORIGIN, backtest.RECENT_ORIGINS):
        coverage = conformal.online_coverage(results, first_origin)
        shares = ", ".join(f"{name} {100 * share:.0f} %" for name, share in coverage.items())
        print(f"P10-P90 coverage, origins since {first_origin:%Y}: {shares}")
    return 0


def decompose(data_dir: Path, config: Path, months: int, rebuilt: Path) -> int:
    """Explain the energy of the last complete months against the forecast made at their start and
    against the same month a year earlier."""
    spec = model.load_spec(config)
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        history = model.daily_frame(con, spec.smoothing)
        print(realtime_note(con, history))
    recent = decomposition.recent_months(history, months)
    latest = model.fit_recent(history, spec)
    weather = climate.since_1950(history, climate.read_rebuilt(rebuilt))
    to_forecast, forecast_temperature = decomposition.against_forecast(
        history, weather, spec, recent
    )
    views = {
        "the forecast made at the start of the month": to_forecast,
        "the same month a year earlier": decomposition.against_year_before(latest, history, recent),
    }
    for reference, table in views.items():
        table.index = pd.DatetimeIndex(table.index).strftime("%Y-%m")
        print(f"monthly energy in TWh, against {reference}")
        print(table.to_string(float_format=lambda value: f"{value:.2f}"))
    temperatures = pd.DataFrame(
        {"month": history["temperature_c"].resample("MS").mean(), "forecast": forecast_temperature}
    ).loc[recent]
    temperatures.index = pd.DatetimeIndex(temperatures.index).strftime("%Y-%m")
    print("mean temperature in °C, of the month and of the weather the forecast assumed")
    print(temperatures.to_string(float_format=lambda value: f"{value:.1f}"))
    return 0


def run_publish(
    data_dir: Path,
    config: Path,
    peak_config: Path,
    scenario_config: Path,
    rebuilt: Path,
    out: Path,
) -> int:
    """Write the weekly bundle of JSON files."""
    spec, peak_spec = model.load_spec(config), model.load_spec(peak_config)
    past_forecasts, past_peaks = read_backtest(data_dir, spec), read_backtest(data_dir, peak_spec)
    if past_forecasts is None or past_peaks is None:
        return 1

    scenario_spec = scenarios.load_spec(scenario_config)
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        history = model.daily_frame(con, spec.smoothing)
        observed = model.load_after(con, history.index[-1], spec.target)
        peak_history = model.daily_frame(con, peak_spec.smoothing)
        peak = publish.PeakInputs(
            peak_history,
            peak_spec,
            past_peaks,
            model.load_after(con, peak_history.index[-1], peak_spec.target),
        )
        rte = correction.rte_monthly(con)
        revision = warehouse.mean_revision(con)
    published = datetime.now(UTC).date()
    weather = climate.since_1950(history, climate.read_rebuilt(rebuilt))
    files = publish.build(
        history,
        weather,
        observed,
        spec,
        past_forecasts,
        rte,
        revision,
        scenario_spec,
        published,
        peak,
    )
    problems = bundle.check(files)
    for problem in problems:
        print(f"bundle check failed: {problem}", file=sys.stderr)
    if problems:
        return 1
    publish.write(files, out)
    print(f"{', '.join(files)} written to {out}")
    return 0


def rebuild_temperature(data_dir: Path, config: Path, out: Path) -> int:
    """Rebuild the national temperature from Météo-France stations for the days before RTE's
    series, and write it to `out`."""
    spec = stations.load_spec(config)
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        paths = stations.download(client, spec, data_dir / "raw" / "meteo-france")
    daily = stations.read_daily(paths, spec.stations)
    daily = daily[daily.index >= spec.first_day]
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        rte = con.execute("SELECT date, temperature_c FROM temperature ORDER BY date").df()
    national = pd.Series(rte["temperature_c"].to_numpy(), index=pd.DatetimeIndex(rte["date"]))
    first, last = spec.fit_years
    years = pd.DatetimeIndex(national.index).year
    national = national[(years >= first) & (years <= last)]

    weights = stations.fit(daily, national)
    rebuilt = stations.rebuild(daily, weights)
    before = rebuilt[rebuilt.index < national.index[0]]
    days = pd.date_range(spec.first_day, national.index[0] - pd.Timedelta(days=1))
    if not days.isin(before.index).all():
        print(f"{(~days.isin(before.index)).sum()} days lack a station", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    before.round(2).rename("temperature_c").rename_axis("date").to_csv(out)

    split = last - 4
    error = stations.holdout_error(daily, national, split)
    print(
        f"weights fitted on {first}-{split - 1} rebuild {split}-{last} with an RMSE of "
        f"{(error**2).mean() ** 0.5:.2f} °C and a mean error of {error.mean():+.2f} °C"
    )
    print(f"weights fitted on {first}-{last}:")
    for station, weight in weights[weights > 0].sort_values(ascending=False).items():
        print(f"  {spec.stations[str(station)]:<24} {weight:.3f}")
    print(f"{days[0]:%Y-%m-%d} to {days[-1]:%Y-%m-%d} written to {out}")
    return 0


def snapshot(data_dir: Path, out: Path) -> int:
    """Save the real-time load of the warehouse, which RTE overwrites once consolidated."""
    with duckdb.connect(data_dir / "warehouse.duckdb", read_only=True) as con:
        rows = warehouse.export_realtime(con, out)
    print(f"{rows} real-time values written to {out}")
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
    """Write the note on a month, if every number of its reading has a source in the tool
    results and in the note itself."""
    loaded = load_agent(bundle_dir, agent_config, facts)
    if loaded is None:
        return 1
    bundle, fact_texts, config = loaded
    months = [entry["month"] for entry in bundle["gaps"]["months"]]
    if month not in months:
        print(f"no gap for {month}: the bundle covers {months[0]} to {months[-1]}", file=sys.stderr)
        return 1
    text, data, reading = note.write(month, bundle, fact_texts, agent.chat_model(config), config)
    report(reading)
    if not reading.verified:
        return 1
    wrong = note.unsupported(data)
    if wrong:
        print(f"figures that the note does not give: {', '.join(wrong)}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{month}.md").write_text(text, encoding="utf-8")
    (out / f"{month}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{out / month}.md and .json written")
    return 0


# A provider that refuses this many questions in a row, past its daily limit for instance, is
# left for later.
STOP_AFTER_ERRORS = 3


def run_eval(
    models: list[str],
    only: str | None,
    paths: dict[str, Path],
    pause: float,
) -> int:
    """Ask the frozen questions to each model, keep its runs, and write the report of every
    model run so far on the same data."""
    loaded = load_agent(paths["bundle"], paths["agent_config"], paths["facts"])
    if loaded is None:
        return 1
    bundle, fact_texts, config = loaded
    questions = evaluate.load_questions(paths["questions"])
    asked = [q for q in questions if only is None or q.id in only.split(",")]
    for name in models:
        path = paths["runs"] / f"{re.sub(r'[^a-z0-9]+', '-', name.lower())}.jsonl"
        runs = {run.id: run for run in evaluate.read_runs(path)}
        model = agent.chat_model(replace(config, model=name), patient=True)
        todo = evaluate.pending(asked, runs.values())
        failures = 0
        for i, question in enumerate(todo):
            if i > 0 and pause > 0:
                time.sleep(pause)
            run = evaluate.ask(question, bundle, fact_texts, model, config, name)
            runs[question.id] = run
            # Kept after each question, so that a stopped run starts again where it stopped.
            evaluate.write_runs(path, runs.values())
            outcome = run.error or ("verified" if run.verified else run.problem)
            print(f"{name} {question.id}: {outcome}, {run.seconds} s")
            failures = failures + 1 if run.error else 0
            if failures == STOP_AFTER_ERRORS:
                print(f"{name} stopped after {failures} errors in a row: run it again later")
                break
    results = {}
    for path in sorted(paths["runs"].glob("*.jsonl")):
        runs_of = [
            r for r in evaluate.read_runs(path) if r.published == bundle["meta"]["published"]
        ]
        if not runs_of:
            print(f"{path}: no run on the data of {bundle['meta']['published']}", file=sys.stderr)
            continue
        by_id = {q.id: q for q in questions}
        scores = [
            evaluate.score(by_id[r.id], r, bundle, fact_texts) for r in runs_of if r.id in by_id
        ]
        results[runs_of[0].model] = (runs_of, scores)
    text = evaluate.report(questions, results)
    paths["report"].write_text(text, encoding="utf-8")
    print(text.split("\n## ")[0])
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
    model_options.add_argument(
        "--rebuilt",
        type=Path,
        default=Path("climate/national-temperature.csv"),
        help="national temperature before RTE's series, from `flf rebuild-temperature`",
    )
    commands.add_parser("fit", parents=[model_options], help="fit the daily load model")
    commands.add_parser(
        "correct",
        parents=[model_options],
        help="compare the climate-corrected consumption with RTE's corrected series",
    )
    commands.add_parser(
        "forecast", parents=[model_options], help="forecast monthly energy or peak over 12 months"
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
    publish_parser.add_argument("--peak-config", type=Path, default=Path("config/peak.toml"))
    publish_parser.add_argument("--scenarios", type=Path, default=Path("config/scenarios.toml"))
    snapshot_parser = commands.add_parser(
        "snapshot", parents=[common], help="save the real-time load as a Parquet file"
    )
    snapshot_parser.add_argument("out", type=Path)
    rebuild_parser = commands.add_parser(
        "rebuild-temperature",
        parents=[common],
        help="rebuild the national temperature before 2012 from Météo-France stations",
    )
    rebuild_parser.add_argument("--config", type=Path, default=Path("config/stations.toml"))
    rebuild_parser.add_argument(
        "--out", type=Path, default=Path("climate/national-temperature.csv")
    )
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
    eval_parser = commands.add_parser(
        "eval", parents=[agent_options], help="ask the frozen questions to models and score them"
    )
    eval_parser.add_argument(
        "--model", action="append", required=True, help='"provider:model", repeated to compare'
    )
    eval_parser.add_argument("--only", help="ids of the questions to ask, separated by commas")
    eval_parser.add_argument("--questions", type=Path, default=Path("evals/questions.toml"))
    eval_parser.add_argument("--runs", type=Path, default=Path("evals/runs"))
    eval_parser.add_argument("--report", type=Path, default=Path("evals/results.md"))
    eval_parser.add_argument(
        "--pause", type=float, default=0.0, help="seconds between questions, under a rate limit"
    )
    # The bundle of 22 November 2026, frozen with the tests, so that every model reads the same
    # data as the reference answers.
    eval_parser.set_defaults(bundle=Path("tests/fixtures/bundle"))
    args = parser.parse_args(argv)

    if args.command == "ingest":
        return ingest(args.data_dir)
    if args.command == "fit":
        return fit(args.data_dir, args.config)
    if args.command == "correct":
        return correct(args.data_dir, args.config)
    if args.command == "forecast":
        return run_forecast(args.data_dir, args.config, args.rebuilt)
    if args.command == "backtest":
        return run_backtest(args.data_dir, args.config, args.first, args.rebuilt)
    if args.command == "decompose":
        return decompose(args.data_dir, args.config, args.months, args.rebuilt)
    if args.command == "publish":
        return run_publish(
            args.data_dir, args.config, args.peak_config, args.scenarios, args.rebuilt, args.out
        )
    if args.command == "snapshot":
        return snapshot(args.data_dir, args.out)
    if args.command == "rebuild-temperature":
        return rebuild_temperature(args.data_dir, args.config, args.out)
    if args.command == "ask":
        return run_ask(args.question, args.bundle, args.agent_config, args.facts)
    if args.command == "note":
        return run_note(args.month, args.bundle, args.agent_config, args.facts, args.out)
    if args.command == "eval":
        paths = {
            "bundle": args.bundle,
            "agent_config": args.agent_config,
            "facts": args.facts,
            "questions": args.questions,
            "runs": args.runs,
            "report": args.report,
        }
        return run_eval(args.model, args.only, paths, args.pause)
    parser.error(f"unknown command {args.command}")
