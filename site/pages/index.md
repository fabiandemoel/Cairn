---
title: Cairn
description: A queryable, auditable benchmark layer over official EU/NL climate data.
---

Cairn turns scattered official climate data into an auditable, queryable
benchmark. It answers, per sector: **"how do your emissions compare to the
sector average?"** — and every figure traces back to a versioned, pinned
official source.

```sql sector_headline
select
    max(year) as latest_year,
    count(distinct nace_section) as sections,
    sum(case when year = (select max(year) from cairn.sector_emissions)
        then sector_emissions_mt_co2eq end) as national_total_mt
from cairn.sector_emissions
```

```sql installation_headline
select
    max(year) as latest_year,
    count(distinct case when year = (select max(year) from cairn.installation_emissions)
        then installation_id end) as installations,
    sum(case when year = (select max(year) from cairn.installation_emissions)
        then installation_emissions_t_co2eq end) / 1e6 as verified_total_mt
from cairn.installation_emissions
```

<BigValue
    data={sector_headline}
    value=national_total_mt
    fmt='#,##0.0" Mt CO₂-eq"'
    title="NL emissions, latest CBS year"
    comparison=latest_year
    comparisonTitle="year"
    comparisonFmt='0'
/>

<BigValue
    data={installation_headline}
    value=installations
    fmt='#,##0'
    title="NL ETS installations benchmarked"
    comparison=latest_year
    comparisonTitle="year"
    comparisonFmt='0'
/>

## The two benchmarks

Cairn pairs two official sources that answer the question at two altitudes —
the whole-economy **denominator** and the installation-level **numerator**.

<div class="grid grid-cols-1 md:grid-cols-2 gap-4">

<div>

### [Sector benchmark — CBS →](/sectors)

Greenhouse-gas emissions per NACE section and year, with each sector's share of
the national total. The whole-economy sector average, from CBS StatLine table
`85669NED` (IPCC method, annual).

</div>

<div>

### [Installation benchmark — EU ETS →](/installations)

Per NL stationary installation, its verified emissions versus its NACE-section
peers. The large-emitter benchmark, from euets.info (the reprocessed EU
Transaction Log), cross-checked against the EEA Union Registry aggregate.

</div>

</div>

## Why it is auditable

Cairn is built on a few load-bearing rules, so a number can never drift away
from its source:

- **Raw data is immutable** — every ingest writes a new, versioned path.
- **The manifest is append-only** — each source pins its exact release by
  `sha256`; a data change without a manifest change is impossible.
- **Mappings are code** — the CBS category → NACE mapping is a reviewed seed,
  so its numeric impact shows up in a CI diff.
- **CI guards the methodology** — reconciliation and coverage tests fail the
  build if a source shifts under us.

See **[Methodology & sources →](/methodology)** for the full provenance of
every figure on this site.
