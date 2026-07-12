-- Singular test: the top-level GGE CRF-sector rows should reconcile to the
-- national total once the surfaced LULUCF row (CRF4) is removed.
--
-- env_air_gge's TOTXMEMO row excludes international aviation and shipping memo
-- items and also excludes LULUCF. This mart surfaces CRF1-CRF5 for peer
-- benchmarking, so the sector sum is not expected to equal TOTXMEMO directly.
-- Instead we compare the non-LULUCF sector sum to mart_gge_national_totals.
--
-- Because both sides come from the same dataset/unit and the mart is read/relabel
-- only, any residual gap should be at most rounding noise. The tolerance is 0.5%.
--
-- Returns zero rows on success.

with sector_totals as (
    select
        country,
        year,
        sum(
            case
                when crf_sector_code <> 'CRF4' then sector_ghg_mt_co2eq
                else 0
            end
        ) as non_lulucf_sector_sum_mt,
        max(
            case
                when crf_sector_code = 'CRF4' then sector_ghg_mt_co2eq
            end
        ) as lulucf_mt
    from {{ ref('mart_gge_sector_totals') }}
    group by 1, 2
),

national_totals as (
    select
        country,
        year,
        national_ghg_mt_co2eq
    from {{ ref('mart_gge_national_totals') }}
)

select
    s.country,
    s.year,
    n.national_ghg_mt_co2eq,
    s.non_lulucf_sector_sum_mt,
    s.lulucf_mt,
    abs(s.non_lulucf_sector_sum_mt - n.national_ghg_mt_co2eq)
    / n.national_ghg_mt_co2eq as relative_deviation
from sector_totals as s
inner join national_totals as n
    using (country, year)
where
    abs(s.non_lulucf_sector_sum_mt - n.national_ghg_mt_co2eq)
    / n.national_ghg_mt_co2eq >= 0.005
