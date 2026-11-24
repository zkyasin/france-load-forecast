from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from france_load_forecast import drivers, warehouse

SPEC = drivers.DriversSpec(
    base_year=2019,
    branches={"production_metals": ["steel_gwh"]},
    other_branch="production_manufacturing",
    left_out=["rail_gwh"],
    cars=drivers.CarsReference(year=2020, twh=2.0, source="a test"),
)


def sectors() -> pd.DataFrame:
    """RTE's industry series in 2019: 100 GWh a month, 30 of steel and 10 of rail."""
    months = pd.date_range("2019-01-01", periods=12, freq="MS")
    return pd.DataFrame({"industry_gwh": 100.0, "steel_gwh": 30.0, "rail_gwh": 10.0}, index=months)


@pytest.fixture
def inputs() -> drivers.Inputs:
    """2018 to 2020: large industry draws 100 GWh a day, then 90 in 2020, while the production of
    metals falls by a fifth in 2020; the car stock doubles each year."""
    days = pd.date_range("2018-01-01", "2020-12-31", freq="D")
    months = pd.date_range("2018-01-01", "2020-12-01", freq="MS")
    in_2020 = months.year == 2020
    insee = pd.DataFrame(
        {
            "production_metals": np.where(in_2020, 80.0, 100.0),
            "production_manufacturing": 100.0,
            "prices_all": 100.0,
            "prices_electricity": np.where(in_2020, 120.0, 100.0),
        },
        index=months,
    )
    cars = pd.Series(
        [1e5, 2e5, 4e5], index=pd.DatetimeIndex(["2018-12-31", "2019-12-31", "2020-12-31"])
    )
    return drivers.Inputs(
        industry=pd.Series(np.where(days.year == 2020, 90_000.0, 100_000.0), index=days),
        sectors=sectors(),
        insee=insee,
        cars=cars,
    )


def corrected() -> pd.Series:
    """Climate-corrected load of 50 GW, then 48 GW in 2020."""
    days = pd.date_range("2018-01-01", "2020-12-31", freq="D")
    return pd.Series(np.where(days.year == 2020, 48.0, 50.0), index=days)


def test_spec_reads_the_repository_config() -> None:
    spec = drivers.load_spec(Path(__file__).parents[1] / "config" / "drivers.toml")

    assert spec.base_year == 2019
    assert spec.branches["production_metals"] == ["steel_gwh", "metallurgy_gwh"]
    assert set(spec.branches) | {spec.other_branch} <= set(warehouse.INSEE_SERIES)
    assert (spec.cars.year, spec.cars.twh) == (2025, 4.9)


def test_each_branch_weighs_its_consumption_of_the_base_year() -> None:
    weights = drivers.branch_weights(sectors(), SPEC)

    # Rail is left out: the other industry is 100 - 30 - 10 GWh a month.
    assert weights.to_dict() == pytest.approx(
        {"production_metals": 0.36, "production_manufacturing": 0.72}
    )


def test_a_base_year_short_of_months_has_no_weights() -> None:
    with pytest.raises(ValueError, match="2019"):
        drivers.branch_weights(sectors().iloc[:11], SPEC)


def test_activity_weights_the_index_of_each_branch() -> None:
    insee = pd.DataFrame(
        {"production_metals": [80.0, 80.0], "production_manufacturing": [100.0, None]},
        index=pd.date_range("2020-01-01", periods=2, freq="MS"),
    )

    index = drivers.activity(insee, drivers.branch_weights(sectors(), SPEC))

    assert index.iloc[0] == pytest.approx((80 * 0.36 + 100 * 0.72) / 1.08)
    assert np.isnan(index.iloc[1])


def test_whole_months_leave_out_29_february_and_partial_months() -> None:
    daily = pd.Series(1.0, index=pd.date_range("2024-01-01", "2024-03-15", freq="D"))

    months = drivers.whole_months(daily)

    assert list(months) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")]
    assert drivers.monthly_sum(daily).to_list() == [31.0, 28.0]


def test_car_stock_grows_steadily_between_and_beyond_the_dates_given() -> None:
    cars = pd.Series([1e6, 4e6], index=pd.DatetimeIndex(["2020-12-31", "2021-12-31"]))
    months = pd.DatetimeIndex(["2021-06-01", "2019-12-01", "2022-12-01"])

    stock = drivers.car_stock(cars, months)

    # The middle of each month, 15 June 2021, 15 December 2019 and 15 December 2022, is 166 days
    # after, 382 days before and 349 days after the date nearest to it.
    growth = np.log(4) / 365
    assert stock.to_list() == pytest.approx(
        [np.exp(growth * 166), np.exp(-growth * 382), 4 * np.exp(growth * 349)]
    )


def test_car_energy_gives_rte_estimate_in_the_reference_year() -> None:
    months = pd.date_range("2019-01-01", "2020-12-01", freq="MS")
    stock = pd.Series(np.where(months.year == 2020, 2.0, 1.0), index=months)

    energy, mwh_per_car = drivers.car_energy(stock, SPEC.cars)

    assert energy[months.year == 2020].sum() == pytest.approx(2.0)
    assert energy[months.year == 2019].sum() == pytest.approx(1.0)
    assert mwh_per_car == pytest.approx(1.0)


def test_the_change_of_large_industry_splits_into_activity_and_intensity() -> None:
    base = pd.Series({"industry": 40.0, "activity": 100.0, "electric_cars": 1.0, "rest": 400.0})
    now = pd.Series({"industry": 30.0, "activity": 80.0, "electric_cars": 3.0, "rest": 390.0})

    parts = drivers.contributions(base, now)

    weight = -10 / np.log(0.75)
    assert parts["industry_activity"] == pytest.approx(weight * np.log(0.8))
    assert parts["industry_activity"] + parts["industry_intensity"] == pytest.approx(-10)
    assert (parts["electric_cars"], parts["rest"]) == (2.0, -10.0)


def test_unchanged_industry_has_no_change_to_split() -> None:
    base = pd.Series({"industry": 40.0, "activity": 100.0, "electric_cars": 1.0, "rest": 400.0})

    parts = drivers.contributions(base, base.copy())

    assert parts.to_list() == pytest.approx([0.0, 0.0, 0.0, 0.0])


def test_the_parts_add_up_to_the_change_of_consumption(inputs: drivers.Inputs) -> None:
    found = drivers.compute(corrected(), inputs, SPEC)

    base, now = found.base, found.now
    assert (found.first_month, found.last_month) == (
        pd.Timestamp("2020-01-01"),
        pd.Timestamp("2020-12-01"),
    )
    # 50 and 48 GW over 8,760 hours; 29 February 2020 is left out.
    assert (base["consumption"], now["consumption"]) == pytest.approx((438.0, 420.48))
    assert (base["industry"], now["industry"]) == pytest.approx((36.5, 32.85))
    assert now["electric_cars"] == pytest.approx(2.0)
    assert drivers.contributions(base, now).sum() == pytest.approx(420.48 - 438.0)
    assert now["rest"] == pytest.approx(420.48 - 32.85 - now["electric_cars"])
    # Metals weigh 0.36 TWh and the other industry 0.72.
    assert (now["real_price"], now["activity"]) == pytest.approx((120.0, (80 * 0.36 + 72) / 1.08))


def test_years_cover_the_whole_years_of_every_source(inputs: drivers.Inputs) -> None:
    table = drivers.years(drivers.compute(corrected(), inputs, SPEC))

    assert table.index.to_list() == [2018, 2019, 2020]
    assert table.loc[2019, "activity"] == pytest.approx(100.0)
    assert table.loc[2018, "consumption"] == pytest.approx(438.0)


def test_sources_that_miss_the_base_year_fail(inputs: drivers.Inputs) -> None:
    days = pd.date_range("2019-06-01", "2020-12-31", freq="D")

    with pytest.raises(ValueError, match="2019"):
        drivers.compute(corrected().loc[days], inputs, SPEC)


def test_inputs_are_read_from_the_warehouse(export_files: dict[str, Path]) -> None:
    con = duckdb.connect()
    warehouse.build(con, export_files)

    inputs = drivers.read(con)

    assert inputs.industry.index.to_list() == [
        pd.Timestamp("2026-08-30"),
        pd.Timestamp("2026-08-31"),
    ]
    assert set(inputs.insee.columns) == set(warehouse.INSEE_SERIES)
    assert inputs.insee.loc["2026-09-01", "production_chemistry"] == 92.31
    assert inputs.sectors.loc["2024-12-01", "industry_gwh"] == pytest.approx(5204.476226)
    assert inputs.cars.iloc[-1] == 2693367
