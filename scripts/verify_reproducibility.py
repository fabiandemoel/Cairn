"""Reproducibility check: a manifest entry -> raw file -> rebuilt mart.

Picks a snapshot from the source manifest, re-fetches its raw file, verifies the
SHA256 matches the pin, then rebuilds the dbt mart against that raw file. This is
the end-to-end proof behind every benchmark figure: commit + manifest + immutable
raw file reproduce the numbers.

Run against the real manifest (needs R2 secrets):
    uv run python scripts/verify_reproducibility.py

If the snapshot lives in R2 and the R2_* env vars are absent, the script skips
gracefully with a clear message and exits 0, so CI stays green without secrets.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ingestion.manifest import Snapshot, compute_sha256, load_manifest  # noqa: E402

DEFAULT_MANIFEST = REPO_ROOT / "sources" / "cbs" / "manifest.yml"
R2_ENV = ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
# Raw files that make up a snapshot release directory (data + decode tables).
RELEASE_FILES = (
    "data.parquet",
    "dim_klimaatsectoren.parquet",
    "dim_emissies.parquet",
    "dim_perioden.parquet",
    "dim_measures.parquet",
)


def _select(manifest, release: str | None) -> Snapshot:
    if release is None:
        snap = manifest.latest
        if snap is None:
            raise SystemExit("Manifest has no snapshots to verify.")
        return snap
    for snap in manifest.snapshots:
        if snap.release == release:
            return snap
    raise SystemExit(f"No snapshot with release {release!r} in manifest.")


def _fetch_release_dir(snapshot: Snapshot, dest: Path) -> Path:
    """Materialise the snapshot's release directory locally; return its path."""
    parsed = urlparse(snapshot.storage_url)
    dest.mkdir(parents=True, exist_ok=True)
    if parsed.scheme == "file":
        src_dir = Path(parsed.path).parent
        for name in RELEASE_FILES:
            src = src_dir / name
            if src.exists():
                (dest / name).write_bytes(src.read_bytes())
        return dest

    # r2://bucket/cbs/<table>/<release>/data.parquet -> download the whole prefix
    import boto3

    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/").rsplit("/", 1)[0]
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )
    for name in RELEASE_FILES:
        client.download_file(bucket, f"{prefix}/{name}", str(dest / name))
    return dest


def _dbt_build(raw_dir: Path, duckdb_path: Path) -> None:
    env = {**os.environ, "CAIRN_DUCKDB": str(duckdb_path), "DBT_PROFILES_DIR": "transform"}
    subprocess.run(
        [
            "dbt",
            "build",
            "--project-dir",
            "transform",
            "--vars",
            f"{{raw_dir: {raw_dir}}}",
        ],
        check=True,
        cwd=REPO_ROOT,
        env=env,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a manifest snapshot reproduces.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--release", default=None, help="Snapshot release to verify (default: latest)."
    )
    parser.add_argument(
        "--skip-build", action="store_true", help="Only verify the hash, don't rebuild."
    )
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    if not manifest.snapshots:
        print(f"Manifest {manifest.source}/{manifest.dataset} pins no snapshots yet.")
        print("  Nothing to verify. Run an ingest (with R2 creds) to pin one. Skipping.")
        return 0
    snapshot = _select(manifest, args.release)
    scheme = urlparse(snapshot.storage_url).scheme
    print(f"Verifying {manifest.source}/{manifest.dataset} release {snapshot.release}")
    print(f"  storage: {snapshot.storage_url}")

    if scheme == "r2" and not all(os.environ.get(k) for k in R2_ENV):
        print("  R2 credentials absent (R2_ENDPOINT/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY).")
        print("  Skipping reproducibility verification. Set the secrets to enable it.")
        return 0

    with tempfile.TemporaryDirectory(prefix="cairn-verify-") as tmp:
        release_dir = _fetch_release_dir(snapshot, Path(tmp) / "raw")
        actual = compute_sha256(release_dir / "data.parquet")
        if actual != snapshot.sha256:
            print(f"  HASH MISMATCH: manifest={snapshot.sha256} actual={actual}")
            return 1
        print(f"  SHA256 OK: {actual}")

        if args.skip_build:
            return 0
        _dbt_build(release_dir, Path(tmp) / "verify.duckdb")
        print("  dbt build OK — snapshot reproduces.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
