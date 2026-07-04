"""Ingestion pipeline: cbs_namea air_emissions -> parquet -> R2 (+ manifest).

TODO(scaffold): describe the dataset, its coverage, and what a "new release" means
for it (see the module docstrings of the existing ingestion/*_pipeline.py modules
for the level of detail expected here).

Run offline (skips R2, no credentials needed):
    uv run python -m ingestion.cbs_namea_pipeline --offline
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

SOURCE = "cbs_namea"
DATASET = "air_emissions"
MANIFEST_PATH = Path(__file__).resolve().parent.parent / "sources" / SOURCE / "manifest.yml"

# TODO(scaffold): the upstream URL used to detect/fetch the current release.
DEFAULT_URL = "https://TODO-scaffold-set-the-real-upstream-url"

PRIMARY = "data.parquet"


def _fetch_release(url: str = DEFAULT_URL) -> str:
    """TODO(scaffold): return a YYYY-MM-DD (or YYYY-MM) release token for cbs_namea air_emissions.

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
    """TODO(scaffold): download the raw file and write $release_dir/$PRIMARY as parquet.

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
