---
title: Transport benchmark — EU ETS aviation & maritime
description: Per NL aviation/maritime EU ETS operator, its verified emissions versus its operator-type peers.
---

The transport-axis **numerator**: for each NL aviation or maritime EU ETS
operator, its verified emissions (tonnes CO₂-eq) against its operator-type mean
and median over the ETS population. These operators are benchmarked against
each other by **operator type** (aircraft vs. maritime), never against
stationary NACE sectors — they are classified by vehicle, not industry, and are
kept out of the [installation benchmark](/installations), the
[sector benchmark](/sectors), and their reconciliation checks.

Source: [euets.info](https://www.euets.info/) (reprocessed EU Transaction Log),
the same pinned snapshot as the installation benchmark.

<Alert status="warning">

**Maritime coverage is partial and recent.** Maritime shipping entered EU ETS
only from the **2024 compliance year**. Maritime rows before then are sparse or
entirely absent — never zero-filled — while aviation has been in scope since
2012.

</Alert>

```sql operators
select distinct
    installation_id,
    installation_name,
    lei,
    gleif_legal_name,
    operator_type
from cairn.transport_emissions
order by installation_name
```

<Dropdown
    data={operators}
    name=operator
    value=installation_id
    label=installation_name
    defaultValue={operators[0].installation_id}
    title="Select an operator"
/>

```sql selected_latest
select *
from cairn.transport_emissions
where installation_id = '${inputs.operator.value}'
    and year = (
        select max(year) from cairn.transport_emissions
        where installation_id = '${inputs.operator.value}'
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
    value=operator_type_mean_emissions_t_co2eq
    fmt='#,##0" t"'
    title="Operator-type mean"
/>

<BigValue
    data={selected_latest}
    value=emissions_vs_operator_type_mean
    fmt='0.0"×"'
    title="vs. operator-type mean"
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

This operator is classified as
**<Value data={selected_latest} column=operator_type />**, benchmarked against
**<Value data={selected_latest} column=operator_type_installation_count />**
other EU ETS transport operators of the same type.

Operating legal entity (where the reviewed
[GLEIF](https://www.gleif.org/en/about-lei/introducing-the-legal-entity-identifier-lei)
mapping has a confident match):
**<Value data={selected_latest} column=gleif_legal_name />**
(LEI <Value data={selected_latest} column=lei />). Unmatched operators are left
blank, never assigned an invented LEI.

<Alert status="info">

A multiple above or below the operator-type mean is **context, not a verdict**
— it can reflect fleet size, route mix, or vessel/aircraft type, not
necessarily worse performance. Read it alongside the trend and the ranking
below.

</Alert>

## This operator versus its type, over time

```sql selected_trend
select year, 'This operator' as metric, installation_emissions_t_co2eq as emissions_t
from cairn.transport_emissions
where installation_id = '${inputs.operator.value}'
union all
select year, 'Operator-type mean' as metric, operator_type_mean_emissions_t_co2eq
from cairn.transport_emissions
where installation_id = '${inputs.operator.value}'
union all
select year, 'Operator-type median' as metric, operator_type_median_emissions_t_co2eq
from cairn.transport_emissions
where installation_id = '${inputs.operator.value}'
union all
select year, 'Free allocation' as metric, allocated_total_t_co2eq
from cairn.transport_emissions
where installation_id = '${inputs.operator.value}'
union all
select year, 'Surrendered allowances' as metric, surrendered_allowances_t_co2eq
from cairn.transport_emissions
where installation_id = '${inputs.operator.value}'
order by year
```

<LineChart
    data={selected_trend}
    x=year
    y=emissions_t
    series=metric
    yAxisTitle="t CO₂-eq"
    title="Verified emissions vs. operator-type benchmark"
/>

## Where it ranks among its type (latest year)

```sql type_peers
with sel as (
    select operator_type, max(year) as year
    from cairn.transport_emissions
    where installation_id = '${inputs.operator.value}'
    group by operator_type
)
select
    t.installation_name,
    t.gleif_legal_name,
    t.installation_emissions_t_co2eq,
    t.allocated_total_t_co2eq,
    t.surrendered_allowances_t_co2eq,
    t.emissions_vs_operator_type_mean,
    t.emissions_vs_allocated,
    t.installation_id = '${inputs.operator.value}' as is_selected
from cairn.transport_emissions t
inner join sel on t.operator_type = sel.operator_type and t.year = sel.year
order by t.installation_emissions_t_co2eq desc
```

<DataTable data={type_peers} rows=15 rowShading={true}>
    <Column id=installation_name title="Operator" />
    <Column id=gleif_legal_name title="Legal entity (GLEIF)" />
    <Column id=installation_emissions_t_co2eq title="Emissions (t CO₂-eq)" fmt='#,##0' />
    <Column id=allocated_total_t_co2eq title="Free allocation (t CO₂-eq)" fmt='#,##0' />
    <Column id=surrendered_allowances_t_co2eq title="Surrendered allowances (t CO₂-eq)" fmt='#,##0' />
    <Column id=emissions_vs_operator_type_mean title="vs. operator-type mean" fmt='0.0"×"' contentType=colorscale />
    <Column id=emissions_vs_allocated title="vs. free allocation" fmt='0.0"×"' contentType=colorscale />
</DataTable>
