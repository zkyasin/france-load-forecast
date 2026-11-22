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
    written = "À 19,9 °C contre 16,6 °C un an plus tôt, le climat pèse -0,14 TWh."
    model = script(("month_gap", {"month": "2026-09"}), written)

    text, data, reading = note.write("2026-09", bundle, facts, model, agent_config)

    assert reading.verified
    assert f"## Lecture\n\n{note.plain(written)}\n" in text
    assert data["month"] == "2026-09"
    assert data["published"] == bundle["meta"]["published"]
    assert data["model"] == agent_config.model
    assert data["against_forecast"] == september(bundle)["against_forecast"]
    assert data["reading"] == note.plain(written)


def test_note_needs_a_month_of_the_bundle(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    with pytest.raises(ValueError, match="no gap for 2020-01"):
        note.write("2020-01", bundle, facts, script(), agent_config)


def test_reading_is_plain_text_that_keeps_values_whole() -> None:
    assert note.plain("Le **climat** a pesé \u20130,14 TWh à 19,9 °C, et -2 GW.") == (
        "Le climat a pesé \u22120,14\u00a0TWh à 19,9\u00a0°C, et \u22122\u00a0GW."
    )
    assert note.plain("19.9 °C.") == "19,9\u00a0°C."
    # A hyphen inside a word or a date is not a sign.
    assert note.plain("ré-estimé, 2025-09") == "ré-estimé, 2025-09"


def test_figures_must_match_the_note_in_unit_and_sign(bundle: tools.Bundle) -> None:
    data = note.record(september(bundle), bundle["meta"], "", "test")

    def check(reading: str) -> list[str]:
        return note.unsupported({**data, "reading": note.plain(reading)})

    assert check("Le climat a pesé -0,14 TWh, à 19,9 °C contre 16,6 °C en septembre 2025.") == []
    assert check("Le climat a pesé +0,14 TWh.") == ["+0,14 TWh"]
    assert check("Le résidu a pesé -0,11 °C.") == ["\u22120,11 °C"]
    # Neither the day of publication nor a difference the model computed is a temperature.
    assert check("Il a fait 22 °C, soit 1,0 °C de plus.") == ["22 °C", "1,0 °C"]
