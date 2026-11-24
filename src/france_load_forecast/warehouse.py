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
    # Energy drawn each day from RTE's grid by large industrial sites, one row per voltage level.
    Source(
        table="industry_daily",
        dataset="soutirages-quotidiens-consolides-rpt",
        columns={
            "date": ("date_de_la_courbe", "DATE"),
            "voltage": ("code_tension", "VARCHAR"),
            "energy_mwh": ("energie_journaliere", "DOUBLE"),
        },
        where="secteur_activite_economique = 'Grande Industrie'",
    ),
    # Monthly consumption of the industry on RTE's grid, seasonally adjusted, in all and for the
    # sectors RTE names, 2014 to 2024. Rail transport is one of them.
    Source(
        table="industry_sectors",
        dataset="conso-finale-corrigee-par-secteur",
        columns={
            "month": ("mois", "DATE"),
            "industry_gwh": ("consommation_rpt_grande_industrie", "DOUBLE"),
            "metallurgy_gwh": ("consommation_rpt_metallurgie", "DOUBLE"),
            "steel_gwh": ("consommation_rpt_siderurgie", "DOUBLE"),
            "chemistry_gwh": ("consommation_rpt_chimie", "DOUBLE"),
            "automotive_gwh": ("consommation_rpt_automobile", "DOUBLE"),
            "paper_gwh": ("consommation_rpt_papier_carton", "DOUBLE"),
            "rail_gwh": ("consommation_rpt_transport_ferroviaire", "DOUBLE"),
        },
        date_format="%Y-%m",
    ),
)

# Monthly series of INSEE, by name: SDMX flow and key. The production indices are seasonally and
# working-day adjusted, base 100 in 2021; the consumer price indices cover all households in
# France, base 100 in 2025.
INSEE_SERIES = {
    "production_metals": ("IPI-2021", "M.BDM.IPI.SO.A38-CH.INDICE.FM.SO.CVS-CJO.2021"),
    "production_chemistry": ("IPI-2021", "M.BDM.IPI.SO.A38-CE.INDICE.FM.SO.CVS-CJO.2021"),
    "production_paper": ("IPI-2021", "M.BDM.IPI.SO.A38-CC.INDICE.FM.SO.CVS-CJO.2021"),
    "production_vehicles": ("IPI-2021", "M.BDM.IPI.SO.A38-CL.INDICE.FM.SO.CVS-CJO.2021"),
    "production_manufacturing": ("IPI-2021", "M.BDM.IPI.SO.A10-CZ.INDICE.FM.SO.CVS-CJO.2021"),
    "prices_all": ("IPC-2025", "M.IPC.SO.00.SO.INDICE.ENSEMBLE.FE.SO.BRUT.2025.FALSE"),
    "prices_electricity": ("IPC-2025", "M.IPC.SO.0451.SO.INDICE.ENSEMBLE.FE.SO.BRUT.2025.FALSE"),
}
INSEE_FIRST_MONTH = "2014-01"

# Tables loaded from the files that `flf ingest` writes from the APIs of INSEE and Agence ORE, with
# their columns, the date first.
API_TABLES: dict[str, dict[str, str]] = {
    "insee_monthly": {"month": "DATE", "series": "VARCHAR", "value": "DOUBLE"},
    "car_stock": {"date": "DATE", "cars": "DOUBLE"},
}

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

# Real-time days after the last consolidated day, raised by the mean revision. The daily peak is
# the highest value of the day: a half-hour for consolidated days, a quarter-hour for real-time
# ones.
LOAD_DAILY = """
CREATE OR REPLACE VIEW load_daily AS
SELECT date, avg(load_mw) / 1000 AS load_gw, max(load_mw) / 1000 AS peak_gw,
    count(*) AS n_values, 'consolidated' AS source
FROM load_consolidated
GROUP BY date
UNION ALL
SELECT date, avg(load_mw) / 1000 + (SELECT avg(revision_gw) FROM revision),
    max(load_mw) / 1000 + (SELECT avg(revision_gw) FROM revision), count(*), 'realtime'
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
    "missing days in large industry": """
        SELECT day::DATE AS date
        FROM range(
            (SELECT min(date) FROM industry_daily), (SELECT max(date) FROM industry_daily),
            INTERVAL 1 DAY
        ) AS days(day)
        WHERE day::DATE NOT IN (SELECT date FROM industry_daily)
    """,
    # RTE leaves out a row when too few sites share it, which would lower the energy of that day.
    "large industry days with fewer voltage levels than the others": """
        WITH levels AS (SELECT date, count(*) AS n FROM industry_daily GROUP BY date)
        SELECT date, n FROM levels WHERE n < (SELECT max(n) FROM levels)
    """,
    "INSEE series with missing months": """
        SELECT series, count(*) AS n FROM insee_monthly GROUP BY series
        HAVING n <> datediff('month', min(month), max(month)) + 1
    """,
}


def build(con: duckdb.DuckDBPyConnection, files: Mapping[str, Path]) -> None:
    """Load one file per table, then create the derived views."""
    for source in SOURCES:
        con.execute(
            f"CREATE OR REPLACE TABLE {source.table} AS "
            "SELECT * FROM read_csv(?, delim=';', header=true, columns=?, dateformat=?)",
            [str(files[source.table]), source.column_types, source.date_format],
        )
    for table, columns in API_TABLES.items():
        con.execute(
            f"CREATE OR REPLACE TABLE {table} AS "
            "SELECT * FROM read_csv(?, delim=';', header=true, columns=?)",
            [str(files[table]), columns],
        )
    con.execute(REVISION)
    con.execute(LOAD_DAILY)


def summarize(con: duckdb.DuckDBPyConnection) -> list[tuple[str, int, date, date]]:
    """Row count and date range of each table."""
    tables = [(s.table, s.date_column) for s in SOURCES]
    tables += [(table, next(iter(columns))) for table, columns in API_TABLES.items()]
    query = " UNION ALL ".join(
        f"SELECT '{table}', count(*), min({column}), max({column}) FROM {table}"
        for table, column in tables
    )
    return con.execute(query).fetchall()


def export_realtime(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Write the real-time load to a Parquet file, and return its number of rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    target = str(path).replace("'", "''")
    con.execute(
        f"COPY (SELECT * FROM load_realtime ORDER BY date, time) TO '{target}' (FORMAT parquet)"
    )
    rows: int = con.execute("SELECT count(*) FROM load_realtime").fetchall()[0][0]
    return rows


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
