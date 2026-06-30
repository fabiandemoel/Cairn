-- Singular test: the NL GGE national total (src_crf = 'TOTXMEMO', airpol = 'GHG',
-- unit = 'MIO_T') must be within 10% of the CBS 85669NED national total (category
-- T001616, gas T001372, Definitief years).
--
-- Both sources use the territorial principle (emissions physically occurring within
-- NL borders), so a direct comparison is valid without a residence-principle
-- correction. Unit: MIO_T (million tonnes = megatonnes), the same unit as CBS
-- emissions_mt_co2eq -- no conversion needed.
--
-- env_air_gge derives from UNFCCC national inventory submissions; CBS 85669NED is
-- CBS's own estimate from the same underlying RIVM/UNFCCC inventory, but CBS
-- revises its estimates more frequently than the annual UNFCCC submission cycle.
-- For recently-revised CBS years the gap can reach ~7% (observed for 2024:
-- CBS 144.4 Mt vs GGE 154.2 Mt), so the tolerance is set at 10% -- wide enough
-- to accommodate submission-timing and revision-cycle differences while still
-- catching unit errors or pipeline mistakes (which would show as orders-of-magnitude
-- differences).
--
-- Only years present in both sources AND final (Definitief) in CBS are tested --
-- the INNER JOIN ensures this automatically.
--
-- Returns zero rows on success (no overlapping year violates the tolerance).

with gge_nl as (
    select
        year,
        value_mio_t_co2eq as gge_total_mt
    from {{ ref('stg_eurostat__gge') }}
    where
        country = 'NL'
        and src_crf = 'TOTXMEMO'
        and airpol = 'GHG'
        and unit = 'MIO_T'
),

cbs_nl as (
    select
        year,
        emissions_mt_co2eq as cbs_total_mt
    from {{ ref('stg_cbs__emissions') }}
    where
        cbs_category_code = 'T001616'
        and gas_code = 'T001372'
        and period_status = 'Definitief'
)

select
    gge_nl.year,
    gge_nl.gge_total_mt,
    cbs_nl.cbs_total_mt,
    abs(gge_nl.gge_total_mt - cbs_nl.cbs_total_mt)
    / cbs_nl.cbs_total_mt as relative_deviation
from gge_nl
inner join cbs_nl using (year)
where
    abs(gge_nl.gge_total_mt - cbs_nl.cbs_total_mt)
    / cbs_nl.cbs_total_mt >= 0.10
