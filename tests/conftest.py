from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from france_load_forecast import model
from france_load_forecast.calendar import calendar_features
from france_load_forecast.warehouse import SOURCES

SYNTHETIC_SPEC = model.ModelSpec(
    model_id="synthetic",
    smoothing=0.5,
    seasonal_harmonics=2,
    window_years=2,
    components={
        "climate": (
            "cr(temperature_smooth, df=6, constraints='center', lower_bound=-15, upper_bound=35)"
        ),
        "calendar": "C(day_type, Treatment('wed'))",
        "lockdown": "lockdown_1 + lockdown_2 + lockdown_3",
    },
)


@pytest.fixture
def fixtures() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def export_files(fixtures: Path) -> dict[str, Path]:
    """Real ODRÉ exports for 30 August to 2 September 2026, one per source table."""
    return {source.table: fixtures / f"{source.dataset}.csv" for source in SOURCES}


@pytest.fixture(scope="session")
def synthetic_frame() -> pd.DataFrame:
    """Three years of daily load with a heating gradient of 2 GW/°C below 15 °C and a weekend
    drop of 6 GW. The reference temperature is the seasonal cycle without weather noise."""
    rng = np.random.default_rng(0)
    dates = pd.date_range("2022-01-01", "2024-12-31", freq="D")
    season = 12 - 8 * np.cos(2 * np.pi * dates.day_of_year.to_numpy() / 365.25)
    temperature = season + rng.normal(0, 2, len(dates))
    smooth = pd.Series(temperature, index=dates).ewm(alpha=0.5, adjust=False).mean()
    reference = pd.Series(season, index=dates).ewm(alpha=0.5, adjust=False).mean()
    weekend = (dates.day_of_week >= 5).astype(float)
    load = 50 + 2 * np.maximum(0, 15 - smooth) - 6 * weekend + rng.normal(0, 0.3, len(dates))
    frame = pd.DataFrame(
        {
            "load_gw": load,
            "temperature_c": temperature,
            "reference_c": season,
            "temperature_smooth": smooth,
            "reference_smooth": reference,
        },
        index=dates,
    )
    return frame.join(calendar_features(dates))


@pytest.fixture(scope="session")
def synthetic_spec() -> model.ModelSpec:
    return SYNTHETIC_SPEC


@pytest.fixture(scope="session")
def synthetic_model(synthetic_frame: pd.DataFrame) -> model.DailyModel:
    return model.fit(synthetic_frame, SYNTHETIC_SPEC)
