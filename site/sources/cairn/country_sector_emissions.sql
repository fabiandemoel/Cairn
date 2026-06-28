-- Eurostat Air Emissions Accounts (AEA, env_ac_ainah_r2): GHG emissions in
-- thousands of tonnes CO2-eq per country, NACE section, and year.
-- Residence principle: emissions attributed to the country of the producing
-- entity, not where production physically occurs.
-- Source mart: benchmark_country_sector_emissions (sources/eurostat/manifest.yml).
select
    country_nace_year_key,
    country,
    nace_section,
    year,
    emissions_ths_t_co2eq,
    national_emissions_ths_t_co2eq,
    emissions_share
from benchmark_country_sector_emissions
