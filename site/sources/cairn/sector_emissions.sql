-- CBS sector benchmark: GHG emissions (Mt CO2-eq) and share of the national
-- total per NACE section and year. Final (Definitief) CBS years only.
-- Source mart: benchmark_sector_emissions (sources/cbs/manifest.yml).
select
    sector_year_key,
    nace_section,
    year,
    sector_emissions_mt_co2eq,
    emissions_share
from benchmark_sector_emissions
