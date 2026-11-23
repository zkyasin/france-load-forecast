"""The forecast as published: the current month and the 11 after, with a calibrated band.

The model stops on the last day with a temperature. The days measured since replace the forecast,
so the energy of the current month adds the days measured so far to the forecast of the remaining
days, and its peak is the highest of both.
"""

import pandas as pd

from france_load_forecast import conformal, forecast
from france_load_forecast.model import DailyModel


def current_month(history: pd.DataFrame, observed: pd.Series) -> pd.Timestamp:
    """First day of the month after the last measured day."""
    last = observed.index[-1] if not observed.empty else history.index[-1]
    return (pd.Timestamp(last) + pd.Timedelta(days=1)).to_period("M").to_timestamp()


def table(
    model: DailyModel, history: pd.DataFrame, observed: pd.Series, past_forecasts: pd.DataFrame
) -> pd.DataFrame:
    """P10, P50 and P90 from the month after `history` to the 11th month after the current one,
    with what is measured so far and the horizon of each month: energy in TWh, or peak in GW for
    the peak model.

    `observed` holds the daily values measured after `history`, and `past_forecasts` the backtest
    results the band is calibrated on.
    """
    start = pd.Timestamp(history.index[-1]) + pd.Timedelta(days=1)
    current = current_month(history, observed)
    months = 12 + (current.year - start.year) * 12 + current.month - start.month
    years = forecast.complete_years(pd.DatetimeIndex(history.index))
    # The forecast of the days still to come: the days measured so far count as zero.
    rest = forecast.paths(model, history, history, years, months, observed * 0.0).median(axis=1)
    measured = forecast.MONTHLY[model.spec.target](observed).reindex(rest.index, fill_value=0.0)
    # Horizons count from the last day the model knows; the backtest stops at 12 months.
    horizon = pd.Series(range(1, months + 1), index=rest.index)
    quantiles = conformal.error_quantiles(past_forecasts, known_before=start)
    band = conformal.band(rest, horizon.clip(upper=12), quantiles).assign(p50=rest)
    # A month's energy adds the days measured so far; its peak is at least the highest of them.
    if model.spec.target == "peak_gw":
        band = band.clip(lower=measured, axis=0)
    else:
        band = band.add(measured, axis=0)
    return band.assign(measured=measured, horizon=horizon)[
        ["p10", "p50", "p90", "measured", "horizon"]
    ]
