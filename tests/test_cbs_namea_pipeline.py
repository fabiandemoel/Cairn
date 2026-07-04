"""Tests for the cbs_namea air_emissions ingestion pipeline.

TODO(scaffold): add tests for the source-specific release-token parsing and the
download/convert step (see tests/test_eurostat_aea_pipeline.py for the shape/
depth expected -- date parsing, column faithfulness, determinism, period
detection). The idempotency short-circuit test below is already reusable as-is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion import cbs_namea_pipeline as ep
from ingestion.manifest import Manifest, Snapshot, save_manifest


def test_run_skips_when_release_already_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = "2024-01-01"
    manifest_path = tmp_path / "manifest.yml"
    save_manifest(
        manifest_path,
        Manifest(
            source=ep.SOURCE,
            dataset=ep.DATASET,
            snapshots=[
                Snapshot(
                    release=release,
                    ingested_at="2024-01-02T00:00:00Z",
                    storage_url="file:///tmp/data.parquet",
                    sha256="a" * 64,
                    row_count=1,
                    periods_covered=["2020", "2023"],
                )
            ],
        ),
    )
    monkeypatch.setattr(ep, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(ep, "_fetch_release", lambda url=ep.DEFAULT_URL: release)

    def _no_download(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "_download_and_convert must not be called for an already-pinned release"
        )

    monkeypatch.setattr(ep, "_download_and_convert", _no_download)

    assert ep.run(offline=True) == 0
