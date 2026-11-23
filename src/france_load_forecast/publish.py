"""The weekly bundle: JSON files read by the page, the agent and the forecast archive.

Each file carries the publication date and the model id. Energies are in TWh, powers in GW,
errors and coverage in %.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from france_load_forecast import (
    backtest,
    conformal,
    correction,
    decomposition,
    model,
    outlook,
    scenarios,
)

GAP_MONTHS = 12
# Temperatures, in °C, at which the response to temperature may be published.
GRADIENT_GRID = [float(t) for t in range(-10, 40, 5)]


def _round(value: float) -> float:
    return round(float(value), 3)


def _rounded(values: pd.Series) -> dict[str, float]:
    return {str(name): _round(value) for name, value in values.items()}


def _month(timestamp: Any) -> str:
    return pd.Timestamp(timestamp).strftime("%Y-%m")


def _day(timestamp: Any) -> str:
    return pd.Timestamp(timestamp).strftime("%Y-%m-%d")


def meta_file(
    history: pd.DataFrame, observed: pd.Series, revision: tuple[float, int]
) -> dict[str, Any]:
    """Dates of the data and revision added to real-time load."""
    consolidated = history.index[history["source"] == "consolidated"]
    measured = observed.index if not observed.empty else history.index
    revision_gw, days = revision
    return {
        "consolidated_until": _day(consolidated[-1]),
        "temperature_until": _day(history.index[-1]),
        "measured_until": _day(measured[-1]),
        "revision": {"gw": _round(revision_gw), "days": days} if days else None,
    }


def forecast_file(
    table: pd.DataFrame, current: pd.Timestamp, provisional: pd.Index
) -> dict[str, Any]:
    """Monthly forecast with its band, and the total P50 of the 12 months from the current one.
    Months measured from real-time data are provisional."""
    return {
        "current_month": _month(current),
        "total_p50": _round(table.loc[table.index >= current, "p50"].sum()),
        "months": [
            {
                "month": _month(month),
                **_rounded(row.drop("horizon")),
                "horizon": int(row["horizon"]),
                "provisional": month in provisional,
            }
            for month, row in table.iterrows()
        ],
    }


def gaps_file(
    against_forecast: pd.DataFrame,
    against_year_before: pd.DataFrame,
    provisional: pd.Index,
    temperatures: pd.DataFrame,
    forecast_temperature: pd.Series,
) -> dict[str, Any]:
    """Both views of the gap of each recent month, term by term, with the mean temperature of
    the month, its reference temperature, the temperature of the same month a year earlier and
    that of the weather the forecast assumed."""
    weather = pd.DataFrame(
        {
            "mean": temperatures["temperature_c"],
            "reference": temperatures["reference_c"],
            "year_before": temperatures["temperature_c"].shift(freq=pd.DateOffset(years=1)),
            "forecast": forecast_temperature,
        }
    ).reindex(against_forecast.index)
    return {
        "months": [
            {
                "month": _month(month),
                "provisional": month in provisional,
                "temperature": _rounded(temperature),
                "against_forecast": _rounded(to_forecast),
                "against_year_before": _rounded(to_year_before),
            }
            for (month, to_forecast), (_, to_year_before), (_, temperature) in zip(
                against_forecast.iterrows(),
                against_year_before.iterrows(),
                weather.iterrows(),
                strict=True,
            )
        ]
    }


def history_file(load: pd.Series, provisional: pd.Index, annual: pd.DataFrame) -> dict[str, Any]:
    """Energy of each whole month measured, and annual energies against RTE's."""
    energy = correction.monthly_energy(load)
    if not pd.Timestamp(load.index[-1]).is_month_end:
        energy = energy.iloc[:-1]
    return {
        "months": [
            {"month": _month(month), "energy": _round(value), "provisional": month in provisional}
            for month, value in energy.items()
        ],
        "years": [{"year": int(str(year)), **_rounded(row)} for year, row in annual.iterrows()],
    }


def accuracy_file(results: pd.DataFrame) -> dict[str, Any]:
    """Backtest errors by horizon for P50 and the naive forecasts, and coverage of the band."""
    origins = pd.DatetimeIndex(results["origin"])
    scores = backtest.accuracy(results)
    recent = backtest.accuracy(results[results["origin"] >= backtest.RECENT_ORIGINS])
    coverage = conformal.online_coverage(results, conformal.FIRST_BAND_ORIGIN)
    recent_coverage = conformal.online_coverage(results, backtest.RECENT_ORIGINS)
    return {
        "first_origin": _month(origins.min()),
        "last_origin": _month(origins.max()),
        "mape": _rounded(scores["p50"]),
        "mape_naive": _rounded(scores["naive"]),
        "mape_naive_corrected": _rounded(scores["naive_corrected"]),
        "mape_since_2023": _rounded(recent["p50"]),
        "coverage_first_origin": _month(conformal.FIRST_BAND_ORIGIN),
        "coverage": _rounded(100 * coverage),
        "coverage_since_2023": _rounded(100 * recent_coverage),
    }


def model_file(fitted: model.DailyModel, history: pd.DataFrame) -> dict[str, Any]:
    """Estimation window and response to temperature of the forecasting model, at the
    temperatures of GRADIENT_GRID that lie between the coldest and the warmest smoothed day of the
    window: beyond them, the spline has no data."""
    window = history.loc[fitted.level.index]
    smooth = window["temperature_smooth"]
    winter = smooth[pd.DatetimeIndex(window.index).month.isin([12, 1, 2])]
    temperatures = pd.Series([t for t in GRADIENT_GRID if smooth.min() <= t <= smooth.max()])
    gradients = model.thermosensitivity(fitted, temperatures)
    return {
        "fitted_from": _day(window.index[0]),
        "fitted_until": _day(window.index[-1]),
        "thermosensitivity": {
            "winter": _round(model.thermosensitivity(fitted, winter).mean()),
            "by_temperature": [
                {"temperature": temperature, "gw_per_c": _round(gradient)}
                for temperature, gradient in zip(temperatures, gradients, strict=True)
            ],
        },
    }


def scenarios_file(
    table: pd.DataFrame, replayed: pd.DataFrame, spec: scenarios.ScenarioSpec
) -> dict[str, Any]:
    """Energy of each year, trajectory and winter, month by month, with the growth rates of the
    trajectories and the weather year each cold or mild winter replays."""
    cases = []
    for (year, trajectory, winter), rows in table.groupby(
        ["year", "trajectory", "winter"], sort=False
    ):
        in_winter = pd.DatetimeIndex(rows["month"]).month.isin(scenarios.WINTER)
        cases.append(
            {
                "year": int(str(year)),
                "trajectory": trajectory,
                "winter": winter,
                "annual_energy": _round(rows["energy"].sum()),
                "winter_energy": _round(rows.loc[in_winter, "energy"].sum()),
                "months": [_round(energy) for energy in rows["energy"]],
            }
        )
    return {
        "source": spec.source,
        "years": spec.years,
        "trajectories": {
            name: {
                "label": trajectory.label,
                "pages": trajectory.pages,
                "growth_pct": {
                    str(year): round(100 * scenarios.growth(spec, name, year), 2)
                    for year in spec.years
                },
            }
            for name, trajectory in spec.trajectories.items()
        },
        "replayed_winters": replayed.to_dict(orient="records"),
        "cases": cases,
    }


def build(
    history: pd.DataFrame,
    observed: pd.Series,
    spec: model.ModelSpec,
    past_forecasts: pd.DataFrame,
    rte: pd.DataFrame,
    revision: tuple[float, int],
    scenario_spec: scenarios.ScenarioSpec,
    published: date,
) -> dict[str, dict[str, Any]]:
    """Every file of the bundle, by name.

    `history` is the daily frame, `observed` the load measured after it, `past_forecasts` the
    backtest results, `rte` RTE's monthly series, `revision` the revision of real-time load and
    `scenario_spec` the trajectories and winters of the scenarios.
    """
    latest = model.fit_recent(history, spec)
    current = outlook.current_month(history, observed)
    months = decomposition.recent_months(history, GAP_MONTHS)
    load = pd.concat([history["load_gw"], observed])
    realtime = history.index[history["source"] == "realtime"].append(observed.index)
    provisional = pd.DatetimeIndex(realtime).to_period("M").to_timestamp().unique()
    corrected = correction.corrected_load(model.fit(history, spec), history)
    to_forecast, forecast_temperature = decomposition.against_forecast(history, spec, months)
    files = {
        "meta": meta_file(history, observed, revision),
        "forecast": forecast_file(
            outlook.table(latest, history, observed, past_forecasts), current, provisional
        ),
        "gaps": gaps_file(
            to_forecast,
            decomposition.against_year_before(latest, history, months),
            provisional,
            history[["temperature_c", "reference_c"]].resample("MS").mean(),
            forecast_temperature,
        ),
        "history": history_file(
            load, provisional, correction.annual_comparison(history["load_gw"], corrected, rte)
        ),
        "accuracy": accuracy_file(past_forecasts),
        "model": model_file(latest, history),
        "scenarios": scenarios_file(*scenarios.grid(latest, history, scenario_spec), scenario_spec),
    }
    header = {"published": published.isoformat(), "model_id": spec.model_id}
    return {name: header | content for name, content in files.items()}


def write(files: dict[str, dict[str, Any]], out: Path) -> None:
    """One JSON file per entry of `files`, in `out`."""
    out.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        text = json.dumps(content, ensure_ascii=False, indent=2)
        (out / f"{name}.json").write_text(text + "\n", encoding="utf-8")
