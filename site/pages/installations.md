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
    lei,
    gleif_legal_name,
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

<BigValue
    data={selected_latest}
    value=allocated_total_t_co2eq
    fmt='#,##0" t"'
    title="Free allocation (latest year)"
/>

<BigValue
    data={selected_latest}
    value=emissions_vs_allocated
    fmt='0.0"×"'
    title="vs. free allocation"
/>

<BigValue
    data={selected_latest}
    value=surrendered_allowances_t_co2eq
    fmt='#,##0" t"'
    title="Surrendered allowances (latest year)"
/>

The **verified-vs-allocated** multiple compares verified emissions to the
installation's free EU ETS allowance grant: above 1× means it emitted more than
it was freely allocated, below 1× less. Both figures are read straight from the
pinned euets.info snapshot — where an installation-year carries no free
allocation, the figure is left blank, never a placeholder zero.

**Surrendered allowances** are the allowances the operator actually surrendered
for the year — the third leg of the EUTL (EU Transaction Log) compliance triple
alongside verified emissions and free allocation. A single surrender can cover
multiple years and can lag the compliance year; some installation-years
legitimately carry no figure — left blank, never a placeholder zero.

This installation is in NACE section
**<Value data={selected_latest} column=nace_section />
(<Value data={selected_latest} column=nace_section_label />)**, benchmarked
against **<Value data={selected_latest} column=sector_installation_count />**
ETS installations in that section.

Operating legal entity (where the reviewed
[GLEIF](https://www.gleif.org/en/about-lei/introducing-the-legal-entity-identifier-lei)
mapping has a confident match):
**<Value data={selected_latest} column=gleif_legal_name />**
(LEI <Value data={selected_latest} column=lei />). The LEI is the open,
authoritative entity identifier that lets emissions roll up from installation to
company; unmatched installations are left blank, never assigned an invented LEI.

<Alert status="info">

A multiple above or below the sector mean is **context, not a verdict**. A
higher figure can reflect larger production volume, an older installation, a
different production process, or lower efficiency — not necessarily worse
performance. Read it alongside the trend and the sector ranking below. Note
also that euets.info lags the latest EEA release (data to ~2023).

</Alert>

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
union all
select year, 'Free allocation' as metric, allocated_total_t_co2eq
from cairn.installation_emissions
where installation_id = '${inputs.installation.value}'
union all
select year, 'Surrendered allowances' as metric, surrendered_allowances_t_co2eq
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
    i.gleif_legal_name,
    i.installation_emissions_t_co2eq,
    i.allocated_total_t_co2eq,
    i.surrendered_allowances_t_co2eq,
    i.emissions_vs_sector_mean,
    i.emissions_vs_allocated,
    i.installation_id = '${inputs.installation.value}' as is_selected
from cairn.installation_emissions i
inner join sel on i.nace_section = sel.nace_section and i.year = sel.year
order by i.installation_emissions_t_co2eq desc
```

<DataTable data={sector_peers} rows=15 rowShading={true}>
    <Column id=installation_name title="Installation" />
    <Column id=gleif_legal_name title="Legal entity (GLEIF)" />
    <Column id=installation_emissions_t_co2eq title="Emissions (t CO₂-eq)" fmt='#,##0' />
    <Column id=allocated_total_t_co2eq title="Free allocation (t CO₂-eq)" fmt='#,##0' />
    <Column id=surrendered_allowances_t_co2eq title="Surrendered allowances (t CO₂-eq)" fmt='#,##0' />
    <Column id=emissions_vs_sector_mean title="vs. sector mean" fmt='0.0"×"' contentType=colorscale />
    <Column id=emissions_vs_allocated title="vs. free allocation" fmt='0.0"×"' contentType=colorscale />
</DataTable>
