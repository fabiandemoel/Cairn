"""Emit a compact "repo orientation" map for the agent workflows.

This is a no-LLM, stdlib-only helper run as a workflow step *before* the Claude
step in cairn-implement.yml and cairn-replenish.yml. Its stdout is injected into the
agent's prompt so the agent starts already knowing the stable, slow-to-discover
facts about the repo — the build/verify sequence, where the dbt warehouse lives
and how Evidence reaches it, and which sources / staging models / marts / site
queries / pages currently exist.

Those facts were being re-derived from scratch on almost every run (listing
directories, reading connection.yaml, re-discovering that `npm run sources`
feeds `build:strict`, probing whether `cairn.duckdb` exists, etc.), which is
pure repeated cost. Generating them once per run as plain text is ~free.

The inventory is scanned from the filesystem on each run, so it never goes
stale: a new source / model / page shows up automatically the run after it
lands. Keep the output tight — it is re-sent on every agent turn.
"""

from __future__ import annotations

import argparse
from pathlib import Path

# The canonical build/verify sequence, mirrored from ci.yml's lint/test/
# dbt-build/evidence-build jobs. The cairn-implement workflow runs all of this
# as real steps *before* the agent starts (via scripts/verify.sh), so the agent
# inherits a verified-green tree (warehouse + ESRS export bundle + built site)
# and only needs to re-run the parts it changes. The verify half of this
# sequence (everything after the deps are installed) is wrapped by
# scripts/verify.sh — the one command runner runs — so keep the two in sync.
BUILD_SEQUENCE = [
    "uv sync --locked --all-groups",
    "uv run ruff check . && uv run ruff format --check .",
    "uv run sqlfluff lint transform/models transform/tests",
    "uv run pytest -q",
    "uv run dbt build --project-dir transform            # writes ./cairn.duckdb",
    "uv run python scripts/export_esrs_e1.py --out-dir site/static/downloads/esrs_e1",
    "cd site && npm ci && npm run build:strict",
]


def _list(directory: Path, suffix: str, exclude_prefix: str = "_") -> list[str]:
    """Sorted filenames in *directory* with *suffix*, skipping dbt's `_*.yml`."""
    if not directory.is_dir():
        return []
    names = [
        p.name
        for p in directory.iterdir()
        if p.is_file() and p.name.endswith(suffix) and not p.name.startswith(exclude_prefix)
    ]
    return sorted(names)


def _bullets(items: list[str], empty: str = "_(none yet)_") -> str:
    if not items:
        return empty
    return "\n".join(f"- {i}" for i in items)


def build_orientation(root: Path) -> str:
    sources = (
        sorted(p.name for p in (root / "sources").iterdir() if p.is_dir())
        if (root / "sources").is_dir()
        else []
    )
    staging = _list(root / "transform" / "models" / "staging", ".sql")
    # marts hold both .sql and a .py model
    marts = sorted(
        _list(root / "transform" / "models" / "marts", ".sql")
        + _list(root / "transform" / "models" / "marts", ".py")
    )
    site_sources = _list(root / "site" / "sources" / "cairn", ".sql", exclude_prefix="\0")
    pages = _list(root / "site" / "pages", ".md", exclude_prefix="\0")

    seq = "\n".join(f"  {i + 1}. {cmd}" for i, cmd in enumerate(BUILD_SEQUENCE))

    return f"""## Repo orientation (generated — stable facts, do NOT re-discover these)

The build environment is ALREADY set up for you before this run: dependencies
installed (`uv sync`, `npm ci`), the dbt warehouse built (`./cairn.duckdb`), the
ESRS E1 export bundle written under `site/static/downloads/esrs_e1/`, and the
site built strictly. The pristine tree already PASSES the full verify, so you
only need to re-verify the parts you change.

### Build & verify sequence (mirrors ci.yml; run before opening the PR)
Run the whole gate in ONE command — `scripts/verify.sh` — which runs the steps
below in order and prints a compact PASS/FAIL summary (it bakes in the
export-before-`build:strict` ordering, so you never sequence those yourself).
Add `--fix` to auto-apply the deterministic formatters (`ruff format`,
`ruff check --fix`, `sqlfluff fix`) before verifying, so formatting nits are
fixed in place instead of surfacing as failures. The underlying steps:
{seq}

### Warehouse & Evidence wiring
- dbt writes the warehouse to `./cairn.duckdb` (repo root); Evidence reads it
  read-only via `site/sources/cairn/connection.yaml` as `../../../cairn.duckdb`.
- `npm run build:strict` (= `evidence build:strict`) rebuilds the Evidence
  source layer and then the site. After editing a `site/sources/cairn/*.sql`
  query, run `npm run sources` first to refresh that layer, then `build:strict`.
- The disclosure page links to the ESRS export bundle; if you change the export,
  re-run `scripts/export_esrs_e1.py` (step 6) BEFORE `build:strict` or the
  strict build 404s on the download.

### Layer inventory (what already exists — the layers a feature splits into)
**Sources (append-only manifests under `sources/<name>/manifest.yml`):**
{_bullets(sources)}

**dbt staging models (`transform/models/staging/`):**
{_bullets(staging)}

**dbt marts (`transform/models/marts/`):**
{_bullets(marts)}

**Evidence site source queries (`site/sources/cairn/`):**
{_bullets(site_sources)}

**Evidence pages (`site/pages/`):**
{_bullets(pages)}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repo root to scan (default: current working directory).",
    )
    args = parser.parse_args()
    print(build_orientation(args.root.resolve()), end="")


if __name__ == "__main__":
    main()
