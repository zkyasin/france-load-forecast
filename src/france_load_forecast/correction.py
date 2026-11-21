"""Climate-corrected consumption and its comparison with RTE's corrected series."""

import duckdb
import pandas as pd

from france_load_forecast.model import DailyModel, component_effect


def corrected_load(model: DailyModel, frame: pd.DataFrame) -> pd.Series:
    """Daily load had the smoothed temperature been the reference one, in GW."""
    actual = component_effect(model, "climate", frame)
    reference = component_effect(
        model, "climate", frame.assign(temperature_smooth=frame["reference_smooth"])
    )
    return frame["load_gw"] - actual + reference


def monthly_energy(daily_gw: pd.Series) -> pd.Series:
    """Monthly energy in TWh, from daily mean power in GW."""
    dates = pd.DatetimeIndex(daily_gw.index)
    # Clock changes make one day 23 hours long and another 25.
    starts = dates.tz_localize("Europe/Paris")
    ends = (dates + pd.Timedelta(days=1)).tz_localize("Europe/Paris")
    hours = (ends - starts) / pd.Timedelta(hours=1)
    return (daily_gw * hours).resample("MS").sum() / 1000


def rte_monthly(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """RTE's monthly gross and corrected consumption, in TWh."""
    frame = (
        con.execute(
            "SELECT month, gross_mwh / 1e6 AS gross, corrected_mwh / 1e6 AS corrected "
            "FROM rte_monthly ORDER BY month"
        )
        .df()
        .set_index("month")
    )
    frame.index = pd.DatetimeIndex(frame.index)
    return frame


def annual_comparison(load: pd.Series, corrected: pd.Series, rte: pd.DataFrame) -> pd.DataFrame:
    """Annual gross and corrected energy, ours against RTE's, for the years both cover in full.

    RTE's corrected series also leaves out 29 February, so ours does the same.
    """
    dates = pd.DatetimeIndex(corrected.index)
    standard_year = corrected[~((dates.month == 2) & (dates.day == 29))]
    ours = pd.DataFrame({"gross": monthly_energy(load), "corrected": monthly_energy(standard_year)})
    months = ours.merge(rte, left_index=True, right_index=True, suffixes=("", "_rte"))
    by_year = months.groupby(pd.DatetimeIndex(months.index).year)
    annual = by_year.sum()[by_year.size() == 12]
    for column in ("gross", "corrected"):
        annual[f"{column}_gap_pct"] = 100 * (annual[column] / annual[f"{column}_rte"] - 1)
    columns = ["gross", "gross_rte", "gross_gap_pct", "corrected", "corrected_rte"]
    return annual[[*columns, "corrected_gap_pct"]].rename_axis("year")
