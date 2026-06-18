-- Staging: typed view of the EEA EU ETS aggregate (country x main activity x
-- year x CITL category x size). Two real-source quirks are handled here so the
-- grain is clean for the coverage cross-check:
--   * The `year` column mixes per-year values with trading-period aggregate
--     labels ('Total Nth trading period (...)'). Those are sums over years
--     (they would double-count) and are not numeric, so only true per-year
--     rows are kept; `year` then casts cleanly to integer.
--   * The bulk carries a known duplicate: Czechia's allocated-allowances at the
--     20-99 aggregate appears twice (a spurious 0 alongside the real value).
--     Exact-grain duplicates are collapsed deterministically, keeping the
--     larger value. The raw `value` is VARCHAR (cast to double; NULL if blank).

with raw_ets as (
    select * from read_parquet('{{ var("eea_raw_dir") }}/data.parquet')
),

typed as (
    select
        country_code,
        main_activity_code,
        citl_information,
        try_cast(year as integer) as year,
        size,
        try_cast(value as double) as value,
        unit
    from raw_ets
    -- drop the non-numeric trading-period aggregate rows
    where try_cast(year as integer) is not null
),

keyed as (
    select
        *,
        -- surrogate natural key for the full grain
        concat_ws(
            '|', country_code, main_activity_code, citl_information, year, size
        ) as observation_key
    from typed
)

select
    country_code,
    main_activity_code,
    citl_information,
    year,
    size,
    value,
    unit,
    observation_key
from keyed
-- collapse the known EEA duplicate (CZ 20-99 allocated allowances), keeping the
-- larger value so the spurious 0 row is dropped
qualify row_number() over (
    partition by observation_key order by value desc nulls last
) = 1
