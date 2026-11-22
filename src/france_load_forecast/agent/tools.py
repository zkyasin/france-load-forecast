"""Read-only tools over the weekly bundle.

Each tool returns a JSON object with the figures the agent may quote, or an `error` message the
agent can act on. Energies are in TWh and powers in GW.
"""

import json
import tomllib
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import BaseTool, tool

Bundle = dict[str, dict[str, Any]]
FactTopic = Literal["method", "sources", "perimeter", "revision", "temperature"]


def load_bundle(path: Path) -> Bundle:
    """The JSON files written by `flf publish`, by name."""
    return {file.stem: json.loads(file.read_text(encoding="utf-8")) for file in path.glob("*.json")}


def load_facts(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("rb") as file:
        return {
            topic: {"text": fact["text"], "source": fact["source"], "date": str(fact["date"])}
            for topic, fact in tomllib.load(file).items()
        }


def _json(content: dict[str, Any]) -> str:
    return json.dumps(content, ensure_ascii=False)


def _error(message: str) -> str:
    return _json({"error": message})


def make_tools(bundle: Bundle, facts: dict[str, dict[str, Any]]) -> list[BaseTool]:
    """The agent's tools, reading `bundle` and `facts`."""
    published = {"published": bundle["meta"]["published"]}

    @tool
    def forecast(month: str | None = None) -> str:
        """Monthly energy forecast in TWh: P10, P50, P90 and the energy already measured.

        With `month` (YYYY-MM), the forecast of that month. Without it, the current month and
        the 11 after, with the total P50 of these 12 months.
        """
        content = bundle["forecast"]
        if month is None:
            months = [m for m in content["months"] if m["month"] >= content["current_month"]]
            return _json(
                published
                | {
                    "current_month": content["current_month"],
                    "total_p50": content["total_p50"],
                    "months": months,
                }
            )
        for entry in content["months"]:
            if entry["month"] == month:
                measured = {"measured_until": bundle["meta"]["measured_until"]}
                return _json(published | entry | measured)
        first, last = content["months"][0]["month"], content["months"][-1]["month"]
        return _error(f"no forecast for {month}: the forecast covers {first} to {last}")

    @tool
    def month_gap(month: str) -> str:
        """Gap in TWh between the energy of a month (YYYY-MM) and the forecast made at its start,
        and the energy of the same month a year earlier, each split into terms: climate,
        calendar, lockdown, structural (level and seasonal states) and residual. Also the mean
        temperature of the month, its reference (normal) temperature and the temperature of the
        same month a year earlier, in °C."""
        for entry in bundle["gaps"]["months"]:
            if entry["month"] == month:
                year, number = month.split("-")
                return _json(published | entry | {"year_before": f"{int(year) - 1}-{number}"})
        months = [entry["month"] for entry in bundle["gaps"]["months"]]
        return _error(f"no gap for {month}: available months are {months[0]} to {months[-1]}")

    @tool
    def annual_energy(first: int, last: int) -> str:
        """Annual energy in TWh of the whole years from `first` to `last`: gross and
        climate-corrected, ours (mainland France without Corsica) and RTE's (with Corsica), and
        the change of our gross energy from the year before."""
        years = {year["year"]: year for year in bundle["history"]["years"]}
        selected = []
        for year in range(first, last + 1):
            if year not in years:
                return _error(
                    f"no whole year {year}: available years are {min(years)} to {max(years)}"
                )
            entry = dict(years[year])
            if year - 1 in years:
                before = years[year - 1]["gross"]
                entry["gross_change"] = round(entry["gross"] - before, 3)
                entry["gross_change_pct"] = round(100 * (entry["gross"] / before - 1), 2)
            selected.append(entry)
        return _json(published | {"years": selected})

    @tool
    def thermosensitivity() -> str:
        """Load increase in GW for 1 °C less: mean over December to February, and by
        temperature (negative above about 18 °C, where cooling takes over)."""
        content = bundle["model"]
        return _json(
            published
            | {
                "fitted_from": content["fitted_from"],
                "fitted_until": content["fitted_until"],
            }
            | content["thermosensitivity"]
        )

    @tool
    def accuracy() -> str:
        """Accuracy of past forecasts: mean absolute percentage error by horizon, for P50 and two
        naive forecasts (same month a year earlier, raw and climate-corrected), and the share of
        months inside the P10-P90 band, in %."""
        return _json(bundle["accuracy"])

    @tool
    def fact(topic: FactTopic) -> str:
        """Dated and sourced fact on the method, the data sources, their perimeter, the revision
        of real-time data or the publication of temperatures."""
        content = dict(facts[topic])
        meta = bundle["meta"]
        if topic == "revision" and meta["revision"]:
            content |= {"revision_gw": meta["revision"]["gw"], "days": meta["revision"]["days"]}
        if topic in ("revision", "temperature"):
            content |= {key: meta[key] for key in ("consolidated_until", "temperature_until")}
        return _json(content)

    return [forecast, month_gap, annual_energy, thermosensitivity, accuracy, fact]
