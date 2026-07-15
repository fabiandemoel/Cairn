---
title: Residence vs territorial — CBS NAMEA bridge
description: NL residence-principle CO2 emissions (CBS NAMEA, 83300NED) next to the territorial-principle total GHG CO2-eq figure (CBS 85669NED), per NACE section and year — a provenance/methodology bridge explaining why the two diverge.
---

CBS publishes two national emission accounts on different **attribution
principles**. The [Sector benchmark](/sectors) (`85669NED`) uses the
**territorial principle**: emissions within Dutch borders, regardless of who
causes them. NAMEA (`83300NED`) uses the **residence principle**: emissions
caused by Dutch-resident economic activity, including Dutch operators abroad,
excluding non-residents on Dutch territory. The two are expected to diverge
for transport, shipping, and multinationals with cross-border activity.

<Alert status="warning">

**A bridge, not a reconciliation.** The two figures below are never expected to
match, and the gap is not tested to a tight tolerance. It also mixes **two**
divergences, not one: attribution principle (residence vs territorial), *and*
gas scope — NAMEA's headline measure here is CO2 only, because 83300NED
carries no pre-aggregated "total GHG in CO2-equivalent" figure like
85669NED's. The territorial column is total GHG in CO2-equivalent. Do not read
the gap as a pure principle effect. See [Methodology & sources](/methodology)
for the full caveat list.

</Alert>

```sql national_over_time
select distinct year, 'NAMEA residence (CO2)' as source, national_residence_co2_emissions_mt as emissions_mt
from cairn.namea_bridge
where national_residence_co2_emissions_mt is not null
union all
select distinct year, '85669NED territorial (GHG CO2-eq)' as source, national_territorial_ghg_emissions_mt_co2eq as emissions_mt
from cairn.namea_bridge
where national_territorial_ghg_emissions_mt_co2eq is not null
order by year, source
```

## National totals, residence vs territorial

<LineChart
    data={national_over_time}
    x=year
    y=emissions_mt
    series=source
    yAxisTitle="Mt"
    title="NL national total — NAMEA residence CO2 vs 85669NED territorial GHG CO2-eq"
/>

## By NACE section and year

```sql years
select distinct year
from cairn.namea_bridge
order by year desc
```

<Dropdown data={years} name=year value=year defaultValue={years[0].year} />

```sql bridge_by_sector
select
    nace_section,
    nace_label,
    residence_co2_emissions_mt,
    territorial_ghg_emissions_mt_co2eq
from cairn.namea_bridge
where year = '${inputs.year.value}'
order by nace_section
```

<DataTable data={bridge_by_sector} rows=all>
    <Column id=nace_section title="NACE section" />
    <Column id=nace_label title="Label" />
    <Column id=residence_co2_emissions_mt title="Residence CO2 (Mt, NAMEA)" fmt='#,##0.0' />
    <Column id=territorial_ghg_emissions_mt_co2eq title="Territorial GHG CO2-eq (Mt, 85669NED)" fmt='#,##0.0' />
</DataTable>

## Residence-principle gas composition by sector

Which gases dominate each sector's footprint under the residence principle?
Same four constituent gases as the [territorial breakdown](/sectors#gas-composition-by-sector),
here from CBS NAMEA (83300NED) — a composition view, not a reconciliation
against that territorial mart (see the accounting caveat above).

```sql namea_gas_mix
select
    nace_section,
    gas_label,
    emissions_mt,
    gas_share
from cairn.namea_gas_composition
where year = '${inputs.year.value}'
order by nace_section, gas_label
```

<BarChart
    data={namea_gas_mix}
    x=nace_section
    y=emissions_mt
    series=gas_label
    type=stacked
    yAxisTitle="Mt"
    title="NAMEA residence-principle GHG composition by gas, {inputs.year.value}"
/>

<DataTable data={namea_gas_mix} rows=all>
    <Column id=nace_section title="NACE section" />
    <Column id=gas_label title="Gas" />
    <Column id=emissions_mt title="Emissions (Mt)" fmt='#,##0.0' />
    <Column id=gas_share title="Share of sector total" fmt='0.0%' contentType=colorscale />
</DataTable>
