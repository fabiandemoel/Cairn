-- NL residence-principle CO2 emissions (CBS NAMEA, 83300NED) next to the
-- territorial-principle total GHG CO2-eq figure (CBS 85669NED), per NACE
-- section and year -- a provenance/methodology bridge, not a reconciliation.
-- Source mart: mart_namea_bridge (sources/cbs_namea/manifest.yml).
select
    bridge_key,
    year,
    nace_section,
    nace_label,
    residence_co2_emissions_mt,
    national_residence_co2_emissions_mt,
    territorial_ghg_emissions_mt_co2eq,
    national_territorial_ghg_emissions_mt_co2eq
from mart_namea_bridge
