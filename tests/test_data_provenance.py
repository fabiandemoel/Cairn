"""Tests for the provenance-integrity mart's pure data-gathering logic.

The dbt build exercises ``mart_data_provenance`` end to end; these tests pin the
``collect_provenance_rows`` contract directly (column order, pin_status
classification, the unpinned placeholder, the is_latest flag) without spinning
up dbt, and assert it reflects the repo's real committed manifests.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "transform" / "models" / "marts" / "mart_data_provenance.py"


def _load_model_module():
    spec = importlib.util.spec_from_file_location("mart_data_provenance", MODEL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_model_module()
COLUMNS = [name for name, _ in mod.COLUMNS]


def _idx(col: str) -> int:
    return COLUMNS.index(col)


def _write_manifest(directory: Path, source: str, payload: dict) -> None:
    src_dir = directory / source
    src_dir.mkdir(parents=True)
    (src_dir / "manifest.yml").write_text(yaml.safe_dump(payload), encoding="utf-8")


def test_pin_status_classification():
    assert mod._pin_status("r2://cairn-raw/cbs/x/data.parquet") == "pinned_r2"
    assert mod._pin_status("file:///abs/path/data.parquet") == "pinned_local"
    assert mod._pin_status(None) == "unpinned"


def test_rows_have_full_column_width(tmp_path):
    _write_manifest(
        tmp_path,
        "cbs",
        {
            "source": "cbs",
            "dataset": "85669NED",
            "snapshots": [
                {
                    "release": "2026-03-11",
                    "ingested_at": "2026-06-14T13:17:28.429930Z",
                    "storage_url": "r2://cairn-raw/cbs/85669NED/2026-03-11/data.parquet",
                    "sha256": "a" * 64,
                    "row_count": 9116,
                    "periods_covered": ["1990", "2025"],
                }
            ],
        },
    )
    rows = mod.collect_provenance_rows(str(tmp_path))
    assert len(rows) == 1
    assert all(len(r) == len(COLUMNS) for r in rows)
    row = rows[0]
    assert row[_idx("pin_status")] == "pinned_r2"
    assert row[_idx("storage_backend")] == "r2"
    assert row[_idx("row_count")] == 9116
    assert row[_idx("period_start")] == "1990"
    assert row[_idx("period_end")] == "2025"
    assert row[_idx("is_pinned")] is True
    assert row[_idx("snapshot_count")] == 1


def test_unpinned_source_yields_placeholder_row(tmp_path):
    _write_manifest(
        tmp_path,
        "eurostat",
        {"source": "eurostat", "dataset": "env_ac_ainah_r2", "snapshots": []},
    )
    rows = mod.collect_provenance_rows(str(tmp_path))
    assert len(rows) == 1
    row = rows[0]
    assert row[_idx("provenance_key")] == "eurostat|UNPINNED"
    assert row[_idx("pin_status")] == "unpinned"
    assert row[_idx("is_pinned")] is False
    assert row[_idx("is_latest")] is True
    assert row[_idx("snapshot_count")] == 0
    # No invented figures: every snapshot field is NULL, never a placeholder.
    for col in ("release", "sha256", "row_count", "storage_url", "period_start"):
        assert row[_idx(col)] is None


def test_is_latest_marks_exactly_one_per_source(tmp_path):
    _write_manifest(
        tmp_path,
        "demo",
        {
            "source": "demo",
            "dataset": "d",
            "snapshots": [
                {
                    "release": "2025-01",
                    "ingested_at": "2025-01-10T00:00:00Z",
                    "storage_url": "file:///tmp/old.parquet",
                    "sha256": "b" * 64,
                    "row_count": 1,
                    "periods_covered": ["2020"],
                },
                {
                    "release": "2026-01",
                    "ingested_at": "2026-01-10T00:00:00Z",
                    "storage_url": "r2://cairn-raw/demo/2026-01/data.parquet",
                    "sha256": "c" * 64,
                    "row_count": 2,
                    "periods_covered": ["2020", "2025"],
                },
            ],
        },
    )
    rows = mod.collect_provenance_rows(str(tmp_path))
    assert len(rows) == 2
    latest = [r for r in rows if r[_idx("is_latest")]]
    assert len(latest) == 1
    assert latest[0][_idx("release")] == "2026-01"
    assert latest[0][_idx("pin_status")] == "pinned_r2"
    # The superseded file:// snapshot is still surfaced and flagged as such.
    older = [r for r in rows if not r[_idx("is_latest")]][0]
    assert older[_idx("pin_status")] == "pinned_local"
    assert all(r[_idx("snapshot_count")] == 2 for r in rows)


def test_reflects_committed_manifests():
    rows = mod.collect_provenance_rows(str(REPO_ROOT / "sources"))
    by_source = {r[_idx("source")]: r for r in rows}
    # The committed sources are present and the keys are unique.
    keys = [r[_idx("provenance_key")] for r in rows]
    assert len(keys) == len(set(keys))
    assert {"cbs", "euets", "eea"} <= set(by_source)
    for row in rows:
        assert row[_idx("pin_status")] in {"pinned_r2", "pinned_local", "unpinned"}
