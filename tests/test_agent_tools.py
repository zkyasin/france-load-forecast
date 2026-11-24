import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

from france_load_forecast import conformal
from france_load_forecast.agent import tools


@pytest.fixture
def by_name(bundle: tools.Bundle, facts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {tool.name: tool for tool in tools.make_tools(bundle, facts)}


def call(by_name: dict[str, Any], name: str, **args: Any) -> Any:
    return json.loads(by_name[name].invoke(args))


def test_tools_are_those_of_the_frozen_questions(by_name: dict[str, Any]) -> None:
    with (Path(__file__).parents[1] / "evals" / "questions.toml").open("rb") as file:
        declared = set(tomllib.load(file)["tools"])

    assert set(by_name) == declared


def test_forecast_starts_with_the_current_month(by_name: dict[str, Any]) -> None:
    content = call(by_name, "forecast")

    assert content["current_month"] == content["months"][0]["month"] == "2026-11"
    assert len(content["months"]) == 12
    assert content["total_p50"] == pytest.approx(447.0, abs=0.1)


def test_forecast_of_a_month_says_how_far_load_is_measured(by_name: dict[str, Any]) -> None:
    content = call(by_name, "forecast", month="2026-11")

    assert content["measured_until"] == "2026-11-21"
    assert content["provisional"]
    assert content["p10"] < content["p50"] < content["p90"]


def test_forecast_gives_the_level_of_its_band(by_name: dict[str, Any]) -> None:
    low, high = conformal.QUANTILES

    assert round(100 * (high - low)) == tools.BAND_LEVEL_PCT
    assert call(by_name, "forecast")["band_level_pct"] == tools.BAND_LEVEL_PCT
    assert call(by_name, "forecast", month="2027-01")["band_level_pct"] == tools.BAND_LEVEL_PCT


def test_month_gap_names_the_month_a_year_earlier(by_name: dict[str, Any]) -> None:
    content = call(by_name, "month_gap", month="2026-02")

    assert (content["year_before"], content["forecast_made_on"]) == ("2025-02", "2026-02-01")
    assert content["terms"]["climate"] == {
        "vs_forecast": pytest.approx(-2.423),
        "vs_year_before": pytest.approx(-3.439),
    }
    assert content["gap"]["vs_forecast"] == pytest.approx(-1.275)
    assert content["temperature"]["actual"] > content["temperature"]["normal"]


def test_month_gap_gives_the_temperature_the_forecast_assumed(by_name: dict[str, Any]) -> None:
    temperature = call(by_name, "month_gap", month="2026-02")["temperature"]

    assert temperature["forecast"] == pytest.approx(7.123)


def test_unknown_months_and_years_get_an_error(by_name: dict[str, Any]) -> None:
    assert "2025-10 to 2026-09" in call(by_name, "month_gap", month="2020-01")["error"]
    assert "2014 to 2025" in call(by_name, "annual_energy", first=2010, last=2011)["error"]
    assert "after" in call(by_name, "annual_energy", first=2025, last=2019)["error"]
    assert "2012-01 to 2027-10" in call(by_name, "peak", month="2030-01")["error"]


def test_peak_gives_the_months_ahead_and_the_last_winter(by_name: dict[str, Any]) -> None:
    content = call(by_name, "peak")

    assert content["current_month"] == content["months"][0]["month"] == "2026-11"
    assert content["months"][0]["measured"] == pytest.approx(68.0, abs=0.05)
    assert content["last_winter_peak"] == {
        "winter": "2025-2026",
        "month": "2026-01",
        "peak": pytest.approx(90.236),
        "day": "2026-01-06",
        "provisional": False,
    }
    assert content["coming_winter_peak"]["winter"] == "2026-2027"
    assert content["coming_winter_peak"]["month"] == "2027-01"
    assert (content["band_level_pct"], content["band_coverage_pct"]) == (80, pytest.approx(72.42))


def test_peak_of_a_month_is_its_forecast_or_its_measured_day(by_name: dict[str, Any]) -> None:
    ahead = call(by_name, "peak", month="2027-01")
    measured = call(by_name, "peak", month="2026-01")

    assert ahead["p10"] < ahead["p50"] < ahead["p90"]
    assert (measured["peak"], measured["day"]) == (pytest.approx(90.236), "2026-01-06")


def test_last_winter_skips_a_winter_still_under_way() -> None:
    def month(name: str, peak: float) -> dict[str, Any]:
        return {"month": name, "peak": peak, "day": f"{name}-10", "provisional": False}

    peaks = [month("2025-12", 80.0), month("2026-01", 85.0), month("2026-02", 82.0)]
    peaks += [month("2026-12", 95.0), month("2027-01", 99.0)]

    assert tools.last_winter(peaks) == {"winter": "2025-2026"} | month("2026-01", 85.0)
    assert tools.last_winter(peaks[3:]) is None


def test_annual_energy_gives_the_change_from_the_year_before(by_name: dict[str, Any]) -> None:
    years = call(by_name, "annual_energy", first=2020, last=2020)["years"]

    change = years[0]["change"]
    assert change["from_year"] == 2019
    assert change["gross_pct"] == pytest.approx(-5.08, abs=0.01)
    assert "corrected_pct" in change


def test_revision_fact_carries_the_measured_revision(by_name: dict[str, Any]) -> None:
    content = call(by_name, "fact", topic="revision")

    assert content["revision_gw"] == pytest.approx(0.758)
    assert content["source"] == "docs/methodology.md"


def test_scenario_compares_with_the_reference(by_name: dict[str, Any]) -> None:
    content = call(by_name, "scenario", trajectory="rapid", winter="cold")

    assert content["year"] == 2027
    assert content["change"]["annual_energy"] == pytest.approx(
        content["annual_energy"] - content["reference"]["annual_energy"], abs=1e-3
    )
    assert content["winter_energy"] > content["reference"]["winter_energy"]
    assert content["replays_the_winter_months_of"] in range(2012, 2026)
    assert "2020" in call(by_name, "scenario", year=2020)["error"]
