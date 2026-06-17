"""Reproducibility check: a manifest entry -> raw file -> rebuilt mart.

Picks a snapshot from a source manifest, re-fetches its raw files, verifies the
SHA256 of the primary file matches the pin, then rebuilds the dbt project against
that raw file. This is the end-to-end proof behind every benchmark figure:
commit + manifest + immutable raw file reproduce the numbers.

By default it verifies every source (CBS, euets.info, EEA); pass --source to
target one. Each source skips gracefully -- if its manifest pins no snapshot
yet, or its snapshot lives in R2 and the R2_* secrets are absent -- so CI stays
green without credentials.

Run against the real manifests (needs R2 secrets):
    uv run python scripts/verify_reproducibility.py
    uv run python scripts/verify_reproducibility.py --source euets --release 2024-10
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

from ingestion.manifest import Snapshot, compute_sha256, load_manifest, r2_client  # noqa: E402

R2_ENV = ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")


# Per source: the manifest, the files that make up a snapshot's release dir, and
# the dbt var that points the staging models at that dir. The primary (hashed)
# file is derived from the snapshot's storage_url, so it need not be listed.
SOURCES: dict[str, dict] = {
    "cbs": {
        "manifest": REPO_ROOT / "sources" / "cbs" / "manifest.yml",
        "var": "raw_dir",
        "files": (
            "data.parquet",
            "dim_klimaatsectoren.parquet",
            "dim_emissies.parquet",
            "dim_perioden.parquet",
            "dim_measures.parquet",
        ),
    },
    "euets": {
        "manifest": REPO_ROOT / "sources" / "euets" / "manifest.yml",
        "var": "euets_raw_dir",
        "files": (
            "compliance.parquet",
            "installation.parquet",
            "dim_nace.parquet",
            "dim_activity_type.parquet",
            "dim_country.parquet",
        ),
    },
    "eea": {
        "manifest": REPO_ROOT / "sources" / "eea" / "manifest.yml",
        "var": "eea_raw_dir",
        "files": ("data.parquet",),
    },
}


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


def _fetch_release_dir(snapshot: Snapshot, files: tuple[str, ...], dest: Path) -> Path:
    """Materialise the snapshot's release directory locally; return its path."""
    parsed = urlparse(snapshot.storage_url)
    dest.mkdir(parents=True, exist_ok=True)
    if parsed.scheme == "file":
        src_dir = Path(parsed.path).parent
        for name in files:
            src = src_dir / name
            if src.exists():
                (dest / name).write_bytes(src.read_bytes())
        return dest

    # r2://bucket/<prefix>/<primary> -> download every file in the prefix
    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/").rsplit("/", 1)[0]
    client = r2_client()
    for name in files:
        client.download_file(bucket, f"{prefix}/{name}", str(dest / name))
    return dest


def _dbt_build(raw_dir: Path, var: str, duckdb_path: Path) -> None:
    env = {**os.environ, "CAIRN_DUCKDB": str(duckdb_path), "DBT_PROFILES_DIR": "transform"}
    subprocess.run(
        ["dbt", "build", "--project-dir", "transform", "--vars", f"{{{var}: {raw_dir}}}"],
        check=True,
        cwd=REPO_ROOT,
        env=env,
    )


def verify_source(name: str, cfg: dict, release: str | None, skip_build: bool) -> int:
    manifest = load_manifest(cfg["manifest"])
    if not manifest.snapshots:
        print(f"[{name}] manifest {manifest.source}/{manifest.dataset} pins no snapshots yet.")
        print("  Nothing to verify. Run an ingest (with R2 creds) to pin one. Skipping.")
        return 0
    snapshot = _select(manifest, release)
    scheme = urlparse(snapshot.storage_url).scheme
    primary = Path(urlparse(snapshot.storage_url).path).name
    print(f"[{name}] verifying {manifest.source}/{manifest.dataset} release {snapshot.release}")
    print(f"  storage: {snapshot.storage_url}")

    if scheme == "r2" and not all(os.environ.get(k) for k in R2_ENV):
        print("  R2 credentials absent (R2_ENDPOINT/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY).")
        print("  Skipping reproducibility verification. Set the secrets to enable it.")
        return 0

    with tempfile.TemporaryDirectory(prefix=f"cairn-verify-{name}-") as tmp:
        release_dir = _fetch_release_dir(snapshot, cfg["files"], Path(tmp) / "raw")
        actual = compute_sha256(release_dir / primary)
        if actual != snapshot.sha256:
            print(f"  HASH MISMATCH: manifest={snapshot.sha256} actual={actual}")
            return 1
        print(f"  SHA256 OK: {actual}")

        if skip_build:
            return 0
        _dbt_build(release_dir, cfg["var"], Path(tmp) / "verify.duckdb")
        print("  dbt build OK -- snapshot reproduces.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify manifest snapshots reproduce.")
    parser.add_argument(
        "--source", choices=sorted(SOURCES), default=None, help="Source to verify (default: all)."
    )
    parser.add_argument(
        "--release", default=None, help="Snapshot release to verify (default: latest)."
    )
    parser.add_argument(
        "--skip-build", action="store_true", help="Only verify the hash, don't rebuild."
    )
    args = parser.parse_args(argv)
    if args.release and not args.source:
        parser.error("--release requires --source (releases are per source).")

    names = [args.source] if args.source else list(SOURCES)
    exit_code = 0
    for name in names:
        exit_code |= verify_source(name, SOURCES[name], args.release, args.skip_build)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
