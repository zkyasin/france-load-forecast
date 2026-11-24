"""Build public/grid/mix.json, the hourly mix of the hour-by-hour chapter, from éCO2mix.

Inputs, in a folder given as the first argument, from RTE éCO2mix on ODRÉ (Licence Ouverte 2.0):
mix-tr.csv and mix-june.csv, exports of eco2mix-national-tr and eco2mix-national-cons-def with
`select=date_heure,consommation,nucleaire,eolien,solaire,hydraulique,gaz,charbon,fioul,
bioenergies,pompage,ech_physiques` over one day each, every 15 minutes, separated by semicolons.

Each value is averaged by hour of the day in Paris time, in MW; missing values are left out.
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
FUELS = ["nucleaire", "hydraulique", "eolien", "solaire", "gaz", "charbon", "fioul", "bioenergies"]
OUT = Path(__file__).resolve().parent.parent / "public" / "grid" / "mix.json"


def number(text: str) -> float | None:
    text = text.strip()
    if text in ("", "ND", "-"):
        return None
    return float(text)


def day_mix(path: Path) -> dict:
    sums: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    day = None
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            local = datetime.fromisoformat(row["date_heure"]).astimezone(PARIS)
            day = local.date().isoformat()
            for key in ["consommation", *FUELS, "pompage", "ech_physiques"]:
                value = number(row[key])
                if value is not None:
                    sums[local.hour][key] += value
                    counts[local.hour][key] += 1
    hours = []
    for h in range(24):
        hours.append(
            {
                key: round(sums[h][key] / counts[h][key]) if counts[h][key] else None
                for key in ["consommation", *FUELS, "pompage", "ech_physiques"]
            }
        )
    return {"day": day, "hours": hours}


def main() -> None:
    folder = Path(sys.argv[1])
    mix = {
        "source": "RTE, éCO2mix (ODRÉ), Licence Ouverte 2.0",
        "unit": "MW, moyenne de chaque heure, heure de Paris",
        "days": [day_mix(folder / "mix-june.csv"), day_mix(folder / "mix-tr.csv")],
    }
    OUT.write_text(json.dumps(mix, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
