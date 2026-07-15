-- Mart: NAMEA (83300NED) residence-principle GHG composition by constituent gas,
-- per NACE section and year. Grain: nace_section × gas_code × year.
--
-- Methodology:
--   * Four constituent gases filtered by measure_label pattern, because
--     stg_cbs_namea__air_emissions's measure codes carry an opaque version
--     suffix (fixture: A044109_2, A044110_2) that diverges from bare CBS codes.
--     Match by label instead: CO2 ('%kooldioxide%'), N2O
--     ('%distikstofoxide%'), CH4 ('%methaan%'), F-gases ('%fluor%').
--   * CBS NAMEA values carry no stated unit in the measure dimension; this
--     mart assumes millions of kg (kilotonnes), consistent with CBS's other
--     emission accounts, and divides by 1,000 for megatonnes so the
--     composition is expressed in the same units as mart_sector_gas_composition.
--   * Final figures only: period_status = 'Definitief' (mirrors
--     mart_namea_bridge and benchmark_sector_emissions).
--   * Same leaf/aggregate hierarchy resolution and sector_mapping_cbs_namea seed
--     as mart_namea_bridge — do not diverge the two.
--   * Categories that don't map to a NACE section bucket as 'UNMAPPED',
--     same as mart_namea_bridge.
--   * Composition breakdown, never a reconciliation against
--     mart_sector_gas_composition's territorial-principle figures —
--     residence vs territorial attribution diverges per-gas the same way
--     it diverges in aggregate.

with namea_gases as (
    select *
    from {{ ref('stg_cbs_namea__air_emissions') }}
    where
        (
            measure_label ilike '%kooldioxide%'
            or measure_label ilike '%distikstofoxide%'
            or measure_label ilike '%methaan%'
            or measure_label ilike '%fluor%'
        )
        and period_status = 'Definitief'
        and value is not null
),

mapping as (
    select * from {{ ref('sector_mapping_cbs_namea') }}
),

leaves as (
    select
        namea_gases.year,
        coalesce(mapping.nace_section, 'UNMAPPED') as nace_section,
        coalesce(
            mapping.nace_label, 'Unmapped / not attributable to a single NACE section'
        ) as nace_label,
        namea_gases.measure_code as gas_code,
        namea_gases.measure_label as gas_label,
        namea_gases.value
    from namea_gases
    inner join mapping on mapping.namea_sector_code = namea_gases.sector_code
    where not mapping.aggregate
),

by_sector_gas as (
    select
        year,
        nace_section,
        max(nace_label) as nace_label,
        gas_code,
        max(gas_label) as gas_label,
        sum(value) / 1000 as emissions_mt
    from leaves
    group by year, nace_section, gas_code
),

sector_total as (
    select
        year,
        nace_section,
        sum(emissions_mt) as sector_total_all_gases_mt
    from by_sector_gas
    group by year, nace_section
)

select
    by_sector_gas.nace_section || '|' || by_sector_gas.gas_code || '|' || by_sector_gas.year
        as namea_gas_year_key,
    by_sector_gas.year,
    by_sector_gas.nace_section,
    by_sector_gas.nace_label,
    by_sector_gas.gas_code,
    by_sector_gas.gas_label,
    by_sector_gas.emissions_mt,
    sector_total.sector_total_all_gases_mt,
    by_sector_gas.emissions_mt / sector_total.sector_total_all_gases_mt as gas_share
from by_sector_gas
inner join sector_total using (year, nace_section)
order by by_sector_gas.year, by_sector_gas.nace_section, by_sector_gas.gas_code
