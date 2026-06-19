---
title: Cairn
description: Een doorzoekbare, controleerbare benchmarklaag over officiële EU/NL-klimaatdata.
---

<span class="text-sm text-gray-500 dark:text-gray-400">🌐 <a href="/">English</a> · <strong>Nederlands</strong></span>

<a href="https://github.com/fabiandemoel/Cairn" class="inline-flex items-center gap-1.5 rounded-full border border-gray-300 dark:border-gray-700 px-2.5 py-0.5 text-sm text-gray-600 dark:text-gray-300 no-underline hover:border-gray-400 dark:hover:border-gray-500"><span class="font-medium">Cairn v1.0.0</span><span class="text-gray-400">·</span><span>Fase 3</span></a>

Cairn maakt van versnipperde officiële klimaatdata een controleerbare,
doorzoekbare benchmark. Het beantwoordt, per sector: **"hoe verhouden jouw
emissies zich tot het sectorgemiddelde?"** — en elk cijfer is herleidbaar naar
een geversioneerde, vastgepinde officiële bron.

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
    title="NL-emissies, laatste CBS-jaar"
    comparison=latest_year
    comparisonTitle="jaar"
    comparisonFmt='0'
/>

<BigValue
    data={installation_headline}
    value=installations
    fmt='#,##0'
    title="NL ETS-installaties gebenchmarkt"
    comparison=latest_year
    comparisonTitle="jaar"
    comparisonFmt='0'
/>

## De twee benchmarks

Cairn combineert twee officiële bronnen die de vraag op twee niveaus
beantwoorden — de **noemer** voor de hele economie en de **teller** op
installatieniveau.

<div class="grid grid-cols-1 md:grid-cols-2 gap-4">

<div>

### [Sectorbenchmark — CBS →](/nl/sectors)

Broeikasgasemissies per NACE-sectie en jaar, met het aandeel van elke sector in
het nationale totaal. Het sectorgemiddelde voor de hele economie, uit CBS
StatLine-tabel `85669NED` (IPCC-methode, jaarlijks).

</div>

<div>

### [Installatiebenchmark — EU ETS →](/nl/installations)

Per NL stationaire installatie: de geverifieerde emissies versus de
NACE-sectorpeers. De benchmark voor grote uitstoters, uit euets.info (het
herverwerkte EU Transaction Log), gekruist met het EEA Union Registry-aggregaat.

</div>

</div>

## Waarom het controleerbaar is

Cairn rust op een paar dragende regels, zodat een cijfer nooit kan afdrijven van
zijn bron:

- **Ruwe data is onveranderlijk** — elke ingest schrijft een nieuw,
  geversioneerd pad.
- **Het manifest is append-only** — elke bron pint zijn exacte release vast met
  `sha256`; een datawijziging zonder manifestwijziging is onmogelijk.
- **Mappings zijn code** — de mapping CBS-categorie → NACE is een beoordeelde
  seed, dus de numerieke impact verschijnt in een CI-diff.
- **CI bewaakt de methodologie** — reconciliatie- en dekkingstests laten de
  build falen als een bron onder ons verschuift.

Zie **[Methodologie & bronnen →](/nl/methodology)** voor de volledige herkomst
van elk cijfer op deze site.
