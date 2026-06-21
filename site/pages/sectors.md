---
title: Sector benchmark — CBS
description: GHG emissions and share of the national total per NACE section and year.
---

The whole-economy **denominator**: greenhouse-gas emissions (total GHG in
CO₂-equivalent, megatonnes) per NACE section and year, with each sector's share
of the national total. Final (`Definitief`) CBS years only.

Source: CBS StatLine [`85669NED`](https://opendata.cbs.nl/statline/#/CBS/nl/dataset/85669NED),
IPCC method. See [Methodology & sources](/methodology) for limitations (notably
the ~30–35% `UNMAPPED` share CBS does not attribute to a single NACE section).

<Alert status="info">

**Why ~30–35% is `UNMAPPED`.** Households, land use, transport, and the CBS G–U
services aggregate are not attributed by CBS to a single NACE section. They are
still counted in the national total — just not sector-attributed, so sector
shares sum to roughly two-thirds of the national figure by design.

</Alert>

```sql emissions_over_time
select
    year,
    nace_section,
    sector_emissions_mt_co2eq
from cairn.sector_emissions
order by year, nace_section
```

## Emissions over time, by sector

<LineChart
    data={emissions_over_time}
    x=year
    y=sector_emissions_mt_co2eq
    series=nace_section
    yAxisTitle="Mt CO₂-eq"
    title="GHG emissions per NACE section"
/>

## Share of the national total

```sql years
select distinct year
from cairn.sector_emissions
order by year desc
```

<Dropdown data={years} name=year value=year defaultValue={years[0].year} />

```sql share_by_sector
select
    nace_section,
    sector_emissions_mt_co2eq,
    emissions_share
from cairn.sector_emissions
where year = '${inputs.year.value}'
order by emissions_share desc
```

<BarChart
    data={share_by_sector}
    x=nace_section
    y=emissions_share
    yFmt='0.0%'
    swapXY=true
    title="Share of national emissions, {inputs.year.value}"
/>

<DataTable data={share_by_sector} rows=all>
    <Column id=nace_section title="NACE section" />
    <Column id=sector_emissions_mt_co2eq title="Emissions (Mt CO₂-eq)" fmt='#,##0.0' />
    <Column id=emissions_share title="Share of national total" fmt='0.0%' contentType=colorscale />
</DataTable>
