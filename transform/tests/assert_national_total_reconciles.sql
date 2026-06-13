-- Singular test: the national total implied by the mart (sum of all NACE
-- buckets, including UNMAPPED) must stay within 0.5% of the CBS source total
-- (the "Totaal klimaatsectoren" row, T001616). This catches mapping gaps: if a
-- leaf category were dropped or mis-flagged as aggregate, the sum would drift.
-- The test passes when it returns zero rows.

with mart_total as (
    select distinct
        year,
        national_emissions_mt_co2eq
    from {{ ref('benchmark_sector_emissions') }}
),

source_total as (
    select
        year,
        emissions_mt_co2eq as source_total_mt_co2eq
    from {{ ref('stg_cbs__emissions') }}
    where
        cbs_category_code = 'T001616'
        and gas_code = 'T001372'
        and period_status = 'Definitief'
)

select
    mart_total.year,
    mart_total.national_emissions_mt_co2eq,
    source_total.source_total_mt_co2eq,
    abs(mart_total.national_emissions_mt_co2eq - source_total.source_total_mt_co2eq)
    / source_total.source_total_mt_co2eq as relative_deviation
from mart_total
inner join source_total using (year)
where
    abs(mart_total.national_emissions_mt_co2eq - source_total.source_total_mt_co2eq)
    / source_total.source_total_mt_co2eq >= 0.005
