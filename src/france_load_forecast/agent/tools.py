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
# Fields of a gap that are not terms.
TOTALS = ("actual", "reference", "gap")
DATES = ("published", "consolidated_until", "temperature_until", "measured_until")


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
    meta = bundle["meta"]
    # Every result says which publication it comes from and how recent its data are.
    published = {key: meta[key] for key in DATES}

    @tool
    def forecast(month: str | None = None) -> str:
        """Monthly energy forecast in TWh: P50, the P10-P90 band and the energy already measured.

        P50 is the median forecast. P10 and P90 bound a band calibrated on the errors of past
        forecasts: they are not scenarios. A month marked provisional relies on real-time data.
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
                return _json(published | entry)
        first, last = content["months"][0]["month"], content["months"][-1]["month"]
        return _error(f"no forecast for {month}: the forecast covers {first} to {last}")

    @tool
    def month_gap(month: str) -> str:
        """Why the energy of a month (YYYY-MM) differs from the forecast made at its start
        (vs_forecast) and from the same month a year earlier (vs_year_before), in TWh: the energy
        of each, both gaps, then each term of both gaps side by side. The terms are climate,
        calendar, lockdown, structural (level and seasonal states) and residual. Also the mean
        temperature of the month, its reference (normal) temperature and the temperature of the
        same month a year earlier, in °C. The climate term vs_year_before compares the weather of
        the two months; vs_forecast, it compares the weather of the month with the past years
        that the forecast replayed, not with the reference temperature."""
        for entry in bundle["gaps"]["months"]:
            if entry["month"] != month:
                continue
            to_forecast, to_year_before = entry["against_forecast"], entry["against_year_before"]
            year, number = month.split("-")
            content = {
                "month": month,
                "forecast_made_on": f"{month}-01",
                "year_before": f"{int(year) - 1}-{number}",
                "provisional": entry["provisional"],
                "energy": {
                    "actual": to_forecast["actual"],
                    "forecast": to_forecast["reference"],
                    "year_before": to_year_before["reference"],
                },
                "gap": {"vs_forecast": to_forecast["gap"], "vs_year_before": to_year_before["gap"]},
                "terms": {
                    term: {"vs_forecast": to_forecast[term], "vs_year_before": to_year_before[term]}
                    for term in to_forecast
                    if term not in TOTALS
                },
                "temperature": entry["temperature"],
            }
            return _json(published | content)
        months = [entry["month"] for entry in bundle["gaps"]["months"]]
        return _error(f"no gap for {month}: available months are {months[0]} to {months[-1]}")

    @tool
    def annual_energy(first: int, last: int) -> str:
        """Annual energy in TWh of the whole years from `first` to `last`: gross and
        climate-corrected, this tool's (mainland France without Corsica, keys gross and
        corrected) and RTE's (with Corsica, keys gross_rte and corrected_rte), with the change
        of this tool's energies from the year before. Consumption means gross energy unless the
        question asks for climate-corrected energy."""
        if first > last:
            return _error(f"first ({first}) is after last ({last})")
        years = {year["year"]: year for year in bundle["history"]["years"]}
        selected = []
        for year in range(first, last + 1):
            if year not in years:
                available = f"{min(years)} to {max(years)}"
                return _error(f"no whole year {year}: available years are {available}")
            entry = dict(years[year])
            if year - 1 in years:
                gross, corrected = years[year - 1]["gross"], years[year - 1]["corrected"]
                entry["change"] = {
                    "from_year": year - 1,
                    "gross": round(entry["gross"] - gross, 3),
                    "gross_pct": round(100 * (entry["gross"] / gross - 1), 2),
                    "corrected": round(entry["corrected"] - corrected, 3),
                    "corrected_pct": round(100 * (entry["corrected"] / corrected - 1), 2),
                }
            selected.append(entry)
        return _json(published | {"years": selected})

    @tool
    def thermosensitivity() -> str:
        """Load increase in GW for 1 °C less: mean over December to February, and by
        temperature. A negative value means that warmer weather raises the load, through
        cooling."""
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
        actual months inside the P10-P90 band, all horizons together, in %."""
        return _json(published | bundle["accuracy"])

    @tool
    def fact(topic: FactTopic) -> str:
        """Dated and sourced fact on the method, the data sources, their perimeter, the revision
        of real-time data or the publication of temperatures."""
        content = published | facts[topic]
        if topic == "revision" and meta["revision"]:
            content |= {"revision_gw": meta["revision"]["gw"], "days": meta["revision"]["days"]}
        return _json(content)

    @tool
    def scenario(
        year: int | None = None,
        trajectory: Literal["stagnation", "slow", "rapid"] = "stagnation",
        winter: Literal["normal", "cold", "mild"] = "normal",
    ) -> str:
        """Energy in TWh of a calendar year ahead under a scenario: a consumption trajectory of
        RTE's Bilan prévisionnel 2025 (stagnation, slow or rapid decarbonisation), applied as
        growth rates to today's level, and a winter (normal, or cold or mild as observed about
        once in ten years). Gives the annual energy and the energy of January, February and
        December, next to the reference: normal winter and stagnation. Without a year, the first
        year of the scenarios."""
        content = bundle["scenarios"]
        years = content["years"]
        year = year or years[0]
        if year not in years:
            return _error(f"no scenario for {year}: years are {years[0]} to {years[-1]}")
        cases = {(c["year"], c["trajectory"], c["winter"]): c for c in content["cases"]}
        case, reference = cases[year, trajectory, winter], cases[year, "stagnation", "normal"]
        about = content["trajectories"][trajectory]
        result = published | {
            "year": year,
            "years": years,
            "trajectory": about["label"],
            "growth_pct": about["growth_pct"][str(year)],
            "source": f"{content['source']}, {about['pages']}",
            "winter": winter,
            "annual_energy": case["annual_energy"],
            "winter_energy": case["winter_energy"],
            "reference": {
                "annual_energy": reference["annual_energy"],
                "winter_energy": reference["winter_energy"],
            },
            "change": {
                key: round(case[key] - reference[key], 3)
                for key in ("annual_energy", "winter_energy")
            },
        }
        if winter != "normal":
            replayed = content["replayed_winters"]
            result["replays_the_winter_months_of"] = next(
                r["weather_year"] for r in replayed if (r["year"], r["winter"]) == (year, winter)
            )
            result["frequency"] = "about 1 year in 10"
        return _json(result)

    return [forecast, month_gap, annual_energy, thermosensitivity, accuracy, fact, scenario]
