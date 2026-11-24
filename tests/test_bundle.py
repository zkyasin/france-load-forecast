import copy
from pathlib import Path
from typing import Any

import pytest

from france_load_forecast import bundle
from france_load_forecast.agent import tools


@pytest.fixture
def files(fixtures: Path) -> dict[str, dict[str, Any]]:
    """The bundle published on 22 November 2026."""
    return tools.load_bundle(fixtures / "bundle")


def test_published_bundle_passes(files: dict[str, dict[str, Any]]) -> None:
    assert bundle.check(files) == []


def test_band_out_of_order_fails(files: dict[str, dict[str, Any]]) -> None:
    broken = copy.deepcopy(files)
    month = broken["forecast"]["months"][3]
    month["p10"], month["p90"] = month["p90"], month["p10"]

    problems = bundle.check(broken)

    assert len(problems) == 1
    assert problems[0].startswith("forecast:")
    assert "out of order" in problems[0]


def test_terms_that_do_not_add_up_fail(files: dict[str, dict[str, Any]]) -> None:
    broken = copy.deepcopy(files)
    broken["gaps"]["months"][0]["against_forecast"]["climate"] += 1.0

    assert "do not add up" in bundle.check(broken)[0]


def test_implausible_energy_fails(files: dict[str, dict[str, Any]]) -> None:
    broken = copy.deepcopy(files)
    broken["history"]["months"][0]["energy"] = 400.0

    assert bundle.check(broken)[0].startswith("history:")


def test_implausible_peak_fails(files: dict[str, dict[str, Any]]) -> None:
    broken = copy.deepcopy(files)
    broken["peak"]["history"][-1]["peak"] = 184.4

    assert bundle.check(broken)[0].startswith("peak:")


def test_scenarios_without_a_winter_or_the_reference_fail(files: dict[str, dict[str, Any]]) -> None:
    without_mild = copy.deepcopy(files)
    scenarios = without_mild["scenarios"]
    scenarios["cases"] = [case for case in scenarios["cases"] if case["winter"] != "mild"]
    without_reference = copy.deepcopy(files)
    scenarios = without_reference["scenarios"]
    del scenarios["trajectories"]["stagnation"]
    scenarios["cases"] = [case for case in scenarios["cases"] if case["trajectory"] != "stagnation"]

    assert bundle.check(without_mild)[0].startswith("scenarios:")
    assert "reference trajectory" in bundle.check(without_reference)[0]


def test_missing_scenario_and_missing_file_fail(files: dict[str, dict[str, Any]]) -> None:
    broken = copy.deepcopy(files)
    broken["scenarios"]["cases"].pop()
    del broken["model"]

    assert sorted(problem.split(":")[0] for problem in bundle.check(broken)) == [
        "model",
        "scenarios",
    ]


def test_only_the_files_required_must_be_there(files: dict[str, dict[str, Any]]) -> None:
    agent_files = {name: files[name] for name in tools.FILES}

    assert bundle.check(agent_files, required=tools.FILES) == []
    assert set(tools.FILES) <= set(bundle.FILES)
