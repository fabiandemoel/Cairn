---
title: Cairn
description: An auditable, queryable benchmark over official EU/NL climate data — every figure traces back to a pinned official source.
---

<div class="flex flex-wrap items-center gap-2">
<a href="https://fabiandemoel.nl" class="inline-flex items-center gap-1.5 rounded-full bg-blue-600 dark:bg-blue-500 px-3 py-1 text-sm font-medium text-white no-underline shadow-sm transition-colors hover:bg-blue-700 dark:hover:bg-blue-600"><span aria-hidden="true">←</span><span>Back to fabiandemoel.nl</span></a>
<a href="https://github.com/fabiandemoel/Cairn" class="inline-flex items-center gap-1.5 rounded-full border border-gray-300 dark:border-gray-700 px-2.5 py-0.5 text-sm text-gray-600 dark:text-gray-300 no-underline hover:border-gray-400 dark:hover:border-gray-500"><span class="font-medium">Cairn v1.2.0</span><span class="text-gray-400">·</span><span>Phase 4</span></a>
</div>

**Cairn turns public climate data into auditable, reproducible datasets with
full lineage.**

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
    title="NL emissions (CBS, latest year)"
/>

<BigValue
    data={installation_headline}
    value=installations
    fmt='#,##0'
    title="NL ETS installations benchmarked (stationary, NACE-mapped)"
/>

Latest years: CBS **{sector_headline[0].latest_year}**, EU ETS
**{installation_headline[0].latest_year}**. "Benchmarked" counts stationary,
NACE-mapped installations only — installations without a NACE section in the
pinned euets.info snapshot have no peer group and are excluded; see
[coverage on Data quality](/data-quality#how-complete-is-the-coverage) for how
much of the EEA aggregate the included set captures.

We build reproducible climate datasets from official public sources with
complete lineage — CSRD/ESRS reporting is one application.

For sustainability teams and auditors who need to prove every number back to an
official source. Integrators can build directly on the
[disclosure CSV bundle](/disclosure) and the
[open repository](https://github.com/fabiandemoel/Cairn) — Cairn ships no hosted
API.

## The NL benchmark spine

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

## EU context & cross-checks

Beyond the NL spine, four more official views widen the picture and cross-check
it from independent sources and accounting principles.

<div class="grid grid-cols-1 md:grid-cols-2 gap-4">

<div>

### [EU sector benchmark — Eurostat AEA →](/sectors-eu)

The same NACE-section cut for every EU member state, on the residence principle
— compare NL with its peers, from the Eurostat Air Emissions Accounts.

</div>

<div>

### [Country GHG totals — Eurostat GGE →](/countries-ghg)

National greenhouse-gas totals (territorial principle, UNFCCC submissions) for
the EU27 plus peers — directly comparable to the CBS figures.

</div>

<div>

### [NAMEA bridge — CBS →](/namea-bridge)

CBS NAMEA residence-principle emissions bridged against the territorial sector
benchmark, per NACE section — the same emissions, two accounting principles.

</div>

<div>

### [Transport benchmark — EU ETS →](/transport)

NL aviation and maritime EU ETS operators, benchmarked by operator type rather
than by industry sector.

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

See the **[Architecture →](/architecture)** page for how raw ingest, pinned
manifests, dbt marts, and this read-only site fit together end to end,
**[Methodology & sources →](/methodology)** for the full provenance of every
figure on this site, or **[Data quality →](/data-quality)** for the live pin
status of each source — whether every figure is still chained, by hash, to an
immutable official source. The **[Data dictionary & glossary →](/data-dictionary)**
lists every model and column with the tests that guard it, and defines the
cross-cutting concepts behind the numbers.

The **[CSRD / ESRS E1 disclosure →](/disclosure)** supports ESRS E1-6 reporting
by providing an auditable source for the verified Scope 1 emissions of EU ETS
installations — downloadable as a self-contained, audit-traceable bundle.

<Alert status="info">

**What Cairn is not.** A verified data source, not a reporting product — not a
CSRD reporting platform, not a double-materiality assessment, not Scope 2/3
calculation, not an assurance opinion, and not legal advice.

</Alert>
