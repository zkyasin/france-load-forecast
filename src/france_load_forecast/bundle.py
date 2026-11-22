"""Schema of the weekly bundle, checked before it is written.

Beyond types, the checks catch values that no correct run produces: a band out of order, an
energy out of plausible bounds, terms that do not add up to their gap, a missing scenario.
"""

from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Bounds of national consumption in TWh, far beyond any month or year since 2012.
MONTHLY_TWH = (15.0, 80.0)
ANNUAL_TWH = (300.0, 700.0)
# The bundle rounds to 3 decimals, so sums may differ by a little.
ROUNDING = 0.01

Month = Annotated[str, Field(pattern=r"^\d{4}-\d{2}$")]
MonthlyEnergy = Annotated[float, Field(ge=MONTHLY_TWH[0], le=MONTHLY_TWH[1])]
AnnualEnergy = Annotated[float, Field(ge=ANNUAL_TWH[0], le=ANNUAL_TWH[1])]
Percent = Annotated[float, Field(ge=0, le=100)]
Celsius = Annotated[float, Field(ge=-20, le=40)]

# The page and the agent read every year and trajectory under these winters, and compare each case
# with this trajectory under a normal winter.
WINTERS = frozenset({"normal", "cold", "mild"})
REFERENCE_TRAJECTORY = "stagnation"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class File(Strict):
    published: date
    model_id: str


class Revision(Strict):
    gw: float = Field(ge=0, le=3)
    days: int = Field(ge=1)


class Meta(File):
    consolidated_until: date
    temperature_until: date
    measured_until: date
    revision: Revision | None


class ForecastMonth(Strict):
    month: Month
    p10: MonthlyEnergy
    p50: MonthlyEnergy
    p90: MonthlyEnergy
    measured: float = Field(ge=0)
    horizon: int = Field(ge=1)
    provisional: bool

    @model_validator(mode="after")
    def band_in_order(self) -> "ForecastMonth":
        if not self.measured - ROUNDING <= self.p10 <= self.p50 <= self.p90:
            raise ValueError(f"{self.month}: measured, P10, P50 and P90 are out of order")
        return self


class Forecast(File):
    current_month: Month
    total_p50: AnnualEnergy
    months: list[ForecastMonth] = Field(min_length=12)


class GapView(BaseModel):
    """A gap and its terms, one per component of the model plus structural and residual."""

    model_config = ConfigDict(extra="allow")

    actual: MonthlyEnergy
    reference: MonthlyEnergy
    gap: float

    @model_validator(mode="after")
    def terms_add_up(self) -> "GapView":
        terms = self.model_extra or {}
        if not all(isinstance(value, int | float) for value in terms.values()):
            raise ValueError("a term is not a number")
        if abs(self.actual - self.reference - self.gap) > ROUNDING:
            raise ValueError("the gap is not the actual energy minus the reference")
        if abs(sum(terms.values()) - self.gap) > ROUNDING:
            raise ValueError("the terms do not add up to the gap")
        return self


class Temperatures(Strict):
    mean: Celsius
    reference: Celsius
    year_before: Celsius


class GapMonth(Strict):
    month: Month
    provisional: bool
    temperature: Temperatures
    against_forecast: GapView
    against_year_before: GapView


class Gaps(File):
    months: list[GapMonth] = Field(min_length=1)


class HistoryMonth(Strict):
    month: Month
    energy: MonthlyEnergy
    provisional: bool


class HistoryYear(Strict):
    year: int
    gross: AnnualEnergy
    gross_rte: AnnualEnergy
    gross_gap_pct: float
    corrected: AnnualEnergy
    corrected_rte: AnnualEnergy
    corrected_gap_pct: float


class History(File):
    months: list[HistoryMonth] = Field(min_length=12)
    years: list[HistoryYear] = Field(min_length=1)


class Accuracy(File):
    first_origin: Month
    last_origin: Month
    mape: dict[str, Percent]
    mape_naive: dict[str, Percent]
    mape_naive_corrected: dict[str, Percent]
    mape_since_2023: dict[str, Percent]
    coverage_first_origin: Month
    coverage: dict[str, Percent]
    coverage_since_2023: dict[str, Percent]


class Gradient(Strict):
    temperature: float
    gw_per_c: float


class Thermosensitivity(Strict):
    winter: float = Field(gt=0, le=5)
    by_temperature: list[Gradient]


class ModelFile(File):
    fitted_from: date
    fitted_until: date
    thermosensitivity: Thermosensitivity


class TrajectoryInfo(Strict):
    label: str
    pages: str
    growth_pct: dict[str, float]


class ReplayedWinter(Strict):
    year: int
    winter: str
    weather_year: int


class Case(Strict):
    year: int
    trajectory: str
    winter: str
    annual_energy: AnnualEnergy
    winter_energy: float = Field(gt=0)
    months: list[MonthlyEnergy] = Field(min_length=12, max_length=12)


class Scenarios(File):
    source: str
    years: list[int] = Field(min_length=1)
    trajectories: dict[str, TrajectoryInfo]
    replayed_winters: list[ReplayedWinter]
    cases: list[Case]

    @model_validator(mode="after")
    def every_case(self) -> "Scenarios":
        if REFERENCE_TRAJECTORY not in self.trajectories:
            raise ValueError(f"the reference trajectory, {REFERENCE_TRAJECTORY}, is missing")
        expected = {(y, t, w) for y in self.years for t in self.trajectories for w in WINTERS}
        if {(case.year, case.trajectory, case.winter) for case in self.cases} != expected:
            raise ValueError("some years, trajectories or winters have no case")
        return self


FILES: dict[str, type[File]] = {
    "meta": Meta,
    "forecast": Forecast,
    "gaps": Gaps,
    "history": History,
    "accuracy": Accuracy,
    "model": ModelFile,
    "scenarios": Scenarios,
}


def check(files: dict[str, dict[str, Any]]) -> list[str]:
    """One message per file missing from `files`, unknown, or breaking its schema."""
    problems = [f"{name}: missing" for name in FILES if name not in files]
    for name, content in files.items():
        if name not in FILES:
            problems.append(f"{name}: unknown file")
            continue
        try:
            FILES[name].model_validate(content)
        except ValidationError as error:
            problems.append(f"{name}: {error}")
    return problems
