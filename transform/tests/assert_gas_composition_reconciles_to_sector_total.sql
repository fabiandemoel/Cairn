-- Singular test: the sum of the four constituent-gas rows (A044109, A044110,
-- A044107, A052484) per NACE section and year must stay within 1% of the
-- aggregate benchmark_sector_emissions total for the same sector-year. The 1%
-- tolerance (vs. 0.5%) accounts for CBS's independent rounding of each gas value
-- to 0.1 Mt, which can accumulate to ~0.6% discrepancies in the sum. The test
-- catches mapping gaps or logic divergence beyond this expected rounding artifact.
-- The test passes when it returns zero rows.

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
        sector_emissions_mt_co2eq
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
    ) / aggregate_total.sector_emissions_mt_co2eq as relative_deviation
from composition_total
inner join aggregate_total using (year, nace_section)
where
    abs(
        composition_total.sector_total_all_gases_mt_co2eq
        - aggregate_total.sector_emissions_mt_co2eq
    ) / aggregate_total.sector_emissions_mt_co2eq >= 0.01
