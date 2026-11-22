"""The notes of notes/, which the page shows, checked as flf note checks them before writing."""

import json
from pathlib import Path

import pytest

from france_load_forecast.agent import note

NOTES = sorted((Path(__file__).parents[1] / "notes").glob("*.json"))


@pytest.mark.parametrize("path", NOTES, ids=[path.stem for path in NOTES])
def test_every_figure_of_a_reading_comes_from_its_note(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["month"] == path.stem
    assert data["reading"]
    assert note.unsupported(data) == []


@pytest.mark.parametrize("path", NOTES, ids=[path.stem for path in NOTES])
def test_markdown_note_has_the_same_reading(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    markdown = path.with_suffix(".md").read_text(encoding="utf-8")

    assert f"## Lecture\n\n{data['reading']}\n" in markdown
