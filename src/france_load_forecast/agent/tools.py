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
# Files of the bundle that the tools read.
FILES = (
    "meta",
    "forecast",
    "gaps",
    "history",
    "accuracy",
    "model",
    "scenarios",
    "peak",
    "drivers",
)
# Percent of the time the P10-P90 band should hold the actual energy, as set by
# conformal.QUANTILES. The question API runs without the forecasting stack, hence the copy.
BAND_LEVEL_PCT = 80


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


def _by_winter(months: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """The months from December to February, by winter, named by the year of its December."""
    by_winter: dict[int, list[dict[str, Any]]] = {}
    for entry in months:
        year, month = int(entry["month"][:4]), int(entry["month"][5:])
        if month in (12, 1, 2):
            by_winter.setdefault(year if month == 12 else year - 1, []).append(entry)
    return by_winter


def last_winter(peaks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The highest of the monthly peaks of the last winter measured in full, with the name of
    that winter."""
    by_winter = _by_winter(peaks)
    whole = [winter for winter, months in by_winter.items() if len(months) == 3]
    if not whole:
        return None
    winter = max(whole)
    return {"winter": f"{winter}-{winter + 1}"} | max(by_winter[winter], key=lambda m: m["peak"])


def coming_winter(forecast: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The month of the first winter ahead with the highest P50, with the name of that winter."""
    by_winter = _by_winter(forecast)
    if not by_winter:
        return None
    winter = min(by_winter)
    return {"winter": f"{winter}-{winter + 1}"} | max(by_winter[winter], key=lambda m: m["p50"])


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
        band = {"band_level_pct": BAND_LEVEL_PCT}
        if month is None:
            months = [m for m in content["months"] if m["month"] >= content["current_month"]]
            return _json(
                published
                | band
                | {
                    "current_month": content["current_month"],
                    "total_p50": content["total_p50"],
                    "months": months,
                }
            )
        for entry in content["months"]:
            if entry["month"] == month:
                return _json(published | band | entry)
        first, last = content["months"][0]["month"], content["months"][-1]["month"]
        return _error(f"no forecast for {month}: the forecast covers {first} to {last}")

    @tool
    def month_gap(month: str) -> str:
        """Why the energy of a month (YYYY-MM) differs from the forecast made at its start
        (vs_forecast) and from the same month a year earlier (vs_year_before), in TWh: the energy
        of each, both gaps, then each term of both gaps side by side. The terms are climate,
        calendar, lockdown, structural (level and seasonal states) and residual. Also the mean
        temperature, in °C, of the month (actual), of the past weather the forecast assumed
        (forecast) and of the same month a year earlier (year_before), and the normal temperature
        of the month (normal). The climate term vs_forecast compares the weather of the month with
        the weather the forecast assumed; vs_year_before, with the weather of the same month a
        year earlier."""
        for entry in bundle["gaps"]["months"]:
            if entry["month"] != month:
                continue
            to_forecast, to_year_before = entry["against_forecast"], entry["against_year_before"]
            temperature = entry["temperature"]
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
                "temperature": {
                    "actual": temperature["mean"],
                    "forecast": temperature["forecast"],
                    "year_before": temperature["year_before"],
                    "normal": temperature["reference"],
                },
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

    @tool
    def peak(month: str | None = None) -> str:
        """Monthly peak in GW, the highest half-hour of a month: for a month ahead, P50, the P10-P90
        band and the highest day measured so far; for a past month, its peak and the day of it.

        P10 and P90 bound a band calibrated on the errors of past forecasts: they are not
        scenarios. band_coverage_pct is the share of past monthly peaks that fell inside it.
        With `month` (YYYY-MM), that month. Without it, the current month and the 11 after, the
        highest month of the coming winter, the peak of the last winter, and how much one degree
        less raises the peak in winter.
        """
        content = bundle["peak"]
        band = {
            "band_level_pct": BAND_LEVEL_PCT,
            "band_coverage_pct": content["accuracy"]["coverage"]["all months"],
        }
        measured = {entry["month"]: entry for entry in content["history"]}
        ahead = [m for m in content["months"] if m["month"] >= content["current_month"]]
        if month is None:
            return _json(
                published
                | band
                | {
                    "current_month": content["current_month"],
                    "months": ahead,
                    "coming_winter_peak": coming_winter(ahead),
                    "last_winter_peak": last_winter(content["history"]),
                    "winter_rise_per_degree_less_gw": content["winter_gw_per_c"],
                }
            )
        if month in measured:
            return _json(published | measured[month])
        for entry in content["months"]:
            if entry["month"] == month:
                return _json(published | band | entry)
        first, last_month = content["history"][0]["month"], content["months"][-1]["month"]
        return _error(f"no peak for {month}: peaks cover {first} to {last_month}")

    @tool
    def drivers() -> str:
        """Energy of electric cars and of large industry, and what changed climate-corrected
        consumption between the base year, before the crises, and the last twelve months, in TWh:
        for consumption and for each of its parts, the energy of both periods and the change.
        Electric cars are estimated from their stock. Large industry is the energy RTE's grid
        delivers to large industrial sites; its change splits into the part due to its production
        and the part due to its energy per unit produced. The rest is households, businesses and
        services: the data do not tell prices, sobriety, efficiency or heat pumps apart in it.
        Also the energy of each part in each whole year."""
        content = bundle["drivers"]
        base, now, parts = content["base"], content["now"], content["contributions"]
        cars = content["cars"]
        industry = parts["industry_activity"] + parts["industry_intensity"]

        def energies(key: str, change: float) -> dict[str, float]:
            return {
                "base_year": base[key],
                "last_twelve_months": now[key],
                "change": round(change, 3),
                "change_pct": round(100 * change / base[key], 2),
            }

        return _json(
            published
            | {
                "base_year": content["base_year"],
                "last_twelve_months": f"{content['first_month']} to {content['last_month']}",
                "consumption": energies("consumption", now["consumption"] - base["consumption"]),
                "large_industry": energies("industry", industry)
                | {
                    "change_due_to_production": parts["industry_activity"],
                    "change_due_to_energy_per_unit_produced": parts["industry_intensity"],
                    "production_change_pct": round(now["activity_index"] - 100, 2),
                },
                "electric_cars": {
                    "base_year": base["electric_cars"],
                    "last_twelve_months": now["electric_cars"],
                    "change": parts["electric_cars"],
                    "cars_millions": {
                        "base_year": base["cars_millions"],
                        "last_twelve_months": now["cars_millions"],
                    },
                    "mwh_per_car": cars["mwh_per_car"],
                    "estimate": f"{cars['reference_twh']} TWh in {cars['reference_year']},"
                    f" {cars['source']}",
                },
                "rest": energies("rest", parts["rest"]),
                "years": [
                    {
                        "year": year["year"],
                        "consumption": year["consumption"],
                        "large_industry": year["industry"],
                        "electric_cars": year["electric_cars"],
                        "rest": year["rest"],
                    }
                    for year in content["years"]
                ],
            }
        )

    return [
        forecast,
        month_gap,
        annual_energy,
        thermosensitivity,
        accuracy,
        fact,
        scenario,
        peak,
        drivers,
    ]
