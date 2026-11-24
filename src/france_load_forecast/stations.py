"""National temperature before RTE's series, rebuilt from Météo-France stations.

RTE's national temperature starts in 2012. Before it, the temperature is rebuilt as a weighted
sum of the daily mean temperatures, (TN + TX) / 2, of Météo-France stations that measured every
day since 1950. The weights are the non-negative ones that best reproduce RTE's temperature on
the years both cover.
"""

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import httpx
import pandas as pd
from scipy.optimize import nnls

# Daily climatological data of Météo-France, one file per department and period, on data.gouv.fr.
DAILY_URL = (
    "https://meteofrance.s3.sbg.io.cloud.ovh.net/data/synchro_ftp/BASE/QUOT/"
    "Q_{department}_previous-{period}_RR-T-Vent.csv.gz"
)


@dataclass(frozen=True)
class StationSpec:
    # Period of Météo-France's files, as their names give it.
    period: str
    first_day: pd.Timestamp
    # Years RTE's temperature and the stations both cover: the weights are fitted on them.
    fit_years: tuple[int, int]
    # Station number and name.
    stations: dict[str, str]


def load_spec(path: Path) -> StationSpec:
    with path.open("rb") as file:
        config = tomllib.load(file)
    return StationSpec(
        period=config["period"],
        first_day=pd.Timestamp(config["first_day"]),
        fit_years=(config["fit_from"], config["fit_until"]),
        stations=config["stations"],
    )


def department(station: str) -> str:
    """The department of a mainland station, from the first two digits of its number."""
    return station[:2]


def download(client: httpx.Client, spec: StationSpec, folder: Path) -> list[Path]:
    """The daily files of the departments of the stations, downloaded once into `folder`."""
    paths = []
    for name in sorted({department(station) for station in spec.stations}):
        path = folder / f"Q_{name}_previous-{spec.period}_RR-T-Vent.csv.gz"
        if not path.exists():
            folder.mkdir(parents=True, exist_ok=True)
            url = DAILY_URL.format(department=name, period=spec.period)
            with client.stream("GET", url) as response:
                response.raise_for_status()
                partial = path.with_name(path.name + ".part")
                with partial.open("wb") as file:
                    for chunk in response.iter_bytes():
                        file.write(chunk)
                partial.replace(path)
        paths.append(path)
    return paths


def read_daily(paths: Iterable[Path], stations: Iterable[str]) -> pd.DataFrame:
    """Daily mean temperature, (TN + TX) / 2, of `stations`, one column per station."""
    wanted = set(stations)
    tables = []
    for path in paths:
        frame = pd.read_csv(
            path,
            sep=";",
            usecols=["NUM_POSTE", "AAAAMMJJ", "TN", "TX", "TNTXM"],
            dtype={"NUM_POSTE": str, "AAAAMMJJ": str},
        )
        frame = frame[frame["NUM_POSTE"].isin(wanted)].assign(
            date=lambda f: pd.to_datetime(f["AAAAMMJJ"], format="%Y%m%d"),
            mean=lambda f: f["TNTXM"].fillna((f["TN"] + f["TX"]) / 2),
        )
        tables.append(frame.pivot(index="date", columns="NUM_POSTE", values="mean"))
    daily = pd.concat(tables, axis=1).sort_index()
    daily.index = pd.DatetimeIndex(daily.index)
    return daily.rename_axis(columns=None)


def fit(daily: pd.DataFrame, national: pd.Series) -> pd.Series:
    """Non-negative weights of the stations that best reproduce `national` on the days where
    every station and `national` have a value."""
    both = daily.join(national.rename("national"), how="inner").dropna()
    weights, _ = nnls(both[daily.columns].to_numpy(), both["national"].to_numpy())
    return pd.Series(weights, index=daily.columns)


def rebuild(daily: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """National temperature from the stations, on the days where every station has a value."""
    complete = daily[weights.index].dropna()
    return pd.Series(complete.to_numpy() @ weights.to_numpy(), index=complete.index)


def holdout_error(daily: pd.DataFrame, national: pd.Series, split: int) -> pd.Series:
    """Daily error of the temperature rebuilt with weights fitted before `split` (a year), on the
    days from `split`."""
    years = pd.DatetimeIndex(national.index).year
    weights = fit(daily, national[years < split])
    error: pd.Series = (rebuild(daily, weights) - national[years >= split]).dropna()
    return error
