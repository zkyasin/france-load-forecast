"""Client for monthly series of INSEE's macroeconomic database (BDM), read through its SDMX web
service, which needs no key."""

import csv
import math
from collections.abc import Mapping
from pathlib import Path
from xml.etree import ElementTree

import httpx

DATA_URL = "https://bdm.insee.fr/series/sdmx/data/{flow}/{key}"


def monthly_values(xml: str) -> dict[str, float]:
    """The values of the single series of an SDMX response, by month (YYYY-MM)."""
    series = list(ElementTree.fromstring(xml).iter("Series"))
    if len(series) != 1:
        raise ValueError(f"expected one series, got {len(series)}")
    values = {
        obs.attrib["TIME_PERIOD"]: float(obs.attrib.get("OBS_VALUE", "nan"))
        for obs in series[0].iter("Obs")
    }
    return {month: value for month, value in values.items() if math.isfinite(value)}


def download_series(
    client: httpx.Client, series: Mapping[str, tuple[str, str]], dest: Path, start: str
) -> None:
    """Write the values of each series from `start` (YYYY-MM) to a CSV file of month;series;value,
    a month being its first day. `series` gives the SDMX flow and key of each series by name."""
    rows = []
    for name, (flow, key) in series.items():
        response = client.get(DATA_URL.format(flow=flow, key=key), params={"startPeriod": start})
        response.raise_for_status()
        values = monthly_values(response.text)
        rows += [(f"{month}-01", name, value) for month, value in sorted(values.items())]
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    with partial.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter=";", lineterminator="\n")
        writer.writerow(["month", "series", "value"])
        writer.writerows(rows)
    partial.replace(dest)
