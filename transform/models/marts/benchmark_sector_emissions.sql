-- Mart: greenhouse-gas emissions per NACE section and year, with each sector's
-- share of the national total. Math is deliberately simple and explicit.
--
-- Methodology:
--   * Headline gas = total greenhouse gases in CO2-equivalent (code T001372).
--   * Final figures only: provisional CBS years (period_status <> 'Definitief')
--     are excluded because their detailed sector breakdown is not yet complete.
--   * The CBS climate-sector dimension is a hierarchy of totals, subtotals and
--     leaves. Only leaf categories (seed: aggregate = false) are summed, so the
--     national total is partitioned exactly once with no double counting.
--   * Categories that do not map to a single NACE section (households, land
--     use, on-road/rail/water/air transport, the CBS G-U services aggregate)
--     are bucketed as 'UNMAPPED' but still counted, so the national total
--     reconciles with the source (see the singular reconciliation test).

with emissions as (
    select *
    from {{ ref('stg_cbs__emissions') }}
    where
        gas_code = 'T001372'
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
        emissions.cbs_category_code,
        emissions.emissions_mt_co2eq
    from emissions
    inner join mapping on mapping.cbs_category_code = emissions.cbs_category_code
    where not mapping.aggregate
),

by_sector as (
    select
        year,
        nace_section,
        max(nace_label) as nace_label,
        sum(emissions_mt_co2eq) as sector_emissions_mt_co2eq,
        count(distinct cbs_category_code) as source_category_count
    from leaves
    group by year, nace_section
),

national as (
    select
        year,
        sum(emissions_mt_co2eq) as national_emissions_mt_co2eq
    from leaves
    group by year
)

select
    by_sector.nace_section || '|' || by_sector.year as sector_year_key,
    by_sector.year,
    by_sector.nace_section,
    by_sector.nace_label,
    by_sector.sector_emissions_mt_co2eq,
    by_sector.source_category_count,
    national.national_emissions_mt_co2eq,
    by_sector.sector_emissions_mt_co2eq / national.national_emissions_mt_co2eq as emissions_share
from by_sector
inner join national using (year)
order by by_sector.year, by_sector.nace_section
