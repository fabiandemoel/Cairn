"""Ingestion pipeline: Eurostat Air Emissions Accounts → parquet → R2 (+ manifest).

Eurostat publishes Air Emission Accounts by NACE Rev. 2 activity (``env_ac_ainah_r2``)
— annual greenhouse-gas and air-pollutant emissions by industry sector across all EU
member states and EFTA. This pipeline ingests the full cross-country dataset as the raw
pin for the future dbt staging and EU-wide sector benchmark mart.

End to end:

1. Fetch the dataset's last-update date from the Eurostat SDMX dataflow JSON API
   (lightweight; a couple of KB, no data download). Use this as the release token.
2. Idempotency: if the latest manifest snapshot already pins that release, exit cleanly --
   no download, no upload, no manifest change.
3. Download the SDMX-CSV from the Eurostat dissemination API and convert it to a clean,
   deterministically-ordered parquet (all columns VARCHAR).
4. Place the raw file immutably: R2 under ``eurostat/env_ac_ainah_r2/{release}/`` (online)
   or ``./.localstack/eurostat/env_ac_ainah_r2/{release}/`` (``--offline``, no credentials).
5. Hash ``data.parquet`` and append a manifest snapshot. Ingestion without a manifest update
   is impossible by construction.

Raw faithfulness: every row of the source CSV is kept (all countries, all pollutants, all
NACE sectors, all years). Filtering to NL-only, GHG-only, or stationary sources is
methodology and belongs in the dbt staging layer, not here.

Note on accounting principle: AEA uses the *residence principle* (emissions attributed to
entities registered/resident in a country), in contrast to the *territorial principle* used
by CBS 85669NED and EU ETS (emissions physically occurring within national borders). The dbt
layer must reconcile these via Eurostat's ``env_ac_aibrid_r2`` bridging dataset before
comparing AEA figures with CBS or EU ETS totals -- do not conflate them.

Run offline (downloads from Eurostat but skips R2, no credentials needed):
    uv run python -m ingestion.eurostat_aea_pipeline --offline
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
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

SOURCE = "eurostat"
DATASET = "env_ac_ainah_r2"
MANIFEST_PATH = Path(__file__).resolve().parent.parent / "sources" / "eurostat" / "manifest.yml"

# Lightweight SDMX dataflow metadata URL — a couple of KB of JSON whose annotations
# include the dataset's last-update timestamp (UPDATE_DATA). Eurostat's older
# catalogue/datasets/<id>/json endpoint, which used to expose this, returns 404 as of
# 2026; this dataflow endpoint is the SDMX-native replacement.
METADATA_URL = (
    f"https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/{DATASET}?format=json"
)

# Full data download URL — returns the SDMX-CSV file directly (no longer zipped, as of 2026).
# The format=SDMX-CSV parameter selects the standard comma-separated SDMX 1.0 layout:
#   DATAFLOW, LAST UPDATE, freq, airpol, unit, nace_r2, geo, TIME_PERIOD, OBS_VALUE, OBS_FLAG
DEFAULT_DATA_URL = (
    f"https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{DATASET}"
    "?format=SDMX-CSV&download=true"
)

PRIMARY = "data.parquet"


def _fetch_last_update(metadata_url: str = METADATA_URL) -> str:
    """Fetch the dataset's last-update date from the Eurostat SDMX dataflow API.

    Returns a release token in YYYY-MM-DD format, suitable for use as the manifest
    snapshot ``release`` field.
    """
    req = urllib.request.Request(metadata_url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode())
    return _parse_release(_extract_update_date(payload))


def _extract_update_date(payload: dict) -> str:
    """Pull the UPDATE_DATA annotation's date out of an SDMX dataflow JSON payload."""
    annotations = payload.get("extension", {}).get("annotation", [])
    for annotation in annotations:
        if annotation.get("type") == "UPDATE_DATA":
            date = annotation.get("date")
            if date:
                return str(date)
    raise ValueError(
        f"Cannot find a UPDATE_DATA annotation in the Eurostat dataflow response "
        f"for {DATASET}. Annotation types present: "
        f"{[a.get('type') for a in annotations]}"
    )


def _parse_release(raw: str) -> str:
    """Normalise a Eurostat date string to YYYY-MM-DD.

    The SDMX dataflow API returns an ISO timestamp (optionally with a timezone
    offset); older catalogue responses used DD.MM.YYYY. Both are normalised to
    ISO YYYY-MM-DD as the release token.
    """
    s = raw.strip()

    # DD.MM.YYYY — older Eurostat catalogue format
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", s)
    if m:
        day, month, year = m.groups()
        return f"{year}-{month}-{day}"

    # YYYY-MM-DD already normalised
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)

    # YYYY-MM (month precision only)
    m = re.match(r"^(\d{4}-\d{2})$", s)
    if m:
        return s

    raise ValueError(
        f"Cannot parse Eurostat date {raw!r} into a YYYY-MM-DD release token. "
        "Expected DD.MM.YYYY or YYYY-MM-DD."
    )


def _download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh)


def _export_parquet(csv_path: Path, out_dir: Path) -> Path:
    """Convert the SDMX-CSV to a clean, deterministically-ordered parquet.

    All columns are read as VARCHAR so the raw parquet is a lossless copy of the CSV
    text — typing is the dbt staging layer's job. ``ORDER BY ALL`` makes a re-ingest
    of unchanged source data byte-stable.

    The SDMX-CSV ``LAST UPDATE`` column name contains a space, which DuckDB handles
    transparently when reading with ``all_varchar=true``; the dbt staging layer must
    quote it (``"LAST UPDATE"``).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / PRIMARY
    con = duckdb.connect()
    try:
        con.sql(
            f"COPY (SELECT * FROM read_csv('{csv_path.as_posix()}', "
            f"all_varchar = true, header = true) ORDER BY ALL) "
            f"TO '{dest.as_posix()}' (FORMAT PARQUET)"
        )
    finally:
        con.close()
    csv_path.unlink()
    return dest


def _periods_covered(data_path: Path) -> list[str]:
    """[min_year, max_year] from the TIME_PERIOD column."""
    row = duckdb.sql(
        f"SELECT min(TRY_CAST(TIME_PERIOD AS INTEGER)), max(TRY_CAST(TIME_PERIOD AS INTEGER)) "
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


def run(data_url: str = DEFAULT_DATA_URL, *, offline: bool = False) -> int:
    print(f"Checking Eurostat {DATASET} last-update date…")
    release = _fetch_last_update()
    print(f"Eurostat {DATASET}: release {release}")

    manifest = (
        load_manifest(MANIFEST_PATH)
        if MANIFEST_PATH.exists()
        else Manifest(source=SOURCE, dataset=DATASET)
    )
    if manifest.release_exists(release):
        print(f"No new release (release {release} already pinned). Nothing to do.")
        return 0

    work = Path(tempfile.mkdtemp(prefix="cairn-eurostat-"))
    csv_path = work / f"{DATASET}.csv"
    _download(data_url, csv_path)

    release_dir = work / "release"
    data_path = _export_parquet(csv_path, release_dir)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=f"Ingest the Eurostat {DATASET} dataset into Cairn."
    )
    parser.add_argument(
        "--data-url",
        default=DEFAULT_DATA_URL,
        help="Eurostat SDMX-CSV download URL (default: %(default)s)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip R2; write raw files to ./.localstack/ (no credentials needed).",
    )
    args = parser.parse_args(argv)
    return run(args.data_url, offline=args.offline)


if __name__ == "__main__":
    sys.exit(main())
