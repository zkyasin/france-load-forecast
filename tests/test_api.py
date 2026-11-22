from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from france_load_forecast import api
from france_load_forecast.agent import agent, tools

Script = Callable[..., Any]
QUESTION = "Pourquoi la consommation de février 2026 a-t-elle été plus basse que prévu ?"
ANSWER = "Février 2026 a fini 1,28 TWh sous la prévision faite au début du mois."
PAGE = "https://zkyasin.github.io"
CONFIG = Path(__file__).parents[1] / "config"


class Down(GenericFakeChatModel):
    """A model whose provider does not answer."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "Down":
        return self

    def _generate(self, *args: Any, **kwargs: Any) -> Any:
        raise httpx.ConnectError("down")


def down() -> Down:
    return Down(messages=iter([]))


def settings(**changes: Any) -> api.Settings:
    base = api.load_settings(CONFIG / "api.toml")
    return replace(base, allowed_origins=[PAGE], **changes)


def client(
    bundle: tools.Bundle,
    facts: dict[str, dict[str, Any]],
    config: agent.AgentConfig,
    models: dict[str, Any],
    **changes: Any,
) -> TestClient:
    source = api.BundleSource(lambda: bundle, ttl=3600)
    app = api.create_app(settings(models=list(models), **changes), config, facts, source, models)
    return TestClient(app)


def ask(test: TestClient, question: str = QUESTION, address: str = "1.1.1.1") -> tuple[int, Any]:
    """The status and the body of the reply to `question`, asked from `address`."""
    reply = test.post("/ask", json={"question": question}, headers={"X-Forwarded-For": address})
    return reply.status_code, reply.json()


def test_answer_gives_its_tools_and_the_date_of_its_data(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(("month_gap", {"month": "2026-02"}), ANSWER)

    status, body = ask(client(bundle, facts, agent_config, {"model": model}))

    assert status == 200
    assert body == {
        "answer": agent.plain(ANSWER),
        "verified": True,
        "tools": ["month_gap"],
        "published": "2026-11-22",
    }


def test_answer_with_a_number_without_source_is_refused(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(
        ("month_gap", {"month": "2026-02"}),
        "Le climat explique 190 % de l'écart.",
        "Le climat explique toujours 190 % de l'écart.",
    )

    status, body = ask(client(bundle, facts, agent_config, {"model": model}))

    assert status == 200
    assert body["verified"] is False
    assert body["answer"] == agent.REFUSAL


@pytest.mark.parametrize("question", ["", "   ", "x" * 301])
def test_question_must_hold_1_to_300_characters(
    question: str, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    status, body = ask(client(bundle, facts, agent_config, {"model": down()}), question)

    assert status == 422
    assert body["detail"] == "Posez une question de 1 à 300 caractères."


def test_a_visitor_is_limited_per_hour_whatever_they_put_before_their_address(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(("month_gap", {"month": "2026-02"}), ANSWER)
    test = client(bundle, facts, agent_config, {"model": model}, questions_per_visitor_per_hour=1)

    first, _ = ask(test, address="5.5.5.5, 1.1.1.1")
    status, body = ask(test, address="6.6.6.6, 1.1.1.1")

    assert first == 200
    assert status == 429
    assert body["detail"] == "Vous avez posé beaucoup de questions. Réessayez plus tard."


def test_all_visitors_share_the_questions_of_the_day(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(("month_gap", {"month": "2026-02"}), ANSWER)
    test = client(bundle, facts, agent_config, {"model": model}, questions_per_day=1)

    first, _ = ask(test, address="1.1.1.1")
    status, body = ask(test, address="2.2.2.2")

    assert first == 200
    assert status == 429
    assert body["detail"] == "Le nombre de questions du jour est atteint. Réessayez demain."


def test_limits_free_up_with_time() -> None:
    now = [0.0]
    limits = api.Limits(
        settings(questions_per_visitor_per_hour=1, questions_per_day=2), clock=lambda: now[0]
    )

    assert limits.refuse("a") is None
    assert limits.refuse("a") is not None
    now[0] = api.HOUR + 1
    assert limits.refuse("a") is None
    # That was the second question of the day: the next one waits for the next UTC day.
    assert limits.refuse("b") is not None
    now[0] = api.DAY + 1
    assert limits.refuse("b") is None


def test_another_model_answers_when_the_first_is_down(
    script: Script, bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    model = script(("month_gap", {"month": "2026-02"}), ANSWER)

    status, body = ask(client(bundle, facts, agent_config, {"first": down(), "second": model}))

    assert status == 200
    assert body["answer"] == agent.plain(ANSWER)


def test_no_model_answering_is_reported(
    bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    status, body = ask(client(bundle, facts, agent_config, {"first": down(), "second": down()}))

    assert status == 503
    assert body["detail"] == "Le modèle ne répond pas pour le moment. Réessayez plus tard."


def test_only_the_page_may_call_the_api(
    bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    test = client(bundle, facts, agent_config, {"model": down()})
    preflight = {"Access-Control-Request-Method": "POST"}

    page = test.options("/ask", headers={"Origin": PAGE, **preflight})
    other = test.options("/ask", headers={"Origin": "https://example.com", **preflight})

    assert page.headers["access-control-allow-origin"] == PAGE
    assert "access-control-allow-origin" not in other.headers


def test_bundle_is_read_again_after_its_ttl_and_kept_when_it_cannot_be(
    bundle: tools.Bundle,
) -> None:
    now, reads = [0.0], []

    def fetch() -> tools.Bundle:
        reads.append(now[0])
        if len(reads) == 2:
            raise httpx.ConnectError("down")
        return bundle

    source = api.BundleSource(fetch, ttl=10, clock=lambda: now[0])

    assert source.get() is bundle
    now[0] = 5
    source.get()
    now[0] = 11
    assert source.get() is bundle
    now[0] = 15
    source.get()

    assert reads == [0.0, 11]


def test_data_that_break_their_schema_are_not_used(
    bundle: tools.Bundle, facts: dict[str, Any], agent_config: agent.AgentConfig
) -> None:
    broken = {name: content for name, content in bundle.items() if name != "model"}
    source = api.BundleSource(lambda: broken, ttl=3600)
    app = api.create_app(settings(models=["model"]), agent_config, facts, source, {"model": down()})

    status, body = ask(TestClient(app))

    assert status == 503
    assert body["detail"] == "Les données ne sont pas disponibles pour le moment."


def test_models_can_be_set_for_a_local_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLF_MODELS", "ollama:ministral-3:14b")

    assert api.load_settings(CONFIG / "api.toml").models == ["ollama:ministral-3:14b"]


def test_app_is_built_from_the_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "not-a-key")

    test = TestClient(api.build(CONFIG))

    assert test.get("/health").json() == {"status": "ok"}
