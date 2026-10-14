-- Singular test: the top-level GGE CRF-sector rows, plus the two TOTXMEMO
-- components no top-level sector carries, should sum to the national total.
--
-- env_air_gge's TOTXMEMO ("Total excluding memo items") is the national total.
-- Memo items are the international aviation/shipping bunkers and biomass-CO2 rows
-- (CRF1D*), which are excluded by definition. LULUCF (CRF4) is a main CRF sector
-- and IS included in TOTXMEMO.
--
-- TOTXMEMO also carries two components that are not attributed to a top-level
-- CRF sector and that mart_gge_sector_totals does not surface:
--   * "Indirect CO2" (CRF_INDCO2) -- NOT always small: on the full release it
--     reaches ~2.8% of the national total (NO, early 2000s) and dominates
--     countries whose net total is near zero because LULUCF offsets almost all
--     emissions (LV 1998: total 0.11 Mt, indirect CO2 0.03 Mt).
--   * "Other" (CRF6) -- zero for almost every country-year, small where not.
-- So the identity checked here is
--     CRF1 + CRF2 + CRF3 + CRF4 + CRF5 + CRF_INDCO2 + CRF6 = TOTXMEMO
-- which holds on the full 2026-06-02 release to within 2e-5 Mt (rounding of
-- the published 5-decimal values) for every country-year. The residual
-- components are read from staging, never synthesised; a NULL cell counts as 0.
--
-- Tolerance is ABSOLUTE (0.001 Mt = 1 kt), not relative: a relative check
-- explodes for near-zero net totals (LV) and would also hide an absolute error
-- in large countries. 1 kt is ~50x the observed rounding noise and orders of
-- magnitude below a unit error or a dropped sector.
--
-- Coverage guard: a FULL OUTER JOIN on (country, year) so a country-year present
-- on only one side is surfaced as a failing row -- an inner join would silently
-- drop missing sector coverage or a missing national total.
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

unallocated as (
    select
        country,
        year,
        coalesce(sum(value_mio_t_co2eq), 0) as unallocated_mt
    from {{ ref('stg_eurostat__gge') }}
    where
        src_crf in ('CRF_INDCO2', 'CRF6')
        and airpol = 'GHG'
        and unit = 'MIO_T'
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
        coalesce(u.unallocated_mt, 0) as unallocated_mt,
        n.national_ghg_mt_co2eq,
        abs(
            s.sector_sum_mt + coalesce(u.unallocated_mt, 0)
            - n.national_ghg_mt_co2eq
        ) as absolute_deviation_mt
    from sector_totals as s
    full outer join national_totals as n
        on s.country = n.country and s.year = n.year
    left join unallocated as u
        on
            coalesce(s.country, n.country) = u.country
            and coalesce(s.year, n.year) = u.year
)

select
    country,
    year,
    national_ghg_mt_co2eq,
    sector_sum_mt,
    unallocated_mt,
    absolute_deviation_mt
from reconciled
where
    sector_sum_mt is null            -- national total with no CRF-sector rows
    or national_ghg_mt_co2eq is null  -- CRF-sector rows with no national total
    or absolute_deviation_mt >= 0.001
