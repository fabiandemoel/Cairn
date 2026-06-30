-- Mart: national greenhouse-gas totals per country and year, from the Eurostat
-- env_air_gge dataset. Grain: country × year.
--
-- Uses the territorial principle (same as CBS 85669NED and EU ETS) -- NL figures
-- are a direct cross-check of the CBS national total (< 1% via
-- assert_gge_nl_total_within_cbs). CRF sector breakdowns are kept in the staging
-- layer but are not surfaced here: CRF sectors (Energy, Industrial processes,
-- Agriculture, Waste, LULUCF) are an IPCC/UNFCCC classification, not NACE, and
-- cannot be mapped to NACE without significant assumptions.
--
-- UNFCCC submission lag: the latest available year trails the current year by 1-2
-- years. As of the 2026-06-02 fixture the latest covered year is 2024.

select
    country || '|' || cast(year as varchar) as country_year_key,
    country,
    year,
    value_mio_t_co2eq as national_ghg_mt_co2eq
from {{ ref('stg_eurostat__gge') }}
where
    src_crf = 'TOTXMEMO'
    and airpol = 'GHG'
    and unit = 'MIO_T'
    and value_mio_t_co2eq is not null
order by country, year
