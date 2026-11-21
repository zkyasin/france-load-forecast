"""Client for dataset exports of ODRÉ, the open data portal of the French energy networks."""

from pathlib import Path

import httpx

EXPORT_URL = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/{dataset}/exports/csv"


def download_export(
    client: httpx.Client,
    dataset: str,
    dest: Path,
    *,
    select: str,
    where: str | None = None,
) -> None:
    """Stream the CSV export of a dataset to `dest`."""
    params = {"select": select}
    if where:
        params["where"] = where
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Write under a temporary name so that an interrupted download never looks complete.
    partial = dest.with_name(dest.name + ".part")
    with client.stream("GET", EXPORT_URL.format(dataset=dataset), params=params) as response:
        response.raise_for_status()
        with partial.open("wb") as file:
            for chunk in response.iter_bytes():
                file.write(chunk)
    partial.replace(dest)
