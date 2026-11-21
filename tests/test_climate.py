import pandas as pd
import pytest

from france_load_forecast import climate


@pytest.fixture
def history() -> pd.DataFrame:
    """Four years at a constant reference of 8 °C, with 2021 five degrees warmer than usual."""
    dates = pd.date_range("2020-01-01", "2023-12-31", freq="D")
    history = pd.DataFrame({"temperature_c": 10.0, "reference_c": 8.0}, index=dates)
    history.loc["2021", "temperature_c"] = 13.0
    return history


def test_member_is_reference_plus_the_past_anomaly(history: pd.DataFrame) -> None:
    dates = pd.date_range("2024-01-01", "2024-03-31", freq="D")

    members = climate.members(history, history, dates, [2021, 2022])

    assert (members[2021] == 13.0).all()
    assert (members[2022] == 10.0).all()


def test_29_february_takes_the_anomaly_of_28_february(history: pd.DataFrame) -> None:
    history.loc["2022-02-28", "temperature_c"] = 0.0

    members = climate.members(history, history, pd.DatetimeIndex(["2024-02-29"]), [2022])

    assert members.loc["2024-02-29", 2022] == 0.0


def test_reference_comes_from_the_latest_year(history: pd.DataFrame) -> None:
    history.loc["2023", "reference_c"] = 9.0

    members = climate.members(history, history, pd.DatetimeIndex(["2024-06-01"]), [2022])

    assert members.loc["2024-06-01", 2022] == 11.0


def test_smoothing_continues_from_the_day_before() -> None:
    temperature = pd.DataFrame({"a": [10.0, 10.0]}, index=pd.date_range("2024-01-01", periods=2))

    smoothed = climate.smooth(temperature, alpha=0.5, start=0.0)

    assert smoothed["a"].tolist() == [5.0, 7.5]
