-- Staging: 1:1 typed view of the EEA EU ETS aggregate (country x main activity
-- x year x CITL category x size). The raw `value` is VARCHAR because the source
-- column mixes numbers with period labels; it is cast to double where numeric
-- (labels become NULL). No rows are filtered; the mart selects the verified-
-- emission category and the NL rows it needs as the benchmark denominator.

with ets as (
    select * from read_parquet('{{ var("eea_raw_dir") }}/data.parquet')
)

select
    country_code,
    main_activity_code,
    citl_information,
    cast(year as integer) as year,
    size,
    try_cast(value as double) as value,
    unit,
    -- surrogate natural key for the full grain
    concat_ws(
        '|', country_code, main_activity_code, citl_information, year, size
    ) as observation_key
from ets
