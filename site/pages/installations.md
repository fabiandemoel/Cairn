---
title: Installation benchmark — EU ETS
description: Per NL stationary installation, its verified emissions versus its NACE-section peers.
---

The installation-level **numerator**: for each NL stationary installation, its
verified EU ETS emissions (tonnes CO₂-eq) against its NACE-section mean and
median over the ETS population. This is the **large-emitter** benchmark — EU ETS
covers only large emitters, not the whole economy (the [sector page](/sectors)
carries that).

Source: [euets.info](https://www.euets.info/) (reprocessed EU Transaction Log),
cross-checked against the EEA Union Registry aggregate. Stationary installations
only; aircraft and maritime operators excluded.

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
    title="Select an installation"
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
    title="Verified emissions (latest year)"
/>

<BigValue
    data={selected_latest}
    value=sector_mean_emissions_t_co2eq
    fmt='#,##0" t"'
    title="Sector mean"
/>

<BigValue
    data={selected_latest}
    value=emissions_vs_sector_mean
    fmt='0.0"×"'
    title="vs. sector mean"
/>

This installation is in NACE section
**<Value data={selected_latest} column=nace_section />
(<Value data={selected_latest} column=nace_section_label />)**, benchmarked
against **<Value data={selected_latest} column=sector_installation_count />**
ETS installations in that section.

## This installation versus its sector, over time

```sql selected_trend
select year, 'This installation' as metric, installation_emissions_t_co2eq as emissions_t
from cairn.installation_emissions
where installation_id = '${inputs.installation.value}'
union all
select year, 'Sector mean' as metric, sector_mean_emissions_t_co2eq
from cairn.installation_emissions
where installation_id = '${inputs.installation.value}'
union all
select year, 'Sector median' as metric, sector_median_emissions_t_co2eq
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
    title="Verified emissions vs. NACE-section benchmark"
/>

## Where it ranks in its sector (latest year)

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
    <Column id=installation_name title="Installation" />
    <Column id=installation_emissions_t_co2eq title="Emissions (t CO₂-eq)" fmt='#,##0' />
    <Column id=emissions_vs_sector_mean title="vs. sector mean" fmt='0.0"×"' contentType=colorscale />
</DataTable>
