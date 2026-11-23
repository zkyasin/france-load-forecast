import tomllib
from pathlib import Path
from typing import Any

import pytest

QUESTIONS = Path(__file__).parents[1] / "evals" / "questions.toml"
CATEGORIES = {"forecast", "gap", "history", "model", "scenario", "data", "off-topic", "injection"}
# The page caps questions at 300 characters.
MAX_LENGTH = 300


@pytest.fixture(scope="module")
def evals() -> dict[str, Any]:
    with QUESTIONS.open("rb") as file:
        return tomllib.load(file)


def test_forty_questions_with_unique_ids(evals: dict[str, Any]) -> None:
    ids = [question["id"] for question in evals["questions"]]

    assert len(ids) == 40
    assert len(set(ids)) == len(ids)


def test_a_follow_up_gives_the_exchange_before_it(evals: dict[str, Any]) -> None:
    follow_ups = [question for question in evals["questions"] if "previous" in question]

    assert follow_ups
    for question in follow_ups:
        assert set(question["previous"]) == {"question", "answer"}, question["id"]
        assert len(question["previous"]["question"]) <= MAX_LENGTH, question["id"]


def test_questions_fit_the_page(evals: dict[str, Any]) -> None:
    for question in evals["questions"]:
        assert question["category"] in CATEGORIES, question["id"]
        assert len(question["text"]) <= MAX_LENGTH, question["id"]
        assert question["answer"].strip(), question["id"]


def test_questions_in_scope_name_a_declared_tool(evals: dict[str, Any]) -> None:
    in_scope = [question for question in evals["questions"] if not question.get("refuse")]

    for question in in_scope:
        assert question["tool"] in evals["tools"], question["id"]
        assert isinstance(question["arguments"], dict), question["id"]
        assert isinstance(question["figures"], list), question["id"]
    assert sum(bool(question["figures"]) for question in in_scope) >= 25


def test_questions_out_of_scope_call_no_tool(evals: dict[str, Any]) -> None:
    refused = [question for question in evals["questions"] if question.get("refuse")]

    assert {question["category"] for question in refused} == {"off-topic", "injection"}
    for question in refused:
        assert "tool" not in question, question["id"]
        assert "figures" not in question, question["id"]
