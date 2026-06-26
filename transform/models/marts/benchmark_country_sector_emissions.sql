-- Mart: cross-country greenhouse-gas emissions per NACE section and year,
-- with each sector's share of that country's national total.
-- Grain: country × nace_section × year.
--
-- Methodology:
--   * Headline pollutant = total GHG in CO2-equivalent (airpol = 'GHG').
--   * 'TOTAL' rows are excluded; per-section rows sum to the national total.
--   * Eurostat-native aggregates M_N (Sections M + N combined) and R_S
--     (R + S combined) are kept as-is -- the AEA publishes at this level
--     and they cannot be split without a secondary source.
--   * Unit is THS_T (thousands of tonnes CO2-equivalent) throughout.
--   * AEA uses the residence principle; NL figures will legitimately differ
--     from CBS 85669NED (territorial) and EU ETS (territorial). See the
--     bridge dataset env_ac_aibrid_r2 (cited in README) for the quantified
--     gap and the reconciliation test for the CI check.

with ghg as (
    select
        country,
        nace_r2 as nace_section,
        year,
        value_ths_t_co2eq
    from {{ ref('stg_eurostat__aea') }}
    where
        airpol = 'GHG'
        and nace_r2 <> 'TOTAL'
        and value_ths_t_co2eq is not null
),

national as (
    select
        country,
        year,
        sum(value_ths_t_co2eq) as national_emissions_ths_t_co2eq
    from ghg
    group by country, year
)

select
    ghg.country || '|' || ghg.nace_section || '|' || cast(ghg.year as varchar)
        as country_nace_year_key,
    ghg.country,
    ghg.nace_section,
    ghg.year,
    ghg.value_ths_t_co2eq as emissions_ths_t_co2eq,
    national.national_emissions_ths_t_co2eq,
    ghg.value_ths_t_co2eq / national.national_emissions_ths_t_co2eq as emissions_share
from ghg
inner join national using (country, year)
order by ghg.country, ghg.year, ghg.nace_section
