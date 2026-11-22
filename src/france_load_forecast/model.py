"""Daily load model.

    load[d] = sum of component effects[d] + level[d] + seasonal[d] + ar[d]
    level[d] = level[d - 1] + level shock        (structural drift, random walk)
    seasonal[d] = annual harmonics whose amplitudes drift slowly
    ar[d] = phi * ar[d - 1] + shock              (short-lived deviations)

Component effects are linear in the patsy design columns of `config/model.toml`. The level, the
seasonal pattern, the autoregressive term and the coefficients are estimated together with a
Kalman filter.
"""

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

import duckdb
import pandas as pd
import patsy
from statsmodels.tsa.statespace.structural import (
    UnobservedComponents,
    UnobservedComponentsResults,
)

from france_load_forecast.calendar import calendar_features


@dataclass(frozen=True)
class ModelSpec:
    smoothing: float
    seasonal_harmonics: int
    window_years: int
    components: dict[str, str]


def load_spec(path: Path) -> ModelSpec:
    with path.open("rb") as file:
        config = tomllib.load(file)
    return ModelSpec(
        smoothing=config["smoothing"],
        seasonal_harmonics=config["seasonal_harmonics"],
        window_years=config["window_years"],
        components=config["components"],
    )


def daily_frame(con: duckdb.DuckDBPyConnection, smoothing: float) -> pd.DataFrame:
    """Consolidated daily load with temperatures and calendar features.

    Real-time days are left out: they sit about 2 % below consolidated data, which the level
    would read as a structural drop.
    """
    frame = (
        con.execute(
            """
            SELECT date, load_gw, temperature_c, reference_c
            FROM load_daily JOIN temperature USING (date)
            WHERE source = 'consolidated'
            ORDER BY date
            """
        )
        .df()
        .set_index("date")
    )
    # The daily frequency also asserts that no day is missing.
    frame.index = pd.DatetimeIndex(frame.index, freq="D")
    # The data checks only let isolated missing temperatures through.
    temperatures = ["temperature_c", "reference_c"]
    frame[temperatures] = frame[temperatures].interpolate(limit=1)
    smoothed = frame[temperatures].ewm(alpha=smoothing, adjust=False).mean()
    frame["temperature_smooth"] = smoothed["temperature_c"]
    frame["reference_smooth"] = smoothed["reference_c"]
    return frame.join(calendar_features(frame.index))


@dataclass(frozen=True)
class DailyModel:
    spec: ModelSpec
    designs: dict[str, patsy.DesignInfo]
    results: UnobservedComponentsResults

    @property
    def coefficients(self) -> pd.Series:
        """Effect of each design column, read from the last smoothed state."""
        state = pd.Series(self.results.smoothed_state[:, -1], index=self.results.model.state_names)
        return state.filter(like="beta.").rename(lambda name: name.removeprefix("beta."))

    @property
    def level(self) -> pd.Series:
        """Smoothed structural level, in GW."""
        return pd.Series(self.results.level["smoothed"], index=self.results.fittedvalues.index)

    @property
    def seasonal(self) -> pd.Series:
        """Smoothed annual pattern, in GW."""
        smoothed = self.results.freq_seasonal[0]["smoothed"]
        return pd.Series(smoothed, index=self.results.fittedvalues.index)

    @property
    def ar(self) -> pd.Series:
        """Smoothed autoregressive term, in GW."""
        smoothed = self.results.autoregressive["smoothed"]
        return pd.Series(smoothed, index=self.results.fittedvalues.index)


def design_matrix(design: patsy.DesignInfo, frame: pd.DataFrame) -> pd.DataFrame:
    # The level of the model replaces the intercept.
    matrix: pd.DataFrame = patsy.build_design_matrices([design], frame, return_type="dataframe")[0]
    return matrix.drop(columns="Intercept")


def fit(frame: pd.DataFrame, spec: ModelSpec) -> DailyModel:
    designs = {
        name: patsy.dmatrix(terms, frame).design_info for name, terms in spec.components.items()
    }
    exog = pd.concat([design_matrix(design, frame) for design in designs.values()], axis=1)
    # Columns that never vary in the sample, such as lockdowns before 2020, cannot be estimated.
    exog = exog.loc[:, exog.std() > 0]
    model = UnobservedComponents(
        frame["load_gw"],
        level=True,
        stochastic_level=True,
        irregular=False,
        autoregressive=1,
        freq_seasonal=[{"period": 365.25, "harmonics": spec.seasonal_harmonics}],
        stochastic_freq_seasonal=[True],
        exog=exog,
        # Coefficients go into the state vector: fitting is much faster and gives the same values.
        mle_regression=False,
    )
    return DailyModel(spec, designs, model.fit(disp=False))


def fit_recent(history: pd.DataFrame, spec: ModelSpec) -> DailyModel:
    """Fit the model on the last `spec.window_years` years of `history`."""
    end = pd.DatetimeIndex(history.index)[-1]
    return fit(history[history.index > end - pd.DateOffset(years=spec.window_years)], spec)


def exog(model: DailyModel, frame: pd.DataFrame) -> pd.DataFrame:
    """Design columns of the fitted model, for new days."""
    columns = pd.concat([design_matrix(design, frame) for design in model.designs.values()], axis=1)
    fitted_columns: list[str] = model.results.model.exog_names
    return columns[fitted_columns]


def extend(model: DailyModel, frame: pd.DataFrame) -> DailyModel:
    """Filter the days of `frame` after the fitted sample, keeping the estimated parameters.

    The level, the autoregressive term and the coefficients still update with the new days.
    """
    new = frame[frame.index > model.results.fittedvalues.index[-1]]
    if new.empty:
        return model
    results = model.results.append(new["load_gw"], exog=exog(model, new))
    return replace(model, results=results)


def component_effect(model: DailyModel, component: str, frame: pd.DataFrame) -> pd.Series:
    """Effect of one component on the daily load, in GW."""
    matrix = design_matrix(model.designs[component], frame)
    columns = matrix.columns.intersection(model.coefficients.index)
    return matrix[columns] @ model.coefficients[columns]


def contributions(model: DailyModel, frame: pd.DataFrame) -> pd.DataFrame:
    """Effect of each component on the daily load, in GW."""
    return pd.DataFrame({name: component_effect(model, name, frame) for name in model.designs})


def thermosensitivity(model: DailyModel, temperature_smooth: pd.Series) -> pd.Series:
    """Load increase for 1 °C less, in GW/°C, at each smoothed temperature."""
    colder = pd.DataFrame({"temperature_smooth": temperature_smooth - 0.5})
    warmer = pd.DataFrame({"temperature_smooth": temperature_smooth + 0.5})
    return component_effect(model, "climate", colder) - component_effect(model, "climate", warmer)
