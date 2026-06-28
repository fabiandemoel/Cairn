-- Mart: cross-country greenhouse-gas emissions per NACE section and year,
-- with each sector's share of that country's national total.
-- Grain: country × nace_section × year.
--
-- Methodology:
--   * Headline pollutant = total GHG in CO2-equivalent (airpol = 'GHG').
--   * Unit is restricted to THS_T (thousands of tonnes CO2-equivalent) --
--     env_ac_ainah_r2 also reports the same observations in T, per-capita,
--     and index units, which must be excluded here.
--   * nace_r2 is restricted to the 21 NACE Rev.2 section letters (A-U).
--     env_ac_ainah_r2 also publishes division-level breakdowns (e.g. A01,
--     C20), household/aggregate rows (HH, TOTAL_HH, G-U_X_H) and the
--     national TOTAL; mixing those into a per-section sum double-counts,
--     so only the 21 mutually-exclusive section codes are kept.
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
        and unit = 'THS_T'
        and nace_r2 in (
            'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
            'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U'
        )
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
