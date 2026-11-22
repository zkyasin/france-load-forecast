"""DuckDB warehouse built from the raw ODRÉ exports."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class Source:
    """An ODRÉ export and the table loaded from it."""

    table: str
    dataset: str
    # Table column -> (ODRÉ field, DuckDB type), in export order.
    columns: Mapping[str, tuple[str, str]]
    where: str | None = None
    date_format: str = "%Y-%m-%d"

    @property
    def select(self) -> str:
        return ",".join(field for field, _ in self.columns.values())

    @property
    def column_types(self) -> dict[str, str]:
        return {name: kind for name, (_, kind) in self.columns.items()}

    @property
    def date_column(self) -> str:
        return next(iter(self.columns))


SOURCES = (
    # Consolidated and definitive data. Consumption is published every half-hour, as 48 values
    # per civil day in local time, including on clock-change days.
    Source(
        table="load_consolidated",
        dataset="eco2mix-national-cons-def",
        columns={
            "date": ("date", "DATE"),
            "time": ("heure", "VARCHAR"),
            "load_mw": ("consommation", "DOUBLE"),
            "status": ("nature", "VARCHAR"),
        },
        where="consommation IS NOT NULL",
    ),
    # Real-time data, every quarter-hour, from the day after the last consolidated day.
    Source(
        table="load_realtime",
        dataset="eco2mix-national-tr",
        columns={
            "date": ("date", "DATE"),
            "time": ("heure", "VARCHAR"),
            "load_mw": ("consommation", "DOUBLE"),
        },
        where="consommation IS NOT NULL",
    ),
    # RTE's consolidated consumption as published with the gas data, every half-hour. It runs
    # about a month ahead of éCO2mix's consolidated series, so it overlaps the first real-time
    # days.
    Source(
        table="load_revised",
        dataset="consommation-quotidienne-brute",
        columns={
            "date": ("date", "DATE"),
            "time": ("heure", "VARCHAR"),
            "load_mw": ("consommation_brute_electricite_rte", "DOUBLE"),
        },
        where="consommation_brute_electricite_rte IS NOT NULL",
        date_format="%d/%m/%Y",
    ),
    Source(
        table="temperature",
        dataset="pic-journalier-consommation-brute",
        columns={
            "date": ("date", "DATE"),
            "peak_mw": ("pic_journalier_consommation", "DOUBLE"),
            "temperature_c": ("temperature_moyenne", "DOUBLE"),
            "reference_c": ("temperature_reference", "DOUBLE"),
        },
    ),
    Source(
        table="rte_monthly",
        dataset="conso_brute_corrigee_client_direct",
        columns={
            "month": ("annee_mois", "DATE"),
            "gross_mwh": ("conso_brute_mwh", "DOUBLE"),
            "corrected_mwh": ("conso_corrigee_mwh", "DOUBLE"),
        },
        date_format="%Y-%m",
    ),
)

# Real-time values are instantaneous telemetry; consolidated values are means of meter readings
# and sit higher. The revision is measured on the days covered by both real-time and revised data.
REVISION = """
CREATE OR REPLACE VIEW revision AS
SELECT date, revised.load_gw - realtime.load_gw AS revision_gw
FROM (
    SELECT date, avg(load_mw) / 1000 AS load_gw FROM load_revised
    GROUP BY date HAVING count(*) >= 46
) AS revised
JOIN (
    -- A full day has 96 quarter-hours; the current day is still incomplete.
    SELECT date, avg(load_mw) / 1000 AS load_gw FROM load_realtime
    GROUP BY date HAVING count(*) >= 92
) AS realtime USING (date)
"""

# Real-time days after the last consolidated day, raised by the mean revision.
LOAD_DAILY = """
CREATE OR REPLACE VIEW load_daily AS
SELECT date, avg(load_mw) / 1000 AS load_gw, count(*) AS n_values, 'consolidated' AS source
FROM load_consolidated
GROUP BY date
UNION ALL
SELECT date, avg(load_mw) / 1000 + (SELECT avg(revision_gw) FROM revision), count(*), 'realtime'
FROM load_realtime
WHERE date > (SELECT max(date) FROM load_consolidated)
GROUP BY date
HAVING count(*) >= 92
"""

CHECKS = {
    "duplicate half-hours in consolidated load": """
        SELECT date, time FROM load_consolidated GROUP BY date, time HAVING count(*) > 1
    """,
    "consolidated days with fewer than 46 half-hours": """
        SELECT date, count(*) AS n FROM load_consolidated GROUP BY date HAVING n < 46
    """,
    "load outside 20-110 GW": """
        SELECT date, time, load_mw FROM load_consolidated WHERE load_mw NOT BETWEEN 20e3 AND 110e3
        UNION ALL
        SELECT date, time, load_mw FROM load_realtime WHERE load_mw NOT BETWEEN 20e3 AND 110e3
        UNION ALL
        SELECT date, time, load_mw FROM load_revised WHERE load_mw NOT BETWEEN 20e3 AND 110e3
    """,
    "real-time days without a measured revision": """
        SELECT date FROM load_daily WHERE source = 'realtime' AND load_gw IS NULL
    """,
    "mean revision outside 0-2 GW": """
        SELECT avg(revision_gw) FROM revision HAVING avg(revision_gw) NOT BETWEEN 0 AND 2
    """,
    "missing days in daily load": """
        SELECT day::DATE AS date
        FROM range(
            (SELECT min(date) FROM load_daily), (SELECT max(date) FROM load_daily), INTERVAL 1 DAY
        ) AS days(day)
        WHERE day::DATE NOT IN (SELECT date FROM load_daily)
    """,
    "missing days in temperature": """
        SELECT day::DATE AS date
        FROM range(
            (SELECT min(date) FROM temperature), (SELECT max(date) FROM temperature), INTERVAL 1 DAY
        ) AS days(day)
        WHERE day::DATE NOT IN (SELECT date FROM temperature)
    """,
    # Isolated missing values are interpolated downstream; longer gaps are not.
    "temperature missing two days in a row": """
        SELECT date FROM (
            SELECT date, temperature_c IS NULL AND lag(temperature_c) OVER (ORDER BY date) IS NULL
                AND date - 1 = lag(date) OVER (ORDER BY date) AS gap
            FROM temperature
        )
        WHERE gap
    """,
    "temperature outside -20 to 40 °C": """
        SELECT date, temperature_c, reference_c FROM temperature
        WHERE temperature_c NOT BETWEEN -20 AND 40 OR reference_c NOT BETWEEN -20 AND 40
    """,
    "missing months in the RTE monthly series": """
        SELECT month::DATE AS month
        FROM range(
            (SELECT min(month) FROM rte_monthly), (SELECT max(month) FROM rte_monthly),
            INTERVAL 1 MONTH
        ) AS months(month)
        WHERE month::DATE NOT IN (SELECT month FROM rte_monthly)
    """,
}


def build(con: duckdb.DuckDBPyConnection, files: Mapping[str, Path]) -> None:
    """Load one export file per source table, then create the derived views."""
    for source in SOURCES:
        con.execute(
            f"CREATE OR REPLACE TABLE {source.table} AS "
            "SELECT * FROM read_csv(?, delim=';', header=true, columns=?, dateformat=?)",
            [str(files[source.table]), source.column_types, source.date_format],
        )
    con.execute(REVISION)
    con.execute(LOAD_DAILY)


def summarize(con: duckdb.DuckDBPyConnection) -> list[tuple[str, int, date, date]]:
    """Row count and date range of each source table."""
    query = " UNION ALL ".join(
        f"SELECT '{s.table}', count(*), min({s.date_column}), max({s.date_column}) FROM {s.table}"
        for s in SOURCES
    )
    return con.execute(query).fetchall()


def mean_revision(con: duckdb.DuckDBPyConnection) -> tuple[float, int]:
    """Revision added to real-time load, in GW, and the number of days it is measured on."""
    revision_gw, days = con.execute("SELECT avg(revision_gw), count(*) FROM revision").fetchall()[0]
    return revision_gw, days


def run_checks(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Return one message per failed data check."""
    failures = []
    for description, query in CHECKS.items():
        rows = con.execute(query).fetchall()
        if rows:
            failures.append(f"{description}: {len(rows)} rows, first {rows[0]}")
    return failures
