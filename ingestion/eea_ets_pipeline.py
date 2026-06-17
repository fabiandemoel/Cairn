"""Ingestion pipeline: EEA EU ETS bulk (Union Registry) -> parquet -> R2.

Cairn's official EU ETS *denominator* and integrity cross-check, alongside the
installation-level euets.info pin (see ``euets_pipeline.py``). The EEA "EU ETS
data from the Union Registry" download is the authoritative, current
(data to 2025) aggregate: emissions, allowances and surrendered units by
country x main activity x year. It is NOT installation-level -- that is why it
is the denominator, not the teller.

The download is a zip from the EEA datashare whose payload is an Excel workbook
(``ETS_Database_<month>_<year>.xlsx``) plus manuals/PDFs we do not ingest. The
release is taken from the versioned zip filename (Content-Disposition), e.g.
``...p_2005-2025_v01_r00.zip`` -> ``2005-2025_v01_r00``, which changes whenever
EEA republishes -- so it is the idempotency anchor.

End to end mirrors the other pipelines: peek the release from headers (no body
download), skip if already pinned, else download, convert the workbook's data
sheet to a clean parquet, place it immutably under ``eea/eu-ets/{release}/``
(R2 or ./.localstack/ with --offline), and append the manifest snapshot as the
final unconditional step.

Columns are read as VARCHAR so the raw parquet is a lossless copy of the sheet;
the ``value`` column legitimately mixes numbers and period labels, and typing
is the dbt staging layer's job.

Run offline (downloads from EEA but skips R2, no credentials):
    uv run python -m ingestion.eea_ets_pipeline --offline
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

SOURCE = "eea"
DATASET = "eu-ets"
MANIFEST_PATH = Path(__file__).resolve().parent.parent / "sources" / "eea" / "manifest.yml"

# EEA datashare link for the current "EU ETS data from the Union Registry"
# release. The Content-Disposition filename carries the version; override with
# --url when EEA publishes a new datashare link.
DEFAULT_URL = "https://sdi.eea.europa.eu/datashare/s/b9SGaYerAH3HyX9/download"

DATA_PARQUET = "data.parquet"
DATA_SHEET = "Sheet1"


def _release_from_filename(filename: str) -> str:
    """``eea_..._p_2005-2025_v01_r00.zip`` -> ``2005-2025_v01_r00``."""
    stem = filename[:-4] if filename.lower().endswith(".zip") else filename
    match = re.search(r"_p_(.+)$", stem)
    if not match:
        raise ValueError(f"Cannot derive a release from EEA filename {filename!r}")
    return match.group(1)


def _peek_release(url: str) -> str:
    """Read the Content-Disposition filename without downloading the body."""
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        filename = resp.headers.get_filename()
    if not filename:
        raise ValueError(f"EEA response for {url!r} has no Content-Disposition filename")
    return _release_from_filename(filename)


def _download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh)


def _find_data_workbook(zf: zipfile.ZipFile) -> str:
    """Locate the ETS_Database_*.xlsx member; the rest of the zip is ignored."""
    candidates = [
        m
        for m in zf.namelist()
        if Path(m).name.startswith("ETS_Database") and m.lower().endswith(".xlsx")
    ]
    if len(candidates) != 1:
        raise ValueError(f"Expected exactly one ETS_Database*.xlsx in the zip, found {candidates}")
    return candidates[0]


def _export_parquet(zip_path: Path, out_dir: Path) -> None:
    """Convert the workbook's data sheet to a clean, ordered parquet."""
    out_dir.mkdir(parents=True, exist_ok=True)
    extract_dir = out_dir / "_extract"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            member = _find_data_workbook(zf)
            xlsx = Path(zf.extract(member, extract_dir))
        con = duckdb.connect()
        try:
            con.sql("INSTALL excel; LOAD excel;")
            dest = out_dir / DATA_PARQUET
            con.sql(
                f"COPY (SELECT * FROM read_xlsx('{xlsx.as_posix()}', sheet = '{DATA_SHEET}', "
                f"all_varchar = true) ORDER BY ALL) TO '{dest.as_posix()}' (FORMAT PARQUET)"
            )
        finally:
            con.close()
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


def _periods_covered(out_dir: Path) -> list[str]:
    path = (out_dir / DATA_PARQUET).as_posix()
    row = duckdb.sql(
        f"SELECT min(TRY_CAST(year AS INTEGER)), max(TRY_CAST(year AS INTEGER)) "
        f"FROM read_parquet('{path}')"
    ).fetchone()
    return [str(row[0]), str(row[1])]


def _row_count(path: Path) -> int:
    return duckdb.sql(f"SELECT count(*) FROM read_parquet('{path.as_posix()}')").fetchone()[0]


def _place_offline(release_dir: Path, release: str) -> str:
    dest_root = Path.cwd() / ".localstack" / SOURCE / DATASET / release
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(release_dir, dest_root)
    return f"file://{(dest_root / DATA_PARQUET).resolve()}"


def _place_r2(release_dir: Path, release: str) -> str:
    bucket = os.environ["R2_BUCKET"]
    client = r2_client()
    prefix = f"{SOURCE}/{DATASET}/{release}"
    for file in sorted(release_dir.iterdir()):
        client.upload_file(str(file), bucket, f"{prefix}/{file.name}")
    return f"r2://{bucket}/{prefix}/{DATA_PARQUET}"


def run(url: str = DEFAULT_URL, *, offline: bool = False) -> int:
    release = _peek_release(url)
    print(f"EEA EU ETS release {release}")

    manifest = (
        load_manifest(MANIFEST_PATH)
        if MANIFEST_PATH.exists()
        else Manifest(source=SOURCE, dataset=DATASET)
    )
    if manifest.release_exists(release):
        print(f"No new release (release {release} already pinned). Nothing to do.")
        return 0

    work = Path(tempfile.mkdtemp(prefix="cairn-eea-"))
    zip_path = work / "eea.zip"
    _download(url, zip_path)

    release_dir = work / "release"
    _export_parquet(zip_path, release_dir)
    periods = _periods_covered(release_dir)

    primary = release_dir / DATA_PARQUET
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

    print(f"Pinned snapshot: {row_count} rows, sha256={sha256[:12]}..., {storage_url}")
    print(f"Manifest updated: {MANIFEST_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest the EEA EU ETS bulk dataset into Cairn.")
    parser.add_argument(
        "--url", default=DEFAULT_URL, help="EEA datashare zip URL (default: latest)."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip R2; write raw files to ./.localstack/ (no credentials needed).",
    )
    args = parser.parse_args(argv)
    return run(args.url, offline=args.offline)


if __name__ == "__main__":
    sys.exit(main())
