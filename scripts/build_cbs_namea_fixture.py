"""Build the committed CI fixture for the cbs_namea air_emissions pipeline.

Like ``build_emissieregistratie_fixture.py``, this source has never been
ingested from this repo -- its manifest ships unpinned (``snapshots: []``;
CLAUDE.md invariant 2) and no real snapshot exists to subset from. This
fixture is synthetic: illustrative sector/measure/period code tables and
observations, loaded into DuckDB the way dlt loads them (snake_case entity
sets plus ``_dlt_*`` bookkeeping columns) and exported through the pipeline's
real ``_export_parquets``, so the committed parquets exercise the same column
shapes and ordering as a real ingest.

    uv run python scripts/build_cbs_namea_fixture.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from ingestion import cbs_namea_pipeline as ep

DEST = Path("tests/fixtures/cbs_namea/air_emissions/2025-11-13")
RAW = "cbs_namea_raw"

_SECTORS = [
    ("B000579", 0, "Totale Nederlandse economie"),
    ("B000581", 1, "Landbouw, bosbouw en visserij"),
]
_MEASURES = [
    ("A044109_2", 0, "Emissie naar lucht: Kooldioxide (CO2)"),
    ("A044110_2", 1, "Emissie naar lucht: Distikstofoxide (N2O)"),
]
_PERIODS = [
    ("1990JJ00", 0, "1990", "Definitief"),
    ("2023JJ00", 1, "2023", "Definitief"),
    ("2024JJ00", 2, "2024", "Voorlopige cijfers"),
]

# (sector, measure, period) -> (value, string_value). One suppressed cell
# (value NULL, string_value ".") exercises the nullable-value path.
_OBSERVATIONS = {
    ("B000579", "A044109_2", "1990JJ00"): (180789.0, None),
    ("B000579", "A044109_2", "2023JJ00"): (146211.0, None),
    ("B000579", "A044109_2", "2024JJ00"): (142788.0, None),
    ("B000579", "A044110_2", "1990JJ00"): (18500.0, None),
    ("B000579", "A044110_2", "2023JJ00"): (10920.0, None),
    ("B000579", "A044110_2", "2024JJ00"): (10410.0, None),
    ("B000581", "A044109_2", "1990JJ00"): (7210.0, None),
    ("B000581", "A044109_2", "2023JJ00"): (6480.0, None),
    ("B000581", "A044109_2", "2024JJ00"): (None, "."),
    ("B000581", "A044110_2", "1990JJ00"): (9840.0, None),
    ("B000581", "A044110_2", "2023JJ00"): (8115.0, None),
    ("B000581", "A044110_2", "2024JJ00"): (7900.0, None),
}


def _q(v: object) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, str):
        return f"'{v}'"
    return str(v)


def main() -> int:
    con = duckdb.connect()
    con.sql(f"CREATE SCHEMA {RAW}")

    obs_rows = [
        f"({i}, {_q(measure)}, NULL, {_q(value)}, {_q(string_value)}, "
        f"{_q(sector)}, {_q(period)}, 'l1', 'r{i}')"
        for i, ((sector, measure, period), (value, string_value)) in enumerate(
            _OBSERVATIONS.items()
        )
    ]
    con.sql(
        f"""
        CREATE TABLE {RAW}.observations AS
        SELECT * FROM (VALUES {", ".join(obs_rows)})
        AS t(id, measure, value_attribute, value, string_value,
             nederlandse_economie, perioden, _dlt_load_id, _dlt_id)
        """
    )

    def _code_table(name: str, rows: list[tuple]) -> None:
        values = ", ".join(f"({_q(r[0])}, {r[1]}, {_q(r[2])}, 'l1', 'r{r[1]}')" for r in rows)
        con.sql(
            f"""
            CREATE TABLE {RAW}.{name} AS
            SELECT * FROM (VALUES {values})
            AS t(identifier, index, title, _dlt_load_id, _dlt_id)
            """
        )

    _code_table("nederlandseeconomiecodes", _SECTORS)
    _code_table("measurecodes", _MEASURES)

    period_values = ", ".join(
        f"({_q(r[0])}, {r[1]}, {_q(r[2])}, {_q(r[3])}, 'l1', 'r{r[1]}')" for r in _PERIODS
    )
    con.sql(
        f"""
        CREATE TABLE {RAW}.periodencodes AS
        SELECT * FROM (VALUES {period_values})
        AS t(identifier, index, title, status, _dlt_load_id, _dlt_id)
        """
    )

    ep._export_parquets(con, RAW, DEST)
    con.close()

    n = ep._row_count(DEST / ep.PRIMARY)
    print(f"  {DEST}  ({n} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
