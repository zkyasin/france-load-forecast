from dataclasses import replace

import pandas as pd
import pytest

from france_load_forecast import backtest, correction, forecast, model


def test_origins_run_until_the_month_after_the_history(synthetic_frame: pd.DataFrame) -> None:
    origins = backtest.monthly_origins(synthetic_frame, "2024-10-01")

    assert origins.tolist() == list(pd.date_range("2024-10-01", "2025-01-01", freq="MS"))


def test_run_scores_twelve_months_per_origin(
    synthetic_frame: pd.DataFrame, synthetic_spec: model.ModelSpec
) -> None:
    origins = pd.DatetimeIndex(["2024-01-01", "2024-02-01"])

    results = backtest.run(
        synthetic_frame, synthetic_frame["temperature_c"], synthetic_spec, origins
    )

    first = results[results["origin"] == origins[0]]
    assert first["horizon"].tolist() == list(range(1, 13))
    assert first["actual"].notna().all()
    assert results[results["origin"] == origins[1]]["actual"].isna().sum() == 1
    april = first[first["month"] == pd.Timestamp("2024-04-01")].iloc[0]
    energy = correction.monthly_energy(synthetic_frame["load_gw"])
    assert april["naive"] == pytest.approx(energy[pd.Timestamp("2023-04-01")])
    assert april["p50"] == pytest.approx(april["actual"], rel=0.05)


def test_run_scores_the_monthly_peak_of_a_peak_model(
    synthetic_frame: pd.DataFrame, synthetic_spec: model.ModelSpec
) -> None:
    spec = replace(synthetic_spec, target="peak_gw")

    results = backtest.run(
        synthetic_frame, synthetic_frame["temperature_c"], spec, pd.DatetimeIndex(["2024-01-01"])
    )

    april = results[results["month"] == pd.Timestamp("2024-04-01")].iloc[0]
    peaks = forecast.monthly_peak(synthetic_frame["peak_gw"])
    assert (april["actual"], april["naive"]) == (peaks["2024-04-01"], peaks["2023-04-01"])
    assert april["p50"] == pytest.approx(april["actual"], rel=0.05)


def test_accuracy_is_the_mean_absolute_percentage_error_by_horizon() -> None:
    results = pd.DataFrame(
        {
            "horizon": [1, 1, 5],
            "actual": [100.0, 100.0, 100.0],
            "p50": [98.0, 104.0, 110.0],
            "naive": [100.0, 100.0, 100.0],
            "naive_corrected": [90.0, 90.0, 90.0],
        }
    )

    table = backtest.accuracy(results)

    assert (table.at["1 month", "p50"], table.at["1 month", "naive_corrected"]) == (3.0, 10.0)
    assert table.at["4-6 months", "p50"] == 10.0
