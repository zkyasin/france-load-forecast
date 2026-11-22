from collections.abc import Callable
from typing import Any

import pytest

from france_load_forecast.agent import agent, note, tools

Script = Callable[..., Any]


def september(bundle: tools.Bundle) -> dict[str, Any]:
    return next(entry for entry in bundle["gaps"]["months"] if entry["month"] == "2026-09")


def test_note_gives_both_gaps_term_by_term(bundle: tools.Bundle) -> None:
    text = note.render(september(bundle), bundle["meta"], "Lecture.")

    assert text.startswith("# Septembre 2026\n")
    assert "Mois provisoire : données en temps réel relevées de +0,76 GW" in text
    assert "| Terme, en TWh | Écart à la prévision | Écart à septembre 2025 |" in text
    assert "| Climat | -0,02 | -0,14 |" in text
    assert "| **Total** | **-0,23** | **-0,20** |" in text


def test_reading_comes_from_the_agent(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(
        ("month_gap", {"month": "2026-09"}),
        "À 19,9 °C contre 16,6 °C un an plus tôt, le climat pèse -0,14 TWh.",
    )

    text, reading = note.write("2026-09", bundle, facts, model, agent_config)

    assert reading.verified
    assert "## Lecture\n\nÀ 19,9 °C contre 16,6 °C" in text


def test_note_needs_a_month_of_the_bundle(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    with pytest.raises(ValueError, match="no gap for 2020-01"):
        note.write("2020-01", bundle, facts, script(), agent_config)
