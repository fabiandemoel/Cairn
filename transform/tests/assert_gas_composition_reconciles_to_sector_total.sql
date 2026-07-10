-- Singular test: the sum of the four constituent-gas rows (A044109, A044110,
-- A044107, A052484) per NACE section and year must reconcile with the aggregate
-- benchmark_sector_emissions total (T001372) for the same sector-year, within
-- CBS's rounding budget. The test catches mapping gaps or logic divergence
-- beyond that expected rounding artifact. It passes when it returns zero rows.
--
-- Why an absolute (not percentage) tolerance: CBS publishes every figure — each
-- gas AND the aggregate total — independently rounded to 0.1 Mt. The gap between
-- the summed gas rows and the aggregate is therefore an *absolute* rounding
-- error that scales with the number of leaf categories summed into the sector,
-- not a fixed percentage. A percentage tolerance mis-fires on small sectors: a
-- single 0.1 Mt step on a 1.5 Mt sector (mining, water/waste) is 6.7%, while the
-- same step on 200 Mt manufacturing is 0.05%.
--
-- The budget is 0.1 Mt x source_category_count (+0.05 Mt for float noise). Note
-- that 0.1 Mt/leaf is the *empirical* bound: across the full 1990-2025 history
-- the observed gap never exceeds it (single-leaf sectors B/D/E sit exactly on
-- it). The *theoretical* per-leaf worst case is 0.2 Mt — four gas roundings can
-- swing +/-0.2 combined and the total rounding another +/-0.05, all on the 0.1
-- grid — but that requires all roundings to err maximally in the same direction,
-- which CBS's non-adversarial rounding never realises here. We keep the tighter
-- empirical 0.1/leaf to stay sensitive to real gaps (0.2/leaf would mask a ~3 Mt
-- divergence in manufacturing). If a future CBS release ever trips this test by
-- a small margin, check whether it is benign rounding drift toward that 0.2/leaf
-- ceiling before treating it as a mapping bug. A genuine mapping/coverage gap (a
-- whole leaf category, several Mt) clears the budget and still fails the test.

with composition_total as (
    select distinct
        year,
        nace_section,
        sector_total_all_gases_mt_co2eq
    from {{ ref('mart_sector_gas_composition') }}
),

aggregate_total as (
    select
        year,
        nace_section,
        sector_emissions_mt_co2eq,
        source_category_count
    from {{ ref('benchmark_sector_emissions') }}
)

select
    composition_total.year,
    composition_total.nace_section,
    composition_total.sector_total_all_gases_mt_co2eq,
    aggregate_total.sector_emissions_mt_co2eq,
    abs(
        composition_total.sector_total_all_gases_mt_co2eq
        - aggregate_total.sector_emissions_mt_co2eq
    ) as absolute_deviation_mt_co2eq,
    0.1 * aggregate_total.source_category_count + 0.05 as rounding_budget_mt_co2eq
from composition_total
inner join aggregate_total using (year, nace_section)
where
    abs(
        composition_total.sector_total_all_gases_mt_co2eq
        - aggregate_total.sector_emissions_mt_co2eq
    ) > 0.1 * aggregate_total.source_category_count + 0.05
