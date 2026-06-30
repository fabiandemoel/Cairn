---
title: Country GHG totals — Eurostat GGE
description: National greenhouse-gas totals (Eurostat env_air_gge, territorial principle) for all EU member states. Compare NL with peer countries over time.
---

National greenhouse-gas totals (million tonnes CO₂-equivalent) for all EU27
member states plus Norway, Iceland, and the UK, from
[Eurostat env\_air\_gge](https://ec.europa.eu/eurostat/databrowser/view/env_air_gge)
(UNFCCC national inventory submissions).

<Alert status="info">

**Territorial principle — directly comparable to CBS and EU ETS.** Unlike the
[EU sector benchmark (AEA)](/sectors-eu), which uses the residence principle,
`env_air_gge` uses the *territorial* principle (emissions physically occurring
within national borders), the same as CBS `85669NED` and the EU ETS. NL totals
from this page and the [Sector benchmark (CBS)](/sectors) will agree closely
(typically within 1%). Do not compare these figures with the AEA page without
accounting for the methodology difference.

</Alert>

```sql latest_year
select max(year) as latest_year from cairn.gge_emissions
```

`env_air_gge` derives from UNFCCC national inventory submissions, which trail the
current calendar year by 1–2 years. Latest available year in this build:
**{latest_year[0].latest_year}**.

## NL vs peer countries over time

```sql peers
select
    year,
    country,
    national_ghg_mt_co2eq
from cairn.gge_emissions
where country in ('NL', 'DE', 'FR', 'BE')
order by year, country
```

<LineChart
    data={peers}
    x=year
    y=national_ghg_mt_co2eq
    series=country
    yAxisTitle="Mt CO₂-eq"
    title="National GHG totals — NL vs DE, FR, BE"
/>

## All countries for a selected year

```sql years
select distinct year from cairn.gge_emissions order by year desc
```

<Dropdown data={years} name=year value=year defaultValue={years[0].year} />

```sql all_countries
select
    country,
    national_ghg_mt_co2eq
from cairn.gge_emissions
where year = ${inputs.year.value}
order by national_ghg_mt_co2eq desc
```

<BarChart
    data={all_countries}
    x=country
    y=national_ghg_mt_co2eq
    yAxisTitle="Mt CO₂-eq"
    title="National GHG totals — {inputs.year.value}"
    swapXY={true}
/>

<DataTable data={all_countries} rows=30 rowShading={true} search={true}>
    <Column id=country title="Country" />
    <Column id=national_ghg_mt_co2eq title="Emissions (Mt CO₂-eq)" fmt='#,##0.0' />
</DataTable>
