"""The monthly note: key figures written by code, then a reading written by the agent.

The note is in French, like the page. It explains one month against the forecast made at its
start and against the same month a year earlier.
"""

from datetime import date
from typing import Any

from langchain_core.language_models import BaseChatModel

from france_load_forecast.agent.agent import AgentConfig, Answer, ask
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
Write the reading of the monthly note on {month}, in one paragraph. The note already gives the \
energy of the month, its gap to the forecast made at the start of the month, its gap to the same \
month a year earlier, and a table of the terms of both gaps. Call month_gap for {month}, then \
explain what drives each gap, naming every term of at least 0.05 TWh in absolute value. Do not \
repeat the table.\
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


def write(
    month: str,
    bundle: Bundle,
    facts: dict[str, dict[str, Any]],
    model: BaseChatModel,
    config: AgentConfig,
) -> tuple[str, Answer]:
    """The note on `month` (YYYY-MM), and the checked reading the agent wrote for it."""
    entries = {entry["month"]: entry for entry in bundle["gaps"]["months"]}
    if month not in entries:
        raise ValueError(f"no gap for {month} in the bundle: available are {sorted(entries)}")
    reading = ask(READING.format(month=month), bundle, facts, model, config, words=150)
    return render(entries[month], bundle["meta"], reading.text), reading
