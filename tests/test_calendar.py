import numpy as np
import pandas as pd
import pytest

from france_load_forecast.calendar import calendar_features


@pytest.fixture
def features() -> pd.DataFrame:
    return calendar_features(pd.date_range("2019-12-01", "2026-01-31", freq="D"))


@pytest.mark.parametrize(
    ("date", "day_type"),
    [
        ("2025-05-01", "holiday"),  # Labour Day, a Thursday
        ("2025-05-02", "fri"),
        ("2025-12-28", "sun"),
    ],
)
def test_public_holidays_override_the_weekday(
    features: pd.DataFrame, date: str, day_type: str
) -> None:
    assert features.loc[date, "day_type"] == day_type


@pytest.mark.parametrize(
    ("date", "bridge"),
    [
        ("2025-05-02", 1),  # Friday after Labour Day
        ("2025-05-30", 1),  # Friday after Ascension
        ("2024-12-30", 0),  # Monday before a Tuesday that is not a holiday
        ("2025-12-29", 0),
        ("2019-12-30", 0),
        ("2024-08-16", 1),  # Friday after Assumption
    ],
)
def test_bridge_days(features: pd.DataFrame, date: str, bridge: int) -> None:
    assert features.loc[date, "bridge"] == bridge


def test_lockdown_periods_include_both_ends(features: pd.DataFrame) -> None:
    first = features["lockdown_1"]

    assert first["2020-03-16"] == 0
    assert first["2020-03-17"] == first["2020-05-10"] == 1
    assert first["2020-05-11"] == 0
    assert features[["lockdown_1", "lockdown_2", "lockdown_3"]].sum().tolist() == [55, 46, 30]


def test_end_of_year_period(features: pd.DataFrame) -> None:
    assert features.loc["2025-12-23", "christmas"] == 0
    assert features.loc["2025-12-24":"2025-12-31", "christmas"].eq(1).all()


def test_annual_harmonics_repeat_every_year(features: pd.DataFrame) -> None:
    harmonics = ["sin1", "cos1", "sin2", "cos2"]

    np.testing.assert_allclose(
        features.loc["2022-03-01", harmonics], features.loc["2023-03-01", harmonics]
    )
