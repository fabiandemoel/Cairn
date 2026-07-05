"""Scaffold the boilerplate for a new ingestion pipeline (no-LLM).

Every ``ingestion/*_pipeline.py`` module shares the same fixed skeleton: an
idempotency check against the source's manifest, a ``_place_offline``/``_place_r2``
pair that is byte-for-byte identical across pipelines bar the source/dataset name,
a Snapshot/``add_snapshot``/``save_manifest`` sequence, and a ``--offline`` CLI. Only
two things actually vary per source: how the release token is detected (an SDMX
metadata probe, a CBS-style OData ``Properties`` Modified date, a human-watched
filename token — see CLAUDE.md's "Recurring maintenance" section for the taxonomy)
and how the raw file is downloaded/converted to parquet.

This script writes that fixed skeleton plus the three source-specific functions as
explicit ``NotImplementedError`` stubs pointing at the closest in-tree exemplar for
each pattern, a matching unpinned ``sources/<source>/manifest.yml``, and a test file
with the one universally-reusable test (the idempotency short-circuit) pre-written.
It never invents a release-detection strategy or a schema -- filling in the stubs
is still a judgement call for the agent or a human, done by picking and adapting an
existing pattern, exactly as CLAUDE.md's per-layer exemplars already ask for.

Creating ``sources/<source>/manifest.yml`` arms the per-source register guards in
``tests/test_source_wiring.py``, so the scaffold also wires the purely mechanical
registers itself: the ``cairn-ingest.yml`` source dropdown and its ``case`` branch
(``<source>) module=ingestion.<source>_pipeline``). The third register --
``scripts/check_freshness.py`` -- is *not* wired here, because the right entry
(probed vs human-watched) depends on the release-detection pattern, which is
exactly the judgement call the stubs leave open. That one stays with the agent.

Usage:
    uv run python scripts/scaffold_ingestion.py --source rivm --dataset emissieregistratie
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from string import Template

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_PIPELINE_TEMPLATE = Template(
    '''"""Ingestion pipeline: $source $dataset -> parquet -> R2 (+ manifest).

TODO(scaffold): describe the dataset, its coverage, and what a "new release" means
for it (see the module docstrings of the existing ingestion/*_pipeline.py modules
for the level of detail expected here).

Run offline (skips R2, no credentials needed):
    uv run python -m ingestion.${source}_pipeline --offline
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from ingestion.manifest import (
    Manifest,
    Snapshot,
    add_snapshot,
    compute_sha256,
    load_manifest,
    r2_client,
    save_manifest,
)

SOURCE = "$source"
DATASET = "$dataset"
MANIFEST_PATH = Path(__file__).resolve().parent.parent / "sources" / SOURCE / "manifest.yml"

# TODO(scaffold): the upstream URL used to detect/fetch the current release.
DEFAULT_URL = "https://TODO-scaffold-set-the-real-upstream-url"

PRIMARY = "data.parquet"


def _fetch_release(url: str = DEFAULT_URL) -> str:
    """TODO(scaffold): return a YYYY-MM-DD (or YYYY-MM) release token for $source $dataset.

    Pick the pattern that matches how this source actually signals a new release --
    do not invent one:
      - metadata-endpoint probe (a small JSON/XML doc carries a last-update date):
        see ingestion/eurostat_aea_pipeline.py:_fetch_last_update /
        ingestion/eurostat_gge_pipeline.py
      - CBS-style OData "Properties" singleton Modified date:
        see ingestion/cbs_pipeline.py
      - human-watched filename/version token in a fixed archive URL (no upstream
        index to probe -- a human bumps DEFAULT_URL when a new archive appears):
        see ingestion/euets_pipeline.py, ingestion/eea_ets_pipeline.py,
        ingestion/eua_pipeline.py
    Delete this docstring note once implemented.
    """
    raise NotImplementedError(f"scaffold: implement release detection for {SOURCE}/{DATASET}")


def _download_and_convert(url: str, release_dir: Path) -> Path:
    """TODO(scaffold): download the raw file and write $$release_dir/$$PRIMARY as parquet.

    All columns should stay VARCHAR (a lossless copy of the source; typing is the
    dbt staging layer's job) and the query should end ``ORDER BY ALL`` so a re-ingest
    of unchanged source data is byte-stable. See ingestion/eurostat_aea_pipeline.py:
    _export_parquet for the reference shape, or ingestion/euets_pipeline.py /
    ingestion/eea_ets_pipeline.py if the raw file is a zip/xlsx rather than a CSV.
    """
    raise NotImplementedError(f"scaffold: implement download+convert for {SOURCE}/{DATASET}")


def _periods_covered(data_path: Path) -> list[str]:
    """TODO(scaffold): return [min_period, max_period] covered by data_path."""
    raise NotImplementedError(f"scaffold: implement periods_covered for {SOURCE}/{DATASET}")


def _row_count(path: Path) -> int:
    return duckdb.sql(f"SELECT count(*) FROM read_parquet('{path.as_posix()}')").fetchone()[0]


def _place_offline(release_dir: Path, release: str) -> str:
    """Copy the release dir into ./.localstack/ and return a file:// URL."""
    dest_root = Path.cwd() / ".localstack" / SOURCE / DATASET / release
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(release_dir, dest_root)
    return f"file://{(dest_root / PRIMARY).resolve()}"


def _place_r2(release_dir: Path, release: str) -> str:
    """Upload the release dir to R2 and return an r2:// URL for data.parquet."""
    bucket = os.environ["R2_BUCKET"]
    client = r2_client()
    prefix = f"{SOURCE}/{DATASET}/{release}"
    for file in sorted(release_dir.iterdir()):
        client.upload_file(str(file), bucket, f"{prefix}/{file.name}")
    return f"r2://{bucket}/{prefix}/{PRIMARY}"


def run(url: str = DEFAULT_URL, *, offline: bool = False) -> int:
    print(f"Checking {SOURCE} {DATASET} release...")
    release = _fetch_release(url)
    print(f"{SOURCE} {DATASET}: release {release}")

    manifest = (
        load_manifest(MANIFEST_PATH)
        if MANIFEST_PATH.exists()
        else Manifest(source=SOURCE, dataset=DATASET)
    )
    if manifest.release_exists(release):
        print(f"No new release (release {release} already pinned). Nothing to do.")
        return 0

    work = Path(tempfile.mkdtemp(prefix=f"cairn-{SOURCE}-"))
    release_dir = work / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    data_path = _download_and_convert(url, release_dir)
    periods = _periods_covered(data_path)

    sha256 = compute_sha256(data_path)
    row_count = _row_count(data_path)

    storage_url = (
        _place_offline(release_dir, release) if offline else _place_r2(release_dir, release)
    )

    snapshot = Snapshot(
        release=release,
        ingested_at=datetime.now(UTC),
        storage_url=storage_url,
        sha256=sha256,
        row_count=row_count,
        periods_covered=periods,
    )
    manifest = add_snapshot(manifest, snapshot)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_manifest(MANIFEST_PATH, manifest)

    print(f"Pinned snapshot: {row_count} rows, sha256={sha256[:12]}..., {storage_url}")
    print(f"Manifest updated: {MANIFEST_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=f"Ingest the {SOURCE} {DATASET} dataset into Cairn."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Upstream URL (default: %(default)s)")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip R2; write raw files to ./.localstack/ (no credentials needed).",
    )
    args = parser.parse_args(argv)
    return run(args.url, offline=args.offline)


if __name__ == "__main__":
    sys.exit(main())
'''
)

_MANIFEST_TEMPLATE = Template("source: $source\ndataset: $dataset\nsnapshots: []\n")

_TEST_TEMPLATE = Template(
    '''"""Tests for the $source $dataset ingestion pipeline.

TODO(scaffold): add tests for the source-specific release-token parsing and the
download/convert step (see tests/test_eurostat_aea_pipeline.py for the shape/
depth expected -- date parsing, column faithfulness, determinism, period
detection). The idempotency short-circuit test below is already reusable as-is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion import ${source}_pipeline as ep
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
'''
)


_INGEST_WORKFLOW_REL = Path(".github") / "workflows" / "cairn-ingest.yml"


def wire_ingest_workflow(root: Path, source: str) -> Path | None:
    """Add ``source`` to cairn-ingest.yml's dropdown and ``case`` mapping.

    Both edits are purely mechanical (the module name is derived from the source
    slug), so they belong to the scaffold rather than the agent -- they satisfy
    two of the three ``tests/test_source_wiring.py`` guards armed by creating
    ``sources/<source>/manifest.yml``. Idempotent: an already-wired source is
    left untouched. Returns the workflow path if the file was modified, else
    ``None`` (also when the workflow file doesn't exist, e.g. in unit-test
    sandboxes -- degrading to the old behaviour, never failing the scaffold).
    """
    path = root / _INGEST_WORKFLOW_REL
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    changed = False

    options_match = re.search(r"^(\s*options:\s*\[)([^\]]*)(\])", text, re.M)
    if options_match:
        options = [o.strip() for o in options_match.group(2).split(",") if o.strip()]
        if source not in options:
            options.append(source)
            text = (
                text[: options_match.start()]
                + options_match.group(1)
                + ", ".join(options)
                + options_match.group(3)
                + text[options_match.end() :]
            )
            changed = True

    if not re.search(rf"^\s*{re.escape(source)}\)\s+module=", text, re.M):
        fallback = re.search(r"^(\s*)\*\)\s+echo \"Unknown source", text, re.M)
        if fallback:
            branch = f"{fallback.group(1)}{source}) module=ingestion.{source}_pipeline ;;\n"
            text = text[: fallback.start()] + branch + text[fallback.start() :]
            changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
        return path
    return None


def scaffold_ingestion(root: Path, source: str, dataset: str, *, force: bool = False) -> list[Path]:
    """Write the pipeline module, manifest stub, and test file for a new source.

    Also wires the source into cairn-ingest.yml's dropdown/``case`` registers
    when that workflow file exists (see ``wire_ingest_workflow``).

    Returns the list of paths written. Raises ``ValueError`` for a malformed
    source/dataset name (must be a valid Python-identifier-safe lowercase slug,
    since it's spliced into module names and code) and ``FileExistsError`` if any
    target already exists and ``force`` is not set -- this never overwrites an
    existing pipeline.
    """
    for label, value in (("source", source), ("dataset", dataset)):
        if not _IDENTIFIER_RE.match(value):
            raise ValueError(
                f"{label}={value!r} must be a lowercase identifier matching "
                f"{_IDENTIFIER_RE.pattern} (letters, digits, underscores, starting with a letter)"
            )

    targets = {
        root / "ingestion" / f"{source}_pipeline.py": _PIPELINE_TEMPLATE,
        root / "sources" / source / "manifest.yml": _MANIFEST_TEMPLATE,
        root / "tests" / f"test_{source}_pipeline.py": _TEST_TEMPLATE,
    }

    if not force:
        existing = [p for p in targets if p.exists()]
        if existing:
            raise FileExistsError(
                f"Refusing to overwrite existing file(s): {[str(p) for p in existing]}. "
                "Pass force=True / --force to overwrite."
            )

    written: list[Path] = []
    for path, template in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(template.substitute(source=source, dataset=dataset), encoding="utf-8")
        written.append(path)

    wired = wire_ingest_workflow(root, source)
    if wired is not None:
        written.append(wired)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Source slug, e.g. 'rivm'.")
    parser.add_argument("--dataset", required=True, help="Dataset slug, e.g. 'emissieregistratie'.")
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Repo root (default: current directory)."
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    args = parser.parse_args()

    written = scaffold_ingestion(args.root.resolve(), args.source, args.dataset, force=args.force)
    print("Scaffolded:")
    for path in written:
        print(f"  {path.relative_to(args.root.resolve())}")
    print(
        "\nNext: fill in the three NotImplementedError stubs in "
        f"ingestion/{args.source}_pipeline.py (_fetch_release, _download_and_convert, "
        "_periods_covered), picking the pattern that matches this source's real release "
        "signal -- never invent one. Add the source-specific tests noted at the top of "
        f"tests/test_{args.source}_pipeline.py. Then register the source in "
        "scripts/check_freshness.py (a prober, or a human-watched row) -- "
        "tests/test_source_wiring.py fails until every register lists it."
    )


if __name__ == "__main__":
    main()
