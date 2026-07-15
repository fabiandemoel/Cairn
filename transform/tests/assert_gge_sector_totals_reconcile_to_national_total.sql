-- Singular test: the top-level GGE CRF-sector rows should sum (LULUCF included)
-- to the national total, up to the small "indirect CO2" residual.
--
-- env_air_gge's TOTXMEMO ("Total excluding memo items") is the national total.
-- Memo items are the international aviation/shipping bunkers and biomass-CO2 rows
-- (CRF1D*), which are excluded by definition. LULUCF (CRF4) is a main CRF sector
-- and IS included in TOTXMEMO -- so the five top-level sectors CRF1-CRF5 (LULUCF
-- included) are expected to sum to TOTXMEMO, not to differ from it.
--
-- The one component in TOTXMEMO that is not attributed to a top-level CRF sector
-- is "Indirect CO2" (CRF_INDCO2), which this mart does not surface. It is small
-- (< 1% of the national total for every observed country-year; the largest gap
-- in the current release is ~0.74% for DK), so the sum of CRF1-CRF5 falls just
-- short of TOTXMEMO by that residual. The tolerance is set at 1.5% -- wide enough
-- to absorb the indirect-CO2 residual across the full country set, tight enough
-- to still catch a unit error or a dropped sector (which would be orders of
-- magnitude).
--
-- Coverage guard: a FULL OUTER JOIN on (country, year) so a country-year present
-- on only one side is surfaced as a failing row -- an inner join would silently
-- drop missing sector coverage or a missing national total, defeating the point
-- of the guardrail. The division is guarded with nullif() so a national total of
-- 0 (which would itself be anomalous) fails loudly rather than erroring.
--
-- Returns zero rows on success.

with sector_totals as (
    select
        country,
        year,
        sum(sector_ghg_mt_co2eq) as sector_sum_mt
    from {{ ref('mart_gge_sector_totals') }}
    group by country, year
),

national_totals as (
    select
        country,
        year,
        national_ghg_mt_co2eq
    from {{ ref('mart_gge_national_totals') }}
),

reconciled as (
    select
        coalesce(s.country, n.country) as country,
        coalesce(s.year, n.year) as year,
        s.sector_sum_mt,
        n.national_ghg_mt_co2eq,
        abs(s.sector_sum_mt - n.national_ghg_mt_co2eq)
        / nullif(n.national_ghg_mt_co2eq, 0) as relative_deviation
    from sector_totals as s
    full outer join national_totals as n
        on s.country = n.country and s.year = n.year
)

select
    country,
    year,
    national_ghg_mt_co2eq,
    sector_sum_mt,
    relative_deviation
from reconciled
where
    sector_sum_mt is null            -- national total with no CRF-sector rows
    or national_ghg_mt_co2eq is null  -- CRF-sector rows with no national total
    or relative_deviation is null     -- national total was 0 (nullif guard)
    or relative_deviation >= 0.015
