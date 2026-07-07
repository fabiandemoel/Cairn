-- Staging: typed view of the raw emissieregistratie crf_summary1 (UNFCCC CRF
-- Summary1) snapshot, unpivoted from the source's one-column-per-gas layout
-- into one row per IPCC source/sink category x gas x inventory year -- the
-- grain the CBS cross-check mart needs. Reads the parquet file at the
-- snapshot directory passed via the `emissieregistratie_crf_summary1_raw_dir`
-- var.
--
-- The raw sheet keeps a units sub-header row (see the ingestion pipeline's
-- module docstring) that carries no category -- it is structural noise left
-- over from the Excel-to-tabular conversion, not an observation, so it is
-- dropped here (unlike a methodology-specific filter, which belongs in the
-- mart, not staging).
--
-- Units: HFCs, the PFCs, the unspecified HFC/PFC mix, and the total are
-- reported as CO2-equivalent baskets per the CRF Summary1 footnotes (each
-- aggregates multiple compounds with different GWPs, so no single native-mass
-- unit applies); CO2, CH4, N2O, SF6, NF3, and the criteria pollutants (NOx,
-- CO, NMVOC, SOx) are single, well-defined substances reported in their own
-- mass (kt).

with raw as (
    select
        inventory_year,
        "GREENHOUSE GAS SOURCE AND SINK CATEGORIES" as ipcc_category,  -- noqa: RF05
        "Net CO2 emissions/removals" as net_co2,  -- noqa: RF05
        ch4,
        n2o,
        "HFCs (1)" as hfcs,  -- noqa: RF05
        "PFCs (1)" as pfcs,  -- noqa: RF05
        "Unspecified mix of HFCs and PFCs (1)" as unspecified_mix_hfc_pfc,  -- noqa: RF05
        sf6,
        nf3,
        nox,
        co,
        nmvoc,
        sox,
        "Total GHG emissions/removals (2)" as total_ghg  -- noqa: RF05
    from read_parquet('{{ var("emissieregistratie_crf_summary1_raw_dir") }}/data.parquet')
),

categorized as (
    select * from raw
    where ipcc_category is not null
),

unpivoted as (
    select
        inventory_year,
        ipcc_category,
        'net_co2' as gas,
        'kt' as unit,
        net_co2 as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'ch4' as gas,
        'kt' as unit,
        ch4 as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'n2o' as gas,
        'kt' as unit,
        n2o as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'hfcs' as gas,
        'kt_co2eq' as unit,
        hfcs as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'pfcs' as gas,
        'kt_co2eq' as unit,
        pfcs as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'unspecified_mix_hfc_pfc' as gas,
        'kt_co2eq' as unit,
        unspecified_mix_hfc_pfc as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'sf6' as gas,
        'kt' as unit,
        sf6 as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'nf3' as gas,
        'kt' as unit,
        nf3 as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'nox' as gas,
        'kt' as unit,
        nox as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'co' as gas,
        'kt' as unit,
        co as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'nmvoc' as gas,
        'kt' as unit,
        nmvoc as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'sox' as gas,
        'kt' as unit,
        sox as raw_value
    from categorized
    union all
    select
        inventory_year,
        ipcc_category,
        'total_ghg' as gas,
        'kt_co2eq' as unit,
        total_ghg as raw_value
    from categorized
)

select
    try_cast(inventory_year as integer) as year,
    ipcc_category,
    gas,
    unit,
    try_cast(raw_value as double) as value,
    concat_ws('|', ipcc_category, gas, inventory_year) as observation_key
from unpivoted
