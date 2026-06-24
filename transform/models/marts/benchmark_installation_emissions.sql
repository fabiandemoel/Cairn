-- Mart: per NL stationary installation and year, its verified EU ETS emissions
-- benchmarked against its NACE-sector average. This is the installation-level
-- "how do your emissions compare to the sector average?" answer. Math is
-- deliberately simple and explicit.
--
-- Methodology:
--   * NL registry only, 'euets' trading system (linked registries also report
--     the same installation-year under the Swiss 'chets'; those duplicates are
--     excluded).
--   * Stationary installations only -- aircraft and maritime operators are
--     classified by vehicle, not by a sector, and are excluded. A NULL flag
--     (a few source installations carry none) is treated as not-confirmed-
--     stationary, so `not is_aircraft_operator` also excludes it.
--   * Verified emissions only: an installation-year with no reported verified
--     figure (e.g. future phase years) is excluded.
--   * Sector = NACE section letter, native to the source. Installations with no
--     NACE code cannot be sector-benchmarked and are excluded.
--   * The sector benchmark (mean and median) is computed across the same NL
--     stationary population per (nace_section, year). EU ETS covers only large
--     emitters, so this is the ETS sector average, not the whole-economy sector
--     average -- the coverage test reconciles the ETS total against the EEA
--     aggregate, and the CBS mart carries the whole-economy figures.
--   * Free allocation (allocated_total_t_co2eq) and the verified-vs-allocated
--     ratio (emissions_vs_allocated) are labelled measures read straight from
--     the pinned snapshot's allocatedTotal column -- who emits above (>1) or
--     below (<1) their free grant. Both are nullable: an installation-year with
--     no allocation stays NULL (never a placeholder zero), and the ratio is
--     NULL where allocation is missing or zero.

with installations as (
    select *
    from {{ ref('stg_euets__installations') }}
    where
        registry = 'NL'
        and not is_aircraft_operator
        and not is_maritime_operator
        and nace_section is not null
),

compliance as (
    select
        installation_id,
        year,
        verified_emissions_t_co2eq,
        allocated_total
    from {{ ref('stg_euets__compliance') }}
    where
        reported_in_system = 'euets'
        and verified_emissions_t_co2eq is not null
),

installation_year as (
    select
        compliance.installation_id,
        installations.installation_name,
        installations.nace_section,
        installations.nace_section_label,
        compliance.year,
        compliance.verified_emissions_t_co2eq as installation_emissions_t_co2eq,
        -- Free allocation (allocatedTotal) is a labelled measure straight from
        -- the pinned euets.info snapshot, not a recomputed figure. It is
        -- nullable: a few installation-years carry no allocation, which stays
        -- NULL (never a placeholder zero).
        compliance.allocated_total as allocated_total_t_co2eq
    from compliance
    inner join installations on installations.installation_id = compliance.installation_id
),

sector_benchmark as (
    select
        nace_section,
        year,
        count(*) as sector_installation_count,
        sum(installation_emissions_t_co2eq) as sector_emissions_t_co2eq,
        avg(installation_emissions_t_co2eq) as sector_mean_emissions_t_co2eq,
        median(installation_emissions_t_co2eq) as sector_median_emissions_t_co2eq
    from installation_year
    group by nace_section, year
)

select
    installation_year.installation_id || '|' || installation_year.year as installation_year_key,
    installation_year.year,
    installation_year.installation_id,
    installation_year.installation_name,
    installation_year.nace_section,
    installation_year.nace_section_label,
    installation_year.installation_emissions_t_co2eq,
    installation_year.allocated_total_t_co2eq,
    sector_benchmark.sector_installation_count,
    sector_benchmark.sector_mean_emissions_t_co2eq,
    sector_benchmark.sector_median_emissions_t_co2eq,
    installation_year.installation_emissions_t_co2eq
    / sector_benchmark.sector_mean_emissions_t_co2eq as emissions_vs_sector_mean,
    -- Verified-vs-allocated: who emits above (>1) or below (<1) their free
    -- grant. A labelled comparison of two source figures, not an invented
    -- number. NULL where allocation is missing or zero (nullif guards the
    -- divide); never a placeholder.
    installation_year.installation_emissions_t_co2eq
    / nullif(installation_year.allocated_total_t_co2eq, 0) as emissions_vs_allocated
from installation_year
inner join sector_benchmark
    using (nace_section, year)
order by
    installation_year.year asc,
    installation_year.nace_section asc,
    installation_year.installation_emissions_t_co2eq desc
