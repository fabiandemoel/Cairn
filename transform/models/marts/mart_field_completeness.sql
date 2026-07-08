-- Mart: field-completeness (NULL-rate) observability. Per mart/column/year,
-- populated-vs-NULL row counts and the resulting share, over a curated set of
-- deliberately nullable columns in the existing marts. Counts only -- never a
-- re-derivation of the underlying figures, an imputation, or a quality
-- verdict on any single figure.
--
-- Methodology:
--   * Tracked columns are enumerated explicitly below, not introspected from
--     the schema, so a newly added nullable column is a reviewed addition.
--   * "Populated" means the column is not NULL, except for
--     benchmark_sector_emissions.nace_section: CBS categories that cannot be
--     attributed to a single NACE section carry the sentinel 'UNMAPPED'
--     rather than NULL, so populated there means nace_section != 'UNMAPPED'.
--   * A NULL (or UNMAPPED) value is a legitimate, documented state --
--     not-yet-mapped in a reviewed seed, or genuinely absent upstream --
--     never an error this mart "fixes".

with benchmark_sector_emissions__nace_section as (
    select
        'benchmark_sector_emissions' as mart_name,
        'nace_section' as column_name,
        year,
        count(*) as total_count,
        sum(case when nace_section != 'UNMAPPED' then 1 else 0 end) as populated_count
    from {{ ref('benchmark_sector_emissions') }}
    group by year
),

benchmark_installation_emissions__lei as (
    select
        'benchmark_installation_emissions' as mart_name,
        'lei' as column_name,
        year,
        count(*) as total_count,
        count(lei) as populated_count
    from {{ ref('benchmark_installation_emissions') }}
    group by year
),

benchmark_installation_emissions__allocated_total as (
    select
        'benchmark_installation_emissions' as mart_name,
        'allocated_total_t_co2eq' as column_name,
        year,
        count(*) as total_count,
        count(allocated_total_t_co2eq) as populated_count
    from {{ ref('benchmark_installation_emissions') }}
    group by year
),

benchmark_installation_emissions__surrendered_allowances as (
    select
        'benchmark_installation_emissions' as mart_name,
        'surrendered_allowances_t_co2eq' as column_name,
        year,
        count(*) as total_count,
        count(surrendered_allowances_t_co2eq) as populated_count
    from {{ ref('benchmark_installation_emissions') }}
    group by year
),

benchmark_transport_emissions__lei as (
    select
        'benchmark_transport_emissions' as mart_name,
        'lei' as column_name,
        year,
        count(*) as total_count,
        count(lei) as populated_count
    from {{ ref('benchmark_transport_emissions') }}
    group by year
),

benchmark_transport_emissions__allocated_total as (
    select
        'benchmark_transport_emissions' as mart_name,
        'allocated_total_t_co2eq' as column_name,
        year,
        count(*) as total_count,
        count(allocated_total_t_co2eq) as populated_count
    from {{ ref('benchmark_transport_emissions') }}
    group by year
),

benchmark_transport_emissions__surrendered_allowances as (
    select
        'benchmark_transport_emissions' as mart_name,
        'surrendered_allowances_t_co2eq' as column_name,
        year,
        count(*) as total_count,
        count(surrendered_allowances_t_co2eq) as populated_count
    from {{ ref('benchmark_transport_emissions') }}
    group by year
),

combined as (
    select * from benchmark_sector_emissions__nace_section
    union all
    select * from benchmark_installation_emissions__lei
    union all
    select * from benchmark_installation_emissions__allocated_total
    union all
    select * from benchmark_installation_emissions__surrendered_allowances
    union all
    select * from benchmark_transport_emissions__lei
    union all
    select * from benchmark_transport_emissions__allocated_total
    union all
    select * from benchmark_transport_emissions__surrendered_allowances
)

select
    mart_name || '|' || column_name || '|' || cast(year as varchar)
        as mart_column_year_key,
    mart_name,
    column_name,
    year,
    total_count,
    populated_count,
    total_count - populated_count as null_count,
    cast(populated_count as double) / total_count as populated_share
from combined
order by mart_name, column_name, year
