-- Staging: typed 1:1 view of the raw CBS 83300NED observations (NAMEA air
-- emission accounts). Reads the parquet files at the snapshot directory passed
-- via the `cbs_namea_air_emissions_raw_dir` var. No rows are filtered here;
-- methodology-specific filters belong in the mart, not here.
--
-- Accounting note: 83300NED uses the residence principle (emissions
-- attributed to Dutch-resident economic activity, including Dutch operators
-- abroad and excluding non-residents on Dutch territory), unlike 85669NED and
-- the EU ETS, which use the territorial principle. The two are expected to
-- diverge for transport, shipping, and multinationals with cross-border
-- activity -- a reconciliation bridge belongs in a downstream mart as an
-- explicit note, never a tight tolerance test here.

with observations as (
    select * from read_parquet('{{ var("cbs_namea_air_emissions_raw_dir") }}/data.parquet')
),

sectors as (
    select
        identifier as code,
        title as label
    from read_parquet(
        '{{ var("cbs_namea_air_emissions_raw_dir") }}/dim_nederlandse_economie.parquet'
    )
),

measures as (
    select
        identifier as code,
        title as label
    from read_parquet('{{ var("cbs_namea_air_emissions_raw_dir") }}/dim_measures.parquet')
),

periods as (
    select
        identifier as code,
        title as label,
        status
    from read_parquet('{{ var("cbs_namea_air_emissions_raw_dir") }}/dim_perioden.parquet')
)

select
    o.nederlandse_economie as sector_code,
    sectors.label as sector_label,
    o.measure as measure_code,
    measures.label as measure_label,
    o.perioden as period_code,
    cast(trim(periods.label) as integer) as year,
    periods.status as period_status,
    o.value as value,
    o.string_value as string_value,
    o.value_attribute as value_attribute,
    -- surrogate natural key: sector | measure (pollutant/gas) | period
    o.nederlandse_economie || '|' || o.measure || '|' || o.perioden as observation_key
from observations as o
left join sectors on sectors.code = o.nederlandse_economie
left join measures on measures.code = o.measure
left join periods on periods.code = o.perioden
