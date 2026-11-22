"""Monthly energy forecast, one path per temperature scenario."""

from collections.abc import Iterable

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


def paths(
    model: DailyModel,
    history: pd.DataFrame,
    weather: pd.DataFrame,
    years: Iterable[int],
    months: int = 12,
) -> pd.DataFrame:
    """Monthly energy in TWh over the `months` months after `history`, one column per weather year.

    `history` is the frame the model was fitted on. It must end on the last day of a month, so
    that the forecast covers whole months.
    """
    end = pd.DatetimeIndex(history.index)[-1]
    if not end.is_month_end:
        raise ValueError(f"the history must end on the last day of a month, not on {end.date()}")
    start = end + pd.Timedelta(days=1)
    dates = pd.date_range(start, start + pd.DateOffset(months=months), freq="D", inclusive="left")
    temperatures = climate.members(history, weather, dates, years)
    smoothed = climate.smooth(
        temperatures, model.spec.smoothing, history["temperature_smooth"].iloc[-1]
    )
    calendar = calendar_features(dates)
    energy = {}
    for year, temperature_smooth in smoothed.items():
        future = calendar.assign(temperature_smooth=temperature_smooth)
        daily = model.results.forecast(len(dates), exog=exog(model, future))
        energy[year] = monthly_energy(pd.Series(daily.to_numpy(), index=dates))
    return pd.DataFrame(energy)
