"""Ingestion pipeline: RIVM Emissieregistratie (NL national GHG inventory) -> parquet -> R2.

RIVM (the Dutch National Institute for Public Health and the Environment) operates
Emissieregistratie, the detailed emissions inventory underlying the figures the
Netherlands submits to the UNFCCC (the UN's climate treaty body) each year -- one
layer upstream of the CBS 85669NED national total Cairn already pins. The
Emissieregistratie web portal (emissieregistratie.nl) itself exposes only an
interactive, JavaScript-driven "export" tool: its ``/api/data/`` and
``/api/export/v1/`` endpoints 404 without a live browser session, so there is no
headless-fetchable bulk API on that site. This pipeline instead ingests the same
underlying data via its actual machine-readable publication channel: the
Netherlands' annual CRF (Common Reporting Format) submission to the UNFCCC -- a
standardised set of per-inventory-year XLSX workbooks published at a stable
unfccc.int URL. Each workbook's ``Summary1`` sheet is RIVM's national total, by
IPCC source/sink category and by greenhouse gas, for that inventory year -- the
natural cross-check target for CBS's national total (see BACKLOG.md candidate #2).

The archive has no lightweight "last updated" metadata endpoint (UNFCCC's own
di.unfccc.int query interface is JS-only, with no documented REST/CSV export) --
so, like ``eua_pipeline.py``'s EEX archive, it is **human-watched**: the release
token is the version string embedded in the zip filename itself
(``NLD-CRT-<year>-V<version>.zip`` -> e.g. ``"2026-V1.0"``), bumped in
``DEFAULT_URL`` when UNFCCC/RVO publish a newer annual submission (each ~April,
covering the prior calendar year).

End to end:

1. Parse the release token from the archive URL filename. No network request is
   needed for the idempotency check.
2. Idempotency: if the manifest already pins that release token, exit cleanly --
   no download, no upload, no manifest change.
3. Download the zip from ``DEFAULT_URL`` (or ``--url`` for a newer submission),
   extract the per-inventory-year XLSX workbooks (e.g.
   ``NLD-CRT-2026-V1.0-2005.xlsx``), read each one's ``Summary1`` sheet, and
   combine them into a single, deterministically-ordered parquet (all columns
   VARCHAR), tagged with the inventory year parsed from each workbook's filename.
4. Place the raw file immutably: R2 under
   ``emissieregistratie/crf_summary1/{release}/`` (online) or
   ``./.localstack/emissieregistratie/crf_summary1/{release}/`` (``--offline``).
5. Hash ``data.parquet`` and append a manifest snapshot. Ingestion without a
   manifest update is impossible by construction.

Raw faithfulness: every category row of each year's ``Summary1`` sheet is kept.
The sheet has a two-row header (gas name, then unit) immediately above the data;
only the first row is consumed as the DuckDB header, so the unit row is preserved
as an ordinary (mostly-null, unit-label) row rather than silently dropped --
identifying and excluding it is the future dbt staging layer's job, not this
pipeline's (mirrors how CBS's provisional-year rows and EU ETS's linked-registry
duplicates are kept raw and filtered downstream).

Note on scope: this dataset partly overlaps CBS 85669NED's national GHG total. A
future staging/mart layer must frame it as a cross-check/provenance layer over
CBS -- not a second independent authority for the same total -- with a
reconciliation test, mirroring ``assert_eurostat_aea_nl_within_cbs`` /
``assert_gge_nl_total_within_cbs``. Not actionable here: this pipeline has no
staging model or mart (ingestion + manifest only).

Run offline (downloads from UNFCCC but skips R2, no credentials needed):
    uv run python -m ingestion.emissieregistratie_pipeline --offline
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

SOURCE = "emissieregistratie"
DATASET = "crf_summary1"
MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent / "sources" / "emissieregistratie" / "manifest.yml"
)

# The Netherlands' current UNFCCC CRF (Common Reporting Format) national GHG
# inventory submission. The version token in the filename is the release; pass
# --url when RVO/UNFCCC publish a newer annual submission (e.g.
# ".../NLD-CRT-2027-V1.0.zip").
DEFAULT_URL = "https://unfccc.int/sites/default/files/resource/NLD-CRT-2026-V1.0.zip"

PRIMARY = "data.parquet"
DATA_SHEET = "Summary1"

# Row 8 (1-indexed) is the gas/category header row; row 9 is a units sub-header
# (kept as an ordinary data row, see module docstring); rows 10-67 are the IPCC
# source/sink category hierarchy. Column A is unused (blank) in every CRF
# Reporter-generated Summary1 sheet; the 14 real columns span B-O.
_DATA_RANGE = "B8:O67"


def _release_from_url(url: str) -> str:
    """Parse the version release token from the UNFCCC archive URL.

    ``.../NLD-CRT-2026-V1.0.zip`` -> ``"2026-V1.0"``
    """
    filename = url.rstrip("/").split("/")[-1]
    stem = filename[:-4] if filename.lower().endswith(".zip") else filename
    m = re.match(r"NLD-CRT-(.+)$", stem)
    if not m:
        raise ValueError(
            f"Cannot derive a release token from Emissieregistratie filename {filename!r}. "
            "Expected 'NLD-CRT-<release>.zip'."
        )
    return m.group(1)


def _download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh)


def _find_xlsx_members(zf: zipfile.ZipFile) -> list[str]:
    """Return the per-inventory-year XLSX members from the zip, sorted by name."""
    return sorted(m for m in zf.namelist() if m.lower().endswith(".xlsx"))


def _year_from_member(name: str) -> str:
    """``NLD-CRT-2026-V1.0-2005.xlsx`` -> ``"2005"``."""
    m = re.search(r"-(\d{4})\.xlsx$", name, re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot derive an inventory year from workbook filename {name!r}")
    return m.group(1)


def _export_parquet(zip_path: Path, out_dir: Path) -> Path:
    """Combine every year's ``Summary1`` sheet into a single ordered parquet.

    All columns are read as VARCHAR (lossless raw copy; typing is the dbt staging
    layer's job). ``ORDER BY ALL`` makes re-ingestion of unchanged source data
    byte-stable. Each year's rows are tagged with ``inventory_year``, parsed from
    that workbook's filename, since the year appears only in the filename and
    sheet title metadata (outside the data range read here), not in the data rows.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / PRIMARY
    extract_dir = out_dir / "_extract"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = _find_xlsx_members(zf)
            if not members:
                raise ValueError(f"No XLSX files found in {zip_path}")
            extracted = [(Path(zf.extract(m, extract_dir)), _year_from_member(m)) for m in members]

        con = duckdb.connect()
        try:
            con.sql("INSTALL excel; LOAD excel;")
            parts = [
                f"SELECT '{year}' AS inventory_year, * FROM read_xlsx('{p.as_posix()}', "
                f"sheet = '{DATA_SHEET}', range = '{_DATA_RANGE}', header = true, "
                f"all_varchar = true, stop_at_empty = true)"
                for p, year in extracted
            ]
            union_sql = " UNION ALL ".join(parts)
            con.sql(f"COPY ({union_sql} ORDER BY ALL) TO '{dest.as_posix()}' (FORMAT PARQUET)")
        finally:
            con.close()
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)

    return dest


def _periods_covered(data_path: Path) -> list[str]:
    """[min_year, max_year] derived from the ``inventory_year`` tag column."""
    row = duckdb.sql(
        f"SELECT min(TRY_CAST(inventory_year AS INTEGER)), "
        f"max(TRY_CAST(inventory_year AS INTEGER)) "
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
    print(f"Emissieregistratie CRF submission: release {release}")

    manifest = (
        load_manifest(MANIFEST_PATH)
        if MANIFEST_PATH.exists()
        else Manifest(source=SOURCE, dataset=DATASET)
    )
    if manifest.release_exists(release):
        print(f"No new release (release {release!r} already pinned). Nothing to do.")
        return 0

    work = Path(tempfile.mkdtemp(prefix="cairn-emissieregistratie-"))
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

    print(f"Pinned snapshot: {row_count} rows, sha256={sha256[:12]}..., {storage_url}")
    print(f"Manifest updated: {MANIFEST_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest the RIVM Emissieregistratie (UNFCCC CRF) national GHG inventory."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Override the archive URL (use when a new submission is published).",
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
