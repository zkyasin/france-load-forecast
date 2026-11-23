"""Monthly energy gaps split into the terms of the daily model, in TWh.

Two gaps are explained for each month.

Against the forecast made at the start of the month (P50, one month ahead), with the model of the
forecast. Each component contributes the effect of the gap between its actual inputs and those
the forecast assumed, valued with the coefficients of the forecast: the actual weather against the
weather paths for the climate, nothing for the calendar, which was known. `structural` is the gap
between the level and seasonal states estimated with all the days known today and those projected
at the origin. `residual` holds the rest: deviations that last a few days and the update of the
coefficients by the days after the origin. P50 is the median across weather paths, so the weather
the forecast assumed is the past weather of its median path.

Against the same month a year earlier, with a model covering both months: the change in the
effect of each component, in the structural states and in the residual. 29 February only exists
in leap years, so its whole load counts as calendar effect.

In both views the terms add up to the gap.
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from france_load_forecast import backtest, correction, forecast
from france_load_forecast.model import DailyModel, ModelSpec, contributions, exog, extend


def recent_months(history: pd.DataFrame, count: int) -> pd.DatetimeIndex:
    """First days of the last `count` months that `history` covers in full."""
    ends = pd.date_range(end=pd.DatetimeIndex(history.index)[-1], periods=count, freq="ME")
    return ends.to_period("M").to_timestamp()


def _monthly(daily: pd.DataFrame) -> pd.DataFrame:
    return daily.apply(correction.monthly_energy)


def _gaps(actual: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """Both energies, their gap and the gap of each term, from the terms of each month."""
    terms = actual - reference
    totals = pd.DataFrame(
        {"actual": actual.sum(axis=1), "reference": reference.sum(axis=1), "gap": terms.sum(axis=1)}
    )
    return totals.join(terms)


def _projection(model: DailyModel, future: pd.DataFrame) -> pd.DataFrame:
    """Structural states and autoregressive term forecast over the days of `future`, in GW.

    The days are filtered as missing observations, so their smoothed states are the forecasts.
    These terms do not depend on the weather.
    """
    unknown = pd.Series(np.nan, index=future.index, name="load_gw")
    projected = replace(model, results=model.results.append(unknown, exog=exog(model, future)))
    states = pd.DataFrame(
        {"structural": projected.level + projected.seasonal, "residual": projected.ar}
    )
    return states.loc[future.index]


def _median_paths(paths: pd.DataFrame) -> pd.Index:
    """Labels of the median path by energy, or of the two middle ones: the mean of their terms
    adds up to P50."""
    ranked = paths.sum(axis=1).sort_values().index
    count = len(ranked)
    return ranked[(count - 1) // 2 : count // 2 + 1]


def against_forecast(
    history: pd.DataFrame, spec: ModelSpec, months: pd.DatetimeIndex
) -> tuple[pd.DataFrame, pd.Series]:
    """Gap between the energy of each month and the forecast made at its start, split into terms,
    and the mean temperature of the weather that the forecast assumed, in °C.

    The forecast is the one of the backtest, one month ahead.
    """
    complete_years = forecast.complete_years(pd.DatetimeIndex(history.index))
    actual_terms, planned_terms, planned_temperature = {}, {}, {}
    for origin, at_origin in backtest.models_at(history, spec, months):
        days = pd.date_range(origin, periods=origin.days_in_month, freq="D")
        past = history[history.index < origin]
        years = backtest.weather_years(complete_years, origin)
        scenarios = forecast.scenarios(past, history, years, days, spec.smoothing)
        states = _projection(at_origin, scenarios[years[0]])
        paths = pd.DataFrame.from_dict(
            {
                year: _monthly(contributions(at_origin, future).join(states)).iloc[0]
                for year, future in scenarios.items()
            },
            orient="index",
        )
        median = _median_paths(paths)
        planned_terms[origin] = paths.loc[median].mean()
        planned_temperature[origin] = np.mean(
            [scenarios[year]["temperature_c"].mean() for year in median]
        )

        observed = history.loc[days]
        realized = extend(at_origin, history)
        actual = contributions(at_origin, observed)
        actual["structural"] = (realized.level + realized.seasonal)[days]
        actual["residual"] = observed["load_gw"] - actual.sum(axis=1)
        actual_terms[origin] = _monthly(actual).iloc[0]
    gaps = _gaps(
        pd.DataFrame.from_dict(actual_terms, orient="index"),
        pd.DataFrame.from_dict(planned_terms, orient="index"),
    )
    return gaps, pd.Series(planned_temperature, name="temperature_c")


def against_year_before(
    model: DailyModel, history: pd.DataFrame, months: pd.DatetimeIndex
) -> pd.DataFrame:
    """Gap between the energy of each month and that of the same month a year earlier, split into
    terms. The model must cover both months."""
    year_before = months - pd.DateOffset(years=1)
    needed = pd.date_range(year_before.min(), months.max() + pd.offsets.MonthEnd(), freq="D")
    if not needed.isin(model.level.index).all():
        raise ValueError("the model must cover each month and the same month a year earlier")

    observed = history.loc[model.level.index]
    daily = contributions(model, observed)
    daily["structural"] = model.level + model.seasonal
    daily["residual"] = observed["load_gw"] - daily.sum(axis=1)
    dates = pd.DatetimeIndex(daily.index)
    leap_day = (dates.month == 2) & (dates.day == 29)
    daily.loc[leap_day] = 0.0
    daily.loc[leap_day, "calendar"] = observed.loc[leap_day, "load_gw"]
    energy = _monthly(daily)
    return _gaps(energy.loc[months], energy.loc[year_before].set_axis(months))
