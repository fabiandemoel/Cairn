"""Tests for the freshness mart's pure data-gathering logic.

The dbt build exercises ``mart_source_freshness`` end to end (including its
``dbt.ref()`` calls into the benchmark marts); these tests pin the
``collect_freshness_rows`` contract directly (column order, the unpinned case,
the age/lag arithmetic) without spinning up dbt, and assert it reflects the
repo's real committed manifests.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "transform" / "models" / "marts" / "mart_source_freshness.py"


def _load_model_module():
    spec = importlib.util.spec_from_file_location("mart_source_freshness", MODEL_PATH)
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


def test_rows_have_full_column_width_and_lag_arithmetic(tmp_path):
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
    computed_at = datetime(2026, 7, 7, tzinfo=timezone.utc)
    rows = mod.collect_freshness_rows(str(tmp_path), {"cbs": 2024}, computed_at=computed_at)
    assert len(rows) == 1
    assert all(len(r) == len(COLUMNS) for r in rows)
    row = rows[0]
    assert row[_idx("freshness_key")] == "cbs"
    assert row[_idx("is_pinned")] is True
    assert row[_idx("release")] == "2026-03-11"
    assert row[_idx("latest_covered_year")] == 2024
    assert row[_idx("coverage_lag_years")] == 2  # 2026 - 2024
    assert row[_idx("ingest_age_days")] == 22  # 2026-06-14T13:17:28Z -> 2026-07-07T00:00:00Z
    assert row[_idx("computed_at")] == computed_at


def test_unpinned_source_yields_null_release_and_age(tmp_path):
    _write_manifest(
        tmp_path,
        "cbs_namea",
        {"source": "cbs_namea", "dataset": "air_emissions", "snapshots": []},
    )
    computed_at = datetime(2026, 7, 7, tzinfo=timezone.utc)
    rows = mod.collect_freshness_rows(str(tmp_path), {}, computed_at=computed_at)
    assert len(rows) == 1
    row = rows[0]
    assert row[_idx("is_pinned")] is False
    # No invented figures: every derived field is NULL, never a placeholder.
    for col in ("release", "ingested_at", "ingest_age_days", "latest_covered_year", "coverage_lag_years"):
        assert row[_idx(col)] is None


def test_source_with_no_matching_mart_has_null_coverage_lag(tmp_path):
    _write_manifest(
        tmp_path,
        "eua",
        {
            "source": "eua",
            "dataset": "auction-results",
            "snapshots": [
                {
                    "release": "2012-2025",
                    "ingested_at": "2026-06-18T20:45:58.708958Z",
                    "storage_url": "r2://cairn-raw/eua/auction-results/2012-2025/data.parquet",
                    "sha256": "b" * 64,
                    "row_count": 100,
                    "periods_covered": ["2012", "2025"],
                }
            ],
        },
    )
    computed_at = datetime(2026, 7, 7, tzinfo=timezone.utc)
    # eua has no benchmark mart per invariant 5 (Scope note), so the caller
    # never supplies a "eua" entry in latest_covered_year.
    rows = mod.collect_freshness_rows(str(tmp_path), {}, computed_at=computed_at)
    row = rows[0]
    assert row[_idx("is_pinned")] is True
    assert row[_idx("release")] == "2012-2025"
    assert row[_idx("latest_covered_year")] is None
    assert row[_idx("coverage_lag_years")] is None
    assert row[_idx("ingest_age_days")] == 18  # 2026-06-18T20:45:58Z -> 2026-07-07T00:00:00Z


def test_reflects_committed_manifests():
    computed_at = datetime(2026, 7, 7, tzinfo=timezone.utc)
    rows = mod.collect_freshness_rows(
        str(REPO_ROOT / "sources"),
        {"cbs": 2024, "euets": 2024, "eurostat": 2024, "eurostat_gge": 2023},
        computed_at=computed_at,
    )
    by_source = {r[_idx("source")]: r for r in rows}
    keys = [r[_idx("freshness_key")] for r in rows]
    assert len(keys) == len(set(keys))
    assert {"cbs", "euets", "eea"} <= set(by_source)
    for row in rows:
        assert isinstance(row[_idx("is_pinned")], bool)
