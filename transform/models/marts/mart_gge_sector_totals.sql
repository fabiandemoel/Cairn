-- Mart: top-level CRF-sector greenhouse-gas totals per country and year, from the
-- Eurostat env_air_gge dataset. Grain: country × CRF sector × year.
--
-- Read/relabel only: the sector totals come directly from env_air_gge's own
-- top-level CRF rows. CRF is an IPCC/UNFCCC classification (not NACE), so this
-- mart must never be cross-walked to benchmark_country_sector_emissions as if
-- they were the same taxonomy.
--
-- TOTXMEMO ("Total excluding memo items") remains owned by
-- mart_gge_national_totals. LULUCF (CRF4) is a main CRF sector and IS included in
-- TOTXMEMO. TOTXMEMO also carries "indirect CO2" (CRF_INDCO2) and "other"
-- (CRF6), which no top-level sector does and this mart does not surface; with
-- those two, CRF1-CRF5 sum exactly to the national total (asserted to within
-- 0.001 Mt by assert_gge_sector_totals_reconcile_to_national_total). Indirect
-- CO2 is usually < 1% of the total but not always (~3% for NO in the early
-- 2000s, and dominant where LULUCF nets the total to near zero, e.g. LV 1998).
-- CRF4 can be negative --
-- LULUCF is a net carbon sink in some countries (e.g. FR) and a net source in
-- others (e.g. NL, DE) -- so sector rows may carry either sign.

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
