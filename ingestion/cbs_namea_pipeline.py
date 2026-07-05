"""dlt ingestion pipeline: CBS NAMEA air emission accounts -> parquet -> R2 (+ manifest).

Table ``83300NED`` ("Emissies naar lucht door de Nederlandse economie; nationale
rekeningen") carries the NAMEA air emission accounts: annual emissions of
greenhouse gases and air pollutants by economic sector under the **residence
principle** (emissions attributed to Dutch-resident economic activity, including
Dutch operators abroad and excluding non-residents on Dutch territory). This is
the deliberate methodological counterpart to ``85669NED`` (territorial
principle, ``ingestion/cbs_pipeline.py``) — their totals diverge by design.
CBS updates the table annually in November; the release is the OData v4
``Properties`` singleton's ``Modified`` date.

End to end (same shape as ``ingestion/cbs_pipeline.py``):

1. Read the table ``Properties`` to get the CBS ``Modified`` date (the release).
2. Idempotency: if the manifest already pins that release, exit cleanly --
   no upload, no manifest change.
3. Extract the observations and the dimension code tables with dlt into a local
   DuckDB, then export each to a clean, single parquet under a release dir.
4. Place the raw files immutably: R2 under ``cbs_namea/air_emissions/{release}/``
   (online) or ``./.localstack/...`` (``--offline``, no credentials).
5. Hash ``data.parquet`` (the observations) and append a manifest snapshot.

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

import dlt
import duckdb

from ingestion.cbs_odata import fetch_properties, iter_entityset
from ingestion.manifest import (
    Manifest,
    Snapshot,
    add_snapshot,
    compute_sha256,
    load_manifest,
    r2_client,
    save_manifest,
)

TABLE_ID = "83300NED"
SOURCE = "cbs_namea"
DATASET = "air_emissions"
MANIFEST_PATH = Path(__file__).resolve().parent.parent / "sources" / SOURCE / "manifest.yml"

PRIMARY = "data.parquet"

# CBS entity set -> output parquet filename in the release dir. ``data.parquet``
# (the observations) is the hashed raw artifact; the dim_* files decode codes to
# labels and are read by the dbt staging model alongside it.
EXPORTS: dict[str, str] = {
    "Observations": PRIMARY,
    "NederlandseEconomieCodes": "dim_nederlandse_economie.parquet",
    "PeriodenCodes": "dim_perioden.parquet",
    "MeasureCodes": "dim_measures.parquet",
}


@dlt.source(name="cbs_namea_emissions")
def cbs_namea_source(table: str = TABLE_ID):
    """A dlt resource per CBS entity set we ingest."""

    def _resource(entity_set: str):
        @dlt.resource(name=entity_set.lower(), write_disposition="replace")
        def _r():
            yield from iter_entityset(table, entity_set)

        return _r()

    return [_resource(name) for name in EXPORTS]


def _release_from_properties(props: dict) -> str:
    """CBS 'Modified' (ISO 8601 with tz) -> release date string YYYY-MM-DD."""
    modified = props["Modified"]
    return datetime.fromisoformat(modified).date().isoformat()


def _periods_covered(con: duckdb.DuckDBPyConnection, dataset: str) -> list[str]:
    """[min_year, max_year] from the Perioden codes (labels like '1990')."""
    rows = con.sql(f"SELECT min(title), max(title) FROM {dataset}.periodencodes").fetchone()
    return [str(rows[0]).strip(), str(rows[1]).strip()]


def _export_parquets(con: duckdb.DuckDBPyConnection, dataset: str, out_dir: Path) -> None:
    """Export each loaded dlt table to a clean single parquet (no _dlt columns).

    Rows are ordered deterministically (observations by ``id``, code tables by
    ``index``) so a re-ingest of unchanged source data yields stable output.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for entity_set, filename in EXPORTS.items():
        table = f"{dataset}.{entity_set.lower()}"
        dest = out_dir / filename
        order_col = "id" if entity_set == "Observations" else "index"
        con.sql(
            f"COPY (SELECT * EXCLUDE (_dlt_load_id, _dlt_id) FROM {table} ORDER BY {order_col}) "
            f"TO '{dest.as_posix()}' (FORMAT PARQUET)"
        )


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


def run(table: str = TABLE_ID, *, offline: bool = False) -> int:
    props = fetch_properties(table)
    release = _release_from_properties(props)
    print(f"CBS {table}: '{props['Title']}' release {release}")

    manifest = (
        load_manifest(MANIFEST_PATH)
        if MANIFEST_PATH.exists()
        else Manifest(source=SOURCE, dataset=DATASET)
    )
    if manifest.release_exists(release):
        print(f"No new release (release {release} already pinned). Nothing to do.")
        return 0

    work = Path(tempfile.mkdtemp(prefix=f"cairn-{SOURCE}-"))
    pipeline = dlt.pipeline(
        pipeline_name=f"{SOURCE}_{table.lower()}",
        destination=dlt.destinations.duckdb(str(work / "load.duckdb")),
        dataset_name=f"{SOURCE}_raw",
        pipelines_dir=str(work / "dlt"),
    )
    info = pipeline.run(cbs_namea_source(table))
    print(info)

    release_dir = work / "release"
    con = duckdb.connect(str(work / "load.duckdb"))
    try:
        _export_parquets(con, f"{SOURCE}_raw", release_dir)
        periods = _periods_covered(con, f"{SOURCE}_raw")
    finally:
        con.close()

    data_parquet = release_dir / PRIMARY
    sha256 = compute_sha256(data_parquet)
    row_count = _row_count(data_parquet)

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
        description=f"Ingest the {SOURCE} {DATASET} dataset (CBS {TABLE_ID}) into Cairn."
    )
    parser.add_argument("--table", default=TABLE_ID, help="CBS table id (default: %(default)s)")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip R2; write raw files to ./.localstack/ (no credentials needed).",
    )
    args = parser.parse_args(argv)
    return run(args.table, offline=args.offline)


if __name__ == "__main__":
    sys.exit(main())
