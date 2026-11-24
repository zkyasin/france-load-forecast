"""Monthly energy or peak forecast, one path per temperature scenario."""

from collections.abc import Iterable

import numpy as np
import pandas as pd

from france_load_forecast import climate
from france_load_forecast.calendar import calendar_features
from france_load_forecast.correction import monthly_energy
from france_load_forecast.model import DailyModel, exog


def monthly_peak(daily_gw: pd.Series) -> pd.Series:
    """Highest daily peak of each month, in GW."""
    return daily_gw.resample("MS").max()


# How the days of a month add up, for each target of the model: energy in TWh for the mean load,
# the highest day in GW for the peak.
MONTHLY = {"load_gw": monthly_energy, "peak_gw": monthly_peak}


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
    """Calendar features, temperature and smoothed temperature on `dates`, the days right after
    `history`, under the weather of each of `years`."""
    years = list(years)
    temperatures = climate.members(history, weather, dates, years)
    smoothed = climate.smooth(temperatures, smoothing, history["temperature_smooth"].iloc[-1])
    calendar = calendar_features(dates)
    return {
        year: calendar.assign(temperature_c=temperatures[year], temperature_smooth=smoothed[year])
        for year in years
    }


def _horizon(history: pd.DataFrame, months: int) -> pd.DatetimeIndex:
    """The days of the `months` months after `history`, which must end on the last day of a
    month so that the forecast covers whole months."""
    end = pd.DatetimeIndex(history.index)[-1]
    if not end.is_month_end:
        raise ValueError(f"the history must end on the last day of a month, not on {end.date()}")
    start = end + pd.Timedelta(days=1)
    return pd.date_range(start, start + pd.DateOffset(months=months), freq="D", inclusive="left")


def normal(model: DailyModel, history: pd.DataFrame, months: int) -> pd.Series:
    """Monthly energy in TWh, or peak in GW, over the `months` months after `history`, at the
    reference temperature."""
    dates = _horizon(history, months)
    temperature = climate.normal(history, dates).to_frame("normal")
    start = history["temperature_smooth"].iloc[-1]
    smoothed = climate.smooth(temperature, model.spec.smoothing, start)["normal"]
    future = calendar_features(dates).assign(temperature_smooth=smoothed)
    daily = model.results.forecast(len(dates), exog=exog(model, future))
    return MONTHLY[model.spec.target](pd.Series(daily.to_numpy(), index=dates))


def paths(
    model: DailyModel,
    history: pd.DataFrame,
    weather: pd.DataFrame,
    years: Iterable[int],
    months: int = 12,
    observed: pd.Series | None = None,
) -> pd.DataFrame:
    """Monthly energy in TWh, or peak in GW, over the `months` months after `history`, one column
    per weather year.

    `history` is the frame the model was fitted on. It must end on the last day of a month, so
    that the forecast covers whole months. The daily values in `observed`, measured after `history`
    but not usable by the model yet, replace the forecast on their days.
    """
    dates = _horizon(history, months)
    known = pd.Series(np.nan, index=dates) if observed is None else observed.reindex(dates)
    monthly = {}
    for year, future in scenarios(history, weather, years, dates, model.spec.smoothing).items():
        daily = model.results.forecast(len(dates), exog=exog(model, future))
        monthly[year] = MONTHLY[model.spec.target](
            known.fillna(pd.Series(daily.to_numpy(), index=dates))
        )
    return pd.DataFrame(monthly)
