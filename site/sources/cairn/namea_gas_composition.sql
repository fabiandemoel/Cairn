-- CBS NAMEA (83300NED) GHG composition by gas type, residence principle: per
-- NACE section, gas, and year, Mt and that gas's share of the sector-year
-- total. Final (Definitief) CBS years only. Composition breakdown, never a
-- reconciliation against sector_gas_composition's territorial-principle figures
-- (see /namea-bridge).
-- Source mart: mart_namea_gas_composition (sources/cbs_namea/manifest.yml).
select
    namea_gas_year_key,
    year,
    nace_section,
    nace_label,
    gas_code,
    gas_label,
    emissions_mt,
    sector_total_all_gases_mt,
    gas_share
from mart_namea_gas_composition
