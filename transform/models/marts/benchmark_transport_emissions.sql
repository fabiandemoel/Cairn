-- Mart: per NL aviation/maritime EU ETS operator and year, its verified
-- emissions (tonnes CO2-eq) benchmarked against its operator-type average
-- (mean and median) over the same population. A sibling of
-- benchmark_installation_emissions, which deliberately excludes these
-- operators -- this mart is the transport-axis answer to the same "how do
-- your emissions compare to your peers?" question, over the same pinned
-- euets.info snapshot.
--
-- Methodology:
--   * NL registry only, 'euets' trading system (Swiss 'chets' duplicates
--     excluded), mirroring the stationary mart.
--   * Aviation and maritime operators only -- the mirror image of the
--     stationary mart's exclusion. A NULL flag (a few source installations
--     carry none) is treated as not-confirmed, so it is excluded here too,
--     consistent with the stationary mart's `not is_aircraft_operator`
--     treatment of NULL.
--   * Benchmarked by operator_type ('aircraft' / 'maritime'), never by NACE
--     section: these operators are classified by vehicle, not industry, and
--     a transport-mode peer group is the methodologically meaningful
--     comparison here (unlike the stationary mart, which benchmarks by
--     NACE section).
--   * An installation flagged as both an aircraft and a maritime operator
--     would break the installation|year grain; none exist in the current
--     snapshot (verify on the full snapshot, not just the CI fixture), and
--     if one appears, aircraft classification takes precedence rather than
--     silently duplicating the row.
--   * Verified emissions only: an installation-year with no reported
--     verified figure is excluded -- maritime entered EU ETS only from the
--     2024 compliance year, so maritime rows are legitimately sparse (or
--     entirely absent, e.g. the CI fixture, which predates 2024) rather
--     than zero-filled.
--   * Free allocation (allocated_total_t_co2eq) and the verified-vs-allocated
--     ratio (emissions_vs_allocated) are labelled read/relabel measures over
--     the pinned snapshot's allocatedTotal column, exactly as in the
--     stationary mart. Both are nullable.
--   * Legal-entity identity (lei, gleif_legal_name) is the same reviewed
--     lei_mapping_euets seed join as the stationary mart.
--   * These operators sit outside CBS national totals and the EEA
--     stationary aggregate (main_activity_code '20-99'), so this mart is
--     deliberately excluded from assert_national_total_reconciles and
--     assert_euets_coverage_within_eea.

with lei_mapping as (
    select
        euets_installation_id,
        lei,
        gleif_legal_name
    from {{ ref('lei_mapping_euets') }}
),

installations as (
    select
        stg.*,
        lei_mapping.lei,
        lei_mapping.gleif_legal_name,
        case
            when stg.is_aircraft_operator then 'aircraft'
            when stg.is_maritime_operator then 'maritime'
        end as operator_type
    from {{ ref('stg_euets__installations') }} as stg
    left join lei_mapping on lei_mapping.euets_installation_id = stg.installation_id
    where
        stg.registry = 'NL'
        and (stg.is_aircraft_operator or stg.is_maritime_operator)
),

compliance as (
    select
        installation_id,
        year,
        verified_emissions_t_co2eq,
        allocated_total,
        surrendered
    from {{ ref('stg_euets__compliance') }}
    where
        reported_in_system = 'euets'
        and verified_emissions_t_co2eq is not null
),

installation_year as (
    select
        compliance.installation_id,
        installations.installation_name,
        installations.parent_company,
        installations.ets_activity_label,
        installations.country_label,
        installations.latitude,
        installations.longitude,
        installations.lei,
        installations.gleif_legal_name,
        installations.operator_type,
        compliance.year,
        compliance.verified_emissions_t_co2eq as installation_emissions_t_co2eq,
        compliance.allocated_total as allocated_total_t_co2eq,
        compliance.surrendered as surrendered_allowances_t_co2eq
    from compliance
    inner join installations on installations.installation_id = compliance.installation_id
),

operator_type_benchmark as (
    select
        operator_type,
        year,
        count(*) as operator_type_installation_count,
        avg(installation_emissions_t_co2eq) as operator_type_mean_emissions_t_co2eq,
        median(installation_emissions_t_co2eq) as operator_type_median_emissions_t_co2eq
    from installation_year
    group by operator_type, year
)

select
    installation_year.installation_id || '|' || installation_year.year as installation_year_key,
    installation_year.year,
    installation_year.installation_id,
    installation_year.installation_name,
    installation_year.parent_company,
    installation_year.ets_activity_label,
    installation_year.country_label,
    installation_year.latitude,
    installation_year.longitude,
    installation_year.lei,
    installation_year.gleif_legal_name,
    installation_year.operator_type,
    installation_year.installation_emissions_t_co2eq,
    installation_year.allocated_total_t_co2eq,
    installation_year.surrendered_allowances_t_co2eq,
    operator_type_benchmark.operator_type_installation_count,
    operator_type_benchmark.operator_type_mean_emissions_t_co2eq,
    operator_type_benchmark.operator_type_median_emissions_t_co2eq,
    installation_year.installation_emissions_t_co2eq
    / operator_type_benchmark.operator_type_mean_emissions_t_co2eq as emissions_vs_operator_type_mean,
    installation_year.installation_emissions_t_co2eq
    / nullif(installation_year.allocated_total_t_co2eq, 0) as emissions_vs_allocated
from installation_year
inner join operator_type_benchmark
    using (operator_type, year)
order by
    installation_year.year asc,
    installation_year.operator_type asc,
    installation_year.installation_emissions_t_co2eq desc
