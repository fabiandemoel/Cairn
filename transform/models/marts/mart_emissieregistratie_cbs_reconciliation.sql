-- Mart: cross-check of RIVM's Emissieregistratie (the CRF -- Common Reporting
-- Format -- national GHG inventory the Netherlands submits to the UNFCCC each
-- year) national total against the CBS 85669NED national total. One layer
-- closer to the UNFCCC submission than CBS itself -- see the ingestion
-- pipeline's module docstring. Grain: year.
--
-- Methodology:
--   * Emissieregistratie side: the CRF Reporter template's standard
--     "Total National Emissions and Removals" row (gas = 'total_ghg', i.e.
--     the per-category "Total GHG emissions/removals" column, reported in
--     CO2-equivalent kt per the CRF footnotes) -- converted kt -> Mt (/1000)
--     to match CBS's unit.
--   * CBS side: category T001616 ("Totaal klimaatsectoren"), gas T001372
--     (total GHG, CO2-eq), Definitief years only -- the same filter
--     benchmark_sector_emissions and assert_national_total_reconciles use.
--   * Both sources use the territorial principle, so no residence-principle
--     correction applies (same reasoning as the Eurostat GGE cross-check in
--     mart_gge_national_totals).
--   * A cross-check/provenance layer only -- not a second authority for the
--     national total. See assert_emissieregistratie_nl_total_within_cbs for
--     the tolerance test.

with emissieregistratie_national as (
    select
        year,
        value / 1000 as emissieregistratie_total_mt_co2eq
    from {{ ref('stg_emissieregistratie__crf_summary1') }}
    where
        ipcc_category = 'Total National Emissions and Removals'
        and gas = 'total_ghg'
        and value is not null
),

cbs_national as (
    select
        year,
        emissions_mt_co2eq as cbs_total_mt_co2eq
    from {{ ref('stg_cbs__emissions') }}
    where
        cbs_category_code = 'T001616'
        and gas_code = 'T001372'
        and period_status = 'Definitief'
)

select
    emissieregistratie_national.year,
    emissieregistratie_national.emissieregistratie_total_mt_co2eq,
    cbs_national.cbs_total_mt_co2eq,
    abs(
        emissieregistratie_national.emissieregistratie_total_mt_co2eq
        - cbs_national.cbs_total_mt_co2eq
    ) / cbs_national.cbs_total_mt_co2eq as relative_deviation
from emissieregistratie_national
inner join cbs_national using (year)
order by emissieregistratie_national.year
