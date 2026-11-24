"""Temperature scenarios: the weather of every year since 1950, replayed in today's climate."""

from collections.abc import Iterable
from pathlib import Path

import pandas as pd
from statsmodels.nonparametric.smoothers_lowess import lowess

# Share of the years that the trend of annual mean temperature draws on at each year: about 40 of
# the years since 1950, so that a few warm or cold years do not bend it. With fewer than
# TREND_MIN_YEARS years, there is no trend to draw, and the years are replayed as observed.
TREND_SPAN = 0.5
TREND_MIN_YEARS = 30


def _calendar_days(dates: pd.DatetimeIndex) -> pd.Index:
    return dates.strftime("%m-%d")


def _by_calendar_day(daily: pd.Series) -> pd.Series:
    """Last value of a daily series for each calendar day; 29 February falls back to 28 February."""
    by_day = daily.groupby(_calendar_days(pd.DatetimeIndex(daily.index))).last()
    if "02-29" not in by_day.index or pd.isna(by_day["02-29"]):
        by_day["02-29"] = by_day["02-28"]
    return by_day


def normal(history: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.Series:
    """Reference temperature on `dates`, taken from the latest year of `history`."""
    reference = _by_calendar_day(history["reference_c"])
    return pd.Series(reference.reindex(_calendar_days(dates)).to_numpy(), index=dates)


def read_rebuilt(path: Path) -> pd.Series:
    """The national temperature rebuilt before RTE's series by `flf rebuild-temperature`."""
    frame = pd.read_csv(path, parse_dates=["date"])
    return pd.Series(frame["temperature_c"].to_numpy(), index=pd.DatetimeIndex(frame["date"]))


def since_1950(history: pd.DataFrame, rebuilt: pd.Series) -> pd.Series:
    """Daily national temperature: the rebuilt one before `history`, RTE's from its first day."""
    first = pd.Timestamp(history.index[0])
    weather: pd.Series = pd.concat([rebuilt[rebuilt.index < first], history["temperature_c"]])
    return weather


def moves(history: pd.DataFrame, weather: pd.Series, years: Iterable[int]) -> pd.Series:
    """By how much the temperature of each of `years` moves to today's climate, in °C: the mean
    reference temperature over the last 365 days of `history`, less the trend of the annual mean
    temperature of `weather` in that year, a locally weighted regression over `years`."""
    annual = weather.groupby(pd.DatetimeIndex(weather.index).year).mean().loc[list(years)]
    if len(annual) < TREND_MIN_YEARS:
        return pd.Series(0.0, index=annual.index)
    trend = lowess(annual.to_numpy(), annual.index.to_numpy(), frac=TREND_SPAN, return_sorted=False)
    today = history["reference_c"].iloc[-365:].mean()
    return pd.Series(today - trend, index=annual.index)


def members(
    history: pd.DataFrame, weather: pd.Series, dates: pd.DatetimeIndex, years: Iterable[int]
) -> pd.DataFrame:
    """Temperature on `dates` under the weather of each of `years`, one column per year.

    A member replays the temperature of `weather` on each calendar day of a past year, moved to
    today's climate as `moves` says.
    """
    years = list(years)
    move = moves(history, weather, years)
    days = _calendar_days(dates)
    columns = {}
    for year in years:
        in_year = weather[pd.DatetimeIndex(weather.index).year == year] + move[year]
        columns[year] = _by_calendar_day(in_year).reindex(days).to_numpy()
    return pd.DataFrame(columns, index=dates)


def smooth(temperature: pd.DataFrame, alpha: float, start: float) -> pd.DataFrame:
    """Exponential smoothing of each column, continued from `start`, the smoothed temperature of
    the day before the first row."""
    day_before = pd.DatetimeIndex(temperature.index)[0] - pd.Timedelta(days=1)
    seed = pd.DataFrame(start, index=[day_before], columns=temperature.columns)
    seeded = pd.concat([seed, temperature])
    return seeded.ewm(alpha=alpha, adjust=False).mean().iloc[1:]
