-- Singular test: the NL AEA national total (nace_r2 = TOTAL, airpol = GHG)
-- must be within 5% of the CBS 85669NED national total (category T001616,
-- gas T001372, Definitief years). The tolerance is wider than the CBS
-- internal reconciliation check (0.5%) because the two sources use different
-- accounting principles:
--   * AEA (env_ac_ainah_r2): residence principle -- emissions attributed to
--     Dutch-resident producers regardless of where they occur.
--   * CBS 85669NED: territorial principle -- emissions occurring within NL
--     borders regardless of the producer's nationality.
-- Eurostat's bridge dataset env_ac_aibrid_r2 documents this residual; it is
-- cited in README.md References as the explanation, not ingested.
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
    / cbs_nl.cbs_total_ths_t >= 0.05
