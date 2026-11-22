from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from france_load_forecast import model, warehouse


def test_fit_recovers_the_heating_gradient(synthetic_model: model.DailyModel) -> None:
    gradient = model.thermosensitivity(synthetic_model, pd.Series([0.0, 5.0, 10.0, 20.0]))

    np.testing.assert_allclose(gradient, [2.0, 2.0, 2.0, 0.0], atol=0.3)


def test_fit_recovers_the_weekend_effect(synthetic_model: model.DailyModel) -> None:
    weekend = synthetic_model.coefficients.filter(regex=r"\[T\.(sat|sun)\]")

    np.testing.assert_allclose(weekend, -6.0, atol=0.3)


def test_components_and_states_add_up_to_the_load(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame
) -> None:
    ar = synthetic_model.results.autoregressive["smoothed"]

    effects = model.contributions(synthetic_model, synthetic_frame).sum(axis=1)
    rebuilt = effects + synthetic_model.level + synthetic_model.seasonal + ar

    np.testing.assert_allclose(rebuilt, synthetic_frame["load_gw"], atol=1e-6)


def test_lockdowns_are_dropped_outside_their_period(synthetic_model: model.DailyModel) -> None:
    assert not synthetic_model.coefficients.index.str.startswith("lockdown").any()


def test_fit_recent_keeps_the_last_years(
    synthetic_frame: pd.DataFrame, synthetic_spec: model.ModelSpec
) -> None:
    fitted = model.fit_recent(synthetic_frame, synthetic_spec)

    assert fitted.level.index[0] == pd.Timestamp("2023-01-01")


def test_spec_reads_the_repository_config() -> None:
    spec = model.load_spec(Path(__file__).parents[1] / "config" / "model.toml")

    assert spec.components["climate"].startswith("cr(temperature_smooth")
    assert 0 < spec.smoothing <= 1


def test_daily_frame_continues_with_realtime_days(export_files: dict[str, Path]) -> None:
    con = duckdb.connect()
    warehouse.build(con, export_files)

    frame = model.daily_frame(con, smoothing=0.5)

    assert frame.index.tolist() == list(pd.date_range("2026-08-30", "2026-09-02"))
    assert frame["source"].tolist() == ["consolidated"] * 2 + ["realtime"] * 2
    first, second = frame["temperature_c"].iloc[:2]
    assert frame["temperature_smooth"].iloc[1] == pytest.approx((first + second) / 2)


def test_load_after_returns_the_later_days(export_files: dict[str, Path]) -> None:
    con = duckdb.connect()
    warehouse.build(con, export_files)
    daily = con.execute("SELECT date, load_gw FROM load_daily WHERE date > '2026-08-31'").fetchall()

    later = model.load_after(con, pd.Timestamp("2026-08-31"))

    assert later.index.tolist() == list(pd.date_range("2026-09-01", "2026-09-02"))
    np.testing.assert_allclose(later, [load_gw for _, load_gw in sorted(daily)])
    assert model.load_after(con, pd.Timestamp("2026-09-02")).empty
