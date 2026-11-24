import numpy as np
import pandas as pd
import pytest

from france_load_forecast import conformal, model, outlook


def test_current_month_adds_the_measured_days(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame, past_forecasts: pd.DataFrame
) -> None:
    observed = pd.Series(60.0, index=pd.date_range("2025-01-01", "2025-01-10"))

    table = outlook.table(
        synthetic_model, synthetic_frame, synthetic_frame["temperature_c"], observed, past_forecasts
    )

    january = table.iloc[0]
    assert table.index[0] == pd.Timestamp("2025-01-01")
    assert len(table) == 12
    assert january["measured"] == pytest.approx(60 * 10 * 24 / 1000)
    # The band only covers the 21 days still to come.
    upper = conformal.error_quantiles(past_forecasts, pd.Timestamp("2025-01-01")).at["1 month", 0.9]
    remaining = january["p50"] - january["measured"]
    assert january["p90"] - january["p50"] == pytest.approx(remaining * upper)


def test_months_measured_in_full_have_no_band(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame, past_forecasts: pd.DataFrame
) -> None:
    observed = pd.Series(60.0, index=pd.date_range("2025-01-01", "2025-02-05"))

    table = outlook.table(
        synthetic_model, synthetic_frame, synthetic_frame["temperature_c"], observed, past_forecasts
    )

    assert outlook.current_month(synthetic_frame, observed) == pd.Timestamp("2025-02-01")
    assert table["horizon"].tolist() == list(range(1, 14))
    np.testing.assert_allclose(table.iloc[0][["p10", "p50", "p90"]], 60 * 31 * 24 / 1000)
    assert table["p10"].notna().all()


def test_the_peak_of_a_month_is_at_least_its_highest_measured_day(
    synthetic_peak_model: model.DailyModel,
    synthetic_frame: pd.DataFrame,
    past_forecasts: pd.DataFrame,
) -> None:
    observed = pd.Series(70.0, index=pd.date_range("2025-01-01", "2025-01-10"))
    observed["2025-01-05"] = 100.0

    table = outlook.table(
        synthetic_peak_model,
        synthetic_frame,
        synthetic_frame["temperature_c"],
        observed,
        past_forecasts,
    )

    january, february = table.iloc[0], table.iloc[1]
    assert january["measured"] == 100.0
    np.testing.assert_allclose(january[["p10", "p50", "p90"]], 100.0)
    assert february["measured"] == 0.0
    assert february["p10"] < february["p50"] < february["p90"] < 100.0
