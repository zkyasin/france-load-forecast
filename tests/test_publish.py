import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from france_load_forecast import correction, model, publish

TOTALS = {"actual", "reference", "gap"}


@pytest.fixture(scope="module")
def bundle(
    synthetic_frame: pd.DataFrame, synthetic_spec: model.ModelSpec, past_forecasts: pd.DataFrame
) -> dict[str, dict[str, Any]]:
    """December 2024 comes from real-time data, and 1 to 5 January 2025 have no temperature."""
    history = synthetic_frame.copy()
    history.loc[history.index >= pd.Timestamp("2024-12-01"), "source"] = "realtime"
    observed = pd.Series(60.0, index=pd.date_range("2025-01-01", "2025-01-05"))
    energy = correction.monthly_energy(synthetic_frame["load_gw"])
    rte = pd.DataFrame({"gross": 1.005 * energy, "corrected": 1.005 * energy})
    return publish.build(
        history, observed, synthetic_spec, past_forecasts, rte, (0.8, 30), date(2025, 1, 6)
    )


def test_every_file_carries_the_date_and_the_model(bundle: dict[str, dict[str, Any]]) -> None:
    for content in bundle.values():
        assert (content["published"], content["model_id"]) == ("2025-01-06", "synthetic")
    assert bundle["meta"]["consolidated_until"] == "2024-11-30"
    assert bundle["meta"]["measured_until"] == "2025-01-05"


def test_forecast_starts_with_the_current_month(bundle: dict[str, dict[str, Any]]) -> None:
    forecast = bundle["forecast"]
    first = forecast["months"][0]

    assert forecast["current_month"] == first["month"] == "2025-01"
    assert first["provisional"]
    assert not forecast["months"][1]["provisional"]
    assert first["measured"] == pytest.approx(60 * 5 * 24 / 1000)
    assert len(forecast["months"]) == 12
    total = sum(month["p50"] for month in forecast["months"])
    assert forecast["total_p50"] == pytest.approx(total, abs=0.01)


def test_gaps_cover_the_last_twelve_months(bundle: dict[str, dict[str, Any]]) -> None:
    months = bundle["gaps"]["months"]

    assert [month["month"] for month in months] == [f"2024-{m:02d}" for m in range(1, 13)]
    assert [month["provisional"] for month in months] == [False] * 11 + [True]
    assert set(months[0]["temperature"]) == {"mean", "reference", "year_before"}
    for month in months:
        for view in ("against_forecast", "against_year_before"):
            terms = sum(value for name, value in month[view].items() if name not in TOTALS)
            assert terms == pytest.approx(month[view]["gap"], abs=0.01)


def test_history_keeps_whole_months_and_years(bundle: dict[str, dict[str, Any]]) -> None:
    history = bundle["history"]
    last = history["months"][-1]

    assert (last["month"], last["provisional"]) == ("2024-12", True)
    assert [year["year"] for year in history["years"]] == [2022, 2023, 2024]


def test_model_reports_the_winter_gradient(bundle: dict[str, dict[str, Any]]) -> None:
    assert bundle["model"]["thermosensitivity"]["winter"] == pytest.approx(2.0, abs=0.3)


def test_bundle_is_written_as_json(bundle: dict[str, dict[str, Any]], tmp_path: Path) -> None:
    publish.write(bundle, tmp_path)

    assert sorted(path.stem for path in tmp_path.iterdir()) == sorted(bundle)
    assert json.loads((tmp_path / "gaps.json").read_text(encoding="utf-8")) == bundle["gaps"]
