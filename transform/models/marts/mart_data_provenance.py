"""Provenance-integrity mart: a read-only view over the source manifests.

This mart surfaces *data-quality insight at the provenance level* -- is the
chain from each published figure back to its official source intact? It reports
observable facts only (pin status, storage backend, SHA256, row count, release,
ingest time, period coverage), never a confidence score: the manifests are the
pin of record, and this mart simply materialises what they already assert so the
Evidence site can show it.

It reads the same ``sources/<source>/manifest.yml`` files that
``ingestion/manifest.py`` writes -- a second *reader* of the pin of record, not
a second source of truth. Nothing is recomputed and no figures are invented; an
unpinned source (``snapshots: []``) is reported as ``unpinned``, never hidden or
filled in.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import yaml

# Column order is the contract shared by the DuckDB DDL below and the pytest
# guard (tests/test_data_provenance.py). Keep the three in step.
COLUMNS: list[tuple[str, str]] = [
    ("provenance_key", "VARCHAR"),
    ("source", "VARCHAR"),
    ("dataset", "VARCHAR"),
    ("pin_status", "VARCHAR"),
    ("is_pinned", "BOOLEAN"),
    ("is_latest", "BOOLEAN"),
    ("snapshot_count", "INTEGER"),
    ("release", "VARCHAR"),
    ("ingested_at", "TIMESTAMP"),
    ("storage_backend", "VARCHAR"),
    ("storage_url", "VARCHAR"),
    ("sha256", "VARCHAR"),
    ("row_count", "BIGINT"),
    ("period_start", "VARCHAR"),
    ("period_end", "VARCHAR"),
]


def _pin_status(storage_url: str | None) -> str:
    """Classify a snapshot's provenance integrity from its storage URL.

    A purely deterministic label, not a quality score:
    * ``pinned_r2``    -- pinned to immutable object storage (the auditable pin
                          of record).
    * ``pinned_local`` -- a ``file://`` pin from an ``--offline`` run; never the
                          committed pin of record, so it is an integrity flag.
    * ``unpinned``     -- the source is configured but has no snapshot yet.
    """
    if storage_url is None:
        return "unpinned"
    scheme = storage_url.split("://", 1)[0]
    if scheme == "r2":
        return "pinned_r2"
    if scheme == "file":
        return "pinned_local"
    return "unpinned"


def collect_provenance_rows(manifests_dir: str) -> list[tuple]:
    """Read every ``<manifests_dir>/*/manifest.yml`` into provenance rows.

    One row per pinned snapshot; one placeholder row for a configured-but-
    unpinned source. Returns tuples in ``COLUMNS`` order, sorted by source then
    most-recent ingest first.
    """
    rows: list[tuple] = []
    for path in sorted(glob.glob(os.path.join(manifests_dir, "*", "manifest.yml"))):
        manifest = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        source = manifest.get("source")
        dataset = manifest.get("dataset")
        snapshots = manifest.get("snapshots") or []

        if not snapshots:
            rows.append(
                (
                    f"{source}|UNPINNED",
                    source,
                    dataset,
                    "unpinned",
                    False,
                    True,
                    0,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                )
            )
            continue

        # The latest pin (by ingest time) is the current pin of record; mirror
        # ingestion.manifest.Manifest.latest.
        latest_at = max(s.get("ingested_at") for s in snapshots)
        for snap in sorted(snapshots, key=lambda s: s.get("ingested_at"), reverse=True):
            storage_url = snap.get("storage_url")
            periods = snap.get("periods_covered") or [None]
            rows.append(
                (
                    f"{source}|{snap.get('release')}",
                    source,
                    dataset,
                    _pin_status(storage_url),
                    True,
                    snap.get("ingested_at") == latest_at,
                    len(snapshots),
                    snap.get("release"),
                    snap.get("ingested_at"),
                    storage_url.split("://", 1)[0] if storage_url else None,
                    storage_url,
                    snap.get("sha256"),
                    snap.get("row_count"),
                    str(periods[0]) if periods[0] is not None else None,
                    str(periods[-1]) if periods[-1] is not None else None,
                )
            )
    return rows


def model(dbt, session):
    """dbt entry point: materialise the manifest provenance as a table."""
    dbt.config(materialized="table")

    # Manifests live at the repo root (process CWD for dbt here, matching the
    # *_raw_dir convention); override with CAIRN_MANIFESTS_DIR for tests.
    manifests_dir = os.environ.get("CAIRN_MANIFESTS_DIR", "sources")
    rows = collect_provenance_rows(manifests_dir)

    ddl_cols = ", ".join(f"{name} {dtype}" for name, dtype in COLUMNS)
    placeholders = ", ".join("?" for _ in COLUMNS)
    session.execute(f"CREATE OR REPLACE TEMP TABLE _data_provenance ({ddl_cols})")
    if rows:
        session.executemany(f"INSERT INTO _data_provenance VALUES ({placeholders})", rows)
    return session.table("_data_provenance")
