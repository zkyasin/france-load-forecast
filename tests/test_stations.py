import gzip
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from france_load_forecast import stations

ROOT = Path(__file__).parents[1]
HEADER = "NUM_POSTE;NOM_USUEL;LAT;LON;ALTI;AAAAMMJJ;RR;QRR;TN;QTN;TX;QTX;TNTXM;QTNTXM"


def daily_file(path: Path, rows: list[str]) -> Path:
    with gzip.open(path, "wt", encoding="utf-8") as file:
        file.write("\n".join([HEADER, *rows]) + "\n")
    return path


def test_spec_reads_the_repository_config() -> None:
    spec = stations.load_spec(ROOT / "config" / "stations.toml")

    assert (spec.period, spec.fit_years, len(spec.stations)) == ("1950-2024", (2012, 2024), 23)
    assert spec.stations["75114001"] == "Paris-Montsouris"
    assert spec.first_day == pd.Timestamp("1950-01-01")


def test_a_station_belongs_to_the_department_of_its_number() -> None:
    assert stations.department("75114001") == "75"


def test_daily_mean_is_tntxm_or_the_mean_of_tn_and_tx(tmp_path: Path) -> None:
    path = daily_file(
        tmp_path / "Q_75.csv.gz",
        [
            "75114001;PARIS;48.8;2.3;75;19500101;0.0;1;2.0;1;6.0;1;4.0;1",
            "75114001;PARIS;48.8;2.3;75;19500102;0.0;1;1.0;1;5.0;1;;",
            "75999001;OTHER;48.8;2.3;75;19500101;0.0;1;9.0;1;9.0;1;9.0;1",
        ],
    )

    daily = stations.read_daily([path], ["75114001"])

    assert list(daily.columns) == ["75114001"]
    assert daily["75114001"].tolist() == [4.0, 3.0]
    assert daily.index.tolist() == [pd.Timestamp("1950-01-01"), pd.Timestamp("1950-01-02")]


def test_weights_rebuild_the_national_temperature() -> None:
    rng = np.random.default_rng(0)
    days = pd.date_range("2012-01-01", "2021-12-31")
    daily = pd.DataFrame(
        {"north": rng.normal(10, 6, len(days)), "south": rng.normal(15, 5, len(days))},
        index=days,
    )
    national = 0.6 * daily["north"] + 0.4 * daily["south"]

    weights = stations.fit(daily, national)

    np.testing.assert_allclose(weights, [0.6, 0.4], atol=1e-9)
    np.testing.assert_allclose(stations.rebuild(daily, weights), national, atol=1e-9)
    assert stations.holdout_error(daily, national, 2018).abs().max() < 1e-9


def test_a_day_without_every_station_is_not_rebuilt() -> None:
    daily = pd.DataFrame(
        {"north": [1.0, np.nan], "south": [3.0, 4.0]},
        index=pd.date_range("1950-01-01", periods=2),
    )

    rebuilt = stations.rebuild(daily, pd.Series({"north": 0.5, "south": 0.5}))

    assert rebuilt.tolist() == [2.0]


def test_the_rebuilt_temperature_covers_every_day_before_rte() -> None:
    rebuilt = pd.read_csv(ROOT / "climate" / "national-temperature.csv", parse_dates=["date"])

    days = pd.DatetimeIndex(rebuilt["date"])
    assert days.equals(pd.date_range("1950-01-01", "2011-12-31"))
    assert rebuilt["temperature_c"].between(-15, 35).all()
    assert rebuilt["temperature_c"].mean() == pytest.approx(11.6, abs=0.5)
