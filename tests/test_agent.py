from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_ollama import ChatOllama
from pydantic import Field

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


def test_an_answer_on_the_peak_quotes_its_tool(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(
        ("peak", {"month": "2027-01"}),
        "En janvier 2027, la pointe attendue est de 82,1 GW, entre 76,8 et 89,7 GW.",
    )

    answer = agent.ask("Quelle pointe en janvier 2027 ?", bundle, facts, model, agent_config)

    assert answer.verified
    assert answer.tool_calls == [{"name": "peak", "args": {"month": "2027-01"}}]


def test_an_answer_on_the_change_since_2019_quotes_its_tool(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(
        ("drivers", {}),
        "Corrigée du climat, la consommation a baissé de 20,49 TWh depuis 2019 (-4,38 %) :"
        " -5,44 TWh pour la grande industrie, +5,18 TWh pour les voitures électriques et"
        " -20,23 TWh pour le reste.",
    )

    question = "Pourquoi la consommation a-t-elle baissé depuis 2019 ?"
    answer = agent.ask(question, bundle, facts, model, agent_config)

    assert answer.verified
    assert "- drivers for what changed consumption since 2019" in agent.instructions(bundle, 120)


def test_the_level_of_the_band_can_be_quoted(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(
        ("forecast", {"month": "2027-01"}),
        "Janvier 2027 : 49,2 TWh en P50, dans une bande à 80 % de 46,5 à 51,5 TWh.",
    )

    answer = agent.ask("Que prévoyez-vous pour janvier 2027 ?", bundle, facts, model, agent_config)

    assert answer.verified


def test_only_the_tools_named_can_run(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(("thermosensitivity", {}), "Le climat a pesé sur la consommation.")

    answer = agent.ask(QUESTION, bundle, facts, model, agent_config, only={"month_gap"})

    assert answer.verified
    assert answer.tool_calls == []


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

    assert answer.problem == "numbers without a source: 987,6"
    assert not answer.verified


def test_numbers_of_the_question_are_not_sources(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(
        ("annual_energy", {"first": 2025, "last": 2025}),
        "En 2025, la consommation a chuté à 410 TWh.",
        "En 2025, la consommation a chuté à 410 TWh.",
    )

    question = "Pourquoi la consommation de 2025 a-t-elle chuté à 410 TWh ?"
    answer = agent.ask(question, bundle, facts, model, agent_config)

    assert answer.problem == "numbers without a source: 410"


def test_an_empty_answer_is_not_verified(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(("month_gap", {"month": "2026-02"}), "", " ")

    answer = agent.ask(QUESTION, bundle, facts, model, agent_config)

    assert answer.problem == "empty answer"


def test_links_are_not_shown(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(
        ("month_gap", {"month": "2026-02"}),
        "Le climat pèse -2,42 TWh, voir https://example.org.",
        "Le climat pèse -2,42 TWh, voir www.example.org.",
    )

    answer = agent.ask(QUESTION, bundle, facts, model, agent_config)

    assert answer.problem == "link in the answer"


def test_tool_calls_stop_at_the_limit(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(*[("forecast", {})] * 6)

    answer = agent.ask(QUESTION, bundle, facts, model, agent_config)

    assert answer.problem == "the model kept calling tools"
    assert not answer.verified


def test_refusals_need_no_tool(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script("Cette question sort du périmètre de l'outil.")

    answer = agent.ask("Quel sera le prix de l'électricité ?", bundle, facts, model, agent_config)

    assert answer.verified
    assert answer.tool_calls == []


class Recording(GenericFakeChatModel):
    """A scripted model that keeps the messages of each call."""

    calls: list[list[BaseMessage]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "Recording":
        return self

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        self.calls.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


def test_each_tool_call_is_reported_before_the_answer(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(
        ("month_gap", {"month": "2026-02"}),
        ("thermosensitivity", {}),
        "Février 2026 a fini 1,28 TWh sous la prévision.",
    )

    items = list(agent.answering(QUESTION, bundle, facts, model, agent_config))

    assert items[:2] == [
        agent.Step("month_gap", {"month": "2026-02"}),
        agent.Step("thermosensitivity", {}),
    ]
    assert isinstance(items[2], agent.Answer)
    assert items[2].verified
    assert len(items) == 3


def test_the_previous_exchange_is_read_but_is_no_source(
    bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    replies = ["Toujours 2,58 TWh sous la prévision.", "Toujours 2,58 TWh sous la prévision."]
    model = Recording(messages=iter([AIMessage(reply) for reply in replies]))
    previous = ("Et avril 2026 ?", "Avril 2026 a fini 2,58 TWh sous la prévision.")

    answer = agent.ask("Et en mai ?", bundle, facts, model, agent_config, previous=previous)

    first = model.calls[0]
    assert [type(m) for m in first[-3:]] == [HumanMessage, AIMessage, HumanMessage]
    assert [m.text for m in first[-3:]] == [*previous, "Et en mai ?"]
    assert answer.problem == "numbers without a source: 2,58"


def test_configured_model_is_the_local_one(agent_config: agent.AgentConfig) -> None:
    model = agent.chat_model(agent_config)

    assert isinstance(model, ChatOllama)
    assert model.num_predict == agent_config.max_output_tokens


def test_a_hosted_model_fails_fast_instead_of_retrying(
    agent_config: agent.AgentConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "not-a-key")

    model = agent.chat_model(replace(agent_config, model="groq:openai/gpt-oss-120b"))

    assert getattr(model, "request_timeout", None) == agent.HOSTED_TIMEOUT_SECONDS
    assert getattr(model, "max_retries", None) == 0
