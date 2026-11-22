from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from france_load_forecast import model, scenarios

CONFIG = Path(__file__).parents[1] / "config" / "scenarios.toml"


@pytest.fixture(scope="module")
def spec() -> scenarios.ScenarioSpec:
    return scenarios.load_spec(CONFIG)


def test_config_holds_the_bp2025_trajectories(spec: scenarios.ScenarioSpec) -> None:
    assert spec.years == [2027, 2028, 2029, 2030, 2031]
    assert spec.trajectories["rapid"].twh == {2030: 510.0, 2035: 580.0}
    assert set(spec.trajectories) == {"stagnation", "slow", "rapid"}


def test_growth_is_geometric_between_the_years_given(spec: scenarios.ScenarioSpec) -> None:
    assert scenarios.growth(spec, "rapid", 2027) == pytest.approx((510 / 447) ** (1 / 6) - 1)
    assert scenarios.growth(spec, "rapid", 2031) == pytest.approx((580 / 510) ** (1 / 5) - 1)
    # Stagnation stops in 2030: its last rate holds after it.
    assert scenarios.growth(spec, "stagnation", 2031) == scenarios.growth(spec, "stagnation", 2030)


def test_factor_compounds_from_today(spec: scenarios.ScenarioSpec) -> None:
    rate = scenarios.growth(spec, "slow", 2027)

    assert scenarios.factor(spec, "slow", 2028, today=2026) == pytest.approx((1 + rate) ** 2)
    assert scenarios.factor(spec, "slow", 2026, today=2026) == 1.0


def test_winter_year_ranks_from_the_mildest() -> None:
    effects = pd.DataFrame({2012: [1.0, 2.0], 2013: [-1.0, 0.0], 2014: [3.0, 4.0]})

    assert scenarios.winter_year(effects, 0.9) == 2014
    assert scenarios.winter_year(effects, 0.1) == 2013


def test_grid_grows_the_reference_and_changes_winter_months_only(
    synthetic_model: model.DailyModel,
    synthetic_frame: pd.DataFrame,
    spec: scenarios.ScenarioSpec,
) -> None:
    short = replace(spec, first_year=2025, last_year=2026)

    table, replayed = scenarios.grid(synthetic_model, synthetic_frame, short)

    energy = table.set_index(["year", "trajectory", "winter", "month"])["energy"].sort_index()
    reference = energy.loc[(2026, "stagnation", "normal")]
    rapid = energy.loc[(2026, "rapid", "normal")]
    # The reference is the stagnation trajectory, which grows a little too.
    growth = scenarios.factor(short, "rapid", 2026, 2024)
    np.testing.assert_allclose(
        rapid / reference, growth / scenarios.factor(short, "stagnation", 2026, 2024)
    )
    cold = energy.loc[(2026, "stagnation", "cold")] - reference
    winter = pd.DatetimeIndex(cold.index).month.isin(scenarios.WINTER)
    assert (cold[~winter] == 0).all()
    assert cold[winter].sum() > 0
    assert set(replayed["weather_year"]) <= {2022, 2023, 2024}
