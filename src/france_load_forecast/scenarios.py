"""Scenarios for the years ahead: a trajectory of RTE's Bilan prévisionnel 2025 and a winter.

The energy of a year is the model's energy at the reference temperature, grown at the rates of
the trajectory from today's level. A cold or mild winter adds, on January, February and December,
the effect of the observed weather year whose winter months rank about 1 year in 10. The climate
effect does not grow with the trajectory.
"""

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from france_load_forecast import forecast
from france_load_forecast.model import DailyModel

WINTER = (1, 2, 12)


@dataclass(frozen=True)
class Trajectory:
    label: str
    pages: str
    # Energy in TWh by year, in the BP2025 perimeter.
    twh: dict[int, float]


@dataclass(frozen=True)
class ScenarioSpec:
    source: str
    base_year: int
    base_twh: float
    first_year: int
    last_year: int
    trajectories: dict[str, Trajectory]
    # Rank of the cold and mild winters among the observed ones, as a share from the mildest.
    winters: dict[str, float]

    @property
    def years(self) -> list[int]:
        return list(range(self.first_year, self.last_year + 1))


def load_spec(path: Path) -> ScenarioSpec:
    with path.open("rb") as file:
        config = tomllib.load(file)
    trajectories = {
        name: Trajectory(
            label=values["label"],
            pages=values["pages"],
            twh={int(year): twh for year, twh in values["twh"].items()},
        )
        for name, values in config["trajectories"].items()
    }
    return ScenarioSpec(
        source=config["source"],
        base_year=config["base_year"],
        base_twh=config["base_twh"],
        first_year=config["first_year"],
        last_year=config["last_year"],
        trajectories=trajectories,
        winters=config["winters"],
    )


def growth(spec: ScenarioSpec, trajectory: str, year: int) -> float:
    """Growth rate of `trajectory` from the year before `year` to `year`."""
    levels = {spec.base_year: spec.base_twh} | spec.trajectories[trajectory].twh
    years = sorted(levels)
    # The segment that holds `year`, or the last one.
    end = next((y for y in years[1:] if y >= year), years[-1])
    start = years[years.index(end) - 1]
    return float((levels[end] / levels[start]) ** (1 / (end - start)) - 1)


def factor(spec: ScenarioSpec, trajectory: str, year: int, today: int) -> float:
    """Growth of `trajectory` from the year `today` to `year`."""
    return math.prod(1 + growth(spec, trajectory, y) for y in range(today + 1, year + 1))


def winter_year(effects: pd.DataFrame, share: float) -> int:
    """The weather year whose winter needs the energy ranked at `share` from the mildest, from
    the climate effect of each weather year (columns) on the winter months (rows)."""
    ranked = effects.sum().sort_values()
    return int(str(ranked.index[math.ceil(share * len(ranked)) - 1]))


def grid(
    model: DailyModel, history: pd.DataFrame, weather: pd.Series, spec: ScenarioSpec
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monthly energy in TWh of each year, trajectory and winter, and the weather year that each
    cold or mild winter replays.

    `model` is the forecasting model fitted on `history`, and `weather` the daily national
    temperature since 1950. Returns one row per month, year, trajectory and winter, with its
    energy; and one row per year and winter, with its weather year.
    """
    end = pd.Timestamp(history.index[-1])
    months = (spec.last_year - end.year) * 12 + 12 - end.month
    normal = forecast.normal(model, history, months)
    weather_years = forecast.years_before(weather, end + pd.Timedelta(days=1))
    effects = forecast.paths(model, history, weather, weather_years, months).sub(normal, axis=0)
    dates = pd.DatetimeIndex(normal.index)
    in_winter = dates.month.isin(WINTER)
    energies, replayed = [], []
    for year in spec.years:
        in_year = dates.year == year
        winters = {"normal": pd.Series(0.0, index=dates[in_year])}
        for name, share in spec.winters.items():
            weather_year = winter_year(effects[in_year & in_winter], share)
            winters[name] = effects.loc[in_year, weather_year].where(in_winter[in_year], 0.0)
            replayed.append({"year": year, "winter": name, "weather_year": weather_year})
        for trajectory in spec.trajectories:
            grown = normal[in_year] * factor(spec, trajectory, year, end.year)
            for name, effect in winters.items():
                energy = (grown + effect).rename("energy").to_frame()
                energies.append(energy.assign(year=year, trajectory=trajectory, winter=name))
    table = pd.concat(energies).rename_axis("month").reset_index()
    return table[["year", "trajectory", "winter", "month", "energy"]], pd.DataFrame(replayed)
