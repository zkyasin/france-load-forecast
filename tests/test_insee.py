from pathlib import Path

import httpx
import pytest

from france_load_forecast import insee


def response(*observations: tuple[str, str], series: int = 1) -> str:
    """An SDMX response of INSEE as its web service writes it, cut down to what is read."""
    obs = "".join(
        f'<Obs TIME_PERIOD="{month}" OBS_VALUE="{value}"/>' for month, value in observations
    )
    body = f'<Series NAF2="A38-CE">{obs}</Series>' * series
    return (
        "<?xml version='1.0' encoding='UTF-8'?><message:StructureSpecificData"
        ' xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message">'
        f"<message:DataSet>{body}</message:DataSet></message:StructureSpecificData>"
    )


def test_values_are_read_by_month_and_missing_ones_left_out() -> None:
    xml = response(("2026-09", "92.31"), ("2026-08", "91.49"), ("2026-07", "NaN"))

    assert insee.monthly_values(xml) == {"2026-09": 92.31, "2026-08": 91.49}


def test_a_key_that_matches_several_series_fails() -> None:
    with pytest.raises(ValueError, match="one series"):
        insee.monthly_values(response(("2026-09", "92.31"), series=2))


def test_download_writes_each_series_in_month_order(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=response(("2026-09", "92.31"), ("2026-08", "91.49")))

    dest = tmp_path / "raw" / "insee.csv"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        insee.download_series(client, {"chemistry": ("IPI-2021", "M.A38-CE")}, dest, "2026-08")

    assert dest.read_text(encoding="utf-8").splitlines() == [
        "month;series;value",
        "2026-08-01;chemistry;91.49",
        "2026-09-01;chemistry;92.31",
    ]
    assert requests[0].url.path == "/series/sdmx/data/IPI-2021/M.A38-CE"
    assert requests[0].url.params["startPeriod"] == "2026-08"


def test_failed_download_leaves_no_file(tmp_path: Path) -> None:
    dest = tmp_path / "insee.csv"
    transport = httpx.MockTransport(lambda request: httpx.Response(503))

    with httpx.Client(transport=transport) as client, pytest.raises(httpx.HTTPStatusError):
        insee.download_series(client, {"chemistry": ("IPI-2021", "M.A38-CE")}, dest, "2026-08")

    assert not dest.exists()
