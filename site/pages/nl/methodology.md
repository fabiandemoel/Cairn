---
title: Methodologie & bronnen
description: De herkomst en beperkingen achter elk cijfer op deze site.
---

<span class="text-sm text-gray-500 dark:text-gray-400">🌐 <a href="/methodology">English</a> · <strong>Nederlands</strong></span>

Cairn bestaat om **controleerbaar** te zijn. Elk cijfer op deze site is
herleidbaar naar een geversioneerde, vastgepinde officiële bron, getransformeerd
door beoordeelde code. Deze pagina legt de herkomst en de bekende beperkingen
vast — lees haar voordat je een cijfer citeert.

## Bronnen

| Bron | Rol | Dataset | Release vastgepind in |
| --- | --- | --- | --- |
| **CBS StatLine `85669NED`** | Sectorbenchmark (noemer hele economie) | Broeikasgasemissies per klimaatsector, IPCC-methode, jaarlijks | `sources/cbs/manifest.yml` |
| **euets.info** | Installatiebenchmark (teller grote uitstoters) | Herverwerkt EU Transaction Log, geverifieerde emissies per installatie + native NACE | `sources/euets/manifest.yml` |
| **EEA Union Registry** | Kruiscontrole & noemer | Officieel aggregaat per land × activiteit × jaar | `sources/eea/manifest.yml` |

De exacte release van elke bron is met `sha256` vastgepind in een append-only
manifest. Een wekelijkse CI-job verifieert de vastgepinde ruwe bestanden
opnieuw; een wijziging is een integriteitsalarm, geen flakiness.

## Sectorbenchmark (CBS) — methode & beperkingen

Hoofdgas: totaal broeikasgassen (CO₂-eq). Alleen **blad**-klimaatsectorcategorieën
worden gesommeerd, zodat het nationale totaal precies één keer wordt verdeeld.
CBS-broncategorieën worden via een geversioneerde seed (`sector_mapping_cbs`)
gemapt op NACE-secties; de mapping wordt via PR beoordeeld, zodat de numerieke
impact in een CI-benchmarkdiff verschijnt.

- Voorlopige jaren worden **uitgesloten** (alleen `Definitief`), dus het laatste
  jaar kan achterlopen.
- **~30–35% van de nationale emissies belandt in `UNMAPPED`** — huishoudens,
  landgebruik, verkeer en het CBS-aggregaat G–U diensten, die CBS niet aan één
  NACE-sectie toewijst. Ze worden wel meegeteld, alleen niet sector-toegewezen.
- De eenheid is megatonnen (CBS "miljard kg CO₂-equivalent"), door CBS afgerond
  op 0,1 Mt.
- Bunkers zijn IPCC-memo-items buiten het nationale totaal en worden uitgesloten.

## Installatiebenchmark (EU ETS) — methode & beperkingen

NL-register, alleen het `euets`-handelssysteem (gekoppelde Zwitserse
`chets`-duplicaten uitgesloten), alleen stationaire installaties (lucht-/zeevaart
uitgesloten), alleen geverifieerde emissies. Sector = NACE-sectie, native aan de
bron. Het sectorgemiddelde/de mediaan wordt berekend over de NL stationaire
ETS-populatie per (NACE-sectie, jaar). Een dekkingstest reconcilieert het
ETS-totaal tegen het EEA-aggregaat (beide afgeleid van het EUTL; ze komen overeen
tot ~0,02%).

- Dit is het **ETS-gemiddelde voor grote uitstoters**, niet het
  sectorgemiddelde voor de hele economie — gebruik daarvoor de
  [sectorpagina](/nl/sectors).
- euets.info **loopt achter** op de EEA-release (laatste data ~2023 vs ~2025).
- Installaties zonder NACE-code worden uitgesloten (kunnen niet
  sector-gebenchmarkt worden).

## Classificatiebasis

De mapping rust op **SBI 2008 ⊃ NACE Rev.2**. Beide migreren (NACE Rev.2.1 vanaf
2025; SBI 2025 vanaf 2026); wanneer CBS `85669NED` overzet, worden de
seed-mapping en de NACE-sectieletters herzien als een beoordeelde
methodologiewijziging.

## Referenties

- CBS `85669NED`: <https://opendata.cbs.nl/statline/#/CBS/nl/dataset/85669NED>
- IPCC 2006-richtlijnen: <https://www.ipcc.ch/report/2006-ipcc-guidelines-for-national-greenhouse-gas-inventories/>
- euets.info: <https://www.euets.info/>
- EEA EU ETS-data (Union Registry): <https://www.eea.europa.eu/en/datahub/datahubitem-view/98f04097-26de-4fca-86c4-63834818c0c0>
- EU ETS-richtlijn 2003/87/EG: <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32003L0087>
- NACE Rev.2: <https://ec.europa.eu/eurostat/web/nace>
- SBI 2008: <https://www.cbs.nl/nl-nl/onze-diensten/methoden/classificaties/activiteiten/sbi-2008-standaard-bedrijfsindeling-2008>
- ESRS E1 (publicatiecontext): <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202302772>
