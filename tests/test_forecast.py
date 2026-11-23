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


def test_measured_days_replace_the_forecast(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame
) -> None:
    january = pd.date_range("2025-01-01", "2025-01-31")
    observed = pd.Series(60.0, index=january)

    forecast_only = forecast.paths(synthetic_model, synthetic_frame, synthetic_frame, [2022, 2023])
    with_observed = forecast.paths(
        synthetic_model, synthetic_frame, synthetic_frame, [2022, 2023], observed=observed
    )

    np.testing.assert_allclose(with_observed.loc["2025-01-01"], 60 * 744 / 1000)
    pd.testing.assert_frame_equal(with_observed.iloc[1:], forecast_only.iloc[1:])


def test_normal_climate_lies_between_a_cold_and_a_warm_year(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame
) -> None:
    weather = synthetic_frame.copy()
    year = pd.DatetimeIndex(weather.index).year
    weather["temperature_c"] = weather["reference_c"] + np.where(year == 2022, -3.0, 3.0)

    paths = forecast.paths(synthetic_model, synthetic_frame, weather, [2022, 2023])
    normal = forecast.normal(synthetic_model, synthetic_frame, 12)

    january = pd.Timestamp("2025-01-01")
    assert paths.at[january, 2022] > normal[january] > paths.at[january, 2023]
    assert normal.index.equals(paths.index)


def test_monthly_peak_is_the_highest_day() -> None:
    daily = pd.Series([70.0, 82.5, 75.0], index=pd.date_range("2027-01-30", periods=3))

    assert forecast.monthly_peak(daily).tolist() == [82.5, 75.0]


def test_every_target_adds_up_over_a_month() -> None:
    assert set(forecast.MONTHLY) == set(model.TARGETS)


def test_a_peak_path_keeps_the_highest_day(
    synthetic_peak_model: model.DailyModel, synthetic_frame: pd.DataFrame
) -> None:
    record = pd.Series(100.0, index=[pd.Timestamp("2025-01-15")])

    paths = forecast.paths(
        synthetic_peak_model, synthetic_frame, synthetic_frame, [2022, 2023], observed=record
    )

    np.testing.assert_allclose(paths.loc["2025-01-01"], 100.0)
    # Without any cold day, the summer peak stays near the 15 % above a mean load of about 50 GW.
    july = paths.loc["2025-07-01"].to_numpy()
    assert ((july > 55) & (july < 65)).all()
