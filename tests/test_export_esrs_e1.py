"""Tests for the ESRS E1 disclosure export. Tiny duckdb fixture in a temp dir."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from scripts.export_esrs_e1 import DATA_DICTIONARY, export

_COLUMNS = [col["column"] for col in DATA_DICTIONARY]


def _write_warehouse(path: Path, rows: list[tuple]) -> None:
    con = duckdb.connect(str(path))
    try:
        cols = ", ".join(
            f"{name} varchar"
            if name
            in {
                "esrs_e1_key",
                "installation_id",
                "installation_name",
                "nace_section",
                "nace_section_label",
                "esrs_datapoint",
                "ghg_scope",
                "unit",
            }
            else f"{name} double"
            if name != "reporting_year"
            else "reporting_year integer"
            for name in _COLUMNS
        )
        con.execute(f"create table mart_esrs_e1 ({cols})")
        placeholders = ", ".join("?" for _ in _COLUMNS)
        con.executemany(f"insert into mart_esrs_e1 values ({placeholders})", rows)
    finally:
        con.close()


def _row(key: str, year: int, inst: str, nace: str, emissions: float) -> tuple:
    return (
        key,
        year,
        inst,
        f"{inst} B.V.",
        nace,
        "MANUFACTURING",
        "E1-6",
        "Scope 1",
        "t CO2eq",
        emissions,
        2,
        emissions,
        emissions,
        1.0,
    )


def test_export_writes_bundle_with_matching_integrity_hash(tmp_path: Path) -> None:
    db = tmp_path / "cairn.duckdb"
    out = tmp_path / "esrs_e1"
    _write_warehouse(
        db,
        [
            _row("NL_1|2022", 2022, "NL_1", "C", 1000.0),
            _row("NL_2|2022", 2022, "NL_2", "C", 500.0),
            _row("NL_1|2023", 2023, "NL_1", "C", 1200.0),
        ],
    )

    meta = export(db, out)

    csv_path = out / "esrs_e1_disclosure.csv"
    assert csv_path.exists()
    assert (out / "esrs_e1_disclosure.meta.json").exists()
    assert (out / "README.md").exists()

    # Coverage is computed from the data, not assumed.
    assert meta["coverage"]["row_count"] == 3
    assert meta["coverage"]["installation_count"] == 2
    assert meta["coverage"]["reporting_years"] == [2022, 2023]

    # The integrity hash in the metadata must match the file actually written.
    recomputed = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    assert meta["integrity"]["csv_sha256"] == recomputed

    # The metadata on disk round-trips and carries the source pin.
    on_disk = json.loads((out / "esrs_e1_disclosure.meta.json").read_text())
    assert on_disk["disclosure"]["datapoint"].startswith("E1-6")
    assert "release" in on_disk["provenance"]


def test_export_orders_by_year_then_emissions_desc(tmp_path: Path) -> None:
    db = tmp_path / "cairn.duckdb"
    out = tmp_path / "esrs_e1"
    _write_warehouse(
        db,
        [
            _row("NL_2|2022", 2022, "NL_2", "C", 500.0),
            _row("NL_1|2022", 2022, "NL_1", "C", 1000.0),
        ],
    )

    export(db, out)

    lines = (out / "esrs_e1_disclosure.csv").read_text().splitlines()
    # Header, then the larger emitter first within the year.
    assert lines[1].startswith("NL_1|2022")
    assert lines[2].startswith("NL_2|2022")
