---
title: Methodology & sources
description: The provenance and limitations behind every figure on this site.
---

Cairn exists to be **auditable**. Every number on this site traces back to a
versioned, pinned official source, transformed by reviewed code. This page
records the provenance and the known limitations — read it before quoting a
figure.

## Sources

| Source | Role | Dataset | Release pinned in |
| --- | --- | --- | --- |
| **CBS StatLine `85669NED`** | Sector benchmark (whole-economy denominator) | GHG emissions per climate sector, IPCC method, annual | `sources/cbs/manifest.yml` |
| **euets.info** | Installation benchmark (large-emitter numerator) | Reprocessed EU Transaction Log, per-installation verified emissions + native NACE | `sources/euets/manifest.yml` |
| **EEA Union Registry** | Cross-check & denominator | Official aggregate by country × activity × year | `sources/eea/manifest.yml` |

Each source's exact release is pinned by `sha256` in an append-only manifest.
A weekly CI job re-verifies the pinned raw files; a change is an integrity alarm,
not flakiness.

## Sector benchmark (CBS) — method & limitations

Headline gas: total greenhouse gases (CO₂-eq). Only **leaf** climate-sector
categories are summed, so the national total is partitioned exactly once. CBS
source categories are mapped to NACE sections via a version-controlled seed
(`sector_mapping_cbs`); the mapping is reviewed via PR so its numeric impact
shows up in a CI benchmark diff.

- Provisional years are **excluded** (`Definitief` only), so the latest year may
  lag.
- **~30–35% of national emissions land in `UNMAPPED`** — households, land use,
  transport, and the CBS G–U services aggregate, which CBS does not attribute to
  a single NACE section. They are still counted, just not sector-attributed.
- Unit is megatonnes (CBS "miljard kg CO₂-equivalent"), rounded by CBS to 0.1 Mt.
- Bunkers are IPCC memo items outside the national total and are excluded.

## Installation benchmark (EU ETS) — method & limitations

NL registry, `euets` trading system only (linked Swiss `chets` duplicates
excluded), stationary installations only (aircraft/maritime excluded), verified
emissions only. Sector = NACE section, native to the source. The sector
mean/median are computed across the NL stationary ETS population per
(NACE section, year). A coverage test reconciles the ETS total against the EEA
aggregate (both derive from the EUTL; they match to ~0.02%).

- This is the **ETS large-emitter** average, not the whole-economy sector
  average — use the [sector page](/sectors) for that.
- euets.info **lags** the EEA release (latest data ~2023 vs ~2025).
- Installations without a NACE code are excluded (cannot be sector-benchmarked).

## Classification basis

The mapping rests on **SBI 2008 ⊃ NACE Rev.2**. Both are migrating (NACE
Rev.2.1 from 2025; SBI 2025 from 2026); when CBS switches `85669NED` over, the
seed mapping and the NACE section letters are revisited as a reviewed
methodology change.

## References

- CBS `85669NED`: <https://opendata.cbs.nl/statline/#/CBS/nl/dataset/85669NED>
- IPCC 2006 guidelines: <https://www.ipcc.ch/report/2006-ipcc-guidelines-for-national-greenhouse-gas-inventories/>
- euets.info: <https://www.euets.info/>
- EEA EU ETS data (Union Registry): <https://www.eea.europa.eu/en/datahub/datahubitem-view/98f04097-26de-4fca-86c4-63834818c0c0>
- EU ETS Directive 2003/87/EC: <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32003L0087>
- NACE Rev.2: <https://ec.europa.eu/eurostat/web/nace>
- SBI 2008: <https://www.cbs.nl/nl-nl/onze-diensten/methoden/classificaties/activiteiten/sbi-2008-standaard-bedrijfsindeling-2008>
- ESRS E1 (disclosure context): <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202302772>
