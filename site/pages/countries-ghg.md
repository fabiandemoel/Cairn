---
title: Country GHG totals — Eurostat GGE
description: National greenhouse-gas totals and CRF-sector comparisons (Eurostat env_air_gge, territorial principle) for all EU member states. Compare NL with peer countries over time.
---

National greenhouse-gas totals (million tonnes CO₂-equivalent) for all EU27
member states plus Norway, Iceland, and the UK, from
[Eurostat env\_air\_gge](https://ec.europa.eu/eurostat/databrowser/view/env_air_gge)
(UNFCCC national inventory submissions).

<Alert status="info">

**[Territorial principle](/data-dictionary#business-glossary) — directly
comparable to CBS and EU ETS.** Unlike the
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

## CRF-sector benchmark (IPCC / UNFCCC taxonomy)

```sql sector_years
select distinct year from cairn.gge_sector_totals order by year desc
```

The same dataset also publishes top-level **CRF** sectors (Energy, Industrial
processes and product use, Agriculture, LULUCF, Waste). CRF is an
IPCC/UNFCCC classification, **not** NACE — do not compare it one-to-one with the
[EU sector benchmark (AEA)](/sectors-eu).

<Alert status="warning">

**Reading the CRF sectors.** The national-total `TOTXMEMO` row is "Total
excluding memo items" — it drops international aviation / shipping bunkers and
biomass-CO₂ (the memo items), but it *includes* LULUCF. The five top-level CRF
sectors therefore sum to approximately the national total (the small remaining
gap is "indirect CO₂", which `TOTXMEMO` carries but no top-level sector does).
Note that **LULUCF (CRF4) can be negative** — it is a net carbon sink in some
countries (e.g. FR) and a net source in others (e.g. NL, DE).

</Alert>

<Dropdown data={sector_years} name=sector_year value=year defaultValue={sector_years[0].year} />

```sql peers_by_crf_sector
select
    country,
    crf_sector_label,
    sector_ghg_mt_co2eq
from cairn.gge_sector_totals
where year = ${inputs.sector_year.value}
  and country in ('NL', 'DE', 'FR', 'BE')
order by crf_sector_code, country
```

<BarChart
    data={peers_by_crf_sector}
    x=crf_sector_label
    y=sector_ghg_mt_co2eq
    series=country
    yAxisTitle="Mt CO₂-eq"
    title="Top-level CRF sectors — NL vs DE, FR, BE ({inputs.sector_year.value})"
/>

## CRF-sector trend by country

```sql crf_sectors
select distinct crf_sector_code, crf_sector_label
from cairn.gge_sector_totals
order by crf_sector_code
```

<Dropdown data={crf_sectors} name=crf_sector value=crf_sector_code defaultValue="CRF1" />

```sql peers_crf_over_time
select
    year,
    country,
    sector_ghg_mt_co2eq
from cairn.gge_sector_totals
where crf_sector_code = '${inputs.crf_sector.value}'
  and country in ('NL', 'DE', 'FR', 'BE')
order by year, country
```

<LineChart
    data={peers_crf_over_time}
    x=year
    y=sector_ghg_mt_co2eq
    series=country
    yAxisTitle="Mt CO₂-eq"
    title="CRF sector {inputs.crf_sector.value} — emissions over time"
/>

## Browse all countries and CRF sectors

```sql all_country_sectors
select
    country,
    crf_sector_label,
    sector_ghg_mt_co2eq
from cairn.gge_sector_totals
where year = ${inputs.sector_year.value}
order by crf_sector_code, country
```

<DataTable data={all_country_sectors} rows=25 rowShading={true} search={true}>
    <Column id=country title="Country" />
    <Column id=crf_sector_label title="CRF sector" />
    <Column id=sector_ghg_mt_co2eq title="Emissions (Mt CO₂-eq)" fmt='#,##0.0' />
</DataTable>
