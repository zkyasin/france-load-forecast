"""Build public/relief/, the relief of French consumption, from éCO2mix.

Inputs, in a folder given as the first argument, exported from ODRÉ (RTE, Licence Ouverte 2.0)
with `select=date_heure,consommation` as CSV separated by semicolons:
- cons-def.csv: dataset eco2mix-national-cons-def, consolidated and final data, every 30 min.
- tr.csv: dataset eco2mix-national-tr, real-time data, every 15 min, used after the last
  consolidated value.

Outputs:
- relief.bin: for each day from 1 January 2012 to the last complete day, 24 hourly means in
  Paris time, as little-endian uint16 in units of 50 MW. 0 means no value.
- relief.json: the dates covered, the source and a few facts computed from the same values.

Each local hour is the mean of the values that start in it. On the spring day without 2:00, that
hour is left empty (0). On the autumn day with two 2:00, both are averaged.
"""

import csv
import json
import struct
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
START = date(2012, 1, 1)
UNIT = 50  # MW


def read(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file, delimiter=";"):
            if row["consommation"]:
                yield datetime.fromisoformat(row["date_heure"]), float(row["consommation"])


def main() -> None:
    folder = Path(sys.argv[1])
    out = Path(__file__).resolve().parent.parent / "public" / "relief"
    out.mkdir(parents=True, exist_ok=True)

    sums: dict[tuple[date, int], list[float]] = defaultdict(lambda: [0.0, 0])
    last_def = None
    for moment, value in read(folder / "cons-def.csv"):
        last_def = moment if last_def is None or moment > last_def else last_def
        local = moment.astimezone(PARIS)
        cell = sums[(local.date(), local.hour)]
        cell[0] += value
        cell[1] += 1
    for moment, value in read(folder / "tr.csv"):
        if last_def is not None and moment <= last_def:
            continue
        local = moment.astimezone(PARIS)
        cell = sums[(local.date(), local.hour)]
        cell[0] += value
        cell[1] += 1

    days_seen = sorted({day for day, _ in sums})
    # The last complete day: its 23:00 is there, and all its hours but the one lost in spring.
    end = max(
        d for d in days_seen if (d, 23) in sums and sum((d, h) in sums for h in range(24)) >= 23
    )
    count = (end - START).days + 1
    hourly: list[list[float | None]] = []
    for i in range(count):
        day = START + timedelta(days=i)
        row = []
        for hour in range(24):
            cell = sums.get((day, hour))
            row.append(cell[0] / cell[1] if cell else None)
        hourly.append(row)

    with (out / "relief.bin").open("wb") as file:
        for row in hourly:
            file.write(struct.pack("<24H", *(round(v / UNIT) if v else 0 for v in row)))

    def day_of(i: int) -> str:
        return (START + timedelta(days=i)).isoformat()

    # Facts for the story, all computed here from the same hourly means.
    peak = max(
        ((v, i, h) for i, row in enumerate(hourly) for h, v in enumerate(row) if v),
        key=lambda t: t[0],
    )

    def energy(first: date, last: date) -> float:
        total = 0.0
        for i in range((first - START).days, (last - START).days + 1):
            total += sum(v for v in hourly[i] if v)
        return total / 1e6  # TWh

    april = {y: energy(date(y, 4, 1), date(y, 4, 30)) for y in range(2015, 2021)}
    april_before = sum(april[y] for y in range(2015, 2020)) / 5
    winter = {
        y: energy(date(y, 11, 1), date(y + 1, 2, 28 if (y + 1) % 4 else 29))
        for y in range(2014, 2023)
    }
    winter_before = sum(winter[y] for y in range(2014, 2019)) / 5

    last = hourly[-1]
    low = min(range(24), key=lambda h: last[h] or 1e9)
    high = max(range(24), key=lambda h: last[h] or 0)
    meta = {
        "source": "RTE, éCO2mix (ODRÉ), Licence Ouverte 2.0",
        "start": START.isoformat(),
        "end": end.isoformat(),
        "days": count,
        "unit_mw": UNIT,
        "consolidated_until": last_def.astimezone(PARIS).date().isoformat() if last_def else None,
        "peak": {"day": day_of(peak[1]), "hour": peak[2], "mw": round(peak[0])},
        "last_day": {
            "day": end.isoformat(),
            "low": {"hour": low, "mw": round(last[low] or 0)},
            "high": {"hour": high, "mw": round(last[high] or 0)},
            "twh": round(sum(v for v in last if v) / 1e6, 3),
        },
        "april_2020": {
            "twh": round(april[2020], 2),
            "mean_2015_2019": round(april_before, 2),
        },
        "winter_2022": {
            "twh": round(winter[2022], 2),
            "mean_2014_2018": round(winter_before, 2),
        },
    }
    (out / "relief.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
