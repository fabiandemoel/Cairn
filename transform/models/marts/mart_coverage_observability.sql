-- Mart: coverage & completeness observability. Surfaces, per source and year,
-- the reconciliation drift and coverage share that
-- assert_national_total_reconciles and assert_euets_coverage_within_eea
-- already compute in CI -- but discard once the test goes green. A second
-- reader of those same figures, never a re-derivation of a national total by
-- an independent route.
--
-- Methodology:
--   * cbs: reconciliation_drift compares the CBS mart's own national total
--     (all leaves, including UNMAPPED) against the CBS source total
--     (T001616) -- the same pair assert_national_total_reconciles compares.
--     unmapped_share is the share of that total landing in the UNMAPPED NACE
--     bucket (categories CBS does not attribute to a single NACE section);
--     covered_share is its complement.
--   * euets: reconciliation_drift compares the installation-level mart's
--     summed verified emissions against the EEA official stationary
--     aggregate (main activity 20-99) -- the same pair
--     assert_euets_coverage_within_eea compares. covered_share is the
--     fraction of that official aggregate the installation register
--     captures. unmapped_share has no EU ETS equivalent (every mart row
--     already carries a NACE section) and is left NULL, never a placeholder.
--   * Both are descriptive observations over existing mart/test figures --
--     never a new benchmark, never surfaced in the ESRS E1 export.

with cbs_mart_total as (
    select distinct
        year,
        national_emissions_mt_co2eq
    from {{ ref('benchmark_sector_emissions') }}
),

cbs_source_total as (
    select
        year,
        emissions_mt_co2eq as source_total_mt_co2eq
    from {{ ref('stg_cbs__emissions') }}
    where
        cbs_category_code = 'T001616'
        and gas_code = 'T001372'
        and period_status = 'Definitief'
),

cbs_unmapped as (
    select
        year,
        emissions_share as unmapped_share
    from {{ ref('benchmark_sector_emissions') }}
    where nace_section = 'UNMAPPED'
),

cbs as (
    select
        'cbs' as source,
        cbs_mart_total.year,
        (cbs_mart_total.national_emissions_mt_co2eq - cbs_source_total.source_total_mt_co2eq)
        / cbs_source_total.source_total_mt_co2eq as reconciliation_drift,
        cbs_unmapped.unmapped_share,
        1 - cbs_unmapped.unmapped_share as covered_share
    from cbs_mart_total
    inner join cbs_source_total using (year)
    left join cbs_unmapped using (year)
),

euets_mart_total as (
    select
        year,
        sum(installation_emissions_t_co2eq) as ets_total_t_co2eq
    from {{ ref('benchmark_installation_emissions') }}
    group by year
),

euets_source_total as (
    select
        year,
        value as eea_total_t_co2eq
    from {{ ref('stg_eea__ets') }}
    where
        country_code = 'NL'
        and main_activity_code = '20-99'
        and citl_information = '2. Verified emissions'
        and size = 'All sizes'
        and value is not null
),

euets as (
    select
        'euets' as source,
        euets_mart_total.year,
        (euets_mart_total.ets_total_t_co2eq - euets_source_total.eea_total_t_co2eq)
        / euets_source_total.eea_total_t_co2eq as reconciliation_drift,
        cast(null as double) as unmapped_share,
        euets_mart_total.ets_total_t_co2eq / euets_source_total.eea_total_t_co2eq as covered_share
    from euets_mart_total
    inner join euets_source_total using (year)
),

combined as (
    select * from cbs
    union all
    select * from euets
)

select
    source || '|' || year as coverage_key,
    source,
    year,
    reconciliation_drift,
    unmapped_share,
    covered_share
from combined
order by source, year
