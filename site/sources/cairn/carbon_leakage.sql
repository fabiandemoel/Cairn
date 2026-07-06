-- EU ETS carbon leakage exposure: per NL stationary installation and year,
-- whether its NACE code is transcribed in the reviewed carbon_leakage_list
-- seed (Commission Delegated Decision (EU) 2019/708, OJ L 120, 8.5.2019, p.
-- 20, Annex points 1-3) as exposed to carbon leakage risk in ETS Phase 4
-- (2021-2030). A policy-context label only -- never a free-allocation
-- entitlement. Source mart: benchmark_installation_emissions
-- (transform/seeds/carbon_leakage_list.csv).
select
    installation_year_key,
    installation_id,
    installation_name,
    nace_section,
    nace_section_label,
    year,
    carbon_leakage_exposed,
    carbon_leakage_sector_description,
    carbon_leakage_oj_citation
from benchmark_installation_emissions
