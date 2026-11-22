"""Monthly energy forecast, one path per temperature scenario."""

from collections.abc import Iterable

import numpy as np
import pandas as pd

from france_load_forecast import climate
from france_load_forecast.calendar import calendar_features
from france_load_forecast.correction import monthly_energy
from france_load_forecast.model import DailyModel, exog


def complete_years(dates: pd.DatetimeIndex) -> list[int]:
    """Calendar years with every day present."""
    years = sorted(set(dates.year.tolist()))
    return [
        year for year in years if pd.date_range(f"{year}-01-01", f"{year}-12-31").isin(dates).all()
    ]


def scenarios(
    history: pd.DataFrame,
    weather: pd.DataFrame,
    years: Iterable[int],
    dates: pd.DatetimeIndex,
    smoothing: float,
) -> dict[int, pd.DataFrame]:
    """Calendar features and smoothed temperature on `dates`, the days right after `history`, under
    the weather of each of `years`."""
    years = list(years)
    temperatures = climate.members(history, weather, dates, years)
    smoothed = climate.smooth(temperatures, smoothing, history["temperature_smooth"].iloc[-1])
    calendar = calendar_features(dates)
    return {year: calendar.assign(temperature_smooth=smoothed[year]) for year in years}


def paths(
    model: DailyModel,
    history: pd.DataFrame,
    weather: pd.DataFrame,
    years: Iterable[int],
    months: int = 12,
    observed: pd.Series | None = None,
) -> pd.DataFrame:
    """Monthly energy in TWh over the `months` months after `history`, one column per weather year.

    `history` is the frame the model was fitted on. It must end on the last day of a month, so
    that the forecast covers whole months. The daily load in `observed`, measured after `history`
    but not usable by the model yet, replaces the forecast on its days.
    """
    end = pd.DatetimeIndex(history.index)[-1]
    if not end.is_month_end:
        raise ValueError(f"the history must end on the last day of a month, not on {end.date()}")
    start = end + pd.Timedelta(days=1)
    dates = pd.date_range(start, start + pd.DateOffset(months=months), freq="D", inclusive="left")
    known = pd.Series(np.nan, index=dates) if observed is None else observed.reindex(dates)
    energy = {}
    for year, future in scenarios(history, weather, years, dates, model.spec.smoothing).items():
        daily = model.results.forecast(len(dates), exog=exog(model, future))
        energy[year] = monthly_energy(known.fillna(pd.Series(daily.to_numpy(), index=dates)))
    return pd.DataFrame(energy)
