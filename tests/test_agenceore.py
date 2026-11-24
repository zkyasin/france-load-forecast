from pathlib import Path
from typing import Any

import httpx
import pytest

from france_load_forecast import agenceore


def aggregation(*stocks: tuple[str, int], other: int = 0) -> dict[str, Any]:
    """A response of Data Fair's values_agg, as Agence ORE's portal gives it."""
    return {
        "total": 762618,
        "total_values": len(stocks),
        "total_other": other,
        "aggs": [
            {"total": 34641, "value": f"{day}T00:00:00.000Z", "results": [], "metric": cars}
            for day, cars in stocks
        ],
    }


def test_download_writes_the_mainland_stock_by_date(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json=aggregation(("2026-08-31", 2693367), ("2025-09-30", 2206225))
        )

    dest = tmp_path / "raw" / "cars.csv"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        agenceore.download_car_stock(client, dest)

    assert dest.read_text(encoding="utf-8").splitlines() == [
        "date;cars",
        "2025-09-30;2206225",
        "2026-08-31;2693367",
    ]
    params = requests[0].url.params
    assert (params["metric_field"], params["qs"]) == ("nb_vp_rechargeables_el", agenceore.MAINLAND)


def test_dates_beyond_one_request_fail(tmp_path: Path) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=aggregation(("2026-08-31", 1), other=5))
    )

    with httpx.Client(transport=transport) as client, pytest.raises(ValueError, match="dates"):
        agenceore.download_car_stock(client, tmp_path / "cars.csv")

    assert not (tmp_path / "cars.csv").exists()
