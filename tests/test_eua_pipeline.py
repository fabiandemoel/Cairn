"""Tests for the EEX EUA auction-results ingestion pipeline.

No network access: all tests use in-memory data or synthetically generated
XLSX workbooks so CI runs fully offline.  Exercises URL parsing, XLSX member
detection, CSV-to-parquet conversion, column faithfulness, determinism,
period detection, row counting, and the idempotency short-circuit.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from ingestion import eua_pipeline as ep
from ingestion.manifest import Manifest, Snapshot, compute_sha256, save_manifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Column names matching the EEX "Primary Market Auction" sheet (B6:BJ)
_AUCTION_COLS = [
    "Time",
    "Auction Name",
    "Contract",
    "Status",
    "Auction Price €/tCO2",
    "Minimum Bid €/tCO2",
    "Maximum Bid €/tCO2",
    "Mean €/tCO2",
    "Median €/tCO2",
    "Auction Volume tCO2",
    "Total Amount of Bids",
    "Number of bids submitted",
    "Number of successful bids",
    "Average number of bids per bidder",
    "Average bid size",
    "Average volume bid per bidder",
    "Standard deviation of bid volume per bidder",
    "Average volume won per bidder",
    "Standard deviation of volume won per bidder",
    "Cover Ratio",
    "Total Number of Bidders",
    "Number of Successful Bidders",
    "Total Revenue €",
    "Country",
    "Austria (AT)",
    "Netherlands (NL)",
    "Germany (DE)",
]

# Two representative auction rows (Excel serial dates: 46006 = 2025-12-16,
# 43862 = 2020-02-01).
_SAMPLE_ROWS = [
    (
        "46006",
        "T3PA",
        "T3PA",
        "successful",
        "84.6",
        "64.0",
        "90.0",
        "82.1",
        "82.5",
        "4200000",
        "145",
        "145",
        "89",
        "3.2",
        "42000",
        "134400",
        "21000",
        "47191",
        "18000",
        "1.55",
        "45",
        "28",
        "355320000",
        "EU",
        "100000",
        "500000",
        "0",
    ),
    (
        "43862",
        "T3PA",
        "T3PA",
        "successful",
        "24.73",
        "10.0",
        "30.0",
        "23.5",
        "24.0",
        "3600000",
        "120",
        "120",
        "75",
        "2.8",
        "30000",
        "84000",
        "12000",
        "48000",
        "10000",
        "1.45",
        "40",
        "22",
        "89028000",
        "EU",
        "90000",
        "450000",
        "0",
    ),
]


def _make_xlsx(tmp_path: Path, rows: list[tuple]) -> Path:
    """Create a minimal EEX-style XLSX in *tmp_path* and return its path.

    Replicates the real workbook structure:
    - Column A: row-sequence integer (ensures DuckDB writes column A so that
      the data columns B… correctly align with range='B6:CA99999')
    - Columns B–...: the test columns from ``_AUCTION_COLS``
    - Row 1–5: title rows
    - Row 6: header row (column names in columns B+)
    - Row 7+: data rows

    Written with ``HEADER false`` and sheet ``"Primary Market Auction"`` so
    that ``_export_parquet``'s ``range='B6:CA99999'`` reads the header from
    row 6.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.sql("INSTALL excel; LOAD excel;")

    n = len(_AUCTION_COLS)
    total_cols = n + 1  # col A (sequence) + n data columns

    def _q(v: object) -> str:
        if v is None:
            return "NULL"
        s = str(v).replace("'", "''")
        return f"'{s}'"

    # Row layout: (col_A_int, col_B, col_C, ...) where col_A is a row counter
    # that ensures column A is written to the XLSX (DuckDB skips all-null cols).
    # Row 1: title label in col B
    title_row_1 = (1, "EEX Emission Spot Primary Market Auction Report") + (None,) * (n - 1)
    # Rows 2–5: just the counter in col A, rest null
    blank_rows = [(i, None) + (None,) * (n - 1) for i in range(2, 6)]
    # Row 6: counter 6 in col A, then the actual column names in B+
    header_row = (6,) + tuple(_AUCTION_COLS)
    # Data rows: counter starts at 7, then actual data values
    data_rows = [(7 + i,) + r for i, r in enumerate(rows)]

    all_rows = [title_row_1] + blank_rows + [header_row] + data_rows

    values_parts = [f"({', '.join(_q(v) for v in r)})" for r in all_rows]
    values_sql = "VALUES " + ", ".join(values_parts)
    col_list = ", ".join(f"c{i}" for i in range(total_cols))

    xlsx = tmp_path / "auction_report.xlsx"
    con.sql(
        f"COPY (SELECT * FROM ({values_sql}) t({col_list})) "
        f"TO '{xlsx.as_posix()}' "
        f"(FORMAT XLSX, SHEET 'Primary Market Auction', HEADER false)"
    )
    con.close()
    return xlsx


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------


def test_release_from_url_standard() -> None:
    url = (
        "https://www.eex.com/fileadmin/EEX/Downloads/"
        "EUA_Emission_Spot_Primary_Market_Auction_Report/Archive_Reports/"
        "emission-spot-primary-market-auction-report-2012-2025-data.zip"
    )
    assert ep._release_from_url(url) == "2012-2025"


def test_release_from_url_future_range() -> None:
    url = (
        "https://www.eex.com/fileadmin/.../emission-spot-primary-market-"
        "auction-report-2012-2026-data.zip"
    )
    assert ep._release_from_url(url) == "2012-2026"


def test_release_from_url_rejects_unknown_pattern() -> None:
    with pytest.raises(ValueError, match="Cannot derive a release token"):
        ep._release_from_url("https://example.com/no-year-range-here.zip")


# ---------------------------------------------------------------------------
# XLSX member detection
# ---------------------------------------------------------------------------


def test_find_xlsx_members_excludes_xls(tmp_path: Path) -> None:
    """XLS files (Phase 3, unsupported format) must be excluded."""
    import zipfile

    zf_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.writestr("2024/report-2024-data.xlsx", b"")
        zf.writestr("2019/report-2019-data.xls", b"")
        zf.writestr("2023/report-2023-data.xlsx", b"")
        zf.writestr("README.pdf", b"")

    with zipfile.ZipFile(zf_path) as zf:
        members = ep._find_xlsx_members(zf)

    assert members == ["2023/report-2023-data.xlsx", "2024/report-2024-data.xlsx"]
    assert not any(m.lower().endswith(".xls") for m in members)


def test_find_xlsx_members_sorted(tmp_path: Path) -> None:
    import zipfile

    zf_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.writestr("b.xlsx", b"")
        zf.writestr("a.xlsx", b"")

    with zipfile.ZipFile(zf_path) as zf:
        members = ep._find_xlsx_members(zf)

    assert members == ["a.xlsx", "b.xlsx"]


# ---------------------------------------------------------------------------
# Parquet export
# ---------------------------------------------------------------------------


def test_export_parquet_column_faithful(tmp_path: Path) -> None:
    """All expected column names must survive the XLSX→parquet conversion."""
    xlsx = _make_xlsx(tmp_path, _SAMPLE_ROWS)

    import zipfile

    zf_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.write(xlsx, "2025/auction_report.xlsx")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    cols = [
        r[0]
        for r in duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{dest.as_posix()}')").fetchall()
    ]
    for expected_col in ("Time", "Auction Name", "Status", "Auction Price €/tCO2"):
        assert expected_col in cols, f"Column {expected_col!r} missing from parquet"


def test_export_parquet_all_varchar(tmp_path: Path) -> None:
    """All columns must be VARCHAR — typing belongs in the dbt staging layer."""
    xlsx = _make_xlsx(tmp_path, _SAMPLE_ROWS)

    import zipfile

    zf_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.write(xlsx, "2025/auction_report.xlsx")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    types = {
        r[0]: r[1]
        for r in duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{dest.as_posix()}')").fetchall()
    }
    non_varchar = {col: t for col, t in types.items() if t != "VARCHAR"}
    assert not non_varchar, f"Expected all VARCHAR columns; got {non_varchar}"


def test_export_parquet_row_count(tmp_path: Path) -> None:
    xlsx = _make_xlsx(tmp_path, _SAMPLE_ROWS)

    import zipfile

    zf_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.write(xlsx, "2025/auction_report.xlsx")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    assert ep._row_count(dest) == len(_SAMPLE_ROWS)


def test_export_parquet_combines_multiple_xlsx(tmp_path: Path) -> None:
    """Rows from multiple XLSX workbooks must be combined into one parquet."""
    row_a = _SAMPLE_ROWS[:1]
    row_b = _SAMPLE_ROWS[1:]

    import zipfile

    zf_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.write(_make_xlsx(tmp_path / "xa", row_a), "2025/a.xlsx")
        zf.write(_make_xlsx(tmp_path / "xb", row_b), "2024/b.xlsx")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    assert ep._row_count(dest) == 2


def test_export_parquet_is_deterministic(tmp_path: Path) -> None:
    xlsx_a = _make_xlsx(tmp_path / "da", _SAMPLE_ROWS)
    xlsx_b = _make_xlsx(tmp_path / "db", _SAMPLE_ROWS)

    import zipfile

    zf_a = tmp_path / "archive_a.zip"
    zf_b = tmp_path / "archive_b.zip"
    for zf_path, xlsx in [(zf_a, xlsx_a), (zf_b, xlsx_b)]:
        with zipfile.ZipFile(zf_path, "w") as zf:
            zf.write(xlsx, "2025/report.xlsx")

    dest_a = ep._export_parquet(zf_a, tmp_path / "out_a")
    dest_b = ep._export_parquet(zf_b, tmp_path / "out_b")
    assert compute_sha256(dest_a) == compute_sha256(dest_b)


def test_export_parquet_raises_on_empty_zip(tmp_path: Path) -> None:
    import zipfile

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

    import zipfile

    zf_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.write(xlsx, "2025/report.xlsx")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    assert ep._row_count(dest) == len(_SAMPLE_ROWS)


def test_periods_covered(tmp_path: Path) -> None:
    """Year range must be derived from the Excel serial-date Time column."""
    xlsx = _make_xlsx(tmp_path, _SAMPLE_ROWS)

    import zipfile

    zf_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zf_path, "w") as zf:
        zf.write(xlsx, "2025/report.xlsx")

    dest = ep._export_parquet(zf_path, tmp_path / "release")
    periods = ep._periods_covered(dest)
    # _SAMPLE_ROWS has serial dates 43862 (2020) and 46006 (2025)
    assert periods == ["2020", "2025"]


# ---------------------------------------------------------------------------
# Fixture parquet sanity check
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "eua" / "2012-2025" / "data.parquet"


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="fixture not committed")
def test_fixture_parquet_schema() -> None:
    """Committed fixture must have all expected auction columns and be all-VARCHAR."""
    types = {
        r[0]: r[1]
        for r in duckdb.sql(
            f"DESCRIBE SELECT * FROM read_parquet('{FIXTURE_PATH.as_posix()}')"
        ).fetchall()
    }
    for col in ("Time", "Auction Name", "Status", "Auction Price €/tCO2"):
        assert col in types, f"Fixture missing column {col!r}"
        assert types[col] == "VARCHAR", f"Column {col!r} is {types[col]!r}, expected VARCHAR"


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="fixture not committed")
def test_fixture_parquet_period_range() -> None:
    """Fixture must span the 2025 period (most recent data in the archive)."""
    periods = ep._periods_covered(FIXTURE_PATH)
    assert int(periods[1]) >= 2025, f"Fixture max year {periods[1]} too old"


# ---------------------------------------------------------------------------
# Idempotency short-circuit
# ---------------------------------------------------------------------------


def test_run_skips_when_release_already_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = "2012-2025"
    manifest_path = tmp_path / "manifest.yml"
    save_manifest(
        manifest_path,
        Manifest(
            source=ep.SOURCE,
            dataset=ep.DATASET,
            snapshots=[
                Snapshot(
                    release=release,
                    ingested_at="2025-03-01T00:00:00Z",
                    storage_url="file:///tmp/data.parquet",
                    sha256="a" * 64,
                    row_count=1000,
                    periods_covered=["2020", "2025"],
                )
            ],
        ),
    )
    monkeypatch.setattr(ep, "MANIFEST_PATH", manifest_path)

    def _no_download(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("_download must not be called when the release is already pinned")

    monkeypatch.setattr(ep, "_download", _no_download)

    assert ep.run(offline=True) == 0
