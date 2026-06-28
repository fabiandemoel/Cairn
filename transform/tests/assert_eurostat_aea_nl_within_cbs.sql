-- Singular test: the NL AEA national total (nace_r2 = TOTAL, airpol = GHG,
-- unit = THS_T -- env_ac_ainah_r2 also reports the same observation in T,
-- per-capita, and index units, which must be excluded from this comparison)
-- must be within 15% of the CBS 85669NED national total (category T001616,
-- gas T001372, Definitief years). The two sources use different accounting
-- principles:
--   * AEA (env_ac_ainah_r2): residence principle -- emissions attributed to
--     Dutch-resident producers regardless of where they occur.
--   * CBS 85669NED: territorial principle -- emissions occurring within NL
--     borders regardless of the producer's nationality.
-- Eurostat's bridge dataset env_ac_aibrid_r2 quantifies this residual; it is
-- cited in README.md References as the explanation, not ingested. Measured
-- directly against the full real series (1995-2024), the residence-vs-
-- territorial gap for NL runs ~7-13% for 1995-2021, narrowing to <5.5% for
-- 2022-2024 (max observed: 13.2%, in 1996) -- the tolerance is set above
-- that historical maximum, not the much tighter 0.5% used by
-- assert_national_total_reconciles (a same-principle, same-source check).
-- Unit conversion: CBS emissions_mt_co2eq is in megatonnes; AEA
-- value_ths_t_co2eq is in thousands of tonnes; 1 Mt = 1 000 THS_T.
-- Returns zero rows on success (no overlapping year violates the tolerance).

with aea_nl as (
    select
        year,
        value_ths_t_co2eq as aea_total_ths_t
    from {{ ref('stg_eurostat__aea') }}
    where
        country = 'NL'
        and nace_r2 = 'TOTAL'
        and airpol = 'GHG'
        and unit = 'THS_T'
),

cbs_nl as (
    select
        year,
        emissions_mt_co2eq * 1000 as cbs_total_ths_t
    from {{ ref('stg_cbs__emissions') }}
    where
        cbs_category_code = 'T001616'
        and gas_code = 'T001372'
        and period_status = 'Definitief'
)

select
    aea_nl.year,
    aea_nl.aea_total_ths_t,
    cbs_nl.cbs_total_ths_t,
    abs(aea_nl.aea_total_ths_t - cbs_nl.cbs_total_ths_t)
    / cbs_nl.cbs_total_ths_t as relative_deviation
from aea_nl
inner join cbs_nl using (year)
where
    abs(aea_nl.aea_total_ths_t - cbs_nl.cbs_total_ths_t)
    / cbs_nl.cbs_total_ths_t >= 0.15
