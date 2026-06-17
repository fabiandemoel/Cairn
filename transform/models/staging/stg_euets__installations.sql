-- Staging: 1:1 typed view of the euets.info installations, with the NACE
-- section letter resolved by walking the NACE hierarchy up to level 1, and the
-- ETS activity and country decoded to labels. No rows are filtered here; the NL
-- filter and the stationary/aircraft/maritime split are methodology applied in
-- the mart, mirroring how the CBS staging stays 1:1 with its raw snapshot.

with recursive
nace as (
    select
        id,
        parent_id,
        level,
        description
    from read_parquet('{{ var("euets_raw_dir") }}/dim_nace.parquet')
),

-- Walk every NACE code up its parent chain; the level-1 ancestor is the section
-- letter. Codes that are already a section letter map to themselves.
walk as (
    select
        id as origin,
        id as node,
        level,
        parent_id
    from nace
    union all
    select
        w.origin,
        n.id,
        n.level,
        n.parent_id
    from walk as w
    inner join nace as n on n.id = w.parent_id
),

nace_section as (
    select
        walk.origin as nace_code,
        walk.node as section_letter,
        nace.description as section_label
    from walk
    inner join nace on nace.id = walk.node
    where walk.level = '1'
),

activities as (
    select
        id as code,
        description as label
    from read_parquet('{{ var("euets_raw_dir") }}/dim_activity_type.parquet')
),

countries as (
    select
        id as code,
        description as label
    from read_parquet('{{ var("euets_raw_dir") }}/dim_country.parquet')
),

installations as (
    select * from read_parquet('{{ var("euets_raw_dir") }}/installation.parquet')
)

select
    i.id as installation_id,
    i.name as installation_name,
    i.registry_id as registry,
    i.country_id as country_code,
    countries.label as country_label,
    i.activity_id as ets_activity_code,
    activities.label as ets_activity_label,
    i.nace_id as nace_code,
    nace_section.section_letter as nace_section,
    nace_section.section_label as nace_section_label,
    cast(i.isaircraftoperator as boolean) as is_aircraft_operator,
    cast(i.ismaritimeoperator as boolean) as is_maritime_operator,
    i.parentcompany as parent_company,
    try_cast(i.latitudegoogle as double) as latitude,
    try_cast(i.longitudegoogle as double) as longitude
from installations as i
left join nace_section on nace_section.nace_code = i.nace_id
left join activities on activities.code = i.activity_id
left join countries on countries.code = i.country_id
