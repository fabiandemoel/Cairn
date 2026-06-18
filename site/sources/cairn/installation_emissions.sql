-- EU ETS installation benchmark: per NL stationary installation and year, its
-- verified emissions (t CO2-eq) versus its NACE-section mean/median over the
-- ETS population. Source mart: benchmark_installation_emissions
-- (sources/euets/manifest.yml; cross-checked against sources/eea/manifest.yml).
select
    installation_year_key,
    year,
    installation_id,
    installation_name,
    nace_section,
    nace_section_label,
    installation_emissions_t_co2eq,
    sector_installation_count,
    sector_mean_emissions_t_co2eq,
    sector_median_emissions_t_co2eq,
    emissions_vs_sector_mean
from benchmark_installation_emissions
