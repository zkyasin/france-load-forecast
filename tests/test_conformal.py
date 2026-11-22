import pandas as pd
import pytest

from france_load_forecast import conformal


def past_forecasts(actual: list[float]) -> pd.DataFrame:
    """One-month-ahead forecasts of 100 for consecutive months from January 2020."""
    months = pd.date_range("2020-01-01", periods=len(actual), freq="MS")
    return pd.DataFrame(
        {"origin": months, "month": months, "horizon": 1, "p50": 100.0, "actual": actual}
    )


def test_quantiles_only_use_months_known_before() -> None:
    results = past_forecasts([95.0, 100.0, 105.0, 200.0])

    quantiles = conformal.error_quantiles(results, known_before=pd.Timestamp("2020-04-01"))

    assert quantiles.at["1 month", 0.1] == pytest.approx(-0.04)
    assert quantiles.at["1 month", 0.9] == pytest.approx(0.04)


def test_band_scales_p50_by_the_error_quantiles() -> None:
    quantiles = pd.DataFrame({0.1: [-0.05], 0.9: [0.03]}, index=["4-6 months"])

    bounds = conformal.band(pd.Series([100.0]), pd.Series([5]), quantiles)

    assert bounds.iloc[0].tolist() == pytest.approx([95.0, 103.0])


def test_coverage_is_full_when_forecasts_are_exact() -> None:
    results = past_forecasts([100.0] * 30)

    coverage = conformal.online_coverage(results, first_origin=pd.Timestamp("2021-01-01"))

    assert coverage["all months"] == 1.0
