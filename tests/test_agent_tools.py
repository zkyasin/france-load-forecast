import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

from france_load_forecast.agent import tools


@pytest.fixture
def by_name(bundle: tools.Bundle, facts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {tool.name: tool for tool in tools.make_tools(bundle, facts)}


def call(by_name: dict[str, Any], name: str, **args: Any) -> Any:
    return json.loads(by_name[name].invoke(args))


def test_tools_are_those_of_the_frozen_questions(by_name: dict[str, Any]) -> None:
    with (Path(__file__).parents[1] / "evals" / "questions.toml").open("rb") as file:
        declared = set(tomllib.load(file)["tools"])

    # The scenario tool comes with the scenarios.
    assert set(by_name) == declared - {"scenario"}


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


def test_month_gap_names_the_month_a_year_earlier(by_name: dict[str, Any]) -> None:
    content = call(by_name, "month_gap", month="2026-02")

    assert (content["year_before"], content["forecast_made_on"]) == ("2025-02", "2026-02-01")
    assert content["terms"]["climate"] == {
        "vs_forecast": pytest.approx(-2.423),
        "vs_year_before": pytest.approx(-3.439),
    }
    assert content["gap"]["vs_forecast"] == pytest.approx(-1.275)
    assert content["temperature"]["mean"] > content["temperature"]["reference"]


def test_unknown_months_and_years_get_an_error(by_name: dict[str, Any]) -> None:
    assert "2025-10 to 2026-09" in call(by_name, "month_gap", month="2020-01")["error"]
    assert "2014 to 2025" in call(by_name, "annual_energy", first=2010, last=2011)["error"]
    assert "after" in call(by_name, "annual_energy", first=2025, last=2019)["error"]


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
