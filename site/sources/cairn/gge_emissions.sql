-- Eurostat env_air_gge: national GHG totals per country and year.
-- Territorial principle: same accounting base as CBS 85669NED and EU ETS,
-- so NL figures are a direct cross-check of the CBS national total.
-- Source mart: mart_gge_national_totals (sources/eurostat_gge/manifest.yml).
select
    country_year_key,
    country,
    year,
    national_ghg_mt_co2eq
from mart_gge_national_totals
