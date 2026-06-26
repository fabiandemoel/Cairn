-- Provenance-integrity view: per source snapshot, whether the chain back to the
-- official source is intact (pin status, storage backend, SHA256, row count,
-- release, period coverage). Observable facts from the manifests, not a score.
-- Source mart: mart_data_provenance (reads sources/*/manifest.yml).
select
    provenance_key,
    source,
    dataset,
    pin_status,
    is_pinned,
    is_latest,
    snapshot_count,
    release,
    ingested_at,
    storage_backend,
    storage_url,
    sha256,
    substr(sha256, 1, 12) as sha256_short,
    row_count,
    period_start,
    period_end
from mart_data_provenance
order by is_pinned desc, source
