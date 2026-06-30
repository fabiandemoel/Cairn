-- Surrendered allowances, when present, must be non-negative. The EUTL records
-- surrenders as positive quantities, so a negative value would signal a data
-- error in the pinned euets.info snapshot, not a real surrender. NULL is a
-- legitimate value (surrender can lag, and a single surrender may cover several
-- years) and is deliberately not flagged here. This is a magnitude sanity
-- bound only -- never a compliance verdict, and deliberately not a check that
-- surrendered matches verified emissions: a multi-year surrender can exceed a
-- single year's verified figure, so such a check would fail on valid data. The
-- test fails (returns rows) on any negative value.

select
    installation_id,
    year,
    surrendered_allowances_t_co2eq
from {{ ref('benchmark_installation_emissions') }}
where surrendered_allowances_t_co2eq < 0
