-- Staging: 1:1 with the raw CBS snapshot, typed, with dimension codes decoded
-- to labels and columns renamed to clear English. Reads the parquet files of
-- the snapshot directory passed via the `raw_dir` var. No rows are filtered
-- here; the climate-sector hierarchy (totals, subtotals, leaves) is resolved
-- downstream in the mart via the seed mapping.

with observations as (
    select * from read_parquet('{{ var("raw_dir") }}/data.parquet')
),

sectors as (
    select
        identifier as code,
        title as label
    from read_parquet('{{ var("raw_dir") }}/dim_klimaatsectoren.parquet')
),

gases as (
    select
        identifier as code,
        title as label
    from read_parquet('{{ var("raw_dir") }}/dim_emissies.parquet')
),

periods as (
    select
        identifier as code,
        title as label,
        status
    from read_parquet('{{ var("raw_dir") }}/dim_perioden.parquet')
)

select
    o.klimaatsectoren as cbs_category_code,
    sectors.label as cbs_category_label,
    o.emissies_naar_lucht as gas_code,
    gases.label as gas_label,
    o.perioden as period_code,
    cast(trim(periods.label) as integer) as year,
    periods.status as period_status,
    o.value as emissions_mt_co2eq,
    -- surrogate natural key for uniqueness testing (one measure in this table)
    o.klimaatsectoren || '|' || o.emissies_naar_lucht || '|' || o.perioden as observation_key
from observations as o
left join sectors on sectors.code = o.klimaatsectoren
left join gases on gases.code = o.emissies_naar_lucht
left join periods on periods.code = o.perioden
