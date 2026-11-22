import numpy as np
import pandas as pd
import pytest

from france_load_forecast import forecast, model


def test_complete_years_need_every_day() -> None:
    dates = pd.date_range("2023-03-01", "2025-12-31", freq="D").delete(10)

    assert forecast.complete_years(dates) == [2024, 2025]


def test_paths_cover_twelve_months_per_weather_year(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame
) -> None:
    paths = forecast.paths(synthetic_model, synthetic_frame, synthetic_frame, [2022, 2023])

    assert paths.shape == (12, 2)
    assert paths.index.tolist() == list(pd.date_range("2025-01-01", periods=12, freq="MS"))
    assert paths.notna().all().all()


def test_a_colder_year_needs_more_energy_in_winter(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame
) -> None:
    weather = synthetic_frame.copy()
    year = pd.DatetimeIndex(weather.index).year
    weather["temperature_c"] = weather["reference_c"] + np.where(year == 2022, -3.0, 3.0)

    paths = forecast.paths(synthetic_model, synthetic_frame, weather, [2022, 2023])

    january = paths.loc["2025-01-01"]
    # 31 days at 2 GW/°C for a 6 °C difference.
    assert january[2022] - january[2023] == pytest.approx(31 * 24 * 2 * 6 / 1000, rel=0.15)


def test_history_must_end_with_a_month(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame
) -> None:
    with pytest.raises(ValueError, match="last day of a month"):
        forecast.paths(synthetic_model, synthetic_frame.iloc[:-1], synthetic_frame, [2022])
