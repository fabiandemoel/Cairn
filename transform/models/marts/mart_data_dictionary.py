"""Data-dictionary mart: a read-only view over the dbt schema ``.yml`` files.

This mart consolidates the documentation Cairn already keeps in its dbt schema
files (``models/staging/_staging.yml``, ``models/marts/_marts.yml``,
``seeds/_seeds.yml``) into one queryable table -- one row per (model, column):
what every model and column means, and which data tests guard it. It is a second
*reader* of the schema files, not a second source of truth: nothing is
recomputed and no documentation is invented. A column with no description simply
carries NULL, never a placeholder.

It mirrors ``mart_data_provenance.py`` (which reads the source manifests) -- the
same read-only, materialise-what-the-files-already-say pattern, here pointed at
the dbt schema instead of the ingest manifests.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

# Column order is the contract shared by the DuckDB DDL below and the pytest
# guard (tests/test_data_dictionary.py). Keep the three in step.
COLUMNS: list[tuple[str, str]] = [
    ("dictionary_key", "VARCHAR"),
    ("layer", "VARCHAR"),
    ("model_name", "VARCHAR"),
    ("model_description", "VARCHAR"),
    ("column_name", "VARCHAR"),
    ("column_description", "VARCHAR"),
    ("data_tests", "VARCHAR"),
    ("is_tested", "BOOLEAN"),
    ("accepted_values", "VARCHAR"),
]

# Each schema file maps to the dbt layer its resources live in. The keys are the
# schema-yml paths (relative to the repo root / process CWD, matching the
# *_raw_dir convention); the values are the layer label carried on every row.
DEFAULT_SCHEMA_FILES: list[tuple[str, str]] = [
    ("transform/models/staging/_staging.yml", "staging"),
    ("transform/models/marts/_marts.yml", "mart"),
    ("transform/seeds/_seeds.yml", "seed"),
]


def _clean(text: str | None) -> str | None:
    """Collapse a folded-scalar description to a single trimmed string."""
    if text is None:
        return None
    cleaned = " ".join(str(text).split())
    return cleaned or None


def _test_name(test) -> str:
    """The name of a dbt test item: the string itself, or the single dict key."""
    if isinstance(test, str):
        return test
    if isinstance(test, dict) and test:
        return next(iter(test))
    return str(test)


def _accepted_values(tests: list) -> str | None:
    """The accepted_values list (comma-joined) if the column has such a test."""
    for test in tests:
        if isinstance(test, dict) and "accepted_values" in test:
            values = (test["accepted_values"] or {}).get("values") or []
            joined = ", ".join(str(v) for v in values)
            return joined or None
    return None


def collect_dictionary_rows(schema_files: list[tuple[str, str]]) -> list[tuple]:
    """Read every (schema_file, layer) into data-dictionary rows.

    One row per documented (model, column). Returns tuples in ``COLUMNS`` order,
    sorted by layer, then model, then the column order as written in the file.
    """
    layer_rank = {"staging": 0, "mart": 1, "seed": 2}
    rows: list[tuple] = []
    for path, layer in schema_files:
        schema = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        # dbt schema files key resources under 'models' or 'seeds'; treat both
        # the same -- a documented resource with its columns.
        resources = (schema.get("models") or []) + (schema.get("seeds") or [])
        for resource in resources:
            model_name = resource.get("name")
            model_description = _clean(resource.get("description"))
            for column in resource.get("columns") or []:
                column_name = column.get("name")
                tests = column.get("tests") or []
                test_names = [_test_name(t) for t in tests]
                rows.append(
                    (
                        f"{model_name}|{column_name}",
                        layer,
                        model_name,
                        model_description,
                        column_name,
                        _clean(column.get("description")),
                        ", ".join(test_names) or None,
                        bool(test_names),
                        _accepted_values(tests),
                    )
                )
    rows.sort(key=lambda r: (layer_rank.get(r[1], 9), r[2]))
    return rows


def model(dbt, session):
    """dbt entry point: materialise the schema documentation as a table."""
    dbt.config(materialized="table")

    # Schema files live under the repo root (process CWD for dbt here, matching
    # the *_raw_dir convention); override with CAIRN_DBT_SCHEMA_PATHS for tests
    # (a path-separated list of '<yml>:<layer>' entries).
    override = os.environ.get("CAIRN_DBT_SCHEMA_PATHS")
    if override:
        schema_files = [
            (spec.rsplit(":", 1)[0], spec.rsplit(":", 1)[1])
            for spec in override.split(os.pathsep)
            if spec
        ]
    else:
        schema_files = DEFAULT_SCHEMA_FILES
    rows = collect_dictionary_rows(schema_files)

    ddl_cols = ", ".join(f"{name} {dtype}" for name, dtype in COLUMNS)
    placeholders = ", ".join("?" for _ in COLUMNS)
    session.execute(f"CREATE OR REPLACE TEMP TABLE _data_dictionary ({ddl_cols})")
    if rows:
        session.executemany(f"INSERT INTO _data_dictionary VALUES ({placeholders})", rows)
    return session.table("_data_dictionary")
