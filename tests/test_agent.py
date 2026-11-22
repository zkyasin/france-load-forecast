from collections.abc import Callable
from typing import Any

from langchain_ollama import ChatOllama

from france_load_forecast.agent import agent, tools

QUESTION = "Pourquoi la consommation de février 2026 a-t-elle été plus basse que prévu ?"
Script = Callable[..., Any]


def test_answer_quotes_the_tool_results(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(
        ("month_gap", {"month": "2026-02"}),
        "Février 2026 a fini 1,28 TWh sous la prévision, dont -2,42 TWh de climat.",
    )

    answer = agent.ask(QUESTION, bundle, facts, model, agent_config)

    assert answer.verified
    assert answer.tool_calls == [{"name": "month_gap", "args": {"month": "2026-02"}}]
    assert answer.text.startswith("Février 2026")


def test_a_number_without_source_gets_one_more_try(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(
        ("month_gap", {"month": "2026-02"}),
        "Le climat explique 190 % de l'écart.",
        "Le climat pèse -2,42 TWh.",
    )

    answer = agent.ask(QUESTION, bundle, facts, model, agent_config)

    assert answer.verified
    assert answer.text == "Le climat pèse -2,42 TWh."


def test_an_answer_failing_twice_is_not_verified(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script("Environ 987,6 TWh.", "Toujours 987,6 TWh.")

    answer = agent.ask(QUESTION, bundle, facts, model, agent_config)

    assert answer.unsupported == ["987,6"]
    assert not answer.verified


def test_refusals_need_no_tool(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script("Cette question sort du périmètre de l'outil.")

    answer = agent.ask("Quel sera le prix de l'électricité ?", bundle, facts, model, agent_config)

    assert answer.verified
    assert answer.tool_calls == []


def test_configured_model_is_the_local_one(agent_config: agent.AgentConfig) -> None:
    model = agent.chat_model(agent_config)

    assert isinstance(model, ChatOllama)
    assert model.num_predict == agent_config.max_output_tokens
