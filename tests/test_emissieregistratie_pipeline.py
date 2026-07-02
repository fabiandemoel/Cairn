"""Tests for the RIVM Emissieregistratie (UNFCCC CRF) ingestion pipeline.

No network access: all tests use in-memory data or synthetically generated XLSX
workbooks so CI runs fully offline. Exercises URL/filename parsing, XLSX member
detection, workbook-to-parquet conversion, column faithfulness, determinism,
period detection, row counting, and the idempotency short-circuit -- like
``test_eua_pipeline.py``, which this mirrors most closely (also a zip of
per-something XLSX workbooks combined into one parquet).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import duckdb
import pytest

from ingestion import emissieregistratie_pipeline as ep
from ingestion.manifest import Manifest, Snapshot, compute_sha256, save_manifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Column names matching the real CRF "Summary1" sheet's row-8 header (B-O).
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

# Three representative IPCC category rows (category, then 13 gas/total values).
_SAMPLE_ROWS = [
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
]


def _make_xlsx(tmp_path: Path, category_rows: list[tuple]) -> Path:
    """Create a minimal, real-shaped "Summary1" XLSX in *tmp_path*.

    Replicates the real workbook structure:
    - Column A: row-sequence integer (ensures DuckDB writes column A so the data
      columns B... correctly align with range='B8:O67'; the real column A is
      blank throughout, but an all-null column is dropped on XLSX write).
    - Rows 1-7: title/metadata (blank in the data columns).
    - Row 8: header row (gas names in columns B+).
    - Row 9: units sub-header (kept as an ordinary row -- the pipeline treats it
      as data, per the module docstring).
    - Row 10+: IPCC category rows.

    Written with ``HEADER false`` and sheet ``"Summary1"`` so
    ``_export_parquet``'s ``range='B8:O67'`` reads the header from row 8.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.sql("INSTALL excel; LOAD excel;")

    n = len(_SUMMARY1_COLS)
    total_cols = n + 1  # col A (sequence) + n data columns

    def _q(v: object) -> str:
        if v is None:
            return "NULL"
        s = str(v).replace("'", "''")
        return f"'{s}'"

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

    values_parts = [f"({', '.join(_q(v) for v in r)})" for r in all_rows]
    values_sql = "VALUES " + ", ".join(values_parts)
    col_list = ", ".join(f"c{i}" for i in range(total_cols))

    xlsx = tmp_path / "summary1.xlsx"
    con.sql(
        f"COPY (SELECT * FROM ({values_sql}) t({col_list})) "
        f"TO '{xlsx.as_posix()}' "
        f"(FORMAT XLSX, SHEET 'Summary1', HEADER false)"
    )
    con.close()
    return xlsx


def _zip_with_year(tmp_path: Path, xlsx: Path, year: str, index: int = 0) -> Path:
    zf_path = tmp_path / f"archive_{index}.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.write(xlsx, f"NLD-CRT-2026-V1.0-{year}.xlsx")
    return zf_path


# ---------------------------------------------------------------------------
# Release-URL parsing
# ---------------------------------------------------------------------------


def test_release_from_url_standard() -> None:
    url = "https://unfccc.int/sites/default/files/resource/NLD-CRT-2026-V1.0.zip"
    assert ep._release_from_url(url) == "2026-V1.0"


def test_release_from_url_future_release() -> None:
    url = "https://unfccc.int/sites/default/files/resource/NLD-CRT-2027-V1.0.zip"
    assert ep._release_from_url(url) == "2027-V1.0"


def test_release_from_url_rejects_unknown_pattern() -> None:
    with pytest.raises(ValueError, match="Cannot derive a release token"):
        ep._release_from_url("https://example.com/no-prefix-here.zip")


# ---------------------------------------------------------------------------
# XLSX member / year detection
# ---------------------------------------------------------------------------


def test_find_xlsx_members_sorted(tmp_path: Path) -> None:
    zf_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.writestr("NLD-CRT-2026-V1.0-1991.xlsx", b"")
        zf.writestr("NLD-CRT-2026-V1.0-1990.xlsx", b"")
        zf.writestr("README.pdf", b"")

    with zipfile.ZipFile(zf_path) as zf:
        members = ep._find_xlsx_members(zf)

    assert members == ["NLD-CRT-2026-V1.0-1990.xlsx", "NLD-CRT-2026-V1.0-1991.xlsx"]


def test_year_from_member() -> None:
    assert ep._year_from_member("NLD-CRT-2026-V1.0-2005.xlsx") == "2005"


def test_year_from_member_rejects_unparseable() -> None:
    with pytest.raises(ValueError, match="Cannot derive an inventory year"):
        ep._year_from_member("summary.xlsx")


# ---------------------------------------------------------------------------
# Parquet export
# ---------------------------------------------------------------------------


def test_export_parquet_column_faithful(tmp_path: Path) -> None:
    xlsx = _make_xlsx(tmp_path, _SAMPLE_ROWS)
    zf_path = _zip_with_year(tmp_path, xlsx, "2024")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    cols = [
        r[0]
        for r in duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{dest.as_posix()}')").fetchall()
    ]
    assert "inventory_year" in cols
    for expected_col in (*_SUMMARY1_COLS,):
        assert expected_col in cols, f"Column {expected_col!r} missing from parquet"


def test_export_parquet_all_varchar(tmp_path: Path) -> None:
    """All columns must be VARCHAR -- typing belongs in the dbt staging layer."""
    xlsx = _make_xlsx(tmp_path, _SAMPLE_ROWS)
    zf_path = _zip_with_year(tmp_path, xlsx, "2024")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    types = {
        r[0]: r[1]
        for r in duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{dest.as_posix()}')").fetchall()
    }
    non_varchar = {col: t for col, t in types.items() if t != "VARCHAR"}
    assert not non_varchar, f"Expected all VARCHAR columns; got {non_varchar}"


def test_export_parquet_keeps_units_subheader_row(tmp_path: Path) -> None:
    """Row 9 (units sub-header) is preserved as an ordinary row, not dropped."""
    xlsx = _make_xlsx(tmp_path, _SAMPLE_ROWS)
    zf_path = _zip_with_year(tmp_path, xlsx, "2024")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    # 1 units row + len(_SAMPLE_ROWS) category rows.
    assert ep._row_count(dest) == len(_SAMPLE_ROWS) + 1


def test_export_parquet_combines_multiple_xlsx(tmp_path: Path) -> None:
    """Rows from multiple per-year XLSX workbooks must be combined into one parquet."""
    xlsx_a = _make_xlsx(tmp_path / "a", _SAMPLE_ROWS[:1])
    xlsx_b = _make_xlsx(tmp_path / "b", _SAMPLE_ROWS[1:])

    zf_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.write(xlsx_a, "NLD-CRT-2026-V1.0-1990.xlsx")
        zf.write(xlsx_b, "NLD-CRT-2026-V1.0-2024.xlsx")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    # 2 units rows (one per year) + 1 + 2 category rows.
    assert ep._row_count(dest) == 2 + 1 + 2

    years = {
        r[0]
        for r in duckdb.sql(
            f"SELECT DISTINCT inventory_year FROM read_parquet('{dest.as_posix()}')"
        ).fetchall()
    }
    assert years == {"1990", "2024"}


def test_export_parquet_is_deterministic(tmp_path: Path) -> None:
    xlsx_a = _make_xlsx(tmp_path / "da", _SAMPLE_ROWS)
    xlsx_b = _make_xlsx(tmp_path / "db", _SAMPLE_ROWS)

    zf_a = tmp_path / "archive_a.zip"
    zf_b = tmp_path / "archive_b.zip"
    for zf_path, xlsx in [(zf_a, xlsx_a), (zf_b, xlsx_b)]:
        with zipfile.ZipFile(zf_path, "w") as zf:
            zf.write(xlsx, "NLD-CRT-2026-V1.0-2024.xlsx")

    dest_a = ep._export_parquet(zf_a, tmp_path / "out_a")
    dest_b = ep._export_parquet(zf_b, tmp_path / "out_b")
    assert compute_sha256(dest_a) == compute_sha256(dest_b)


def test_export_parquet_raises_on_empty_zip(tmp_path: Path) -> None:
    zf_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.writestr("README.pdf", b"")

    with pytest.raises(ValueError, match="No XLSX files found"):
        ep._export_parquet(zf_path, tmp_path / "release")


# ---------------------------------------------------------------------------
# Derived metadata
# ---------------------------------------------------------------------------


def test_row_count(tmp_path: Path) -> None:
    xlsx = _make_xlsx(tmp_path, _SAMPLE_ROWS)
    zf_path = _zip_with_year(tmp_path, xlsx, "2024")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    assert ep._row_count(dest) == len(_SAMPLE_ROWS) + 1


def test_periods_covered(tmp_path: Path) -> None:
    xlsx_a = _make_xlsx(tmp_path / "a", _SAMPLE_ROWS[:1])
    xlsx_b = _make_xlsx(tmp_path / "b", _SAMPLE_ROWS[1:])

    zf_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.write(xlsx_a, "NLD-CRT-2026-V1.0-1990.xlsx")
        zf.write(xlsx_b, "NLD-CRT-2026-V1.0-2024.xlsx")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    assert ep._periods_covered(dest) == ["1990", "2024"]


# ---------------------------------------------------------------------------
# Fixture parquet sanity check
# ---------------------------------------------------------------------------

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "emissieregistratie"
    / "crf_summary1"
    / "2026-V1.0"
    / "data.parquet"
)


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="fixture not committed")
def test_fixture_parquet_schema() -> None:
    """Committed fixture must have the expected Summary1 columns and be all-VARCHAR."""
    types = {
        r[0]: r[1]
        for r in duckdb.sql(
            f"DESCRIBE SELECT * FROM read_parquet('{FIXTURE_PATH.as_posix()}')"
        ).fetchall()
    }
    for col in ("inventory_year", *_SUMMARY1_COLS):
        assert col in types, f"Fixture missing column {col!r}"
        assert types[col] == "VARCHAR", f"Column {col!r} is {types[col]!r}, expected VARCHAR"


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="fixture not committed")
def test_fixture_parquet_has_rows() -> None:
    assert ep._row_count(FIXTURE_PATH) > 0


# ---------------------------------------------------------------------------
# Idempotency short-circuit (no download)
# ---------------------------------------------------------------------------


def test_run_skips_when_release_already_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = "2026-V1.0"
    manifest_path = tmp_path / "manifest.yml"
    save_manifest(
        manifest_path,
        Manifest(
            source=ep.SOURCE,
            dataset=ep.DATASET,
            snapshots=[
                Snapshot(
                    release=release,
                    ingested_at="2026-07-01T00:00:00Z",
                    storage_url="file:///tmp/data.parquet",
                    sha256="a" * 64,
                    row_count=1,
                    periods_covered=["1990", "2024"],
                )
            ],
        ),
    )
    monkeypatch.setattr(ep, "MANIFEST_PATH", manifest_path)

    def _no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("download must not run when the release is already pinned")

    monkeypatch.setattr(ep, "_download", _no_network)

    assert (
        ep.run(
            "https://unfccc.int/sites/default/files/resource/NLD-CRT-2026-V1.0.zip", offline=True
        )
        == 0
    )
