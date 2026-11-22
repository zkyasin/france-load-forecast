"""Check that every number of an answer comes from its sources.

A number of the answer is supported when a number of the sources, rounded to the same number of
decimals, has the same absolute value. Signs are not compared, because answers often state them
in words, as in "1,3 TWh below the forecast". A number glued to a letter, such as P50, 1er or
Covid-19, is a label: it is neither checked in the answer nor taken from the sources.
"""

import re
from collections.abc import Iterable

# With a decimal comma or point, not glued to a letter or a digit, nor to a letter and a hyphen.
FIGURE = re.compile(r"(?<![^\W_])(?<![^\W\d_]-)(\d+(?:[.,]\d+)?)(?![^\W_])")


def _value(number: str) -> float:
    return float(number.replace(",", "."))


def _supported(figure: str, pool: list[float]) -> bool:
    decimals = len(re.split(r"[.,]", figure)[1]) if re.search(r"[.,]", figure) else 0
    tolerance = 0.5 * 10**-decimals + 1e-9
    value = _value(figure)
    return any(abs(abs(number) - value) <= tolerance for number in pool)


def unsupported(answer: str, sources: Iterable[str]) -> list[str]:
    """Numbers of `answer` that no number of `sources` supports, in order of appearance."""
    pool = [_value(number) for text in sources for number in FIGURE.findall(text)]
    return [figure for figure in FIGURE.findall(answer) if not _supported(figure, pool)]
