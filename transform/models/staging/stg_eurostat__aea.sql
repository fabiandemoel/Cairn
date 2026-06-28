-- Staging: typed 1:1 view of the raw Eurostat AEA (Air Emissions Accounts)
-- snapshot. Reads the parquet file at the snapshot directory passed via the
-- `eurostat_aea_raw_dir` var. No rows are filtered here; NACE, pollutant,
-- and country filters are applied downstream in the mart.
--
-- Accounting note: AEA uses the residence principle (emissions attributed to
-- resident producers regardless of where they occur). CBS 85669NED and the
-- EU ETS use the territorial principle (emissions occurring within NL borders
-- regardless of producer nationality). The two will legitimately differ; the
-- Eurostat bridge dataset env_ac_aibrid_r2 documents this gap.

with raw as (
    select * from read_parquet('{{ var("eurostat_aea_raw_dir") }}/data.parquet')
)

select
    geo as country,
    nace_r2,
    airpol,
    unit,
    cast(time_period as integer) as year,
    try_cast(obs_value as double) as value_ths_t_co2eq,
    obs_flag,
    geo || '|' || nace_r2 || '|' || airpol || '|' || unit || '|' || time_period as observation_key
from raw
