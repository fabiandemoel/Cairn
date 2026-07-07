-- Freshness/staleness view: per source, its pinned release/ingest date, the
-- latest calendar year its benchmark mart covers, and the observed lag
-- between them. Descriptive facts, not a freshness SLA/alarm/score.
-- Source mart: mart_source_freshness (reads sources/*/manifest.yml + refs
-- each source's benchmark mart).
select
    freshness_key,
    source,
    dataset,
    is_pinned,
    release,
    ingested_at,
    ingest_age_days,
    latest_covered_year,
    coverage_lag_years,
    computed_at
from mart_source_freshness
order by source
