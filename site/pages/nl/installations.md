---
title: Installatiebenchmark — EU ETS
description: Per NL stationaire installatie, de geverifieerde emissies versus de NACE-sectorpeers.
---

<span class="text-sm text-gray-500 dark:text-gray-400">🌐 <a href="/installations">English</a> · <strong>Nederlands</strong></span>

De **teller** op installatieniveau: voor elke NL stationaire installatie de
geverifieerde EU ETS-emissies (ton CO₂-eq) tegenover het gemiddelde en de
mediaan van de NACE-sectie. Dit is de benchmark voor **grote uitstoters** — EU
ETS dekt alleen grote uitstoters, niet de hele economie (de
[sectorpagina](/nl/sectors) doet dat).

Bron: [euets.info](https://www.euets.info/) (herverwerkt EU Transaction Log),
gekruist met het EEA Union Registry-aggregaat. Alleen stationaire installaties;
lucht- en zeevaartexploitanten uitgesloten.

```sql installations
select distinct
    installation_id,
    installation_name,
    nace_section
from cairn.installation_emissions
order by installation_name
```

<Dropdown
    data={installations}
    name=installation
    value=installation_id
    label=installation_name
    defaultValue={installations[0].installation_id}
    title="Kies een installatie"
/>

```sql selected_latest
select *
from cairn.installation_emissions
where installation_id = '${inputs.installation.value}'
    and year = (
        select max(year) from cairn.installation_emissions
        where installation_id = '${inputs.installation.value}'
    )
```

<BigValue
    data={selected_latest}
    value=installation_emissions_t_co2eq
    fmt='#,##0" t"'
    title="Geverifieerde emissies (laatste jaar)"
/>

<BigValue
    data={selected_latest}
    value=sector_mean_emissions_t_co2eq
    fmt='#,##0" t"'
    title="Sectorgemiddelde"
/>

<BigValue
    data={selected_latest}
    value=emissions_vs_sector_mean
    fmt='0.0"×"'
    title="t.o.v. sectorgemiddelde"
/>

Deze installatie zit in NACE-sectie
**<Value data={selected_latest} column=nace_section />
(<Value data={selected_latest} column=nace_section_label />)**, gebenchmarkt
tegen **<Value data={selected_latest} column=sector_installation_count />**
ETS-installaties in die sectie.

## Deze installatie versus haar sector, door de tijd

```sql selected_trend
select year, 'Deze installatie' as metric, installation_emissions_t_co2eq as emissions_t
from cairn.installation_emissions
where installation_id = '${inputs.installation.value}'
union all
select year, 'Sectorgemiddelde' as metric, sector_mean_emissions_t_co2eq
from cairn.installation_emissions
where installation_id = '${inputs.installation.value}'
union all
select year, 'Sectormediaan' as metric, sector_median_emissions_t_co2eq
from cairn.installation_emissions
where installation_id = '${inputs.installation.value}'
order by year
```

<LineChart
    data={selected_trend}
    x=year
    y=emissions_t
    series=metric
    yAxisTitle="t CO₂-eq"
    title="Geverifieerde emissies vs. NACE-sectiebenchmark"
/>

## Waar het rangschikt in zijn sector (laatste jaar)

```sql sector_peers
with sel as (
    select nace_section, max(year) as year
    from cairn.installation_emissions
    where installation_id = '${inputs.installation.value}'
    group by nace_section
)
select
    i.installation_name,
    i.installation_emissions_t_co2eq,
    i.emissions_vs_sector_mean,
    i.installation_id = '${inputs.installation.value}' as is_selected
from cairn.installation_emissions i
inner join sel on i.nace_section = sel.nace_section and i.year = sel.year
order by i.installation_emissions_t_co2eq desc
```

<DataTable data={sector_peers} rows=15 rowShading={true}>
    <Column id=installation_name title="Installatie" />
    <Column id=installation_emissions_t_co2eq title="Emissies (t CO₂-eq)" fmt='#,##0' />
    <Column id=emissions_vs_sector_mean title="t.o.v. sectorgemiddelde" fmt='0.0"×"' contentType=colorscale />
</DataTable>
