import shutil
from pathlib import Path

import httpx
import pytest

from france_load_forecast import agenceore, cli, insee, odre


def test_ingest_builds_the_warehouse(
    fixtures: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def copy_fixture(
        client: httpx.Client, dataset: str, dest: Path, *, select: str, where: str | None = None
    ) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures / f"{dataset}.csv", dest)

    def copy_series(client: httpx.Client, series: object, dest: Path, start: str) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures / "insee_monthly.csv", dest)

    def copy_cars(client: httpx.Client, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures / "car_stock.csv", dest)

    monkeypatch.setattr(odre, "download_export", copy_fixture)
    monkeypatch.setattr(insee, "download_series", copy_series)
    monkeypatch.setattr(agenceore, "download_car_stock", copy_cars)

    exit_code = cli.main(["ingest", "--data-dir", str(tmp_path)])

    assert exit_code == 0
    assert (tmp_path / "warehouse.duckdb").exists()
    out = capsys.readouterr().out
    assert "load_realtime" in out
    assert "insee_monthly" in out
    assert "car_stock" in out


def test_forecast_needs_the_backtest_of_its_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    peak = Path(__file__).parents[1] / "config" / "peak.toml"

    assert cli.main(["forecast", "--data-dir", str(tmp_path)]) == 1
    assert "backtest-baseline.csv is missing" in capsys.readouterr().err
    assert cli.main(["forecast", "--data-dir", str(tmp_path), "--config", str(peak)]) == 1
    assert "backtest-peak.csv is missing" in capsys.readouterr().err


def test_note_needs_a_month_of_the_bundle(
    fixtures: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(["note", "2026-10", "--bundle", str(fixtures / "bundle")])

    assert exit_code == 1
    assert "covers 2025-10 to 2026-09" in capsys.readouterr().err
