"""Rolling-origin backtest of the monthly forecast.

At each origin, the forecast only uses the days before it: the model is re-estimated on 1 January
of each year, over the preceding `window_years` years, then filtered day by day up to the origin.
Weather paths come from every complete year outside the forecast window, so the target months
never replay their own weather.
"""

from collections.abc import Iterable, Iterator
from itertools import groupby

import pandas as pd

from france_load_forecast import correction, forecast, model

HORIZON_BUCKETS = {
    "1 month": (1, 1),
    "2-3 months": (2, 3),
    "4-6 months": (4, 6),
    "7-12 months": (7, 12),
}


def monthly_origins(history: pd.DataFrame, first: str) -> pd.DatetimeIndex:
    """First day of each month from `first` until the month after the history ends."""
    end = pd.DatetimeIndex(history.index)[-1] + pd.Timedelta(days=1)
    return pd.date_range(first, end, freq="MS")


def models_at(
    history: pd.DataFrame, spec: model.ModelSpec, origins: Iterable[pd.Timestamp]
) -> Iterator[tuple[pd.Timestamp, model.DailyModel]]:
    """The model as it stood at each origin, fitted and filtered on the days before it."""
    for year, group in groupby(origins, key=lambda origin: origin.year):
        fitted = model.fit_recent(history[history.index < pd.Timestamp(f"{year}-01-01")], spec)
        for origin in group:
            yield origin, model.extend(fitted, history[history.index < origin])


def weather_years(complete_years: Iterable[int], origin: pd.Timestamp) -> list[int]:
    """Complete years outside the 12 months from `origin`."""
    window = pd.date_range(origin, periods=12, freq="MS")
    return [year for year in complete_years if year not in set(window.year)]


def run(
    history: pd.DataFrame, spec: model.ModelSpec, origins: Iterable[pd.Timestamp]
) -> pd.DataFrame:
    """One row per origin and forecast month: P50 and spread across weather paths, the actual
    energy, and two naive forecasts (same month a year earlier, raw and climate-corrected)."""
    actual = correction.monthly_energy(history["load_gw"])
    all_years = forecast.complete_years(pd.DatetimeIndex(history.index))
    rows = []
    for origin, at_origin in models_at(history, spec, origins):
        past = history[history.index < origin]
        paths = forecast.paths(at_origin, past, history, weather_years(all_years, origin))
        corrected = correction.monthly_energy(correction.corrected_load(at_origin, past))
        window = pd.date_range(origin, periods=12, freq="MS")
        year_before = window - pd.DateOffset(years=1)
        rows.append(
            pd.DataFrame(
                {
                    "origin": origin,
                    "month": window,
                    "horizon": range(1, 13),
                    "p50": paths.median(axis=1).to_numpy(),
                    "spread": paths.std(axis=1).to_numpy(),
                    "actual": actual.reindex(window).to_numpy(),
                    "naive": actual.reindex(year_before).to_numpy(),
                    "naive_corrected": corrected.reindex(year_before).to_numpy(),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def accuracy(results: pd.DataFrame) -> pd.DataFrame:
    """Mean absolute percentage error by horizon bucket, for P50 and the naive forecasts."""
    scored = results.dropna(subset=["actual"])
    table = {}
    for bucket, (low, high) in HORIZON_BUCKETS.items():
        rows = scored[scored["horizon"].between(low, high)]
        table[bucket] = {
            name: 100 * ((rows[name] - rows["actual"]).abs() / rows["actual"]).mean()
            for name in ("p50", "naive", "naive_corrected")
        }
    return pd.DataFrame(table).T
