"""Manifest read/write/verify logic for Cairn source snapshots.

The manifest is the auditability backbone: every immutable raw file is pinned
here by SHA256, storage URL, source release date and row count. The design
rules are deliberately strict:

* The manifest schema is a Pydantic model -- loading an invalid manifest raises.
* ``add_snapshot`` is append-only. It refuses to modify or delete an existing
  entry, so a data change without a manifest change is impossible.
* ``verify_snapshot`` re-downloads the object, recomputes the SHA256 and
  compares, so a silently-mutated raw file is detectable.

Storage URLs use a scheme that names the backend:

* ``r2://{bucket}/{key}``   -- Cloudflare R2 (S3-compatible), via boto3.
* ``file://{absolute path}`` -- local filesystem, used by ``--offline`` runs.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

SHA256_RE = r"^[0-9a-f]{64}$"


class Snapshot(BaseModel):
    """A single immutable source snapshot, pinned in the manifest."""

    model_config = ConfigDict(extra="forbid")

    release: str = Field(..., description="CBS 'Modified' date of the table (YYYY-MM-DD).")
    ingested_at: datetime = Field(..., description="When Cairn ingested this snapshot (UTC).")
    storage_url: str = Field(..., description="r2:// or file:// URL of the raw parquet.")
    sha256: str = Field(..., pattern=SHA256_RE, description="SHA256 of the raw parquet file.")
    row_count: int = Field(..., ge=0, description="Number of observation rows in the raw file.")
    periods_covered: list[str] = Field(
        ..., min_length=1, description="[min_period, max_period] of the snapshot."
    )

    @field_validator("storage_url")
    @classmethod
    def _known_scheme(cls, value: str) -> str:
        scheme = urlparse(value).scheme
        if scheme not in {"r2", "file"}:
            raise ValueError(f"storage_url must use scheme r2:// or file://, got {scheme!r}")
        return value


class Manifest(BaseModel):
    """The pinned source snapshots for a single dataset."""

    model_config = ConfigDict(extra="forbid")

    source: str
    dataset: str
    snapshots: list[Snapshot] = Field(default_factory=list)

    @property
    def latest(self) -> Snapshot | None:
        """The most recently ingested snapshot, or ``None`` if empty."""
        if not self.snapshots:
            return None
        return max(self.snapshots, key=lambda s: s.ingested_at)

    def release_exists(self, release: str) -> bool:
        return any(s.release == release for s in self.snapshots)


def compute_sha256(path: str | Path, *, chunk_size: int = 1 << 20) -> str:
    """Return the hex SHA256 of a local file, streamed in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: str | Path) -> Manifest:
    """Load and validate a manifest YAML file. Raises on invalid content."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if raw is None:
        raise ValueError(f"Manifest at {path} is empty")
    return Manifest.model_validate(raw)


def save_manifest(path: str | Path, manifest: Manifest) -> None:
    """Serialise a manifest back to YAML, preserving key order."""
    payload = manifest.model_dump(mode="json")
    Path(path).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def add_snapshot(manifest: Manifest, snapshot: Snapshot) -> Manifest:
    """Append a snapshot, append-only.

    Refuses to add a snapshot for a ``release`` that already exists -- that
    would be an in-place modification of pinned data, which the architecture
    forbids. Returns a new ``Manifest``; the input is not mutated.
    """
    if manifest.release_exists(snapshot.release):
        raise ValueError(
            f"Refusing to add snapshot: release {snapshot.release!r} already pinned. "
            "Manifests are append-only; raw data is immutable."
        )
    return manifest.model_copy(update={"snapshots": [*manifest.snapshots, snapshot]})


def _resolve_local_path(storage_url: str) -> Path | None:
    """Return the local path for a ``file://`` URL, else ``None``."""
    parsed = urlparse(storage_url)
    if parsed.scheme != "file":
        return None
    # file:///abs/path -> /abs/path
    return Path(parsed.path)


def r2_client():
    """Build a boto3 S3 client for Cloudflare R2 from the ``R2_*`` env vars.

    Cloudflare R2 rejects the flexible-checksum integrity headers that botocore
    enables by default (since botocore 1.36), returning ``400 Bad Request`` on
    PutObject/HeadObject/GetObject. Setting both checksum modes to
    ``when_required`` disables that, and ``region_name="auto"`` matches R2.
    """
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def _download_r2(storage_url: str, dest: Path) -> None:
    """Download an ``r2://bucket/key`` object to ``dest`` using boto3."""
    parsed = urlparse(storage_url)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    r2_client().download_file(bucket, key, str(dest))


def verify_snapshot(snapshot: Snapshot, *, work_dir: str | Path | None = None) -> bool:
    """Re-fetch the snapshot's object, recompute SHA256 and compare.

    For ``file://`` URLs the local file is hashed in place. For ``r2://`` URLs
    the object is downloaded to ``work_dir`` (a temp dir by default) first.
    Returns ``True`` on a match; raises ``FileNotFoundError`` if the object is
    missing and ``ValueError`` on a hash mismatch.
    """
    local = _resolve_local_path(snapshot.storage_url)
    if local is not None:
        if not local.exists():
            raise FileNotFoundError(f"Raw file missing: {local}")
        actual = compute_sha256(local)
    else:
        import tempfile

        tmp_parent = Path(work_dir) if work_dir is not None else Path(tempfile.mkdtemp())
        tmp_parent.mkdir(parents=True, exist_ok=True)
        dest = tmp_parent / "verify.parquet"
        _download_r2(snapshot.storage_url, dest)
        actual = compute_sha256(dest)

    if actual != snapshot.sha256:
        raise ValueError(
            f"SHA256 mismatch for {snapshot.storage_url}: "
            f"manifest={snapshot.sha256} actual={actual}"
        )
    return True
