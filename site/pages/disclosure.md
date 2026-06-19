---
title: CSRD / ESRS E1 disclosure
description: Verified EU ETS emissions as the ESRS E1-6 gross Scope 1 GHG emissions datapoint, with an auditable download.
---

The **CSRD/ESRS E1-6** disclosure: for each NL stationary EU ETS installation
and reporting year, its verified emissions reframed as the *gross Scope 1
greenhouse-gas emissions* datapoint (tonnes CO₂-eq), with the
[NACE-section benchmark](/installations) carried alongside as context.

This is a read/relabel over the installation benchmark — no figures are
recomputed. **Scope 1 only**: ESRS E1-6 also requires Scope 2 and Scope 3, which
Cairn has no source for, so they are omitted — never filled with placeholder
figures.

## Download the disclosure bundle

A self-contained, auditable bundle a third party can pick up on its own:

- <a href="/downloads/esrs_e1/esrs_e1_disclosure.csv" download>**esrs_e1_disclosure.csv**</a>
  — the data, one row per installation-year.
- <a href="/downloads/esrs_e1/esrs_e1_disclosure.meta.json" download>**esrs_e1_disclosure.meta.json**</a>
  — the audit trail: the EU ETS source pin (release + SHA256), the methodology
  git commit, the warehouse version, a data dictionary, and a SHA256 of the CSV
  so you can prove the file was not altered after export.

The bundle is generated from the same R2-pinned warehouse that produces this
site (`scripts/export_esrs_e1.py`), so the disclosure always traces back to a
versioned, SHA256-verified source release. See
[Methodology & sources →](/methodology) for the full provenance chain.

## Preview

```sql e1
select
    reporting_year,
    installation_name,
    nace_section,
    gross_scope_1_ghg_emissions,
    sector_mean_emissions_t_co2eq,
    emissions_vs_sector_mean
from cairn.esrs_e1
order by reporting_year desc, gross_scope_1_ghg_emissions desc
```

<DataTable data={e1} rows=15 rowShading={true} downloadable={true} search={true}>
    <Column id=reporting_year title="Year" fmt='0' />
    <Column id=installation_name title="Installation" />
    <Column id=nace_section title="NACE" />
    <Column id=gross_scope_1_ghg_emissions title="Gross Scope 1 (t CO₂-eq)" fmt='#,##0' />
    <Column id=sector_mean_emissions_t_co2eq title="Sector mean (t CO₂-eq)" fmt='#,##0' />
    <Column id=emissions_vs_sector_mean title="vs. sector mean" fmt='0.0"×"' contentType=colorscale />
</DataTable>
