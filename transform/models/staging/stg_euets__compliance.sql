-- Staging: 1:1 typed view of the euets.info compliance table -- verified
-- emissions (allocation/surrender/penalty) per installation per year. Raw values
-- are VARCHAR (a lossless copy of the source CSV); they are cast here. No rows
-- are filtered: future phase years carry NULL verified emissions, and the NL
-- filter and the euets-vs-chets system split are applied in the mart.
--
-- The grain is (installation, year, trading system): linked registries report
-- the same installation-year under both 'euets' and the Swiss 'chets', so the
-- trading system is part of the natural key.

with compliance as (
    select * from read_parquet('{{ var("euets_raw_dir") }}/compliance.parquet')
)

select
    installation_id,
    cast(year as integer) as year,
    reportedinsystem_id as reported_in_system,
    euetsphase as euets_phase,
    try_cast(verified as double) as verified_emissions_t_co2eq,
    try_cast(allocatedtotal as double) as allocated_total,
    try_cast(surrendered as double) as surrendered,
    try_cast(penalty as double) as excess_emissions_penalty_eur,
    -- surrogate natural key: one compliance row per installation-year-system
    installation_id || '|' || year || '|' || reportedinsystem_id as compliance_key
from compliance
