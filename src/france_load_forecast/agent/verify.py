"""Check that every number of an answer comes from its sources.

A number of the answer is supported when a number of the sources, rounded to the same number of
decimals, has the same absolute value. Signs are not compared, because answers often state them
in words, as in "1,3 TWh below the forecast". A number glued to a letter, such as P50 or 1er, is
a label and is not checked.
"""

import re
from collections.abc import Iterable

# Not preceded or followed by a letter or a digit, with a decimal comma or point.
FIGURE = re.compile(r"(?<![^\W_])(\d+(?:[.,]\d+)?)(?![^\W_])")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _value(number: str) -> float:
    return float(number.replace(",", "."))


def _supported(figure: str, pool: list[float]) -> bool:
    decimals = len(re.split(r"[.,]", figure)[1]) if re.search(r"[.,]", figure) else 0
    tolerance = 0.5 * 10**-decimals + 1e-9
    value = _value(figure)
    return any(abs(abs(number) - value) <= tolerance for number in pool)


def unsupported(answer: str, sources: Iterable[str]) -> list[str]:
    """Numbers of `answer` that no number of `sources` supports, in order of appearance."""
    pool = [_value(number) for text in sources for number in NUMBER.findall(text)]
    return [figure for figure in FIGURE.findall(answer) if not _supported(figure, pool)]
