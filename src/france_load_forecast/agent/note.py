"""The monthly note: key figures written by code, then a reading written by the agent.

The note is in French, like the page. It explains one month against the forecast made at its
start and against the same month a year earlier. It is written twice: in Markdown for readers of
the repository, and in JSON for the page.
"""

import re
from datetime import date
from typing import Any

from langchain_core.language_models import BaseChatModel

from france_load_forecast.agent.agent import AgentConfig, Answer, ask, plain
from france_load_forecast.agent.tools import TOTALS, Bundle

MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
# Components without a label here keep their name from config/model.toml.
LABELS = {
    "climate": "Climat",
    "calendar": "Calendrier",
    "lockdown": "Confinements",
    "structural": "Structurel",
    "residual": "Résidu",
}

READING = """\
Write the reading of the monthly note on {month}. The note already gives the energy of the month, \
the total of both gaps, a table of their terms and the date of the data: do not write them again. \
Call month_gap for {month}, then write two short paragraphs of plain text, without asterisks or \
Markdown, with one sentence per term, as « Le résidu a pesé <valeur> TWh. », where the value \
has its sign as a symbol, + or -, and a decimal comma.
The first paragraph is about the gap to the forecast made at the start of the month. Its climate \
term compares the weather of the month with the past years that the forecast replayed, not with \
the reference temperature, so give no temperature in this paragraph.
The second paragraph is about the gap to the same month a year earlier. Begin it with « Par \
rapport à » and that month, and give the temperature of the month and that of the year before in \
the sentence on the climate term.
Name only the terms of at least 0.05 TWh in absolute value, without quoting that threshold. Do not \
judge their size, with words such as fortement, légèrement or principalement, and do not say that \
a term explains the gap. In French, the terms are le climat, le calendrier, les confinements, le \
terme structurel and le résidu.\
"""


def _month_name(month: str) -> str:
    year, number = month.split("-")
    return f"{MONTHS[int(number) - 1]} {year}"


def _date_name(day: str) -> str:
    parsed = date.fromisoformat(day)
    return f"{parsed.day} {MONTHS[parsed.month - 1]} {parsed.year}"


def _energy(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _gap(value: float) -> str:
    return "0,00" if round(value, 2) == 0 else f"{value:+.2f}".replace(".", ",")


def render(entry: dict[str, Any], meta: dict[str, Any], reading: str) -> str:
    """The note on the month of `entry`, an entry of the bundle's gaps."""
    to_forecast, to_year_before = entry["against_forecast"], entry["against_year_before"]
    year, number = entry["month"].split("-")
    previous = _month_name(f"{int(year) - 1}-{number}")
    header = f"*Données publiées le {_date_name(meta['published'])}."
    if entry["provisional"] and meta["revision"]:
        revision = f"{meta['revision']['gw']:+.2f}".replace(".", ",")
        header += (
            f" Mois provisoire : données en temps réel relevées de {revision} GW en attendant"
            " les données consolidées."
        )
    terms = [term for term in to_forecast if term not in TOTALS]
    lines = [
        f"# {_month_name(entry['month']).capitalize()}",
        "",
        header + "*",
        "",
        f"La consommation a atteint {_energy(to_forecast['actual'])} TWh, soit"
        f" {_gap(to_forecast['gap'])} TWh par rapport à la prévision faite en début de mois"
        f" ({_energy(to_forecast['reference'])} TWh) et {_gap(to_year_before['gap'])} TWh par"
        f" rapport à {previous} ({_energy(to_year_before['reference'])} TWh).",
        "",
        f"| Terme, en TWh | Écart à la prévision | Écart à {previous} |",
        "|---|---:|---:|",
        *(
            f"| {LABELS.get(term, term)} | {_gap(to_forecast[term])} |"
            f" {_gap(to_year_before[term])} |"
            for term in terms
        ),
        f"| **Total** | **{_gap(to_forecast['gap'])}** | **{_gap(to_year_before['gap'])}** |",
        "",
        "## Lecture",
        "",
        reading.strip(),
        "",
        "*Sources : données de RTE publiées sur ODRÉ sous Licence Ouverte 2.0. Méthode :"
        " docs/methodology.md.*",
    ]
    return "\n".join(lines) + "\n"


# A figure of a reading: the sign written before it, its value and its unit, if any. A figure
# glued to a letter, such as 1er, is a label.
FIGURE = re.compile(r"(?<![\w,])([+\u2212]?)(\d+(?:,\d+)?)(?![\w,])(?:[ \u00a0](TWh|°C))?")


def unsupported(data: dict[str, Any]) -> list[str]:
    """Figures of the reading of a note that the note's own values do not give. An energy must be
    one of its energies or terms, a temperature one of its temperatures, with the same sign when
    one is written; a figure without a unit must be the year of the month or the year before."""
    year = int(data["month"][:4])
    pools: dict[str, list[float]] = {
        "TWh": [*data["against_forecast"].values(), *data["against_year_before"].values()],
        "°C": list(data["temperature"].values()),
        "": [year, year - 1],
    }
    wrong = []
    for sign, figure, unit in FIGURE.findall(data["reading"]):
        tolerance = 0.5 * 10 ** -len(figure.partition(",")[2]) + 1e-9
        value = float(figure.replace(",", "."))
        candidates = [v for v in pools[unit] if not sign or (v < 0) == (sign == "\u2212")]
        if not any(abs(abs(v) - value) <= tolerance for v in candidates):
            wrong.append(f"{sign}{figure} {unit}".strip())
    return wrong


def record(entry: dict[str, Any], meta: dict[str, Any], reading: str, model: str) -> dict[str, Any]:
    """The note as the page reads it: the gaps of the month, the reading and the model that wrote
    it."""
    return {"published": meta["published"], "model": model, **entry, "reading": reading.strip()}


def write(
    month: str,
    bundle: Bundle,
    facts: dict[str, dict[str, Any]],
    model: BaseChatModel,
    config: AgentConfig,
) -> tuple[str, dict[str, Any], Answer]:
    """The note on `month` (YYYY-MM) in Markdown and in JSON, and the checked reading the agent
    wrote for it. The climate terms already hold the response to temperature, so the agent reads
    the gaps of the month only."""
    entries = {entry["month"]: entry for entry in bundle["gaps"]["months"]}
    if month not in entries:
        raise ValueError(f"no gap for {month} in the bundle: available are {sorted(entries)}")
    reading = ask(
        READING.format(month=month),
        bundle,
        facts,
        model,
        config,
        words=130,
        only={"month_gap"},
        cite=False,
    )
    text = plain(reading.text)
    entry, meta = entries[month], bundle["meta"]
    return render(entry, meta, text), record(entry, meta, text, config.model), reading
