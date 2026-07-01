"""Build the committed CI fixture for the Emissieregistratie pipeline.

Unlike ``build_eu_ets_fixtures.py`` (which subsets a real ``.localstack`` snapshot),
this source has never been ingested from this repo -- its manifest ships unpinned
(``snapshots: []``; CLAUDE.md invariant 2) and no real snapshot exists to subset
from. So this fixture is synthetic: two representative inventory years' "Summary1"
-shaped workbooks, zipped and run through the pipeline's real ``_export_parquet``
conversion, so the committed parquet exercises the same DuckDB ``read_xlsx`` path
as production while containing only fixture data (real IPCC category labels,
illustrative values -- not scraped from the actual UNFCCC submission).

    uv run python scripts/build_emissieregistratie_fixture.py
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

import duckdb

from ingestion import emissieregistratie_pipeline as ep

DEST = Path("tests/fixtures/emissieregistratie/crf_summary1/2026-V1.0/data.parquet")

_SUMMARY1_COLS = [
    "GREENHOUSE GAS SOURCE AND SINK CATEGORIES",
    "Net CO2 emissions/removals",
    "CH4",
    "N2O",
    "HFCs (1)",
    "PFCs (1)",
    "Unspecified mix of HFCs and PFCs (1)",
    "SF6",
    "NF3",
    "NOx",
    "CO",
    "NMVOC",
    "SOX",
    "Total GHG emissions/removals (2)",
]

_YEARS = {
    "1990": [
        (
            "1. Energy",
            "158.2",
            "1.8",
            "0.6",
            "NE",
            "NE",
            "NE",
            "NE",
            "NE",
            "42.0",
            "15.0",
            "11.0",
            "6.0",
            "160.6",
        ),
        (
            "6. Waste",
            "0.2",
            "12.4",
            "0.2",
            "NE",
            "NE",
            "NE",
            "NE",
            "NE",
            "0.1",
            "0.3",
            "0.1",
            "0.0",
            "12.8",
        ),
    ],
    "2024": [
        (
            "1. Energy",
            "142.0",
            "1.2",
            "0.4",
            "NE",
            "NE",
            "NE",
            "NE",
            "NE",
            "38.0",
            "12.0",
            "9.0",
            "4.0",
            "143.6",
        ),
        (
            "1.A. Fuel combustion",
            "140.5",
            "0.9",
            "0.3",
            "NE",
            "NE",
            "NE",
            "NE",
            "NE",
            "37.0",
            "11.0",
            "8.5",
            "3.9",
            "141.7",
        ),
        (
            "6. Waste",
            "0.3",
            "8.1",
            "0.1",
            "NE",
            "NE",
            "NE",
            "NE",
            "NE",
            "0.1",
            "0.2",
            "0.1",
            "0.0",
            "8.5",
        ),
    ],
}


def _q(v: object) -> str:
    if v is None:
        return "NULL"
    s = str(v).replace("'", "''")
    return f"'{s}'"


def _make_xlsx(con: duckdb.DuckDBPyConnection, dest: Path, category_rows: list[tuple]) -> Path:
    """Write a real-shaped "Summary1" XLSX (see emissieregistratie_pipeline docstring)."""
    n = len(_SUMMARY1_COLS)
    total_cols = n + 1

    meta_rows = [(i,) + (None,) * n for i in range(1, 8)]
    header_row = (8,) + tuple(_SUMMARY1_COLS)
    units_row = (
        9,
        None,
        "(kt)",
        None,
        None,
        "CO2 equivalents (kt)",
        None,
        None,
        "(kt)",
        None,
        None,
        None,
        None,
        None,
        "CO2 equivalents (kt)",
    )
    data_rows = [(10 + i,) + r for i, r in enumerate(category_rows)]
    all_rows = [*meta_rows, header_row, units_row, *data_rows]

    values_sql = "VALUES " + ", ".join(f"({', '.join(_q(v) for v in r)})" for r in all_rows)
    col_list = ", ".join(f"c{i}" for i in range(total_cols))

    con.sql(
        f"COPY (SELECT * FROM ({values_sql}) t({col_list})) "
        f"TO '{dest.as_posix()}' "
        f"(FORMAT XLSX, SHEET 'Summary1', HEADER false)"
    )
    return dest


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="cairn-emissieregistratie-fixture-"))
    con = duckdb.connect()
    con.sql("INSTALL excel; LOAD excel;")

    zip_path = work / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for year, rows in _YEARS.items():
            xlsx = _make_xlsx(con, work / f"summary1_{year}.xlsx", rows)
            zf.write(xlsx, f"NLD-CRT-2026-V1.0-{year}.xlsx")
    con.close()

    out = ep._export_parquet(zip_path, work / "release")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(out, DEST)
    n = ep._row_count(DEST)
    print(f"  {DEST}  ({n} rows)")

    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
