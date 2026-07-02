"""Scaffold the boilerplate for a new dbt staging model (no-LLM).

Every ``stg_<source>__<dataset>.sql`` model shares the same fixed shape: a
``with raw as (select * from read_parquet('{{ var("<source>_<dataset>_raw_dir") }}
/data.parquet'))`` CTE, a 1:1 select with no row filtering, and a
``col_a || '|' || col_b ...`` surrogate ``observation_key``. The one thing that
genuinely varies per source is which raw columns exist and what they mean --
renaming/casting them and choosing the dataset's true grain for the key is a
real judgement call, confirmed against the live source per CLAUDE.md ("Mappings
are code... never invent figures or mappings"), not something to guess from a
template.

This script writes that fixed shape as a new model file with TODO markers (and
a ``cast(null as varchar)`` placeholder key that fails the pre-written
``not_null``/``unique`` tests loudly if left unfilled -- the same "fail loudly,
don't invent" stance as ``scaffold_ingestion.py``'s ``NotImplementedError``
stubs), and extends the two *shared* files every staging model must also touch:

* ``transform/models/staging/_staging.yml`` -- appends a new model entry
  alongside the existing ones. Idempotent: if an entry for this model already
  exists, it is left untouched, never duplicated.
* ``transform/dbt_project.yml`` -- inserts a new ``<source>_<dataset>_raw_dir``
  var into the existing ``vars:`` block, pointing at a placeholder fixture path
  the ingestion layer's CI fixture must fill in. Idempotent for the same reason.

Both are targeted text insertions, not a full YAML parse/re-dump: these files
carry hand-written comments and a deliberate key order that a round-trip
load-and-dump would not reliably preserve.

Usage:
    uv run python scripts/scaffold_staging.py --source rivm --dataset emissieregistratie
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from string import Template

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_VARS_BLOCK_RE = re.compile(r"(?m)^vars:\n((?:  [^\n]+\n)+)")

_MODEL_TEMPLATE = Template(
    """-- Staging: typed 1:1 view of the raw $source $dataset snapshot. Reads the
-- parquet file at the snapshot directory passed via the
-- `${source}_${dataset}_raw_dir` var. No rows are filtered here -- methodology-
-- specific filters belong in the mart, not here.
--
-- TODO(scaffold): note any accounting-principle / grain caveat this source
-- needs (see stg_eurostat__aea.sql's residence-vs-territorial-principle note
-- for the level of detail expected), or delete this comment if none applies.

with raw as (
    select * from read_parquet('{{ var("${source}_${dataset}_raw_dir") }}/data.parquet')
)

select
    -- TODO(scaffold): rename and cast every raw column here, confirmed against
    -- the real ingested schema -- never guessed. Keep every source column, 1:1,
    -- no filtering; typing/renaming is staging's whole job.
    *,
    -- TODO(scaffold): replace with the real surrogate key for this dataset's
    -- grain, e.g. col_a || '|' || col_b || '|' || year (see
    -- stg_eurostat__aea.sql / stg_euets__compliance.sql for the pattern). Left
    -- as NULL so the not_null/unique tests below fail loudly until it is real.
    cast(null as varchar) as observation_key
from raw
"""
)

_STAGING_YML_ENTRY_TEMPLATE = Template(
    """  - name: stg_${source}__${dataset}
    description: >
      TODO(scaffold): typed 1:1 view of the raw $source $dataset snapshot. Describe
      what it covers (grain, countries/years, any accounting-principle caveat).
    columns:
      - name: observation_key
        description: "TODO(scaffold): document the grain, e.g. col_a|col_b|year."
        tests:
          - unique
          - not_null
      # TODO(scaffold): one entry per meaningful column, mirroring the other
      # models in this file -- not_null on required columns, relationships to a
      # seed/staging model where one exists, accepted_values for a fixed code
      # list confirmed against the live source (never guessed).
"""
)


def _insert_raw_dir_var(dbt_project_path: Path, var_name: str, placeholder: str) -> bool:
    """Insert a new `<var_name>: "<placeholder>"` line into the `vars:` block.

    Returns False (no-op) if the var already exists -- idempotent, so re-running
    the scaffold never duplicates an entry in this shared file.
    """
    text = dbt_project_path.read_text(encoding="utf-8")
    match = _VARS_BLOCK_RE.search(text)
    if match is None:
        raise ValueError(f"Could not find a 'vars:' block in {dbt_project_path}")
    block = match.group(1)
    if re.search(rf"(?m)^  {re.escape(var_name)}:", block):
        return False
    new_block = block + f'  {var_name}: "{placeholder}"\n'
    new_text = text[: match.start(1)] + new_block + text[match.end(1) :]
    dbt_project_path.write_text(new_text, encoding="utf-8")
    return True


def _append_staging_model_entry(staging_yml_path: Path, model_name: str, entry: str) -> bool:
    """Append a new model entry to `_staging.yml`.

    Returns False (no-op) if an entry for this model already exists -- idempotent,
    so re-running the scaffold never duplicates an entry in this shared file.
    """
    text = staging_yml_path.read_text(encoding="utf-8")
    if re.search(rf"(?m)^  - name: {re.escape(model_name)}$", text):
        return False
    if not text.endswith("\n"):
        text += "\n"
    staging_yml_path.write_text(text + "\n" + entry, encoding="utf-8")
    return True


def scaffold_staging(root: Path, source: str, dataset: str, *, force: bool = False) -> list[Path]:
    """Write a new staging model and extend the two shared staging files.

    Raises ``ValueError`` for a malformed source/dataset slug, and
    ``FileExistsError`` if the model `.sql` file already exists and ``force`` is
    not set. The `_staging.yml` entry and the `dbt_project.yml` var are always
    appended idempotently (skipped if already present) regardless of ``force``,
    since duplicating an entry in either shared file would corrupt it.
    """
    for label, value in (("source", source), ("dataset", dataset)):
        if not _IDENTIFIER_RE.match(value):
            raise ValueError(
                f"{label}={value!r} must be a lowercase identifier matching "
                f"{_IDENTIFIER_RE.pattern} (letters, digits, underscores, starting with a letter)"
            )

    model_name = f"stg_{source}__{dataset}"
    model_path = root / "transform" / "models" / "staging" / f"{model_name}.sql"
    staging_yml_path = root / "transform" / "models" / "staging" / "_staging.yml"
    dbt_project_path = root / "transform" / "dbt_project.yml"

    if model_path.exists() and not force:
        raise FileExistsError(
            f"Refusing to overwrite existing file: {model_path}. Pass force=True / --force "
            "to overwrite."
        )

    written: list[Path] = []

    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(
        _MODEL_TEMPLATE.substitute(source=source, dataset=dataset), encoding="utf-8"
    )
    written.append(model_path)

    entry = _STAGING_YML_ENTRY_TEMPLATE.substitute(source=source, dataset=dataset)
    if _append_staging_model_entry(staging_yml_path, model_name, entry):
        written.append(staging_yml_path)

    var_name = f"{source}_{dataset}_raw_dir"
    placeholder = f"tests/fixtures/{source}/{dataset}/TODO-scaffold-set-real-release-dir"
    if _insert_raw_dir_var(dbt_project_path, var_name, placeholder):
        written.append(dbt_project_path)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Source slug, e.g. 'rivm'.")
    parser.add_argument("--dataset", required=True, help="Dataset slug, e.g. 'emissieregistratie'.")
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Repo root (default: current directory)."
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite the model file if it exists."
    )
    args = parser.parse_args()

    root = args.root.resolve()
    written = scaffold_staging(root, args.source, args.dataset, force=args.force)
    print("Scaffolded / extended:")
    for path in written:
        print(f"  {path.relative_to(root)}")
    model_name = f"stg_{args.source}__{args.dataset}"
    print(
        f"\nNext: fill in the TODO(scaffold) markers in transform/models/staging/{model_name}.sql "
        "(real column renames/casts, real observation_key) and in its _staging.yml entry "
        "(description, column tests), confirmed against the real ingested schema -- never "
        f"guessed. Point the new {args.source}_{args.dataset}_raw_dir var at a real CI fixture "
        "once the ingestion layer has landed one."
    )


if __name__ == "__main__":
    main()
