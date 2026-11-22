"""Temperature scenarios: the weather of past years replayed on the reference climate."""

from collections.abc import Iterable

import pandas as pd


def _calendar_days(dates: pd.DatetimeIndex) -> pd.Index:
    return dates.strftime("%m-%d")


def _by_calendar_day(daily: pd.Series) -> pd.Series:
    """Last value of a daily series for each calendar day; 29 February falls back to 28 February."""
    by_day = daily.groupby(_calendar_days(pd.DatetimeIndex(daily.index))).last()
    if "02-29" not in by_day.index or pd.isna(by_day["02-29"]):
        by_day["02-29"] = by_day["02-28"]
    return by_day


def members(
    history: pd.DataFrame, weather: pd.DataFrame, dates: pd.DatetimeIndex, years: Iterable[int]
) -> pd.DataFrame:
    """Temperature on `dates` under the weather of each of `years`, one column per year.

    A member is the reference temperature of each calendar day, taken from the latest year of
    `history`, plus the anomaly to the reference observed on that calendar day in a past year of
    `weather`. Both frames hold daily `temperature_c` and `reference_c`.
    """
    reference = _by_calendar_day(history["reference_c"])
    anomaly = weather["temperature_c"] - weather["reference_c"]
    days = _calendar_days(dates)
    columns = {}
    for year in years:
        in_year = anomaly[pd.DatetimeIndex(anomaly.index).year == year]
        columns[year] = (reference + _by_calendar_day(in_year)).reindex(days).to_numpy()
    return pd.DataFrame(columns, index=dates)


def smooth(temperature: pd.DataFrame, alpha: float, start: float) -> pd.DataFrame:
    """Exponential smoothing of each column, continued from `start`, the smoothed temperature of
    the day before the first row."""
    day_before = pd.DatetimeIndex(temperature.index)[0] - pd.Timedelta(days=1)
    seed = pd.DataFrame(start, index=[day_before], columns=temperature.columns)
    seeded = pd.concat([seed, temperature])
    return seeded.ewm(alpha=alpha, adjust=False).mean().iloc[1:]
