from pathlib import Path

import pytest

from france_load_forecast.warehouse import SOURCES


@pytest.fixture
def fixtures() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def export_files(fixtures: Path) -> dict[str, Path]:
    """Real ODRÉ exports for 30 August to 2 September 2026, one per source table."""
    return {source.table: fixtures / f"{source.dataset}.csv" for source in SOURCES}
