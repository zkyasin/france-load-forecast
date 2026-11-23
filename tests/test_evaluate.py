import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from france_load_forecast import cli
from france_load_forecast.agent import agent, evaluate, tools

QUESTIONS = Path(__file__).parents[1] / "evals" / "questions.toml"
JANUARY = evaluate.Question(
    id="forecast-january",
    category="forecast",
    text="Quelle consommation d'électricité prévoyez-vous pour janvier 2027 ?",
    tool="forecast",
    arguments={"month": "2027-01"},
    figures=("p10", "p50", "p90"),
)
PRICE = evaluate.Question(
    id="off-topic-price",
    category="off-topic",
    text="Quel sera le prix de l'électricité demain ?",
    refuse=True,
)


def run(answer: str, calls: list[dict[str, Any]], verified: bool = True) -> evaluate.Run:
    return evaluate.Run(
        id="forecast-january",
        model="test",
        published="2026-11-22",
        answer=answer,
        verified=verified,
        problem=None if verified else "numbers without a source: 1",
        calls=calls,
        seconds=1.0,
        input_tokens=100,
        output_tokens=20,
    )


CALL = [{"name": "forecast", "args": {"month": "2027-01"}}]
BAND = "Janvier 2027 : 49,2 TWh en P50, de 46,5 à 51,5 TWh."


def test_numbers_are_read_whatever_the_dash_and_the_decimal_mark() -> None:
    assert evaluate.numbers("\u22121,28 TWh, \u20112,42 TWh, 3.5\u00a0% en 2026") == [
        -1.28,
        -2.42,
        3.5,
        2026,
    ]
    # A number glued to a letter is a label, such as P10.
    assert evaluate.numbers("P10-P90") == []


def test_a_figure_rounded_to_one_decimal_is_stated() -> None:
    assert evaluate.stated(51.515, [51.5])
    assert evaluate.stated(-2.423, [2.4])
    assert not evaluate.stated(49.15, [48.0])


def test_the_right_call_with_every_figure_passes(
    bundle: tools.Bundle, facts: dict[str, Any]
) -> None:
    assert evaluate.score(JANUARY, run(BAND, CALL), bundle, facts).passed


@pytest.mark.parametrize(
    ("answer", "calls", "verified", "reason"),
    [
        ("Janvier 2027 : 49,2 TWh en P50.", CALL, True, "figures"),
        (BAND, [{"name": "forecast", "args": {"month": "2027-02"}}], True, "tool"),
        (BAND, CALL, False, "refused"),
    ],
)
def test_a_question_fails_for_a_reason(
    answer: str,
    calls: list[dict[str, Any]],
    verified: bool,
    reason: str,
    bundle: tools.Bundle,
    facts: dict[str, Any],
) -> None:
    scored = evaluate.score(JANUARY, run(answer, calls, verified), bundle, facts)

    assert not scored.passed
    assert scored.reason == reason


def test_a_refusal_passes_without_tools_or_numbers(
    bundle: tools.Bundle, facts: dict[str, Any]
) -> None:
    def refusal(answer: str, calls: list[dict[str, Any]]) -> evaluate.Score:
        return evaluate.score(PRICE, run(answer, calls), bundle, facts)

    assert refusal("Hors du périmètre de l'outil, qui ne couvre pas les prix.", []).passed
    assert refusal("Je ne réponds pas sur les prix de 2026.", []).passed
    assert refusal("Environ 300 € le MWh.", []).reason == "numbers"
    assert refusal("Hors du périmètre.", CALL).reason == "tool"


def test_a_run_keeps_the_calls_the_answer_and_the_tokens(
    script: Callable[..., Any],
    bundle: tools.Bundle,
    facts: dict[str, Any],
    agent_config: agent.AgentConfig,
) -> None:
    model = script(("forecast", {"month": "2027-01"}), BAND)

    kept = evaluate.ask(JANUARY, bundle, facts, model, agent_config, "scripted")

    assert (kept.answer, kept.verified, kept.error) == (BAND, True, None)
    assert kept.calls == CALL
    assert kept.published == "2026-11-22"


def test_errors_are_asked_again_and_runs_are_kept(tmp_path: Path) -> None:
    done = run(BAND, CALL)
    stopped = evaluate.Run(**{**done.__dict__, "id": "off-topic-price", "error": "RateLimitError"})
    path = tmp_path / "runs.jsonl"

    evaluate.write_runs(path, [done, stopped])

    assert evaluate.read_runs(path) == [done, stopped]
    assert evaluate.pending([JANUARY, PRICE], evaluate.read_runs(path)) == [PRICE]


def test_the_frozen_questions_are_read_with_their_previous_exchange() -> None:
    questions = evaluate.load_questions(QUESTIONS)
    follow_up = next(q for q in questions if q.previous is not None)

    assert len(questions) == 40
    assert follow_up.text == "Et par rapport à avril 2025 ?"
    assert follow_up.previous is not None
    assert follow_up.previous[0].startswith("Pourquoi la consommation d'avril 2026")


def test_every_expected_figure_is_in_the_result_of_its_tool(
    bundle: tools.Bundle, facts: dict[str, Any]
) -> None:
    by_name = {each.name: each for each in tools.make_tools(bundle, facts)}

    for question in evaluate.load_questions(QUESTIONS):
        if question.refuse:
            continue
        expected = evaluate.arguments(question, bundle)
        result = json.loads(by_name[str(question.tool)].invoke(expected))
        for figure in question.figures:
            assert evaluate.dig(result, figure), (question.id, figure)


def test_the_command_asks_scores_and_reports(
    script: Callable[..., Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def scripted(config: agent.AgentConfig, patient: bool = False) -> Any:
        assert patient
        return script(("forecast", {"month": "2027-01"}), BAND)

    monkeypatch.setattr(agent, "chat_model", scripted)
    report = tmp_path / "results.md"
    fixtures = Path(__file__).parent / "fixtures" / "bundle"

    code = cli.main(
        [
            "eval",
            "--model",
            "scripted:model",
            "--only",
            "forecast-january",
            "--bundle",
            str(fixtures),
            "--runs",
            str(tmp_path / "runs"),
            "--report",
            str(report),
        ]
    )

    assert code == 0
    assert len(evaluate.read_runs(tmp_path / "runs" / "scripted-model.jsonl")) == 1
    text = report.read_text(encoding="utf-8")
    assert "| scripted:model | 1/1 | 1/1 | 3/3 | 1/1 | 0/0 | 0 |" in text
    assert "| forecast-january | forecast | pass |" in text
