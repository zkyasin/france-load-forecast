"""Client for the stock of rechargeable cars that Agence ORE, the agency of the French energy
network operators, publishes by commune."""

import csv
from pathlib import Path

import httpx

STOCK_URL = (
    "https://opendata.agenceore.fr/data-fair/api/v1/datasets/"
    "voitures-par-commune-par-energie/values_agg"
)
# Mainland France without Corsica, as the national load: the communes of Corsica and of the
# overseas departments are left out.
MAINLAND = "NOT codgeo:2A* AND NOT codgeo:2B* AND NOT codgeo:97*"


def download_car_stock(client: httpx.Client, dest: Path) -> None:
    """Write the stock of rechargeable cars at each date of the dataset, summed over the communes
    of mainland France without Corsica, to a CSV file of date;cars."""
    params: dict[str, str | int] = {
        "field": "date_arrete",
        "metric": "sum",
        "metric_field": "nb_vp_rechargeables_el",
        "qs": MAINLAND,
        "agg_size": 100,
    }
    response = client.get(STOCK_URL, params=params)
    response.raise_for_status()
    content = response.json()
    if content["total_other"]:
        raise ValueError("more dates than one request returns")
    rows = sorted((bucket["value"][:10], bucket["metric"]) for bucket in content["aggs"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    with partial.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter=";", lineterminator="\n")
        writer.writerow(["date", "cars"])
        writer.writerows(rows)
    partial.replace(dest)
