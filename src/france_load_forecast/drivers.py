"""What changed climate-corrected consumption between a base year and the last twelve months.

The change splits into three parts:
- large industry, the energy RTE's grid delivers to large industrial sites. Its change splits
  into activity, the production index of its branches weighted by their consumption in the base
  year, and intensity, the energy per unit produced, by the logarithmic mean Divisia index: both
  add up to the change;
- electric cars, the stock of rechargeable cars times the energy of a car, set so that a
  reference year gives RTE's estimate;
- the rest: households, businesses and services, and the other sites on RTE's grid.

Every year leaves out 29 February, as RTE's corrected series does.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from france_load_forecast import correction

# Days of a year without 29 February.
YEAR_DAYS = 365


@dataclass(frozen=True)
class CarsReference:
    """RTE's estimate of the energy of electric cars over a year, in TWh."""

    year: int
    twh: float
    source: str


@dataclass(frozen=True)
class DriversSpec:
    base_year: int
    # INSEE series standing for each branch, and the sectors of RTE's industry series it covers.
    branches: dict[str, list[str]]
    # INSEE series for the industry RTE names no sector for, and the sectors left out.
    other_branch: str
    left_out: list[str]
    cars: CarsReference


def load_spec(path: Path) -> DriversSpec:
    with path.open("rb") as file:
        config = tomllib.load(file)
    return DriversSpec(
        base_year=config["base_year"],
        branches=config["branches"],
        other_branch=config["industry"]["other_branch"],
        left_out=config["industry"]["left_out"],
        cars=CarsReference(**config["cars"]),
    )


@dataclass(frozen=True)
class Inputs:
    """The data of the warehouse the drivers come from."""

    # Energy drawn from RTE's grid by large industry each day, in MWh.
    industry: pd.Series
    # RTE's monthly industry consumption, in GWh, one column per sector.
    sectors: pd.DataFrame
    # Monthly INSEE series, one column per series.
    insee: pd.DataFrame
    # Stock of rechargeable cars at each date given.
    cars: pd.Series


def _dated(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    frame = frame.set_index(column)
    frame.index = pd.DatetimeIndex(frame.index)
    return frame


def read(con: duckdb.DuckDBPyConnection) -> Inputs:
    industry = con.execute(
        "SELECT date, sum(energy_mwh) AS mwh FROM industry_daily GROUP BY date ORDER BY date"
    ).df()
    insee = con.execute(
        "PIVOT insee_monthly ON series USING first(value) GROUP BY month ORDER BY month"
    ).df()
    return Inputs(
        industry=_dated(industry, "date")["mwh"],
        sectors=_dated(con.execute("SELECT * FROM industry_sectors ORDER BY month").df(), "month"),
        insee=_dated(insee, "month"),
        cars=_dated(con.execute("SELECT * FROM car_stock ORDER BY date").df(), "date")["cars"],
    )


def without_29_february(daily: pd.Series) -> pd.Series:
    dates = pd.DatetimeIndex(daily.index)
    return daily[~((dates.month == 2) & (dates.day == 29))]


def _month_days(months: pd.DatetimeIndex) -> pd.Series:
    """Days of each month, 28 for February."""
    days = np.where(months.month == 2, 28, months.days_in_month)
    return pd.Series(days, index=months)


def whole_months(daily: pd.Series) -> pd.DatetimeIndex:
    """The months of which `daily` has every day but 29 February."""
    days = without_29_february(daily)
    counts = days.groupby(pd.DatetimeIndex(days.index).to_period("M").to_timestamp()).size()
    months = pd.DatetimeIndex(counts.index)
    return pd.DatetimeIndex(months[counts.to_numpy() == _month_days(months).to_numpy()])


def monthly_sum(daily: pd.Series) -> pd.Series:
    """Sum of each whole month of `daily`, 29 February left out."""
    days = without_29_february(daily)
    sums = days.groupby(pd.DatetimeIndex(days.index).to_period("M").to_timestamp()).sum()
    return sums.loc[whole_months(daily)]


def branch_weights(sectors: pd.DataFrame, spec: DriversSpec) -> pd.Series:
    """Consumption of each branch of large industry in the base year, in TWh, by INSEE series."""
    year = sectors[pd.DatetimeIndex(sectors.index).year == spec.base_year]
    if len(year) != 12:
        raise ValueError(f"RTE's industry series lacks months of {spec.base_year}")
    totals = year.sum()
    named = {series: totals[columns].sum() for series, columns in spec.branches.items()}
    covered = [column for columns in spec.branches.values() for column in columns]
    other = totals["industry_gwh"] - totals[covered + spec.left_out].sum()
    return pd.Series(named | {spec.other_branch: other}) / 1000


def activity(insee: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Production index of large industry: the index of each branch weighted by its consumption
    in the base year. A month without every branch has none."""
    weighted = insee[weights.index].mul(weights).sum(axis=1, min_count=len(weights))
    return weighted / weights.sum()


def car_stock(cars: pd.Series, months: pd.DatetimeIndex) -> pd.Series:
    """Stock of rechargeable cars in the middle of each month, in millions. It is interpolated on
    its logarithm between the dates given, and extended before the first and after the last at
    the growth of the first and the last year given."""
    days = pd.DatetimeIndex(cars.index)
    given = (days - days[0]).days.to_numpy(dtype=float)
    if given[-1] < YEAR_DAYS:
        raise ValueError("the car stock covers less than a year")
    log_stock = np.log(cars.to_numpy(dtype=float))
    middle = (months + pd.Timedelta(days=14) - days[0]).days.to_numpy(dtype=float)
    first_growth = (np.interp(YEAR_DAYS, given, log_stock) - log_stock[0]) / YEAR_DAYS
    last_growth = (log_stock[-1] - np.interp(given[-1] - YEAR_DAYS, given, log_stock)) / YEAR_DAYS
    values = np.interp(middle, given, log_stock)
    values = np.where(middle < 0, log_stock[0] + first_growth * middle, values)
    values = np.where(
        middle > given[-1], log_stock[-1] + last_growth * (middle - given[-1]), values
    )
    return pd.Series(np.exp(values) / 1e6, index=months)


def car_energy(stock: pd.Series, reference: CarsReference) -> tuple[pd.Series, float]:
    """Monthly energy of electric cars in TWh, from their stock in millions, and the energy of a
    car over a year in MWh, set so that the reference year gives RTE's estimate."""
    months = pd.DatetimeIndex(stock.index)
    car_years = stock * _month_days(months) / YEAR_DAYS
    in_reference = car_years[months.year == reference.year]
    if len(in_reference) != 12:
        raise ValueError(f"the car stock does not cover {reference.year}")
    # TWh per million car-years is MWh per car-year.
    mwh_per_car = reference.twh / float(in_reference.sum())
    return car_years * mwh_per_car, mwh_per_car


@dataclass(frozen=True)
class Drivers:
    # By month: energies in TWh of climate-corrected consumption, large industry, electric cars
    # and the rest; stock of rechargeable cars in millions; production index of large industry
    # and real price of electricity, the price index of electricity over that of all items.
    monthly: pd.DataFrame
    base_year: int
    # `period` of the base year and of the last twelve months.
    base: pd.Series
    now: pd.Series
    first_month: pd.Timestamp
    last_month: pd.Timestamp
    mwh_per_car: float


def compute(corrected: pd.Series, inputs: Inputs, spec: DriversSpec) -> Drivers:
    """The drivers of the change of `corrected`, the climate-corrected daily load in GW, between
    the base year and the last twelve months that every source covers."""
    consumption = correction.monthly_energy(without_29_february(corrected))
    monthly = pd.DataFrame(
        {
            "consumption": consumption.loc[whole_months(corrected)],
            "industry": monthly_sum(inputs.industry) / 1e6,
            "activity": activity(inputs.insee, branch_weights(inputs.sectors, spec)),
            "real_price": inputs.insee["prices_electricity"] / inputs.insee["prices_all"],
        }
    ).dropna()
    months = pd.DatetimeIndex(monthly.index)
    reference_year = pd.date_range(f"{spec.cars.year}-01-01", periods=12, freq="MS")
    stock = car_stock(inputs.cars, months.union(reference_year))
    cars, mwh_per_car = car_energy(stock, spec.cars)
    monthly["cars"] = stock.loc[months]
    monthly["electric_cars"] = cars.loc[months]
    monthly["rest"] = monthly["consumption"] - monthly["industry"] - monthly["electric_cars"]

    if (months.year == spec.base_year).sum() != 12:
        raise ValueError(f"the sources do not all cover {spec.base_year}")
    recent = pd.date_range(end=months[-1], periods=12, freq="MS")
    if not recent.isin(months).all():
        raise ValueError("the sources do not all cover the last twelve months")
    return Drivers(
        monthly=monthly,
        base_year=spec.base_year,
        base=period(monthly, months[months.year == spec.base_year], spec.base_year),
        now=period(monthly, recent, spec.base_year),
        first_month=recent[0],
        last_month=recent[-1],
        mwh_per_car=mwh_per_car,
    )


def period(monthly: pd.DataFrame, months: pd.DatetimeIndex, base_year: int) -> pd.Series:
    """Energies summed over `months`, the car stock averaged, and the production index and the
    real price of electricity averaged and set to 100 in the base year."""
    part = monthly.loc[months]
    base = monthly[pd.DatetimeIndex(monthly.index).year == base_year]
    sums = part[["consumption", "industry", "electric_cars", "rest"]].sum()
    means = part[["cars", "activity", "real_price"]].mean()
    for index in ("activity", "real_price"):
        means[index] = 100 * means[index] / base[index].mean()
    combined: pd.Series = pd.concat([sums, means])
    return combined


def years(drivers: Drivers) -> pd.DataFrame:
    """`period` of each calendar year that the monthly table covers in full, by year."""
    months = pd.DatetimeIndex(drivers.monthly.index)
    whole = sorted(year for year in set(months.year) if (months.year == year).sum() == 12)
    return pd.DataFrame(
        {
            year: period(drivers.monthly, months[months.year == year], drivers.base_year)
            for year in whole
        }
    ).T


def contributions(base: pd.Series, now: pd.Series) -> pd.Series:
    """The change of consumption from `base` to `now` in TWh, by part. The change of large
    industry splits into activity and intensity by the logarithmic mean Divisia index."""
    change = now["industry"] - base["industry"]
    ratio = now["industry"] / base["industry"]
    # The logarithmic mean of both energies, or either when they are equal.
    weight = change / np.log(ratio) if ratio != 1 else base["industry"]
    activity_ratio = now["activity"] / base["activity"]
    return pd.Series(
        {
            "industry_activity": weight * np.log(activity_ratio),
            "industry_intensity": weight * np.log(ratio / activity_ratio),
            "electric_cars": now["electric_cars"] - base["electric_cars"],
            "rest": now["rest"] - base["rest"],
        }
    )
