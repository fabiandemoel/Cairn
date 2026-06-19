-- Mart: ESRS E1-6 disclosure export -- gross Scope 1 greenhouse-gas emissions
-- per NL stationary EU ETS installation and reporting year, with the NACE-
-- section ETS benchmark carried alongside as comparative context.
--
-- This is a read/relabel layer on top of benchmark_installation_emissions: it
-- does NOT recompute emissions. It reframes the already-verified EU ETS figure
-- as the ESRS E1-6 datapoint "gross Scope 1 GHG emissions". EU ETS verified
-- emissions are the regulated Scope 1 figure for a covered installation
-- (combustion + process emissions at the site). Scope 2 and Scope 3 are out of
-- source scope -- Cairn has no basis to compute them, so they are deliberately
-- not emitted rather than filled with placeholder zeros (no invented figures).
--
-- Scope / methodology inherited from benchmark_installation_emissions:
--   * NL registry, 'euets' trading system, stationary installations only,
--     verified emissions only.
--   * Grain: one row per installation per reporting year.
--   * Unit is tonnes CO2-equivalent, native to the EUTL.
-- The export grain is the installation (the regulated reporting boundary); an
-- undertaking that operates several installations would aggregate these rows.

with benchmark as (
    select * from {{ ref('benchmark_installation_emissions') }}
)

select
    installation_year_key as esrs_e1_key,
    year as reporting_year,
    installation_id,
    installation_name,
    nace_section,
    nace_section_label,
    -- ESRS E1-6 self-describing datapoint metadata, so the export stands alone.
    'E1-6' as esrs_datapoint,
    'Scope 1' as ghg_scope,
    't CO2eq' as unit,
    installation_emissions_t_co2eq as gross_scope_1_ghg_emissions,
    -- Comparative context: the NACE-section ETS benchmark for the same year.
    sector_installation_count,
    sector_mean_emissions_t_co2eq,
    sector_median_emissions_t_co2eq,
    emissions_vs_sector_mean
from benchmark
order by reporting_year asc, nace_section asc, gross_scope_1_ghg_emissions desc
