"""P10-P90 band calibrated on the backtest errors (split conformal prediction).

The band applies to P50 the 10th and 90th percentiles of past relative errors, actual / P50 - 1,
by horizon bucket. Only errors on months already known are used, so the band at an origin never
looks ahead.
"""

import numpy as np
import pandas as pd

from france_load_forecast.backtest import HORIZON_BUCKETS

QUANTILES = (0.1, 0.9)


def horizon_bucket(horizon: pd.Series) -> pd.Series:
    labels = pd.Series(index=horizon.index, dtype="object")
    for bucket, (low, high) in HORIZON_BUCKETS.items():
        labels[horizon.between(low, high)] = bucket
    return labels


def error_quantiles(results: pd.DataFrame, known_before: pd.Timestamp) -> pd.DataFrame:
    """10th and 90th percentiles of relative errors by horizon bucket, over the forecasts whose
    month ended before `known_before`."""
    known = results[results["actual"].notna() & (results["month"] < known_before)]
    errors = known["actual"] / known["p50"] - 1
    by_bucket = errors.groupby(horizon_bucket(known["horizon"]))
    return by_bucket.quantile(np.array(QUANTILES)).unstack()


def band(p50: pd.Series, horizon: pd.Series, quantiles: pd.DataFrame) -> pd.DataFrame:
    """P10 and P90 around each P50."""
    bucket = horizon_bucket(horizon)
    return pd.DataFrame(
        {
            "p10": p50 * (1 + bucket.map(quantiles[QUANTILES[0]]).astype(float)),
            "p90": p50 * (1 + bucket.map(quantiles[QUANTILES[1]]).astype(float)),
        }
    )


def online_coverage(results: pd.DataFrame, first_origin: pd.Timestamp) -> pd.Series:
    """Share of actual energies inside the band, each origin's band being calibrated on the errors
    known at that origin. Reported for all months, winter months and summer months."""
    inside = []
    origins = pd.DatetimeIndex(results["origin"].unique())
    for origin in origins[origins >= first_origin]:
        known = results[(results["origin"] == origin) & results["actual"].notna()]
        quantiles = error_quantiles(results, known_before=origin)
        bounds = band(known["p50"], known["horizon"], quantiles)
        inside.append(known["actual"].between(bounds["p10"], bounds["p90"]).rename(None))
    scored = pd.concat(inside)
    month = pd.DatetimeIndex(results.loc[scored.index, "month"]).month
    return pd.Series(
        {
            "all months": scored.mean(),
            "December to February": scored[month.isin([12, 1, 2])].mean(),
            "June to August": scored[month.isin([6, 7, 8])].mean(),
        }
    )
