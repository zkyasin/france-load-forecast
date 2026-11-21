import numpy as np
import pandas as pd
import pytest

from france_load_forecast import correction, model


def test_no_correction_at_reference_temperature(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame
) -> None:
    at_reference = synthetic_frame.assign(temperature_smooth=synthetic_frame["reference_smooth"])

    corrected = correction.corrected_load(synthetic_model, at_reference)

    np.testing.assert_allclose(corrected, at_reference["load_gw"])


def test_colder_days_are_corrected_downwards(
    synthetic_model: model.DailyModel, synthetic_frame: pd.DataFrame
) -> None:
    corrected = correction.corrected_load(synthetic_model, synthetic_frame)
    colder = synthetic_frame["temperature_smooth"] < synthetic_frame["reference_smooth"] - 2
    winter = pd.DatetimeIndex(synthetic_frame.index).month.isin([12, 1, 2])

    assert (corrected[colder & winter] < synthetic_frame["load_gw"][colder & winter]).all()


@pytest.mark.parametrize(("month", "hours"), [("2026-03", 743), ("2026-10", 745), ("2026-07", 744)])
def test_monthly_energy_counts_clock_change_hours(month: str, hours: int) -> None:
    days = pd.date_range(f"{month}-01", periods=pd.Period(month).days_in_month, freq="D")

    energy = correction.monthly_energy(pd.Series(50.0, index=days))

    assert energy.iloc[0] == pytest.approx(50 * hours / 1000)


def test_annual_comparison_keeps_full_years_without_29_february() -> None:
    days = pd.date_range("2024-01-01", "2025-06-30", freq="D")
    load = pd.Series(50.0, index=days)
    without_leap_day = load.drop(pd.Timestamp("2024-02-29"))
    rte = pd.DataFrame(
        {
            "gross": correction.monthly_energy(load),
            "corrected": correction.monthly_energy(without_leap_day),
        }
    )

    annual = correction.annual_comparison(load, load, rte)

    assert annual.index.tolist() == [2024]
    assert annual.at[2024, "corrected"] == pytest.approx(50 * 365 * 24 / 1000)
    assert annual.at[2024, "gross_gap_pct"] == pytest.approx(0)
    assert annual.at[2024, "corrected_gap_pct"] == pytest.approx(0)
