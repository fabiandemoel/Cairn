"""Tests for the euets.info ingestion pipeline. No network: a tiny in-memory
zip of CSV tables exercises extraction, column-faithful conversion, the
deliberate exclusion of unused tables, deterministic ordering, and the
release-id parsing and idempotency short-circuit.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import duckdb
import pytest

from ingestion import euets_pipeline as ep
from ingestion.manifest import Manifest, Snapshot, compute_sha256, save_manifest

# Minimal stand-ins for the real zip members: only enough columns to exercise
# the logic. ``transaction.csv`` represents the big tables Cairn must NOT ingest.
FIXTURE_CSVS = {
    "compliance.csv": "installation_id,year,verified\nNL_2,2006,10\nNL_1,2005,5\nNL_1,2006,7\n",
    "installation.csv": "id,registry_id,nace_id\nNL_1,NL,35\nNL_2,NL,20\n",
    "nace_code.csv": "id,level,description\n35,2,Electricity\n20,2,Chemicals\n",
    "activity_type.csv": "id,description\n20,Combustion of fuels\n",
    "country_code.csv": "id,description\nNL,Netherlands\n",
    "transaction.csv": "id,amount\n1,999\n",  # must be excluded
}


def _make_zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return path


# --- release id parsing ------------------------------------------------------


def test_release_from_url_publication_token() -> None:
    url = "https://x.s3.eu-central-1.amazonaws.com/eutl_2024_202410.zip"
    assert ep._release_from_url(url) == "2024-10"


def test_release_from_url_year_only() -> None:
    assert ep._release_from_url("https://x/eutl_2023.zip") == "2023"


def test_release_from_url_rejects_unparseable() -> None:
    with pytest.raises(ValueError, match="Cannot derive a release"):
        ep._release_from_url("https://x/eutl_latest.zip")


# --- extraction & conversion -------------------------------------------------


def test_export_parquets_writes_only_wanted_tables(tmp_path: Path) -> None:
    zip_path = _make_zip(tmp_path / "eutl.zip", FIXTURE_CSVS)
    out = tmp_path / "release"
    ep._export_parquets(zip_path, out)

    produced = {p.name for p in out.iterdir()}
    assert produced == set(ep.EUETS_TABLES.values())
    # the excluded big table never lands, in any form
    assert not (out / "transaction.parquet").exists()
    assert "transaction.csv" not in produced


def test_export_parquets_is_column_faithful(tmp_path: Path) -> None:
    zip_path = _make_zip(tmp_path / "eutl.zip", FIXTURE_CSVS)
    out = tmp_path / "release"
    ep._export_parquets(zip_path, out)

    cols = [
        c[0]
        for c in duckdb.sql(
            f"DESCRIBE SELECT * FROM read_parquet('{(out / 'compliance.parquet').as_posix()}')"
        ).fetchall()
    ]
    assert cols == ["installation_id", "year", "verified"]


def test_export_parquets_is_deterministic(tmp_path: Path) -> None:
    zip_path = _make_zip(tmp_path / "eutl.zip", FIXTURE_CSVS)
    a, b = tmp_path / "a", tmp_path / "b"
    ep._export_parquets(zip_path, a)
    ep._export_parquets(zip_path, b)
    # ORDER BY ALL makes a re-export of the same source byte-stable
    assert compute_sha256(a / "compliance.parquet") == compute_sha256(b / "compliance.parquet")


def test_export_parquets_raises_on_missing_table(tmp_path: Path) -> None:
    incomplete = {k: v for k, v in FIXTURE_CSVS.items() if k != "compliance.csv"}
    zip_path = _make_zip(tmp_path / "eutl.zip", incomplete)
    with pytest.raises(ValueError, match="missing expected tables"):
        ep._export_parquets(zip_path, tmp_path / "release")


# --- derived metadata --------------------------------------------------------


def test_periods_and_row_count(tmp_path: Path) -> None:
    zip_path = _make_zip(tmp_path / "eutl.zip", FIXTURE_CSVS)
    out = tmp_path / "release"
    ep._export_parquets(zip_path, out)
    assert ep._periods_covered(out) == ["2005", "2006"]
    assert ep._row_count(out / "compliance.parquet") == 3


# --- idempotency short-circuit (no download) ---------------------------------


def test_run_skips_when_release_already_pinned(tmp_path: Path, monkeypatch) -> None:
    release = ep._release_from_url(ep.DEFAULT_URL)
    manifest_path = tmp_path / "manifest.yml"
    save_manifest(
        manifest_path,
        Manifest(
            source=ep.SOURCE,
            dataset=ep.DATASET,
            snapshots=[
                Snapshot(
                    release=release,
                    ingested_at="2026-06-17T00:00:00Z",
                    storage_url="file:///tmp/compliance.parquet",
                    sha256="a" * 64,
                    row_count=1,
                    periods_covered=["2005", "2024"],
                )
            ],
        ),
    )
    monkeypatch.setattr(ep, "MANIFEST_PATH", manifest_path)

    def _no_network(*args, **kwargs):
        raise AssertionError("download must not run when the release is already pinned")

    monkeypatch.setattr(ep, "_download", _no_network)

    assert ep.run(ep.DEFAULT_URL, offline=True) == 0
