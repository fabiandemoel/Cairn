"""Tests for the benchmark diff renderer. Tiny parquet fixtures via duckdb."""

from __future__ import annotations

from pathlib import Path

import duckdb

from scripts.benchmark_diff import compute_diff, render_markdown


def _write_mart(path: Path, rows: list[tuple]) -> None:
    con = duckdb.connect()
    con.execute(
        "create table m (nace_section varchar, year integer, sector_emissions_mt_co2eq double)"
    )
    if rows:
        con.executemany("insert into m values (?, ?, ?)", rows)
    con.execute(f"COPY (SELECT * FROM m) TO '{path.as_posix()}' (FORMAT PARQUET)")


def test_diff_flags_large_change_and_tracks_appearance(tmp_path: Path) -> None:
    old = tmp_path / "old.parquet"
    new = tmp_path / "new.parquet"
    _write_mart(old, [("C", 2024, 100.0), ("A", 2024, 10.0)])
    _write_mart(new, [("C", 2024, 120.0), ("D", 2024, 5.0)])  # C +20%, A removed, D new

    rows = compute_diff(str(old), str(new))
    by_key = {(r[0], r[1]): r for r in rows}

    assert by_key[("C", 2024)][4] == 20.0  # delta_pct
    assert by_key[("A", 2024)][4] is None  # removed
    assert by_key[("D", 2024)][4] is None  # new

    md = render_markdown(rows)
    assert "⚠️" in md  # C +20% exceeds the 10% threshold
    assert "_removed_" in md
    assert "_new_" in md


def test_diff_empty_inputs(tmp_path: Path) -> None:
    old = tmp_path / "old.parquet"
    new = tmp_path / "new.parquet"
    _write_mart(old, [])
    _write_mart(new, [])
    md = render_markdown(compute_diff(str(old), str(new)))
    assert "no rows" in md
