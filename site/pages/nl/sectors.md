---
title: Sectorbenchmark — CBS
description: Broeikasgasemissies en aandeel in het nationale totaal per NACE-sectie en jaar.
---

<span class="text-sm text-gray-500 dark:text-gray-400">🌐 <a href="/sectors">English</a> · <strong>Nederlands</strong></span>

De **noemer** voor de hele economie: broeikasgasemissies (totaal broeikasgas in
CO₂-equivalent, megatonnen) per NACE-sectie en jaar, met het aandeel van elke
sector in het nationale totaal. Alleen definitieve (`Definitief`) CBS-jaren.

Bron: CBS StatLine [`85669NED`](https://opendata.cbs.nl/statline/#/CBS/nl/dataset/85669NED),
IPCC-methode. Zie [Methodologie & bronnen](/nl/methodology) voor de beperkingen
(met name het ~30–35% `UNMAPPED`-aandeel dat CBS niet aan één NACE-sectie
toewijst).

```sql emissions_over_time
select
    year,
    nace_section,
    sector_emissions_mt_co2eq
from cairn.sector_emissions
order by year, nace_section
```

## Emissies door de tijd, per sector

<LineChart
    data={emissions_over_time}
    x=year
    y=sector_emissions_mt_co2eq
    series=nace_section
    yAxisTitle="Mt CO₂-eq"
    title="Broeikasgasemissies per NACE-sectie"
/>

## Aandeel in het nationale totaal

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
    title="Aandeel in nationale emissies, {inputs.year.value}"
/>

<DataTable data={share_by_sector} rows=all>
    <Column id=nace_section title="NACE-sectie" />
    <Column id=sector_emissions_mt_co2eq title="Emissies (Mt CO₂-eq)" fmt='#,##0.0' />
    <Column id=emissions_share title="Aandeel in nationaal totaal" fmt='0.0%' contentType=colorscale />
</DataTable>
