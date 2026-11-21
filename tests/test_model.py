from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from france_load_forecast import model, warehouse
from france_load_forecast.calendar import calendar_features

CLIMATE = "cr(temperature_smooth, df=6, constraints='center', lower_bound=-15, upper_bound=35)"
SPEC = model.ModelSpec(
    smoothing=0.5,
    components={
        "climate": CLIMATE,
        "calendar": "C(day_type, Treatment('wed'))",
        "lockdown": "lockdown_1 + lockdown_2 + lockdown_3",
    },
)


def synthetic_frame(start: str, years: int = 3, gradient: float = 2.0) -> pd.DataFrame:
    """Daily load with a known heating gradient below 15 °C and a weekend drop of 6 GW."""
    rng = np.random.default_rng(0)
    dates = pd.date_range(start, periods=365 * years, freq="D")
    season = np.cos(2 * np.pi * dates.day_of_year.to_numpy() / 365.25)
    temperature = 12 - 8 * season + rng.normal(0, 2, len(dates))
    smooth = pd.Series(temperature, index=dates).ewm(alpha=0.5, adjust=False).mean()
    weekend = (dates.day_of_week >= 5).astype(float)
    load = 50 + gradient * np.maximum(0, 15 - smooth) - 6 * weekend + rng.normal(0, 0.3, len(dates))
    frame = pd.DataFrame({"load_gw": load, "temperature_smooth": smooth}, index=dates)
    return frame.join(calendar_features(dates))


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return synthetic_frame("2022-01-01")


@pytest.fixture(scope="module")
def fitted(frame: pd.DataFrame) -> model.DailyModel:
    return model.fit(frame, SPEC)


def test_fit_recovers_the_heating_gradient(fitted: model.DailyModel) -> None:
    gradient = model.thermosensitivity(fitted, pd.Series([0.0, 5.0, 10.0, 20.0]))

    np.testing.assert_allclose(gradient, [2.0, 2.0, 2.0, 0.0], atol=0.3)


def test_fit_recovers_the_weekend_effect(fitted: model.DailyModel) -> None:
    weekend = fitted.coefficients.filter(regex=r"\[T\.(sat|sun)\]")

    np.testing.assert_allclose(weekend, -6.0, atol=0.3)


def test_components_level_and_ar_add_up_to_the_load(
    fitted: model.DailyModel, frame: pd.DataFrame
) -> None:
    ar = fitted.results.smoothed_state[1]

    rebuilt = model.contributions(fitted, frame).sum(axis=1) + fitted.level + ar

    np.testing.assert_allclose(rebuilt, frame["load_gw"], atol=1e-6)


def test_lockdowns_are_dropped_outside_their_period(fitted: model.DailyModel) -> None:
    assert not fitted.coefficients.index.str.startswith("lockdown").any()


def test_spec_reads_the_repository_config() -> None:
    spec = model.load_spec(Path(__file__).parents[1] / "config" / "model.toml")

    assert spec.components["climate"].startswith("cr(temperature_smooth")
    assert 0 < spec.smoothing <= 1


def test_daily_frame_smooths_consolidated_temperatures(export_files: dict[str, Path]) -> None:
    con = duckdb.connect()
    warehouse.build(con, export_files)

    frame = model.daily_frame(con, smoothing=0.5)

    assert frame.index.tolist() == list(pd.date_range("2026-08-30", "2026-08-31"))
    first, second = frame["temperature_c"]
    assert frame["temperature_smooth"].iloc[1] == pytest.approx((first + second) / 2)
