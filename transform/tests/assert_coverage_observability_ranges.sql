-- Singular test: mart_coverage_observability's descriptive ratios must stay
-- within a generous sanity range -- this guards against a gross modelling bug
-- (e.g. a double-counted total), not a re-assertion of the tight tolerances
-- assert_national_total_reconciles / assert_euets_coverage_within_eea already
-- enforce upstream (both < 0.5%). The test passes when it returns zero rows.
--
-- euets is checked one-sided (upper bound only), mirroring
-- assert_euets_coverage_within_eea: the CI fixture holds only a subset of NL
-- installations, so a large *negative* drift / low covered_share is expected
-- there and on any partial snapshot, never a bug. Only a drift/share that
-- *exceeds* the official aggregate signals a real problem (e.g. double
-- counting). cbs has no such asymmetry -- its mart always partitions the full
-- national total -- so it stays a two-sided check.

select
    coverage_key,
    source,
    year,
    reconciliation_drift,
    unmapped_share,
    covered_share
from {{ ref('mart_coverage_observability') }}
where
    (source = 'cbs' and abs(reconciliation_drift) > 0.05)
    or (source = 'cbs' and (unmapped_share is null or unmapped_share < 0 or unmapped_share > 1))
    or (source = 'cbs' and covered_share > 1)
    or (source = 'euets' and reconciliation_drift > 0.05)
    or (source = 'euets' and covered_share > 1.05)
