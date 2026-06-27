"""Materialise the dbt warehouse from the pinned R2 snapshots, for the site build.

Downloads each source's latest pinned snapshot (CBS, euets.info, EEA, Eurostat AEA)
from R2 into a local cache dir, verifies its SHA256 against the manifest, then runs
a single ``dbt build`` with the ``*_raw_dir`` vars pointing at them. The result is
``cairn.duckdb`` at the repo root -- the warehouse the Evidence site reads.

Unlike ``verify_reproducibility.py`` (which checks each snapshot in isolation and
discards the build), this produces one real warehouse from all sources at once.
It is the data step of the GitHub Pages deploy. Requires the ``R2_*`` secrets and
every source pinned; it exits non-zero otherwise, so the site is never published
from incomplete or unverified data.

    uv run python scripts/materialize_warehouse.py

The reproducibility job already proves manifest -> raw file -> mart; this reuses
the same download + hash check so the published numbers carry the same guarantee.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ingestion.manifest import compute_sha256, load_manifest  # noqa: E402
from scripts.verify_reproducibility import (  # noqa: E402
    R2_ENV,
    SOURCES,
    _fetch_release_dir,
)

CACHE = REPO_ROOT / ".r2cache"


def main() -> int:
    if not all(os.environ.get(k) for k in R2_ENV):
        raise SystemExit(
            "R2 credentials absent (need "
            + "/".join(R2_ENV)
            + "). The site is built from the pinned R2 snapshots; set the secrets."
        )

    raw_vars: dict[str, Path] = {}
    for name, cfg in SOURCES.items():
        manifest = load_manifest(cfg["manifest"])
        snapshot = manifest.latest
        if snapshot is None:
            raise SystemExit(
                f"[{name}] manifest pins no snapshot yet -- run its ingest (with R2 "
                f"creds) to establish the pin before publishing the site."
            )
        if urlparse(snapshot.storage_url).scheme != "r2":
            raise SystemExit(
                f"[{name}] latest snapshot is not in R2 ({snapshot.storage_url}); "
                f"the published site must build from R2-pinned data."
            )

        dest = _fetch_release_dir(snapshot, cfg["files"], CACHE / name)
        primary = Path(urlparse(snapshot.storage_url).path).name
        actual = compute_sha256(dest / primary)
        if actual != snapshot.sha256:
            raise SystemExit(
                f"[{name}] SHA256 mismatch: manifest={snapshot.sha256} actual={actual}"
            )
        print(f"[{name}] materialised {snapshot.release} -> {dest} (SHA256 OK)")
        raw_vars[cfg["var"]] = dest

    vars_str = "{" + ", ".join(f"{var}: {path}" for var, path in raw_vars.items()) + "}"
    print(f"dbt build --vars '{vars_str}'")
    subprocess.run(
        ["dbt", "build", "--project-dir", "transform", "--vars", vars_str],
        check=True,
        cwd=REPO_ROOT,
        env={**os.environ, "DBT_PROFILES_DIR": "transform"},
    )
    print("Warehouse materialised from R2 -> cairn.duckdb")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
