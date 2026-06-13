"""Tests for the manifest logic: schema validation, append-only enforcement,
and SHA256 verification. No network -- ``file://`` URLs and a tiny local
parquet fixture keep the full path testable without R2 credentials.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from ingestion.manifest import (
    Manifest,
    Snapshot,
    add_snapshot,
    compute_sha256,
    load_manifest,
    save_manifest,
    verify_snapshot,
)

VALID_SHA = "a" * 64


def _snapshot(**overrides) -> Snapshot:
    base = dict(
        release="2026-03-11",
        ingested_at=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
        storage_url="file:///tmp/data.parquet",
        sha256=VALID_SHA,
        row_count=42,
        periods_covered=["1990", "2025"],
    )
    base.update(overrides)
    return Snapshot(**base)


def _write_parquet(path: Path) -> str:
    duckdb.sql(
        "COPY (SELECT * FROM (VALUES (1.0), (2.0), (3.0)) AS t(value)) "
        f"TO '{path}' (FORMAT PARQUET)"
    )
    return compute_sha256(path)


# --- schema validation -------------------------------------------------------


def test_snapshot_rejects_bad_sha() -> None:
    with pytest.raises(ValueError):
        _snapshot(sha256="not-a-hash")


def test_snapshot_rejects_unknown_storage_scheme() -> None:
    with pytest.raises(ValueError):
        _snapshot(storage_url="http://example.com/data.parquet")


def test_snapshot_rejects_negative_row_count() -> None:
    with pytest.raises(ValueError):
        _snapshot(row_count=-1)


def test_manifest_forbids_extra_keys() -> None:
    with pytest.raises(ValueError):
        Manifest.model_validate(
            {"source": "cbs", "dataset": "85669NED", "snapshots": [], "rogue": 1}
        )


def test_load_invalid_manifest_raises(tmp_path: Path) -> None:
    bad = tmp_path / "manifest.yml"
    bad.write_text("source: cbs\n", encoding="utf-8")  # missing dataset
    with pytest.raises(ValueError):
        load_manifest(bad)


def test_load_empty_manifest_raises(tmp_path: Path) -> None:
    empty = tmp_path / "manifest.yml"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(empty)


# --- append-only enforcement -------------------------------------------------


def test_add_snapshot_appends() -> None:
    manifest = Manifest(source="cbs", dataset="85669NED")
    updated = add_snapshot(manifest, _snapshot())
    assert len(updated.snapshots) == 1
    assert manifest.snapshots == []  # input not mutated


def test_add_snapshot_refuses_duplicate_release() -> None:
    manifest = Manifest(source="cbs", dataset="85669NED", snapshots=[_snapshot()])
    with pytest.raises(ValueError, match="append-only"):
        add_snapshot(manifest, _snapshot(release="2026-03-11", sha256="b" * 64))


def test_add_snapshot_allows_new_release() -> None:
    manifest = Manifest(source="cbs", dataset="85669NED", snapshots=[_snapshot()])
    updated = add_snapshot(
        manifest,
        _snapshot(release="2026-06-10", ingested_at=datetime(2026, 6, 13, 7, 0, tzinfo=UTC)),
    )
    assert len(updated.snapshots) == 2
    assert updated.latest.release == "2026-06-10"


# --- round-trip --------------------------------------------------------------


def test_save_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yml"
    manifest = Manifest(source="cbs", dataset="85669NED", snapshots=[_snapshot()])
    save_manifest(path, manifest)
    reloaded = load_manifest(path)
    assert reloaded == manifest


# --- hash verification -------------------------------------------------------


def test_verify_snapshot_passes_on_match(tmp_path: Path) -> None:
    data = tmp_path / "data.parquet"
    sha = _write_parquet(data)
    snap = _snapshot(storage_url=f"file://{data}", sha256=sha)
    assert verify_snapshot(snap) is True


def test_verify_snapshot_raises_on_mismatch(tmp_path: Path) -> None:
    data = tmp_path / "data.parquet"
    _write_parquet(data)
    snap = _snapshot(storage_url=f"file://{data}", sha256=VALID_SHA)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        verify_snapshot(snap)


def test_verify_snapshot_raises_on_missing_file(tmp_path: Path) -> None:
    snap = _snapshot(storage_url=f"file://{tmp_path / 'nope.parquet'}")
    with pytest.raises(FileNotFoundError):
        verify_snapshot(snap)
