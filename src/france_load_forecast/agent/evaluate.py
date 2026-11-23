"""The frozen questions of evals/questions.toml asked to a model, and scored without a judge.

A question in scope passes when the agent calls the expected tool with the expected arguments, or
with others whose result holds the expected figures, states each expected figure as the tool
returns it, and the verifier accepts its answer. A question out of scope passes when the agent
calls no tool and states no number but a year. Each run keeps the answer, the tool calls, the time
and the tokens, so that models can be compared on the same questions and the same data.
"""

import json
import re
import time
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean, median
from typing import Any

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from france_load_forecast.agent import agent, tools

# A number as a model writes it: maybe a sign or a dash before it, a decimal comma or point.
NUMBER = re.compile(r"(?<![\w,.])[+\-\u2010-\u2014\u2212]?\d+(?:[.,]\d+)?")
YEAR = re.compile(r"(19|20)\d{2}")


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    text: str
    tool: str | None = None
    # The arguments the call must have; others are free.
    arguments: dict[str, Any] = field(default_factory=dict)
    # Fields of the tool result that the answer must state; a dotted name reaches into a field,
    # and "a|b" is stated when either is.
    figures: tuple[str, ...] = ()
    refuse: bool = False
    # The question and the answer just before, for a follow-up.
    previous: tuple[str, str] | None = None


def load_questions(path: Path) -> list[Question]:
    with path.open("rb") as file:
        entries = tomllib.load(file)["questions"]
    return [
        Question(
            id=entry["id"],
            category=entry["category"],
            text=entry["text"],
            tool=entry.get("tool"),
            arguments=entry.get("arguments", {}),
            figures=tuple(entry.get("figures", ())),
            refuse=entry.get("refuse", False),
            previous=(entry["previous"]["question"], entry["previous"]["answer"])
            if "previous" in entry
            else None,
        )
        for entry in entries
    ]


@dataclass(frozen=True)
class Run:
    """What a model did with a question."""

    id: str
    model: str
    # Date of the bundle the agent read.
    published: str
    answer: str
    verified: bool
    problem: str | None
    calls: list[dict[str, Any]]
    seconds: float
    input_tokens: int
    output_tokens: int
    # The type of the exception that stopped the model, such as a rate limit.
    error: str | None = None


def arguments(question: Question, bundle: tools.Bundle) -> dict[str, Any]:
    """The arguments of `question`, with "{current_month}" replaced by the month of the data."""
    current = bundle["forecast"]["current_month"]
    return {
        key: current if value == "{current_month}" else value
        for key, value in question.arguments.items()
    }


def ask(
    question: Question,
    bundle: tools.Bundle,
    facts: dict[str, dict[str, Any]],
    model: BaseChatModel,
    config: agent.AgentConfig,
    name: str,
) -> Run:
    """The run of `question` on `model`, called `name` in the results."""
    start = time.monotonic()
    error, answer = None, None
    with get_usage_metadata_callback() as usage:
        try:
            answer = agent.ask(
                question.text, bundle, facts, model, config, previous=question.previous
            )
        except Exception as failure:  # A rate limit or a timeout is a result too.
            error = type(failure).__name__
    spent = list(usage.usage_metadata.values())
    return Run(
        id=question.id,
        model=name,
        published=bundle["meta"]["published"],
        answer="" if answer is None else answer.text,
        verified=answer is not None and answer.verified,
        problem=None if answer is None else answer.problem,
        calls=[] if answer is None else answer.tool_calls,
        seconds=round(time.monotonic() - start, 1),
        input_tokens=sum(item["input_tokens"] for item in spent),
        output_tokens=sum(item["output_tokens"] for item in spent),
        error=error,
    )


def numbers(text: str) -> list[float]:
    """The numbers of `text`, whatever dash or decimal mark the model wrote."""
    found = []
    for match in NUMBER.findall(text.replace("\u00a0", " ")):
        cleaned = re.sub(r"^[\u2010-\u2014\u2212]", "-", match).replace(",", ".")
        found.append(float(cleaned))
    return found


def stated(value: float, said: list[float]) -> bool:
    """Whether one of `said` gives `value`, rounded to one decimal or within 1 %, either sign."""
    tolerance = max(0.01 * abs(value), 0.05)
    return any(abs(abs(number) - abs(value)) <= tolerance for number in said)


def dig(result: dict[str, Any], dotted: str) -> list[float]:
    """The values of a dotted field of a tool result; of each year, for annual energies."""
    years = result.get("years")
    if isinstance(years, list) and dotted.split(".")[0] not in result:
        rows = [year for year in years if isinstance(year, dict)]
        if rows:
            return [value for row in rows for value in dig(row, dotted)]
    value: Any = result
    for part in dotted.split("."):
        value = value[part]
    return [float(value)]


def leaves(value: Any) -> Iterator[float]:
    """The numbers of a JSON value, however deep."""
    if isinstance(value, dict):
        for item in value.values():
            yield from leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from leaves(item)
    elif isinstance(value, int | float) and not isinstance(value, bool):
        yield float(value)


def fetched(
    call: dict[str, Any], tool: BaseTool, expected: dict[str, Any], values: list[float]
) -> bool:
    """Whether `call` is the expected call of `tool`, or another whose result holds each of
    `values`, as the forecast of every month holds the forecast of one."""
    if call["name"] != tool.name:
        return False
    if all(call["args"].get(key) == value for key, value in expected.items()):
        return True
    if not values:
        return False
    try:
        found = set(leaves(json.loads(tool.invoke(call["args"]))))
    except ValueError:  # Arguments the tool turns down.
        return False
    return all(value in found for value in values)


@dataclass(frozen=True)
class Score:
    id: str
    category: str
    # The expected call was made, or one that fetched the expected figures; none at all for a
    # question out of scope.
    tool: bool
    # The expected figures that the answer does not state.
    missing: tuple[str, ...]
    verified: bool
    passed: bool
    # Why the question failed, as "tool, figures"; empty when it passed.
    reason: str = ""


def _reasons(**failed: bool) -> str:
    return ", ".join(name for name, failing in failed.items() if failing)


def score(
    question: Question, run: Run, bundle: tools.Bundle, facts: dict[str, dict[str, Any]]
) -> Score:
    said = numbers(run.answer)
    if question.refuse:
        silent = all(YEAR.fullmatch(f"{number:g}") for number in said)
        called = bool(run.calls)
        why = _reasons(error=run.error is not None, tool=called, numbers=not silent)
        return Score(question.id, question.category, not called, (), run.verified, not why, why)
    expected = arguments(question, bundle)
    tool = {each.name: each for each in tools.make_tools(bundle, facts)}[str(question.tool)]
    result = json.loads(tool.invoke(expected))
    values = [
        value
        for figure in question.figures
        for name in figure.split("|")
        for value in dig(result, name)
    ]
    called = any(fetched(call, tool, expected, values) for call in run.calls)
    missing = tuple(
        figure
        for figure in question.figures
        if not any(
            all(stated(value, said) for value in dig(result, name)) for name in figure.split("|")
        )
    )
    why = _reasons(
        error=run.error is not None,
        tool=not called,
        figures=bool(missing),
        refused=not run.verified,
    )
    return Score(question.id, question.category, called, missing, run.verified, not why, why)


def pending(questions: Iterable[Question], runs: Iterable[Run]) -> list[Question]:
    """The questions without a run, or whose run stopped on an error: those to ask again."""
    done = {run.id for run in runs if run.error is None}
    return [question for question in questions if question.id not in done]


def read_runs(path: Path) -> list[Run]:
    """The runs kept in `path`, the last of each question."""
    if not path.exists():
        return []
    runs = [Run(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()]
    return list({run.id: run for run in runs}.values())


def write_runs(path: Path, runs: Iterable[Run]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(run), ensure_ascii=False) for run in runs]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


@dataclass(frozen=True)
class Summary:
    model: str
    questions: int
    passed: int
    # In scope: right tool, stated figures among expected ones, verified answers.
    tool: int
    in_scope: int
    figures: int
    expected: int
    verified: int
    # Out of scope: correct refusals.
    refused: int
    out_of_scope: int
    errors: int
    seconds: float
    input_tokens: float
    output_tokens: float


def summarize(
    model: str, questions: list[Question], runs: list[Run], scores: list[Score]
) -> Summary:
    by_id = {question.id: question for question in questions}
    inside = [s for s in scores if not by_id[s.id].refuse]
    outside = [s for s in scores if by_id[s.id].refuse]
    return Summary(
        model=model,
        questions=len(scores),
        passed=sum(s.passed for s in scores),
        tool=sum(s.tool for s in inside),
        in_scope=len(inside),
        figures=sum(len(by_id[s.id].figures) - len(s.missing) for s in inside),
        expected=sum(len(by_id[s.id].figures) for s in inside),
        verified=sum(s.verified for s in inside),
        refused=sum(s.passed for s in outside),
        out_of_scope=len(outside),
        errors=sum(run.error is not None for run in runs),
        seconds=median(run.seconds for run in runs) if runs else 0.0,
        input_tokens=mean(run.input_tokens for run in runs) if runs else 0.0,
        output_tokens=mean(run.output_tokens for run in runs) if runs else 0.0,
    )


def report(questions: list[Question], results: dict[str, tuple[list[Run], list[Score]]]) -> str:
    """A Markdown report of the runs of each model on the same questions."""
    published = sorted({run.published for runs, _ in results.values() for run in runs})
    lines = [
        "# Evaluation of the agent",
        "",
        f"{len(questions)} frozen questions of [questions.toml](questions.toml), asked on the data "
        f"published on {', '.join(published)}. Written by `flf eval`.",
        "",
        "| Model | Passed | Right tool | Figures stated | Verified | Refusals | Errors "
        "| Median time | Tokens in / out |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for model, (runs, scores) in results.items():
        s = summarize(model, questions, runs, scores)
        lines.append(
            f"| {model} | {s.passed}/{s.questions} | {s.tool}/{s.in_scope} "
            f"| {s.figures}/{s.expected} | {s.verified}/{s.in_scope} "
            f"| {s.refused}/{s.out_of_scope} | {s.errors} | {s.seconds:.1f} s "
            f"| {s.input_tokens:,.0f} / {s.output_tokens:,.0f} |"
        )
    models = list(results)
    lines += [
        "",
        "## By question",
        "",
        f"| Question | Category | {' | '.join(models)} |",
        f"|---|---|{'---|' * len(models)}",
    ]
    for question in questions:
        cells = []
        for model in models:
            found = {s.id: s for s in results[model][1]}.get(question.id)
            cells.append(
                "" if found is None else "pass" if found.passed else f"fail: {found.reason}"
            )
        lines.append(f"| {question.id} | {question.category} | {' | '.join(cells)} |")
    return "\n".join(lines) + "\n"
