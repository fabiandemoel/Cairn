---
title: EU sector benchmark — Eurostat AEA
description: GHG emissions per NACE section and year for all EU member states, from the Eurostat Air Emissions Accounts (AEA, env_ac_ainah_r2). Compare NL with peer countries by sector.
---

Greenhouse-gas emissions (total GHG in CO₂-equivalent, thousands of tonnes) per
NACE section and year for all EU member states. Data from
[Eurostat Air Emissions Accounts](https://ec.europa.eu/eurostat/web/environment/air-emissions-accounts)
(`env_ac_ainah_r2`).

<Alert status="warning">

**[Residence principle](/data-dictionary#business-glossary) — not the same as
CBS or EU ETS figures.** AEA attributes
emissions to the country of the *producing entity*, regardless of where
production physically occurs. CBS `85669NED` and the EU ETS instead use the
*territorial* principle (emissions within national borders). NL figures from this
page will legitimately differ from the [Sector benchmark (CBS)](/sectors) and
[Installation benchmark (EU ETS)](/installations): the gap reflects the
methodology difference, not an error. Do not use AEA figures as a correction of
or substitute for the CBS/ETS numbers.

</Alert>

```sql years
select distinct year
from cairn.country_sector_emissions
order by year desc
```

```sql latest_year
select max(year) as latest_year
from cairn.country_sector_emissions
```

AEA data typically trails by 1–2 years. Latest available year in this build: **{latest_year[0].latest_year}**.

## NL vs peer countries by NACE section

Compare the Netherlands with Germany (DE), France (FR), and Belgium (BE) for a
selected year. Emissions are in thousands of tonnes CO₂-eq (kt CO₂-eq).

<Dropdown data={years} name=year value=year defaultValue={years[0].year} />

```sql peers_by_section
select
    country,
    nace_section,
    emissions_ths_t_co2eq
from cairn.country_sector_emissions
where year = '${inputs.year.value}'
  and country in ('NL', 'DE', 'FR', 'BE')
order by nace_section, country
```

<BarChart
    data={peers_by_section}
    x=nace_section
    y=emissions_ths_t_co2eq
    series=country
    yAxisTitle="kt CO₂-eq"
    title="GHG emissions per NACE section — NL vs DE, FR, BE ({inputs.year.value})"
/>

## NL vs peers over time — by NACE section

Select a NACE section to trace its emissions trend across countries.

```sql nace_sections
select distinct nace_section
from cairn.country_sector_emissions
order by nace_section
```

<Dropdown data={nace_sections} name=nace_section value=nace_section defaultValue="C" />

```sql peers_over_time
select
    year,
    country,
    emissions_ths_t_co2eq
from cairn.country_sector_emissions
where nace_section = '${inputs.nace_section.value}'
  and country in ('NL', 'DE', 'FR', 'BE')
order by year, country
```

<LineChart
    data={peers_over_time}
    x=year
    y=emissions_ths_t_co2eq
    series=country
    yAxisTitle="kt CO₂-eq"
    title="NACE {inputs.nace_section.value} — GHG emissions over time"
/>

## Browse all countries and sectors

All EU member states for the selected year. Use the year dropdown above to change
the year. Sector share is each NACE section's share of that country's national
total (residence-principle).

```sql all_countries
select
    country,
    nace_section,
    emissions_ths_t_co2eq,
    emissions_share
from cairn.country_sector_emissions
where year = '${inputs.year.value}'
order by country, nace_section
```

<DataTable data={all_countries} rows=20 rowShading={true} search={true}>
    <Column id=country title="Country" />
    <Column id=nace_section title="NACE section" />
    <Column id=emissions_ths_t_co2eq title="Emissions (kt CO₂-eq)" fmt='#,##0' />
    <Column id=emissions_share title="Share of national total" fmt='0.0%' contentType=colorscale />
</DataTable>
