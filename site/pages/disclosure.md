---
title: CSRD / ESRS E1 disclosure
description: Verified EU ETS emissions provided as the verified basis for the ESRS E1-6 gross Scope 1 GHG emissions datapoint, with an auditable download.
---

The **CSRD/ESRS E1-6** disclosure: for each NL stationary EU ETS installation
and reporting year, its verified emissions provided as the verified basis for
the *gross Scope 1 greenhouse-gas emissions* datapoint (tonnes CO₂-eq), with the
[NACE-section benchmark](/installations) carried alongside as context.

This is a read/relabel over the installation benchmark — no figures are
recomputed. **Scope 1 only**: ESRS E1-6 also requires Scope 2 and Scope 3, which
Cairn has no source for, so they are omitted — never filled with placeholder
figures.

**Verified ETS ≠ ESRS Scope 1, exactly.** The two usually align, but the EU ETS
verified figure and an entity's reported Scope 1 can diverge on organisational
boundary, consolidation scope, and emission sources outside the ETS. Cairn
supplies the verified ETS basis for the datapoint — not a finished,
entity-level Scope 1 figure.

<Alert status="info">

**What Cairn is not.** Cairn is a verified data source, not a reporting product.
It is not a CSRD reporting platform, not a double-materiality assessment, not
Scope 2/3 calculation, not an assurance opinion, not an ESRS reporting engine,
and not legal advice. It supplies one auditable datapoint; the disclosure built
around it remains the reporter's responsibility.

</Alert>

## Download the disclosure bundle

A self-contained, auditable bundle a third party can pick up on its own:

<div class="my-4 flex flex-wrap gap-3">
<a href="/downloads/esrs_e1/esrs_e1_disclosure.csv" download class="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white no-underline hover:bg-blue-700">
<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" /></svg>
Download CSV
</a>
<a href="/downloads/esrs_e1/esrs_e1_disclosure.meta.json" download class="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 no-underline hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800">
<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" /></svg>
Audit metadata (JSON)
</a>
</div>

- **esrs_e1_disclosure.csv** — the data, one row per installation-year.
- **esrs_e1_disclosure.meta.json** — the audit trail: the EU ETS source pin
  (release + SHA256), the methodology git commit, the warehouse version, a data
  dictionary, and a SHA256 of the CSV so you can prove the file was not altered
  after export.

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
