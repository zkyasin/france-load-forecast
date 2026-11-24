from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from france_load_forecast import climate


@pytest.fixture
def history() -> pd.DataFrame:
    """Four years at 10 °C, with a constant reference of 8 °C."""
    dates = pd.date_range("2020-01-01", "2023-12-31", freq="D")
    return pd.DataFrame({"temperature_c": 10.0, "reference_c": 8.0}, index=dates)


def test_too_few_years_for_a_trend_are_replayed_as_observed(history: pd.DataFrame) -> None:
    weather = history["temperature_c"].copy()
    weather[pd.DatetimeIndex(weather.index).year == 2021] = 13.0
    dates = pd.date_range("2024-01-01", "2024-03-31", freq="D")

    members = climate.members(history, weather, dates, [2021, 2022])

    assert (members[2021] == 13.0).all()
    assert (members[2022] == 10.0).all()


def test_a_past_year_moves_by_the_warming_since_then() -> None:
    days = pd.date_range("1960-01-01", "2019-12-31", freq="D")
    # Sixty years warming by 0.03 °C a year, and a cold day in 1963.
    weather = pd.Series(10 + 0.03 * (days.year - 1960), index=days)
    weather[days == pd.Timestamp("1963-01-15")] -= 8.0
    history = pd.DataFrame({"temperature_c": weather, "reference_c": 12.0}, index=days)
    years = list(range(1960, 2020))

    members = climate.members(history, weather, pd.DatetimeIndex(["2020-01-15"]), years)

    np.testing.assert_allclose(members.drop(columns=1963).iloc[0], 12.0, atol=0.01)
    assert members.at[pd.Timestamp("2020-01-15"), 1963] == pytest.approx(4.0, abs=0.05)


def test_29_february_takes_28_february(history: pd.DataFrame) -> None:
    weather = history["temperature_c"].copy()
    weather[pd.DatetimeIndex(weather.index) == pd.Timestamp("2022-02-28")] = 0.0

    members = climate.members(history, weather, pd.DatetimeIndex(["2024-02-29"]), [2022])

    assert members.at[pd.Timestamp("2024-02-29"), 2022] == 0.0


def test_today_is_the_reference_of_the_last_365_days() -> None:
    days = pd.date_range("1960-01-01", "2019-12-31", freq="D")
    weather = pd.Series(10 + 0.03 * (days.year - 1960), index=days)
    history = pd.DataFrame({"temperature_c": weather, "reference_c": 12.0}, index=days)
    history.loc[history.index[-365:], "reference_c"] = 13.0

    members = climate.members(
        history, weather, pd.DatetimeIndex(["2020-06-01"]), list(range(1960, 2020))
    )

    np.testing.assert_allclose(members.iloc[0], 13.0, atol=0.01)


def test_the_rebuilt_temperature_comes_before_rte(history: pd.DataFrame, tmp_path: Path) -> None:
    path = tmp_path / "national-temperature.csv"
    path.write_text("date,temperature_c\n2019-12-30,1.5\n2019-12-31,2.5\n", encoding="utf-8")

    weather = climate.since_1950(history, climate.read_rebuilt(path))

    assert weather.index[0] == pd.Timestamp("2019-12-30")
    assert weather.iloc[:3].tolist() == [1.5, 2.5, 10.0]
    assert pd.DatetimeIndex(weather.index).is_monotonic_increasing


def test_smoothing_continues_from_the_day_before() -> None:
    temperature = pd.DataFrame({"a": [10.0, 10.0]}, index=pd.date_range("2024-01-01", periods=2))

    smoothed = climate.smooth(temperature, alpha=0.5, start=0.0)

    assert smoothed["a"].tolist() == [5.0, 7.5]
