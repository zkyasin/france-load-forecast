from pathlib import Path

import httpx
import pytest

from france_load_forecast.odre import download_export

CSV = "date;heure;consommation\r\n2026-09-01;00:00;42233\r\n"


def test_download_writes_the_export(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=CSV)

    dest = tmp_path / "raw" / "export.csv"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        download_export(
            client,
            "eco2mix-national-tr",
            dest,
            select="date,heure,consommation",
            where="consommation IS NOT NULL",
        )

    assert dest.read_bytes() == CSV.encode()
    assert requests[0].url.path.endswith("/datasets/eco2mix-national-tr/exports/csv")
    assert requests[0].url.params["select"] == "date,heure,consommation"
    assert requests[0].url.params["where"] == "consommation IS NOT NULL"


def test_failed_download_leaves_no_file(tmp_path: Path) -> None:
    dest = tmp_path / "export.csv"
    transport = httpx.MockTransport(lambda request: httpx.Response(503))

    with httpx.Client(transport=transport) as client, pytest.raises(httpx.HTTPStatusError):
        download_export(client, "eco2mix-national-tr", dest, select="date")

    assert list(tmp_path.iterdir()) == []
