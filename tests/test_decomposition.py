import numpy as np
import pandas as pd
import pytest

from france_load_forecast import backtest, climate, correction, decomposition, model

MONTHS = pd.DatetimeIndex(["2024-11-01", "2024-12-01"])
TOTALS = ["actual", "reference", "gap"]


@pytest.fixture(scope="module")
def forecast_view(
    synthetic_frame: pd.DataFrame, synthetic_spec: model.ModelSpec
) -> tuple[pd.DataFrame, pd.Series]:
    return decomposition.against_forecast(
        synthetic_frame, synthetic_frame["temperature_c"], synthetic_spec, MONTHS
    )


@pytest.fixture(scope="module")
def against_forecast(forecast_view: tuple[pd.DataFrame, pd.Series]) -> pd.DataFrame:
    return forecast_view[0]


@pytest.fixture(scope="module")
def against_year_before(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame
) -> pd.DataFrame:
    months = pd.DatetimeIndex(["2024-02-01", "2024-07-01"])
    return decomposition.against_year_before(synthetic_model, synthetic_frame, months)


def test_recent_months_are_complete(synthetic_frame: pd.DataFrame) -> None:
    months = decomposition.recent_months(synthetic_frame.loc[:"2024-12-15"], 2)

    assert months.tolist() == [pd.Timestamp("2024-10-01"), pd.Timestamp("2024-11-01")]


def test_reference_is_the_backtest_forecast_one_month_ahead(
    against_forecast: pd.DataFrame, synthetic_frame: pd.DataFrame, synthetic_spec: model.ModelSpec
) -> None:
    results = backtest.run(
        synthetic_frame, synthetic_frame["temperature_c"], synthetic_spec, MONTHS
    )
    one_month_ahead = results[results["horizon"] == 1].set_index("month")

    np.testing.assert_allclose(against_forecast["reference"], one_month_ahead["p50"])
    np.testing.assert_allclose(against_forecast["actual"], one_month_ahead["actual"])


def test_year_before_compares_the_actual_energies(
    against_year_before: pd.DataFrame, synthetic_frame: pd.DataFrame
) -> None:
    energy = correction.monthly_energy(synthetic_frame["load_gw"])
    months = pd.DatetimeIndex(against_year_before.index)

    np.testing.assert_allclose(against_year_before["actual"], energy[months])
    np.testing.assert_allclose(
        against_year_before["reference"], energy[months - pd.DateOffset(years=1)]
    )


@pytest.mark.parametrize("view", ["against_forecast", "against_year_before"])
def test_terms_add_up_to_the_gap(view: str, request: pytest.FixtureRequest) -> None:
    table: pd.DataFrame = request.getfixturevalue(view)

    np.testing.assert_allclose(table["gap"], table["actual"] - table["reference"])
    np.testing.assert_allclose(table.drop(columns=TOTALS).sum(axis=1), table["gap"])


def test_the_calendar_was_known_when_forecasting(against_forecast: pd.DataFrame) -> None:
    np.testing.assert_allclose(against_forecast[["calendar", "lockdown"]], 0.0, atol=1e-9)


def test_a_colder_month_shows_as_climate(
    against_forecast: pd.DataFrame, synthetic_frame: pd.DataFrame, synthetic_spec: model.ModelSpec
) -> None:
    cold = synthetic_frame.copy()
    cold.loc[cold.index >= MONTHS[1], "temperature_c"] -= 3.0
    cold["temperature_smooth"] = cold["temperature_c"].ewm(alpha=0.5, adjust=False).mean()
    # December stays below 15 °C, where the heating gradient is 2 GW/°C.
    colder_by = synthetic_frame["temperature_smooth"] - cold["temperature_smooth"]
    cold["load_gw"] += 2 * colder_by

    december_gap = decomposition.against_forecast(
        cold, cold["temperature_c"], synthetic_spec, MONTHS[1:]
    )[0].iloc[0]

    extra_heating = correction.monthly_energy(2 * colder_by)[MONTHS[1]]
    climate = december_gap["climate"] - against_forecast.at[MONTHS[1], "climate"]
    assert climate == pytest.approx(extra_heating, rel=0.05)


def test_the_forecast_assumed_the_weather_of_its_median_paths(
    forecast_view: tuple[pd.DataFrame, pd.Series], synthetic_frame: pd.DataFrame
) -> None:
    # With two past years to replay, P50 is the mean of both paths, so the forecast assumed the
    # mean of their weather.
    origin = MONTHS[1]
    days = pd.date_range(origin, periods=origin.days_in_month, freq="D")
    past = synthetic_frame[synthetic_frame.index < origin]
    replayed = climate.members(past, synthetic_frame["temperature_c"], days, [2022, 2023])

    assert forecast_view[1][origin] == pytest.approx(replayed.to_numpy().mean())


def test_the_weather_the_forecast_assumed_ignores_the_month(
    forecast_view: tuple[pd.DataFrame, pd.Series],
    synthetic_frame: pd.DataFrame,
    synthetic_spec: model.ModelSpec,
) -> None:
    cold = synthetic_frame.copy()
    cold.loc[cold.index >= MONTHS[1], "temperature_c"] -= 3.0

    _, assumed = decomposition.against_forecast(
        cold, cold["temperature_c"], synthetic_spec, MONTHS[1:]
    )

    assert assumed[MONTHS[1]] == pytest.approx(forecast_view[1][MONTHS[1]])


def test_29_february_counts_as_calendar_effect(
    against_year_before: pd.DataFrame, synthetic_frame: pd.DataFrame
) -> None:
    # 1 to 28 February hold four of each weekday in 2023 and 2024.
    leap_day = synthetic_frame["load_gw"][pd.Timestamp("2024-02-29")] * 24 / 1000

    assert against_year_before.at[pd.Timestamp("2024-02-01"), "calendar"] == pytest.approx(leap_day)


def test_year_before_needs_both_months_in_the_model(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame
) -> None:
    with pytest.raises(ValueError, match="same month a year earlier"):
        decomposition.against_year_before(
            synthetic_model, synthetic_frame, pd.DatetimeIndex(["2022-06-01"])
        )
