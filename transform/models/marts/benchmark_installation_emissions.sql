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
--   * Surrendered allowances (surrendered_allowances_t_co2eq) is the third leg
--     of the EUTL compliance triple: allowances the operator actually handed back
--     to cover their verified emissions. It is a labelled measure read straight
--     from the pinned snapshot's surrendered column -- never a recomputed running
--     balance, never a compliance verdict. Nullable: surrender can lag and a
--     single surrender may cover multiple years, so some installation-years
--     legitimately carry NULL (never a placeholder zero).

--   * Legal-entity identity (lei, gleif_legal_name) is a labelled read/relabel
--     dimension joined from the reviewed lei_mapping_euets seed -- the GLEIF
--     LEI (ISO 17442) of the operating legal entity, letting the benchmark roll
--     up to company level. The left join is 1:1 on installation_id (the seed is
--     unique on it), so it adds no rows and changes no figure. Installations
--     with no reviewed match carry a NULL lei (never an invented identifier).
--   * Installation identity context (parent_company, ets_activity_label,
--     country_label, latitude, longitude) is promoted straight from the
--     staging layer (stg_euets__installations). These are descriptive context
--     columns only, not authoritative identifiers:
--       - parent_company is free text from euets.info; not normalised or
--         deduplicated -- the LEI seed is the authoritative entity identifier.
--       - latitude/longitude are euets.info's latitudeGoogle/longitudeGoogle --
--         source-provided and approximate. Nullable: not all installations
--         carry coordinates.
--   * Carbon leakage exposure (carbon_leakage_exposed, and its supporting
--     sector_description/oj_citation) is a labelled read/relabel dimension
--     joined from the reviewed carbon_leakage_list seed (Commission Delegated
--     Decision (EU) 2019/708, OJ L 120, 8.5.2019, p. 20) on the installation's
--     NACE code -- policy context only, never a computed figure and never a
--     free-allocation entitlement. Only the Decision's Annex points 1-3
--     ('nace') rows are joined: point 4's Prodcom sub-sector rows cannot be
--     matched, since euets.info carries no Prodcom classification per
--     installation.

with lei_mapping as (
    select
        euets_installation_id,
        lei,
        gleif_legal_name
    from {{ ref('lei_mapping_euets') }}
),

carbon_leakage as (
    select
        code,
        sector_description,
        oj_citation
    from {{ ref('carbon_leakage_list') }}
    where code_type = 'nace'
),

installations as (
    select
        stg.*,
        lei_mapping.lei,
        lei_mapping.gleif_legal_name
    from {{ ref('stg_euets__installations') }} as stg
    left join lei_mapping on lei_mapping.euets_installation_id = stg.installation_id
    where
        stg.registry = 'NL'
        and not stg.is_aircraft_operator
        and not stg.is_maritime_operator
        and stg.nace_section is not null
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
        installations.nace_section,
        installations.nace_section_label,
        -- Carbon leakage exposure is a labelled policy flag, not a computed
        -- figure: true only where the installation's NACE code is transcribed
        -- in the reviewed carbon_leakage_list seed (Annex points 1-3).
        carbon_leakage.code is not null as carbon_leakage_exposed,
        carbon_leakage.sector_description as carbon_leakage_sector_description,
        carbon_leakage.oj_citation as carbon_leakage_oj_citation,
        compliance.year,
        compliance.verified_emissions_t_co2eq as installation_emissions_t_co2eq,
        -- Free allocation (allocatedTotal) is a labelled measure straight from
        -- the pinned euets.info snapshot, not a recomputed figure. It is
        -- nullable: a few installation-years carry no allocation, which stays
        -- NULL (never a placeholder zero).
        compliance.allocated_total as allocated_total_t_co2eq,
        -- Surrendered allowances (surrendered) is the third leg of the EUTL
        -- compliance triple: allowances the operator actually handed back.
        -- Nullable: surrender can lag and a single surrender may cover multiple
        -- years; NULL stays NULL (never a placeholder zero).
        compliance.surrendered as surrendered_allowances_t_co2eq
    from compliance
    inner join installations on installations.installation_id = compliance.installation_id
    left join carbon_leakage on carbon_leakage.code = installations.nace_code
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
    installation_year.parent_company,
    installation_year.ets_activity_label,
    installation_year.country_label,
    installation_year.latitude,
    installation_year.longitude,
    installation_year.lei,
    installation_year.gleif_legal_name,
    installation_year.nace_section,
    installation_year.nace_section_label,
    installation_year.carbon_leakage_exposed,
    installation_year.carbon_leakage_sector_description,
    installation_year.carbon_leakage_oj_citation,
    installation_year.installation_emissions_t_co2eq,
    installation_year.allocated_total_t_co2eq,
    installation_year.surrendered_allowances_t_co2eq,
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
