"""Business-glossary mart: a read-only view over the curated glossary.

This mart materialises ``transform/glossary.yml`` -- a reviewed, PR-gated set of
definitions for Cairn's cross-cutting business concepts (territorial vs.
residence principle, Scope 1, verified emissions, free allocation, LEI, ESRS
E1-6, ...). One row per term. Nothing is computed and no term is invented; the
mart is a second *reader* of the curated file, the same read-only pattern as
``mart_data_provenance.py`` and ``mart_data_dictionary.py``.

The glossary lives outside the dbt model/seed paths on purpose, so dbt does not
parse it as a schema file; this mart reads it explicitly.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

# Column order is the contract shared by the DuckDB DDL below and the pytest
# guard (tests/test_business_glossary.py). Keep the three in step.
COLUMNS: list[tuple[str, str]] = [
    ("glossary_key", "VARCHAR"),
    ("term", "VARCHAR"),
    ("category", "VARCHAR"),
    ("definition", "VARCHAR"),
    ("aliases", "VARCHAR"),
    ("related_models", "VARCHAR"),
    ("reference_url", "VARCHAR"),
]

DEFAULT_GLOSSARY_PATH = "transform/glossary.yml"


def _slug(term: str) -> str:
    """A stable lowercase key for a term (its natural primary key)."""
    return "_".join("".join(c if c.isalnum() else " " for c in term.lower()).split())


def _clean(text: str | None) -> str | None:
    """Collapse a folded-scalar definition to a single trimmed string."""
    if text is None:
        return None
    cleaned = " ".join(str(text).split())
    return cleaned or None


def _join(values) -> str | None:
    """Comma-join a list, or NULL when absent -- never an empty placeholder."""
    if not values:
        return None
    return ", ".join(str(v) for v in values) or None


def collect_glossary_rows(glossary_path: str) -> list[tuple]:
    """Read ``glossary_path`` into glossary rows, one per term.

    Returns tuples in ``COLUMNS`` order, sorted by category then term.
    """
    glossary = yaml.safe_load(Path(glossary_path).read_text(encoding="utf-8")) or {}
    rows: list[tuple] = []
    for entry in glossary.get("terms") or []:
        term = entry.get("term")
        rows.append(
            (
                _slug(term),
                term,
                entry.get("category"),
                _clean(entry.get("definition")),
                _join(entry.get("aliases")),
                _join(entry.get("related_models")),
                entry.get("reference"),
            )
        )
    rows.sort(key=lambda r: (r[2] or "", r[1] or ""))
    return rows


def model(dbt, session):
    """dbt entry point: materialise the curated glossary as a table."""
    dbt.config(materialized="table")

    # The glossary lives at the repo root (process CWD for dbt here, matching the
    # *_raw_dir convention); override with CAIRN_GLOSSARY_PATH for tests.
    glossary_path = os.environ.get("CAIRN_GLOSSARY_PATH", DEFAULT_GLOSSARY_PATH)
    rows = collect_glossary_rows(glossary_path)

    ddl_cols = ", ".join(f"{name} {dtype}" for name, dtype in COLUMNS)
    placeholders = ", ".join("?" for _ in COLUMNS)
    session.execute(f"CREATE OR REPLACE TEMP TABLE _business_glossary ({ddl_cols})")
    if rows:
        session.executemany(f"INSERT INTO _business_glossary VALUES ({placeholders})", rows)
    return session.table("_business_glossary")
