import csv
import datetime as dt
from pathlib import Path

import duckdb
import pytest

from france_load_forecast import warehouse


@pytest.fixture
def con(export_files: dict[str, Path]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    warehouse.build(con, export_files)
    return con


def daily_load(con: duckdb.DuckDBPyConnection) -> dict[dt.date, tuple[float, int, str]]:
    rows = con.execute("SELECT date, load_gw, n_values, source FROM load_daily").fetchall()
    return {date: (load_gw, n_values, source) for date, load_gw, n_values, source in rows}


def test_daily_load_is_the_mean_of_the_day(con: duckdb.DuckDBPyConnection, fixtures: Path) -> None:
    with (fixtures / "eco2mix-national-cons-def.csv").open(encoding="utf-8-sig") as file:
        values = [float(row["consommation"]) for row in csv.DictReader(file, delimiter=";")]
    first_day = values[:48]

    load_gw, n_values, source = daily_load(con)[dt.date(2026, 8, 30)]

    assert load_gw == pytest.approx(sum(first_day) / 48 / 1000)
    assert (n_values, source) == (48, "consolidated")


def test_realtime_days_extend_the_consolidated_series(con: duckdb.DuckDBPyConnection) -> None:
    days = daily_load(con)

    assert sorted(days) == [dt.date(2026, 8, d) for d in (30, 31)] + [
        dt.date(2026, 9, d) for d in (1, 2)
    ]
    assert days[dt.date(2026, 9, 1)][1:] == (96, "realtime")


def mean_by_day(path: Path, field: str, day_format: str) -> dict[dt.date, float]:
    by_day: dict[dt.date, list[float]] = {}
    with path.open(encoding="utf-8-sig") as file:
        for row in csv.DictReader(file, delimiter=";"):
            day = dt.datetime.strptime(row["date"], day_format).date()
            by_day.setdefault(day, []).append(float(row[field]) / 1000)
    return {day: sum(values) / len(values) for day, values in by_day.items()}


def test_realtime_days_are_raised_by_the_mean_revision(
    con: duckdb.DuckDBPyConnection, fixtures: Path
) -> None:
    realtime = mean_by_day(fixtures / "eco2mix-national-tr.csv", "consommation", "%Y-%m-%d")
    revised = mean_by_day(
        fixtures / "consommation-quotidienne-brute.csv",
        "consommation_brute_electricite_rte",
        "%d/%m/%Y",
    )
    revision = sum(revised[day] - realtime[day] for day in realtime) / len(realtime)

    load_gw, _, _ = daily_load(con)[dt.date(2026, 9, 1)]

    assert load_gw == pytest.approx(realtime[dt.date(2026, 9, 1)] + revision)
    assert 0.5 < revision < 1.5


def test_checks_report_realtime_days_without_revision(
    export_files: dict[str, Path], fixtures: Path, tmp_path: Path
) -> None:
    lines = (fixtures / "consommation-quotidienne-brute.csv").read_text(encoding="utf-8-sig")
    august_only = tmp_path / "revised.csv"
    august_only.write_text("\n".join(line for line in lines.splitlines() if "/09/" not in line))
    con = duckdb.connect()

    warehouse.build(con, export_files | {"load_revised": august_only})

    failures = warehouse.run_checks(con)
    assert any(f.startswith("real-time days without a measured revision") for f in failures)


def test_incomplete_realtime_day_is_left_out(
    export_files: dict[str, Path], fixtures: Path, tmp_path: Path
) -> None:
    lines = (fixtures / "eco2mix-national-tr.csv").read_text(encoding="utf-8-sig").splitlines()
    truncated = tmp_path / "realtime.csv"
    truncated.write_text("\n".join(lines[:-10]) + "\n")
    con = duckdb.connect()

    warehouse.build(con, export_files | {"load_realtime": truncated})

    assert dt.date(2026, 9, 2) not in daily_load(con)


def test_clock_change_day_has_48_unique_half_hours(
    export_files: dict[str, Path], fixtures: Path
) -> None:
    con = duckdb.connect()
    clock_change = fixtures / "eco2mix-national-cons-def-clock-change.csv"

    warehouse.build(con, export_files | {"load_consolidated": clock_change})

    assert daily_load(con)[dt.date(2026, 3, 29)][1] == 48
    assert not con.execute(warehouse.CHECKS["duplicate half-hours in consolidated load"]).fetchall()


def test_monthly_series_is_keyed_by_first_day_of_month(con: duckdb.DuckDBPyConnection) -> None:
    months = [row[0] for row in con.execute("SELECT month FROM rte_monthly").fetchall()]

    assert months[0] == dt.date(2026, 6, 1)


def test_checks_pass_on_consistent_exports(con: duckdb.DuckDBPyConnection) -> None:
    assert warehouse.run_checks(con) == []


def test_checks_report_missing_days(export_files: dict[str, Path], fixtures: Path) -> None:
    con = duckdb.connect()
    # The clock-change export ends in March, so the series jumps to September.
    clock_change = fixtures / "eco2mix-national-cons-def-clock-change.csv"

    warehouse.build(con, export_files | {"load_consolidated": clock_change})

    assert any(f.startswith("missing days in daily load") for f in warehouse.run_checks(con))


def test_checks_report_consecutive_missing_temperatures(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        "UPDATE temperature SET temperature_c = NULL WHERE date IN ('2026-08-31', '2026-09-01')"
    )

    failures = warehouse.run_checks(con)

    assert any(f.startswith("temperature missing two days in a row") for f in failures)
