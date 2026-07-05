-- Singular test: mart_coverage_observability's descriptive ratios must stay
-- within a generous sanity range -- this guards against a gross modelling bug
-- (e.g. a double-counted total), not a re-assertion of the tight tolerances
-- assert_national_total_reconciles / assert_euets_coverage_within_eea already
-- enforce upstream (both < 0.5%). The test passes when it returns zero rows.

select
    coverage_key,
    source,
    year,
    reconciliation_drift,
    unmapped_share,
    covered_share
from {{ ref('mart_coverage_observability') }}
where
    abs(reconciliation_drift) > 0.05
    or (unmapped_share is not null and (unmapped_share < 0 or unmapped_share > 1))
    or covered_share < 0
    or covered_share > 1.05
