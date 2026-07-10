-- CBS GHG composition by gas type: per NACE section, gas, and year, the
-- CO2-eq emissions and that gas's share of the sector-year total.
-- Final (Definitief) CBS years only.
-- Source mart: mart_sector_gas_composition (sources/cbs/manifest.yml).
select
    sector_gas_year_key,
    year,
    nace_section,
    nace_label,
    gas_code,
    gas_label,
    emissions_mt_co2eq,
    gas_share
from mart_sector_gas_composition
