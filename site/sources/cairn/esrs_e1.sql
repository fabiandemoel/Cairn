-- CSRD/ESRS E1 disclosure: per NL stationary EU ETS installation and reporting
-- year, its verified emissions provided as the verified basis for the
-- ESRS E1-6 "gross Scope 1 GHG emissions" datapoint, with the NACE-section
-- benchmark as context. Source mart:
-- mart_esrs_e1 (a read/relabel over benchmark_installation_emissions). The
-- downloadable, auditable bundle is produced by scripts/export_esrs_e1.py.
select
    esrs_e1_key,
    reporting_year,
    installation_id,
    installation_name,
    lei,
    gleif_legal_name,
    nace_section,
    nace_section_label,
    esrs_datapoint,
    ghg_scope,
    unit,
    gross_scope_1_ghg_emissions,
    sector_installation_count,
    sector_mean_emissions_t_co2eq,
    sector_median_emissions_t_co2eq,
    emissions_vs_sector_mean
from mart_esrs_e1
