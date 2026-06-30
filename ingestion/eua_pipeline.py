"""Ingestion pipeline: EEX EU ETS Phase 4 auction results → parquet → R2 (+ manifest).

EEX (European Energy Exchange) is the appointed auctioneer for EU ETS Phase 4
(2021–2030) allowances under Commission Regulation 1031/2010/EU. After each auction
EEX publishes official clearing-price reports on their downloads page. This pipeline
ingests the current historical archive — a zip of per-year XLSX workbooks — as an
immutable snapshot with SHA-256 fingerprint and an append-only manifest.

End to end:

1. Parse the release token from the archive URL filename (e.g. ``"2012-2025"`` from
   ``emission-spot-primary-market-auction-report-2012-2025-data.zip``). No network
   request is needed for the idempotency check.
2. Idempotency: if the manifest already pins that release token, exit cleanly —
   no download, no upload, no manifest change.
3. Download the zip from ``DEFAULT_URL`` (or ``--url`` for a newer release), extract
   the XLSX workbooks (2020–latest; XLS files from 2012–2019 are the older Excel
   97-2003 format, not supported by DuckDB's excel extension, and cover Phase 3
   only), and combine them into a single, deterministically-ordered parquet (all
   columns VARCHAR).
4. Place the raw file immutably: R2 under ``eua/auction-results/{release}/`` (online)
   or ``./.localstack/eua/auction-results/{release}/`` (``--offline``, no credentials).
5. Hash ``data.parquet`` and append a manifest snapshot. Ingestion without a manifest
   update is impossible by construction.

Raw faithfulness: every XLSX row is preserved; no price computation or filtering
is applied here. The dbt staging layer is responsible for filtering to Phase 4
(year >= 2021) and typing the columns appropriately.

Note on scope: this pipeline ingests the *auction clearing price* — the price at
which EUAs were auctioned at EEX primary market — not secondary-market spot or
futures prices (ICE, CME). A future site overlay may display the auction price as
context alongside verified emissions. It must never appear in a dbt mart figure
or the ESRS E1 export (invariant 5).

Run offline (downloads from EEX but skips R2, no credentials needed):
    uv run python -m ingestion.eua_pipeline --offline
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

SOURCE = "eua"
DATASET = "auction-results"
MANIFEST_PATH = Path(__file__).resolve().parent.parent / "sources" / "eua" / "manifest.yml"

# Public EEX download — the Emission Spot Primary Market Auction Report archive.
# The filename carries the year-range release token; pass ``--url`` when EEX
# publishes a new archive (e.g. ``...-2012-2026-data.zip`` for the 2026 release).
DEFAULT_URL = (
    "https://www.eex.com/fileadmin/EEX/Downloads/"
    "EUA_Emission_Spot_Primary_Market_Auction_Report/Archive_Reports/"
    "emission-spot-primary-market-auction-report-2012-2025-data.zip"
)

PRIMARY = "data.parquet"
DATA_SHEET = "Primary Market Auction"

# Row 6 (1-indexed) is the header row in each XLSX sheet; rows 1–5 contain
# title/subtitle metadata. Column A is an unused index column; the 62 data
# columns span B onward (B–BK in Phase 4 workbooks).  The generous end column
# (CA) avoids the need to know the exact last column; ``stop_at_empty`` prevents
# DuckDB from padding with NULLs beyond the last data row.
_DATA_RANGE = "B6:CA99999"


def _release_from_url(url: str) -> str:
    """Parse the year-range release token from the EEX archive URL.

    ``emission-spot-primary-market-auction-report-2012-2025-data.zip``
    → ``"2012-2025"``
    """
    filename = url.rstrip("/").split("/")[-1]
    stem = filename[:-4] if filename.lower().endswith(".zip") else filename
    m = re.search(r"(\d{4}-\d{4})", stem)
    if not m:
        raise ValueError(
            f"Cannot derive a release token from EEX filename {filename!r}. "
            "Expected a four-digit year range like '2012-2025' in the filename."
        )
    return m.group(1)


def _download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh)


def _find_xlsx_members(zf: zipfile.ZipFile) -> list[str]:
    """Return XLSX members from the zip, sorted by name.

    XLS files (2012–2019, Phase 3) are excluded — DuckDB's excel extension
    supports XLSX only.
    """
    return sorted(m for m in zf.namelist() if m.lower().endswith(".xlsx"))


def _export_parquet(zip_path: Path, out_dir: Path) -> Path:
    """Extract XLSX workbooks and combine into a single ordered parquet.

    All columns are read as VARCHAR (lossless raw copy; typing is the dbt
    staging layer's responsibility).  ``ORDER BY ALL`` makes re-ingestion of
    unchanged source data byte-stable.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / PRIMARY
    extract_dir = out_dir / "_extract"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = _find_xlsx_members(zf)
            if not members:
                raise ValueError(f"No XLSX files found in {zip_path}")
            extracted = [Path(zf.extract(m, extract_dir)) for m in members]

        con = duckdb.connect()
        try:
            con.sql("INSTALL excel; LOAD excel;")
            parts = [
                f"SELECT * FROM read_xlsx('{p.as_posix()}', "
                f"sheet = '{DATA_SHEET}', "
                f"range = '{_DATA_RANGE}', "
                f"header = true, "
                f"all_varchar = true, "
                f"stop_at_empty = true)"
                for p in extracted
            ]
            union_sql = " UNION ALL ".join(parts)
            con.sql(f"COPY ({union_sql} ORDER BY ALL) TO '{dest.as_posix()}' (FORMAT PARQUET)")
        finally:
            con.close()
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)

    return dest


def _periods_covered(data_path: Path) -> list[str]:
    """[min_year, max_year] derived from the Excel serial-date ``Time`` column."""
    row = duckdb.sql(
        f"SELECT "
        f"  min(YEAR(DATE '1899-12-30' + TRY_CAST(TRY_CAST(\"Time\" AS DOUBLE) AS INTEGER))), "
        f"  max(YEAR(DATE '1899-12-30' + TRY_CAST(TRY_CAST(\"Time\" AS DOUBLE) AS INTEGER))) "
        f"FROM read_parquet('{data_path.as_posix()}')"
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
    """Upload the release dir to R2 and return an r2:// URL for data.parquet."""
    bucket = os.environ["R2_BUCKET"]
    client = r2_client()
    prefix = f"{SOURCE}/{DATASET}/{release}"
    for file in sorted(release_dir.iterdir()):
        client.upload_file(str(file), bucket, f"{prefix}/{file.name}")
    return f"r2://{bucket}/{prefix}/{PRIMARY}"


def run(url: str = DEFAULT_URL, *, offline: bool = False) -> int:
    release = _release_from_url(url)
    print(f"EEX EU ETS auction archive: release {release}")

    manifest = (
        load_manifest(MANIFEST_PATH)
        if MANIFEST_PATH.exists()
        else Manifest(source=SOURCE, dataset=DATASET)
    )
    if manifest.release_exists(release):
        print(f"No new release (release {release!r} already pinned). Nothing to do.")
        return 0

    work = Path(tempfile.mkdtemp(prefix="cairn-eua-"))
    zip_path = work / "archive.zip"
    _download(url, zip_path)

    release_dir = work / "release"
    data_path = _export_parquet(zip_path, release_dir)
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

    print(f"Pinned snapshot: {row_count} rows, sha256={sha256[:12]}…, {storage_url}")
    print(f"Manifest updated: {MANIFEST_PATH}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest EEX EU ETS auction results.")
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Override the archive URL (use when EEX publishes a new release).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip R2 upload; place data under .localstack/ instead.",
    )
    args = parser.parse_args()
    sys.exit(run(url=args.url, offline=args.offline))


if __name__ == "__main__":
    main()
