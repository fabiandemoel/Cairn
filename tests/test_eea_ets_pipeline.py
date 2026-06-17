"""Tests for the EEA EU ETS bulk pipeline. No network and no Excel engine: the
release-filename parsing, the workbook-locating logic, and the idempotency
short-circuit are all exercised against in-memory inputs. (The xlsx->parquet
conversion needs the duckdb excel extension and is validated by running the
pipeline, not in unit tests -- like the CBS OData fetch.)
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ingestion import eea_ets_pipeline as ep
from ingestion.manifest import Manifest, Snapshot, save_manifest

# --- release-filename parsing ------------------------------------------------


def test_release_from_filename_version_token() -> None:
    fn = "eea_t_eu-emission-trading-scheme_p_2005-2025_v01_r00.zip"
    assert ep._release_from_filename(fn) == "2005-2025_v01_r00"


def test_release_from_filename_rejects_unparseable() -> None:
    with pytest.raises(ValueError, match="Cannot derive a release"):
        ep._release_from_filename("random_download.zip")


# --- workbook location -------------------------------------------------------


def _zip_with(tmp_path: Path, names: list[str]) -> Path:
    path = tmp_path / "eea.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(name, "x")
    return path


def test_find_data_workbook_picks_the_database(tmp_path: Path) -> None:
    folder = "eea_t_eu-emission-trading-scheme_p_2005-2025_v01_r00"
    zip_path = _zip_with(
        tmp_path,
        [
            f"{folder}/ETS_Database_April_2026.xlsx",
            f"{folder}/Translation of activity codes May 2019.xlsx",
            f"{folder}/README.md",
            f"{folder}/manual.pdf",
        ],
    )
    with zipfile.ZipFile(zip_path) as zf:
        assert ep._find_data_workbook(zf) == f"{folder}/ETS_Database_April_2026.xlsx"


def test_find_data_workbook_raises_when_absent(tmp_path: Path) -> None:
    zip_path = _zip_with(tmp_path, ["folder/README.md", "folder/manual.pdf"])
    with zipfile.ZipFile(zip_path) as zf, pytest.raises(ValueError, match="exactly one"):
        ep._find_data_workbook(zf)


# --- idempotency short-circuit (no download) ---------------------------------


def test_run_skips_when_release_already_pinned(tmp_path: Path, monkeypatch) -> None:
    release = "2005-2025_v01_r00"
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
                    storage_url="file:///tmp/data.parquet",
                    sha256="a" * 64,
                    row_count=1,
                    periods_covered=["2005", "2025"],
                )
            ],
        ),
    )
    monkeypatch.setattr(ep, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(ep, "_peek_release", lambda url: release)

    def _no_network(*args, **kwargs):
        raise AssertionError("download must not run when the release is already pinned")

    monkeypatch.setattr(ep, "_download", _no_network)

    assert ep.run("https://example/download", offline=True) == 0
