-- Mart: NL residence-principle CO2 emissions (CBS NAMEA, 83300NED) per NACE
-- section and year, presented side by side with the territorial-principle
-- total GHG CO2-eq figure (CBS 85669NED, benchmark_sector_emissions) -- a
-- provenance/methodology bridge, never a reconciliation.
--
-- Methodology:
--   * Headline NAMEA measure = CO2 (matched via measure_label ilike
--     '%kooldioxide%'), because 83300NED's measure dimension carries no
--     pre-aggregated "total GHG in CO2-equivalent" figure analogous to
--     85669NED's T001372. The bridge therefore differs in gas scope (CO2 only
--     vs total GHG CO2-eq) *in addition to* attribution principle -- both are
--     real, documented divergences, never reconciled away or tested to a
--     tight tolerance.
--   * CBS NAMEA values carry no stated unit in the measure dimension; this
--     mart assumes millions of kg (kilotonnes), consistent with CBS's other
--     emission accounts, and divides by 1,000 for megatonnes so the two sides
--     are expressed in comparable units.
--   * Final figures only: period_status <> 'Definitief' is excluded,
--     mirroring benchmark_sector_emissions.
--   * Sector codes are mapped to NACE sections via the reviewed seed
--     sector_mapping_cbs_namea. Only leaf categories (seed: aggregate = false)
--     are summed per sector-year; the seed's "Totale Nederlandse economie"
--     aggregate row is read directly as the official national
--     residence-principle total rather than re-summed from leaves.
--   * The territorial side is read straight from benchmark_sector_emissions
--     (already NACE-mapped, T001372 total GHG CO2-eq) -- no logic duplicated.
--   * FULL OUTER JOIN on (nace_section, year): a sector-year present on only
--     one side surfaces with NULLs on the other, rather than being dropped.

with namea_co2 as (
    select *
    from {{ ref('stg_cbs_namea__air_emissions') }}
    where
        measure_label ilike '%kooldioxide%'
        and period_status = 'Definitief'
        and value is not null
),

mapping as (
    select * from {{ ref('sector_mapping_cbs_namea') }}
),

leaves as (
    select
        namea_co2.year,
        coalesce(mapping.nace_section, 'UNMAPPED') as nace_section,
        coalesce(
            mapping.nace_label, 'Unmapped / not attributable to a single NACE section'
        ) as nace_label,
        namea_co2.value
    from namea_co2
    inner join mapping on mapping.namea_sector_code = namea_co2.sector_code
    where not mapping.aggregate
),

residence_by_sector as (
    select
        year,
        nace_section,
        max(nace_label) as nace_label,
        sum(value) / 1000 as residence_co2_emissions_mt
    from leaves
    group by year, nace_section
),

national_residence as (
    select
        namea_co2.year,
        namea_co2.value / 1000 as national_residence_co2_emissions_mt
    from namea_co2
    inner join mapping on mapping.namea_sector_code = namea_co2.sector_code
    where mapping.aggregate
),

territorial as (
    select
        year,
        nace_section,
        nace_label as territorial_nace_label,
        sector_emissions_mt_co2eq as territorial_ghg_emissions_mt_co2eq,
        national_emissions_mt_co2eq as national_territorial_ghg_emissions_mt_co2eq
    from {{ ref('benchmark_sector_emissions') }}
)

select
    coalesce(residence_by_sector.nace_section, territorial.nace_section)
    || '|' || coalesce(residence_by_sector.year, territorial.year) as bridge_key,
    coalesce(residence_by_sector.year, territorial.year) as year,
    coalesce(residence_by_sector.nace_section, territorial.nace_section) as nace_section,
    coalesce(residence_by_sector.nace_label, territorial.territorial_nace_label) as nace_label,
    residence_by_sector.residence_co2_emissions_mt,
    national_residence.national_residence_co2_emissions_mt,
    territorial.territorial_ghg_emissions_mt_co2eq,
    territorial.national_territorial_ghg_emissions_mt_co2eq
from residence_by_sector
full outer join territorial
    on
        residence_by_sector.nace_section = territorial.nace_section
        and residence_by_sector.year = territorial.year
left join national_residence
    on coalesce(residence_by_sector.year, territorial.year) = national_residence.year
order by year, nace_section
