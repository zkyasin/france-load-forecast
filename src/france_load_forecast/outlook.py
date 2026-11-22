"""The forecast as published: the current month and the 11 after, with a calibrated band.

The model stops on the last day with a temperature. The days measured since replace the forecast,
so the current month adds the days measured so far to the forecast of the remaining days.
"""

import pandas as pd

from france_load_forecast import conformal, correction, forecast
from france_load_forecast.model import DailyModel


def current_month(history: pd.DataFrame, observed: pd.Series) -> pd.Timestamp:
    """First day of the month after the last measured day."""
    last = observed.index[-1] if not observed.empty else history.index[-1]
    return (pd.Timestamp(last) + pd.Timedelta(days=1)).to_period("M").to_timestamp()


def table(
    model: DailyModel, history: pd.DataFrame, observed: pd.Series, past_forecasts: pd.DataFrame
) -> pd.DataFrame:
    """P10, P50 and P90 in TWh from the month after `history` to the 11th month after the current
    one, with the energy measured so far and the horizon of each month.

    `observed` is the daily load measured after `history`, and `past_forecasts` the backtest
    results the band is calibrated on.
    """
    start = pd.Timestamp(history.index[-1]) + pd.Timedelta(days=1)
    current = current_month(history, observed)
    months = 12 + (current.year - start.year) * 12 + current.month - start.month
    years = forecast.complete_years(pd.DatetimeIndex(history.index))
    p50 = forecast.paths(model, history, history, years, months, observed).median(axis=1)
    measured = correction.monthly_energy(observed).reindex(p50.index, fill_value=0.0)
    # Horizons count from the last day the model knows; the backtest stops at 12 months.
    horizon = pd.Series(range(1, months + 1), index=p50.index)
    quantiles = conformal.error_quantiles(past_forecasts, known_before=start)
    # The band only covers the days still to come.
    band = conformal.band(p50 - measured, horizon.clip(upper=12), quantiles).add(measured, axis=0)
    return band.assign(p50=p50, measured=measured, horizon=horizon)[
        ["p10", "p50", "p90", "measured", "horizon"]
    ]
