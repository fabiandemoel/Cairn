-- Mart: GHG composition by constituent gas, per NACE section and year.
-- Grain: nace_section × gas_code × year.
--
-- Methodology:
--   * Four constituent gases (CBS's own CO2-eq values): A044109 CO2,
--     A044110 N2O, A044107 CH4, A052484 F-gases.
--   * Final figures only: period_status = 'Definitief' (mirrors
--     benchmark_sector_emissions).
--   * Same leaf/aggregate hierarchy resolution and sector_mapping_cbs seed
--     as benchmark_sector_emissions — don't diverge the two.
--   * Categories that don't map to a NACE section bucket as 'UNMAPPED',
--     same as benchmark_sector_emissions.

with emissions as (
    select *
    from {{ ref('stg_cbs__emissions') }}
    where
        gas_code in ('A044109', 'A044110', 'A044107', 'A052484')
        and period_status = 'Definitief'
        and emissions_mt_co2eq is not null
),

mapping as (
    select * from {{ ref('sector_mapping_cbs') }}
),

leaves as (
    select
        emissions.year,
        coalesce(mapping.nace_section, 'UNMAPPED') as nace_section,
        coalesce(
            mapping.nace_label, 'Unmapped / not attributable to a single NACE section'
        ) as nace_label,
        emissions.gas_code,
        emissions.gas_label,
        emissions.cbs_category_code,
        emissions.emissions_mt_co2eq
    from emissions
    inner join mapping on mapping.cbs_category_code = emissions.cbs_category_code
    where not mapping.aggregate
),

by_sector_gas as (
    select
        year,
        nace_section,
        max(nace_label) as nace_label,
        gas_code,
        max(gas_label) as gas_label,
        sum(emissions_mt_co2eq) as emissions_mt_co2eq
    from leaves
    group by year, nace_section, gas_code
),

sector_total as (
    select
        year,
        nace_section,
        sum(emissions_mt_co2eq) as sector_total_all_gases_mt_co2eq
    from by_sector_gas
    group by year, nace_section
)

select
    by_sector_gas.nace_section || '|' || by_sector_gas.gas_code || '|' || by_sector_gas.year
        as sector_gas_year_key,
    by_sector_gas.year,
    by_sector_gas.nace_section,
    by_sector_gas.nace_label,
    by_sector_gas.gas_code,
    by_sector_gas.gas_label,
    by_sector_gas.emissions_mt_co2eq,
    sector_total.sector_total_all_gases_mt_co2eq,
    by_sector_gas.emissions_mt_co2eq / sector_total.sector_total_all_gases_mt_co2eq as gas_share
from by_sector_gas
inner join sector_total using (year, nace_section)
order by by_sector_gas.year, by_sector_gas.nace_section, by_sector_gas.gas_code
