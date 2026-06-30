-- Staging: typed 1:1 view of the raw Eurostat env_air_gge snapshot.
-- Reads the parquet file at the snapshot directory passed via the
-- `eurostat_gge_raw_dir` var. No rows are filtered here; CRF-sector,
-- country, and pollutant filters are applied downstream in tests and marts.
--
-- Accounting note: env_air_gge uses the territorial principle (emissions
-- physically occurring within national borders), the same as CBS 85669NED
-- and the EU ETS. NL national totals (src_crf = 'TOTXMEMO', airpol = 'GHG')
-- are therefore a direct cross-check of the CBS national total without any
-- residence-principle correction.
--
-- CRF sectors (src_crf) are IPCC Common Reporting Format sectors -- not NACE
-- economic sectors. Do not attempt a CRF-to-NACE mapping in this layer or
-- downstream. National totals (src_crf = 'TOTXMEMO') are the only grain used
-- for the CBS cross-check; sector-level CRF rows are kept raw.

with raw as (
    select * from read_parquet('{{ var("eurostat_gge_raw_dir") }}/data.parquet')
)

select
    geo as country,
    src_crf,
    airpol,
    unit,
    cast(time_period as integer) as year,
    try_cast(obs_value as double) as value_mio_t_co2eq,
    obs_flag,
    geo || '|' || src_crf || '|' || airpol || '|' || unit || '|' || time_period as observation_key
from raw
