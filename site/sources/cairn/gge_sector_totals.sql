-- Eurostat env_air_gge: top-level CRF-sector greenhouse-gas totals per country
-- and year.
-- Territorial principle: same accounting base as CBS 85669NED and EU ETS.
-- CRF is an IPCC/UNFCCC classification (not NACE); use this source for CRF-sector
-- peer benchmarking only, not for NACE crosswalks.
-- Source mart: mart_gge_sector_totals (sources/eurostat_gge/manifest.yml).
select
    country_crf_year_key,
    country,
    crf_sector_code,
    crf_sector_label,
    year,
    sector_ghg_mt_co2eq
from mart_gge_sector_totals
