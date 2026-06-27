"""Tests for the Eurostat AEA ingestion pipeline.

No network access: all tests use in-memory CSVs / JSON payloads so CI runs offline.
Exercises date parsing, the SDMX dataflow metadata parser, CSV-to-parquet conversion,
column faithfulness, determinism, period detection, and the idempotency short-circuit
that prevents duplicate manifest entries.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from ingestion import eurostat_aea_pipeline as ep
from ingestion.manifest import Manifest, Snapshot, compute_sha256, save_manifest

# Minimal SDMX-CSV matching the Eurostat env_ac_ainah_r2 format.
# Two countries, two pollutants, two NACE sectors, two years.
FIXTURE_CSV = (
    "DATAFLOW,LAST UPDATE,freq,airpol,unit,nace_r2,geo,TIME_PERIOD,OBS_VALUE,OBS_FLAG\n"
    "ESTAT:env_ac_ainah_r2(1.0),2024-10-23,A,GHG,THS_T,A,NL,2022,85432.1,\n"
    "ESTAT:env_ac_ainah_r2(1.0),2024-10-23,A,GHG,THS_T,A,NL,2021,89123.5,\n"
    "ESTAT:env_ac_ainah_r2(1.0),2024-10-23,A,GHG,THS_T,B,DE,2022,12345.6,\n"
    "ESTAT:env_ac_ainah_r2(1.0),2024-10-23,A,CO2,THS_T,A,NL,2022,70123.4,\n"
)


# --- date parsing ------------------------------------------------------------


def test_parse_release_dd_mm_yyyy() -> None:
    assert ep._parse_release("23.10.2024") == "2024-10-23"


def test_parse_release_iso_date() -> None:
    assert ep._parse_release("2024-10-23") == "2024-10-23"


def test_parse_release_iso_date_with_time() -> None:
    # Some catalogue responses include a time component after the date.
    assert ep._parse_release("2024-10-23T12:00:00") == "2024-10-23"


def test_parse_release_iso_month() -> None:
    assert ep._parse_release("2024-10") == "2024-10"


def test_parse_release_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Cannot parse"):
        ep._parse_release("Oct 2024")


# --- dataflow metadata parsing ------------------------------------------------


def test_extract_update_date_finds_update_data_annotation() -> None:
    payload = {
        "extension": {
            "annotation": [
                {"type": "CREATED", "date": "2012-12-19T15:46:33+0100"},
                {"type": "UPDATE_DATA", "date": "2026-06-16T11:00:00+0200"},
                {"type": "UPDATE_STRUCTURE", "date": "2026-06-16T11:00:00+0200"},
            ]
        }
    }
    assert ep._extract_update_date(payload) == "2026-06-16T11:00:00+0200"


def test_extract_update_date_missing_annotation_raises() -> None:
    payload = {"extension": {"annotation": [{"type": "CREATED", "date": "2012-12-19"}]}}
    with pytest.raises(ValueError, match="Cannot find a UPDATE_DATA annotation"):
        ep._extract_update_date(payload)


# --- parquet conversion ------------------------------------------------------


def test_export_parquet_column_faithful(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text(FIXTURE_CSV, encoding="utf-8")
    dest = ep._export_parquet(csv_path, tmp_path / "release")
    cols = [
        c[0]
        for c in duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{dest.as_posix()}')").fetchall()
    ]
    # All SDMX-CSV columns must survive the conversion verbatim.
    assert "DATAFLOW" in cols
    assert "LAST UPDATE" in cols
    assert "freq" in cols
    assert "airpol" in cols
    assert "unit" in cols
    assert "nace_r2" in cols
    assert "geo" in cols
    assert "TIME_PERIOD" in cols
    assert "OBS_VALUE" in cols
    assert "OBS_FLAG" in cols


def test_export_parquet_all_varchar(tmp_path: Path) -> None:
    """All columns must be VARCHAR (lossless raw copy; typing belongs in dbt)."""
    csv_path = tmp_path / "data.csv"
    csv_path.write_text(FIXTURE_CSV, encoding="utf-8")
    dest = ep._export_parquet(csv_path, tmp_path / "release")
    types = {
        row[0]: row[1]
        for row in duckdb.sql(
            f"DESCRIBE SELECT * FROM read_parquet('{dest.as_posix()}')"
        ).fetchall()
    }
    non_varchar = {col: t for col, t in types.items() if t != "VARCHAR"}
    assert not non_varchar, f"Expected all VARCHAR columns; got {non_varchar}"


def test_export_parquet_is_deterministic(tmp_path: Path) -> None:
    csv_a = tmp_path / "a.csv"
    csv_b = tmp_path / "b.csv"
    csv_a.write_text(FIXTURE_CSV, encoding="utf-8")
    csv_b.write_text(FIXTURE_CSV, encoding="utf-8")
    dest_a = ep._export_parquet(csv_a, tmp_path / "out_a")
    dest_b = ep._export_parquet(csv_b, tmp_path / "out_b")
    assert compute_sha256(dest_a) == compute_sha256(dest_b)


def test_export_parquet_deletes_source_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text(FIXTURE_CSV, encoding="utf-8")
    ep._export_parquet(csv_path, tmp_path / "release")
    assert not csv_path.exists()


# --- derived metadata --------------------------------------------------------


def test_row_count(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text(FIXTURE_CSV, encoding="utf-8")
    dest = ep._export_parquet(csv_path, tmp_path / "release")
    assert ep._row_count(dest) == 4


def test_periods_covered(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text(FIXTURE_CSV, encoding="utf-8")
    dest = ep._export_parquet(csv_path, tmp_path / "release")
    assert ep._periods_covered(dest) == ["2021", "2022"]


# --- idempotency short-circuit -----------------------------------------------


def test_run_skips_when_release_already_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = "2024-10-23"
    manifest_path = tmp_path / "manifest.yml"
    save_manifest(
        manifest_path,
        Manifest(
            source=ep.SOURCE,
            dataset=ep.DATASET,
            snapshots=[
                Snapshot(
                    release=release,
                    ingested_at="2024-10-24T00:00:00Z",
                    storage_url="file:///tmp/data.parquet",
                    sha256="a" * 64,
                    row_count=100,
                    periods_covered=["1995", "2022"],
                )
            ],
        ),
    )
    monkeypatch.setattr(ep, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(ep, "_fetch_last_update", lambda: release)

    def _no_download(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("_download must not be called when the release is already pinned")

    monkeypatch.setattr(ep, "_download", _no_download)

    assert ep.run(offline=True) == 0
