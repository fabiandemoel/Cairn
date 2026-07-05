-- Coverage & completeness observability: per source and year, the
-- reconciliation drift against the official aggregate, the UNMAPPED share
-- (CBS only), and the covered share -- descriptive facts the assert tests
-- already compute, surfaced rather than discarded.
-- Source mart: mart_coverage_observability.
select
    coverage_key,
    source,
    year,
    reconciliation_drift,
    unmapped_share,
    covered_share
from mart_coverage_observability
order by source, year
