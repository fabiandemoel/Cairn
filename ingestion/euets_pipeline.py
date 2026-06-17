"""Ingestion pipeline: euets.info (EUTL) zip -> parquet -> R2 (+ manifest).

This is Cairn's second source and the *installation-level* pin of record for
EU ETS. Unlike the CBS source there is no clean API: euets.info (Jan Abrell,
EUI -- a reprocessing of the EU Transaction Log with published, reproducible
routines) ships the data as a single versioned zip of normalised CSV tables at
a stable S3 URL. So ingestion is download + extract + convert, not a dlt feed.

End to end:

1. Derive the release from the source zip filename (the publication token, e.g.
   ``eutl_2024_202410.zip`` -> ``2024-10``).
2. Idempotency: if the latest manifest snapshot already pins that release, exit
   cleanly -- no download of the body, no upload, no manifest change.
3. Download the zip, extract only the tables Cairn uses (see ``EUETS_TABLES``),
   and convert each to a clean, deterministically-ordered parquet. The 164 MB
   ``transaction.csv`` and other allowance-movement tables are intentionally
   not ingested -- they are irrelevant to emissions benchmarking.
4. Place the raw files immutably: R2 under ``euets/eutl/{release}/`` (online) or
   ``./.localstack/euets/eutl/{release}/`` (``--offline``, no credentials).
5. Hash ``compliance.parquet`` (the verified-emissions observations -- the
   primary artifact) and append a manifest snapshot. As with CBS, the manifest
   write is the final, unconditional step: ingestion without a manifest update
   is impossible by construction.

Raw stays faithful to the source: every row of every ingested table is kept
(all countries, all years). The NL filter and the stationary/aircraft/maritime
split are methodology and live in the dbt staging layer, not here.

Run offline (downloads from S3 but skips R2, no credentials):
    uv run python -m ingestion.euets_pipeline --offline
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
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

SOURCE = "euets"
DATASET = "eutl"
MANIFEST_PATH = Path(__file__).resolve().parent.parent / "sources" / "euets" / "manifest.yml"

# The current euets.info release. The URL changes per release (the filename
# carries the version), so pinning which URL was ingested is part of the audit
# trail. Override with --url when a newer release is published.
DEFAULT_URL = "https://euets-info-public.s3.eu-central-1.amazonaws.com/eutl_2024_202410.zip"

# Zip member -> output parquet filename. ``compliance.parquet`` (verified
# emissions per installation-year) is the hashed primary artifact; the others
# decode/identify installations and codes and travel alongside it, read by the
# dbt staging models. Everything else in the zip (transactions, accounts,
# surrenders, projects) is deliberately not ingested.
EUETS_TABLES: dict[str, str] = {
    "compliance.csv": "compliance.parquet",
    "installation.csv": "installation.parquet",
    "nace_code.csv": "dim_nace.parquet",
    "activity_type.csv": "dim_activity_type.parquet",
    "country_code.csv": "dim_country.parquet",
}
PRIMARY = "compliance.parquet"


def _release_from_url(url: str) -> str:
    """Derive a release id from the zip filename.

    ``eutl_2024_202410.zip`` -> ``2024-10`` (publication year-month); a
    publication-less name like ``eutl_2023.zip`` -> ``2023`` (the data vintage).
    """
    name = url.rsplit("/", 1)[-1]
    pub = re.search(r"_(\d{4})(\d{2})\.zip$", name)
    if pub:
        return f"{pub.group(1)}-{pub.group(2)}"
    year = re.search(r"_(\d{4})\.zip$", name)
    if year:
        return year.group(1)
    raise ValueError(f"Cannot derive a release from euets.info URL {url!r}")


def _download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh)


def _export_parquets(zip_path: Path, out_dir: Path) -> None:
    """Extract the wanted CSVs and convert each to a clean, ordered parquet.

    Columns are read as VARCHAR so the raw parquet is a lossless copy of the CSV
    text -- typing and decoding are the dbt staging layer's job. ``ORDER BY ALL``
    makes a re-ingest of unchanged source data byte-stable.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = set(zf.namelist())
            missing = [m for m in EUETS_TABLES if m not in members]
            if missing:
                raise ValueError(f"euets.info zip is missing expected tables: {missing}")
            for member, filename in EUETS_TABLES.items():
                extracted = Path(zf.extract(member, out_dir))
                dest = out_dir / filename
                con.sql(
                    f"COPY (SELECT * FROM read_csv('{extracted.as_posix()}', "
                    f"all_varchar = true, header = true) ORDER BY ALL) "
                    f"TO '{dest.as_posix()}' (FORMAT PARQUET)"
                )
                extracted.unlink()
    finally:
        con.close()


def _periods_covered(out_dir: Path) -> list[str]:
    """[min_year, max_year] from the compliance table."""
    path = (out_dir / PRIMARY).as_posix()
    row = duckdb.sql(
        f"SELECT min(TRY_CAST(year AS INTEGER)), max(TRY_CAST(year AS INTEGER)) "
        f"FROM read_parquet('{path}')"
    ).fetchone()
    return [str(row[0]), str(row[1])]


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
    """Upload the release dir to R2 and return an r2:// URL for the primary file."""
    bucket = os.environ["R2_BUCKET"]
    client = r2_client()
    prefix = f"{SOURCE}/{DATASET}/{release}"
    for file in sorted(release_dir.iterdir()):
        client.upload_file(str(file), bucket, f"{prefix}/{file.name}")
    return f"r2://{bucket}/{prefix}/{PRIMARY}"


def run(url: str = DEFAULT_URL, *, offline: bool = False) -> int:
    release = _release_from_url(url)
    print(f"euets.info EUTL release {release} ({url.rsplit('/', 1)[-1]})")

    manifest = (
        load_manifest(MANIFEST_PATH)
        if MANIFEST_PATH.exists()
        else Manifest(source=SOURCE, dataset=DATASET)
    )
    if manifest.release_exists(release):
        print(f"No new release (release {release} already pinned). Nothing to do.")
        return 0

    work = Path(tempfile.mkdtemp(prefix="cairn-euets-"))
    zip_path = work / "eutl.zip"
    _download(url, zip_path)

    release_dir = work / "release"
    _export_parquets(zip_path, release_dir)
    periods = _periods_covered(release_dir)

    primary = release_dir / PRIMARY
    sha256 = compute_sha256(primary)
    row_count = _row_count(primary)

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

    print(f"Pinned snapshot: {row_count} compliance rows, sha256={sha256[:12]}..., {storage_url}")
    print(f"Manifest updated: {MANIFEST_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest the euets.info EUTL dataset into Cairn.")
    parser.add_argument("--url", default=DEFAULT_URL, help="euets.info zip URL (default: latest)")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip R2; write raw files to ./.localstack/ (no credentials needed).",
    )
    args = parser.parse_args(argv)
    return run(args.url, offline=args.offline)


if __name__ == "__main__":
    sys.exit(main())
