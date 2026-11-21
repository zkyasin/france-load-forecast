import shutil
from pathlib import Path

import httpx
import pytest

from france_load_forecast import cli, odre


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

    monkeypatch.setattr(odre, "download_export", copy_fixture)

    exit_code = cli.main(["ingest", "--data-dir", str(tmp_path)])

    assert exit_code == 0
    assert (tmp_path / "warehouse.duckdb").exists()
    assert "load_realtime" in capsys.readouterr().out
