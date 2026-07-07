"""Freshness/staleness mart: a read-only view over the manifests and marts.

This mart surfaces *how current each source is*, per source: its pinned release
and ingest date (read from ``sources/<source>/manifest.yml``, the same pin of
record ``mart_data_provenance.py`` reads), the latest calendar year the
source's benchmark mart actually covers, and the observed lag between "now"
(the mart's own build time) and those two facts. It is descriptive only --
release-to-now age in days, and covered-year-to-now lag in years -- never a
freshness SLA, alarm, or quality score. That role belongs to the weekly
``scripts/verify_reproducibility.py`` job and ``scripts/check_freshness.py``
(the no-LLM dispatcher's live-vs-pinned diff); this mart never probes a live
upstream endpoint, it only reads what Cairn already pinned and already built.

Unlike the other read-only Python marts (``mart_data_provenance.py``,
``mart_business_glossary.py``, ``mart_data_dictionary.py``), which read only
files, this one also ``dbt.ref()``s each source's benchmark mart to read its
``max(year)`` -- the "latest covered year" fact does not exist anywhere in the
manifests. The ``ref()`` calls are written as literal calls directly in
``model()`` (not looked up dynamically from a dict) so dbt's static
python-model parser can see the DAG edges and build this mart after its
upstream marts.
"""

from __future__ import annotations

import glob
import os
from datetime import UTC, datetime
from pathlib import Path

import yaml

# Column order is the contract shared by the DuckDB DDL below and the pytest
# guard (tests/test_source_freshness.py). Keep the three in step.
COLUMNS: list[tuple[str, str]] = [
    ("freshness_key", "VARCHAR"),
    ("source", "VARCHAR"),
    ("dataset", "VARCHAR"),
    ("is_pinned", "BOOLEAN"),
    ("release", "VARCHAR"),
    ("ingested_at", "VARCHAR"),
    ("ingest_age_days", "INTEGER"),
    ("latest_covered_year", "INTEGER"),
    ("coverage_lag_years", "INTEGER"),
    ("computed_at", "TIMESTAMP"),
]


def collect_freshness_rows(
    manifests_dir: str,
    latest_covered_year: dict[str, int | None],
    *,
    computed_at: datetime,
) -> list[tuple]:
    """Read every ``<manifests_dir>/*/manifest.yml`` into freshness rows.

    One row per configured source (pinned or not). ``latest_covered_year`` maps
    a source name to the ``max(year)`` already read from its benchmark mart (or
    absent/``None`` when no mart covers that source yet). Returns tuples in
    ``COLUMNS`` order, sorted by source.
    """
    rows: list[tuple] = []
    for path in sorted(glob.glob(os.path.join(manifests_dir, "*", "manifest.yml"))):
        manifest = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        source = manifest.get("source")
        dataset = manifest.get("dataset")
        snapshots = manifest.get("snapshots") or []

        release = None
        ingested_at_raw = None
        ingested_at_dt = None
        if snapshots:
            # The latest pin (by ingest time) is the current pin of record;
            # mirrors ingestion.manifest.Manifest.latest.
            latest = max(snapshots, key=lambda s: s.get("ingested_at"))
            release = latest.get("release")
            ingested_at_raw = latest.get("ingested_at")
            if ingested_at_raw:
                ingested_at_dt = datetime.fromisoformat(ingested_at_raw)

        ingest_age_days = (
            (computed_at - ingested_at_dt).days if ingested_at_dt is not None else None
        )
        covered_year = latest_covered_year.get(source)
        coverage_lag_years = computed_at.year - covered_year if covered_year is not None else None

        rows.append(
            (
                source,
                source,
                dataset,
                bool(snapshots),
                release,
                ingested_at_raw,
                ingest_age_days,
                covered_year,
                coverage_lag_years,
                computed_at,
            )
        )
    return rows


def _max_year(relation) -> int | None:
    """The largest ``year`` value in a ref'd relation, or None if it has none."""
    row = relation.aggregate("max(year) as max_year").fetchone()
    return int(row[0]) if row and row[0] is not None else None


def model(dbt, session):
    """dbt entry point: materialise per-source freshness as a table."""
    dbt.config(materialized="table")

    # Literal dbt.ref() calls -- dbt's python-model parser statically scans the
    # file for these to build the DAG, so the target names must be string
    # literals here, never looked up from a dict at runtime.
    cbs_year = _max_year(dbt.ref("benchmark_sector_emissions"))
    euets_installation_year = _max_year(dbt.ref("benchmark_installation_emissions"))
    euets_transport_year = _max_year(dbt.ref("benchmark_transport_emissions"))
    eurostat_year = _max_year(dbt.ref("benchmark_country_sector_emissions"))
    eurostat_gge_year = _max_year(dbt.ref("mart_gge_national_totals"))

    # euets has two sibling marts (stationary installations, aviation/maritime
    # transport); the source's latest covered year is the more recent of the two.
    euets_years = [y for y in (euets_installation_year, euets_transport_year) if y is not None]

    # Sources with no benchmark mart yet (eea, eua, cbs_namea, emissieregistratie)
    # are simply absent here, so collect_freshness_rows reports them as NULL --
    # never an invented year.
    latest_covered_year = {
        "cbs": cbs_year,
        "euets": max(euets_years) if euets_years else None,
        "eurostat": eurostat_year,
        "eurostat_gge": eurostat_gge_year,
    }

    # Manifests live at the repo root (process CWD for dbt here, matching the
    # *_raw_dir convention); override with CAIRN_MANIFESTS_DIR for tests.
    manifests_dir = os.environ.get("CAIRN_MANIFESTS_DIR", "sources")
    rows = collect_freshness_rows(manifests_dir, latest_covered_year, computed_at=datetime.now(UTC))

    ddl_cols = ", ".join(f"{name} {dtype}" for name, dtype in COLUMNS)
    placeholders = ", ".join("?" for _ in COLUMNS)
    session.execute(f"CREATE OR REPLACE TEMP TABLE _source_freshness ({ddl_cols})")
    if rows:
        session.executemany(f"INSERT INTO _source_freshness VALUES ({placeholders})", rows)
    return session.table("_source_freshness")
