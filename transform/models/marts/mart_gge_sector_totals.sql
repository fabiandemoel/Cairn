-- Mart: top-level CRF-sector greenhouse-gas totals per country and year, from the
-- Eurostat env_air_gge dataset. Grain: country × CRF sector × year.
--
-- Read/relabel only: the sector totals come directly from env_air_gge's own
-- top-level CRF rows. CRF is an IPCC/UNFCCC classification (not NACE), so this
-- mart must never be cross-walked to benchmark_country_sector_emissions as if
-- they were the same taxonomy.
--
-- TOTXMEMO remains owned by mart_gge_national_totals. LULUCF (CRF4) is surfaced
-- here for completeness but is excluded from TOTXMEMO, so reconciliation tests
-- must subtract it before comparing sector sums to the national total.

select
    country || '|' || src_crf || '|' || cast(year as varchar) as country_crf_year_key,
    country,
    src_crf as crf_sector_code,
    case src_crf
        when 'CRF1' then 'Energy'
        when 'CRF2' then 'Industrial processes and product use'
        when 'CRF3' then 'Agriculture'
        when 'CRF4' then 'Land use, land-use change and forestry (LULUCF)'
        when 'CRF5' then 'Waste'
    end as crf_sector_label,
    year,
    value_mio_t_co2eq as sector_ghg_mt_co2eq
from {{ ref('stg_eurostat__gge') }}
where
    src_crf in ('CRF1', 'CRF2', 'CRF3', 'CRF4', 'CRF5')
    and airpol = 'GHG'
    and unit = 'MIO_T'
    and value_mio_t_co2eq is not null
order by country, year, crf_sector_code
