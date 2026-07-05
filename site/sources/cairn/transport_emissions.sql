-- EU ETS aviation & maritime benchmark: per NL aircraft/maritime operator and
-- year, its verified emissions (t CO2-eq) versus its operator-type mean/median
-- over the ETS population. Source mart: benchmark_transport_emissions
-- (sources/euets/manifest.yml). Maritime entered EU ETS only from the 2024
-- compliance year, so maritime rows are sparse (or absent) before then.
select
    installation_year_key,
    year,
    installation_id,
    installation_name,
    parent_company,
    ets_activity_label,
    country_label,
    latitude,
    longitude,
    lei,
    gleif_legal_name,
    operator_type,
    installation_emissions_t_co2eq,
    allocated_total_t_co2eq,
    surrendered_allowances_t_co2eq,
    operator_type_installation_count,
    operator_type_mean_emissions_t_co2eq,
    operator_type_median_emissions_t_co2eq,
    emissions_vs_operator_type_mean,
    emissions_vs_allocated
from benchmark_transport_emissions
