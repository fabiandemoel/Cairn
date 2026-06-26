# BACKLOG.md — curated menu of candidate expansions for Cairn

This file is the **menu** the automation loop draws from. It is curated, not a
dumping ground. Agents read it; a human merges every change to it.

- **Replenish** (weekly) proposes *new* candidates and re-scores existing ones,
  as a docs-only PR. It may move dead/off-spine ideas into _Considered and
  rejected_ so they don't get re-proposed.
- **Scout** (daily) dispatches from the top of _Live candidates_ and reacts to
  new upstream data releases, turning one item into a single concrete issue.
- **Implement** does the work for an issue you've labelled `approved`, on a
  branch, as a PR. The existing CI (dbt build, tests, `benchmark-diff`,
  `evidence-build`) is the gate.

## Rules of the game (a candidate is only valid if it passes all of these)

Read `CLAUDE.md` first — these restate its invariants as admission criteria.

1. **Official source only.** EU/NL authoritative data (EUTL/euets.info, EEA,
   CBS, Eurostat, RIVM, GLEIF). No modelled, scraped, or estimated figures.
2. **Read/relabel, never recompute.** New numbers belong in a dbt mart, tested
   there. The site and the ESRS E1 export only read and reshape. No invented or
   placeholder figures — real source categories or explicit `NULL` + a note.
3. **Adds a benchmark axis or provenance/identity depth.** If it does neither,
   it's not a candidate.
4. **No scope creep.** Cairn is **not**: a CSRD reporting platform, a double-
   materiality tool, a Scope 2/3 calculator, an assurance provider, a public
   API, or a legal-advice service. Candidates that pull it that way go to
   _Considered and rejected_ with the reason.
5. **Provenance survives.** Every new source gets its own append-only manifest
   under `sources/<source>/`; every mapping is a reviewed seed.

## Scoring

- **Value** — how much it strengthens the benchmark/provenance proposition (H/M/L).
- **Effort** — integration cost: pipeline + manifest + staging + mart + fixture
  + site query (L/M/H).
- **Spine-fit** — how cleanly it fits read/relabel + the pinned-snapshot model
  (H = pure read/relabel; L = introduces volatility or computation).

Order _Live candidates_ by value, then spine-fit, then (inverse) effort.

---

## Live candidates

### 1. GLEIF / LEI → installation → legal-entity mapping
**Value: H · Effort: M · Spine-fit: H**

Open, authoritative entity IDs. Makes the benchmark meaningful at company level
("all of operator X's installations") and is the natural bridge to the ESRS E1
export, whose disclosures are entity-level, not installation-level.
- *Watch:* the mapping **is** the methodology — a reviewed seed like
  `sector_mapping_cbs.csv`. Never invent an LEI; unmatched operators get `NULL`
  + a `notes` entry. The mapping change shows its impact via `benchmark-diff`.
  The source's free-text `parent_company` (see candidate #5) is a useful *match
  aid*, not the authority.
- *Touches:* a reviewed seed, an entity dimension on the installation mart,
  optional entity rollup in the ESRS export.

### 2. Eurostat Air Emissions Accounts (`env_ac_ainah_r2`) → cross-country sector benchmark
**Value: H · Effort: H · Spine-fit: M**

Turns the NL-only CBS sector benchmark into "is NL chemicals high vs EU
chemicals?" on one harmonised, per-NACE methodology. Authoritative, versioned,
bulk-downloadable.
- *Watch:* AEA uses the residence principle; ETS/CBS are territorial. **Document
  the bridge** — Eurostat ships `env_ac_aibrid_r2` precisely to reconcile AEA
  totals to inventory totals; cite it in the README references and add a
  reconciliation test. Do **not** use the intensities dataset
  (`env_ac_aeint_r2`) — derived ratios are recompute-adjacent.
- *Touches:* new `ingestion/eurostat_aea_pipeline.py` + `sources/eurostat/manifest.yml`,
  staging + a benchmark dimension, NACE-alignment seed if needed, CI fixture,
  site query + page.

### 3. EUA carbon price → € valuation overlay
**Value: H (commercial) · Effort: M · Spine-fit: L**

Adds "these emissions = €X at the current EUA price" — directly addresses the
commercial-positioning gap. **Lowest spine-fit:** the price is volatile and
time-varying, and tonnes × price is a computation, both in tension with the
pinned-snapshot, read/relabel model.
- *Watch:* keep it strictly as a **labelled context overlay** in the site, sourced
  from official auction results, pinned per release like any other source. Never
  a stored mart figure, never in the ESRS E1 export. Defer unless commercial
  positioning becomes the active priority.

### 4. EUTL surrendered allowances → verified-vs-surrendered compliance-integrity axis
**Value: M · Effort: L · Spine-fit: H**

The third leg of the EUTL triple, after allocation and verified emissions:
allowances actually surrendered per installation-year. Already staged —
`stg_euets__compliance` exposes `surrendered`. Surfacing "surrendered vs
verified" is a pure read/relabel provenance axis over the pinned snapshot; no
new source, no recomputation. Natural to ship alongside verified-vs-allocated.
- *Watch:* surrender can lag and a single surrender may cover multiple years —
  present it as a **labelled measure**, not a recomputed running balance, and
  never as a compliance *verdict* (that would drift toward the assurance scope
  rule 4 forbids). Missing values stay `NULL` + a note.
- *Touches:* one mart measure on `benchmark_installation_emissions` (or sibling),
  `site/sources/cairn/*.sql`, a page. Column already in the fixture's
  `compliance.parquet`.

### 5. EUTL installation identity enrichment (parent company, ETS activity, geo)
**Value: M · Effort: L · Spine-fit: H**

`stg_euets__installations` already stages `parent_company`, `ets_activity_label`,
`country_label`, and `latitude`/`longitude`, but the marts surface only
`installation_name` + NACE section. Promoting these adds **identity/provenance
depth** (admission rule 3) at near-zero cost — and `parent_company` lets a
rough company rollup exist from the pinned snapshot even before the GLEIF/LEI
seed (#1) lands.
- *Watch:* `parent_company` is **free text, not an authoritative ID** — surface
  it as descriptive context only; the authoritative entity mapping stays the
  reviewed LEI seed (#1). Do **not** normalise/dedupe names into a synthesised
  entity (that's invention). Geo is euets.info's `latitudeGoogle/longitudeGoogle`
  — label it source-provided and approximate.
- *Touches:* installation mart dimension columns, `site/sources/cairn/*.sql`,
  a page (table/map). Fields already present in the fixture's `installation.parquet`.

### 6. Eurostat `env_air_gge` — EU member-state GHG inventory national totals
**Value: M · Effort: L · Spine-fit: H**

Eurostat aggregates member-state UNFCCC national inventory reports into a single
bulk download (`env_air_gge`): annual national GHG totals and CRF-sector
breakdowns for all EU27 + Norway, Iceland, and UK, back to 1990. Because it uses
the **territorial/production principle** — the same as CBS 85669NED and the EUTL
— NL's `env_air_gge` total is a direct cross-check of the CBS figure. A
peer-country view ("NL industry emissions vs DE/FR/BE industry") becomes possible
at CRF-sector granularity without any residence-principle correction.
- *Watch:* CRF sectors (energy, industrial processes, agriculture, waste, LULUCF)
  are **not** NACE — no installation-level or NACE-sector alignment is possible
  from this source alone. Use it as a **national-total cross-check**
  (`assert_gge_nl_total_within_cbs`, <1% tolerance) and a peer-country chart,
  not as a NACE sector benchmark. Do not conflate with Eurostat AEA (#2), which
  uses the residence principle and NACE sectors for a different purpose. Time
  lag: UNFCCC submissions trail the current year by 1–2 years; document the
  latest available year explicitly.
- *Touches:* `ingestion/eurostat_gge_pipeline.py`, `sources/eurostat_gge/manifest.yml`,
  a `stg_eurostat__gge` staging model, a cross-check test, `site/sources/cairn/*.sql`,
  a page.

### 7. Emissieregistratie (RIVM) → deepen NL provenance + granularity
**Value: M · Effort: M · Spine-fit: H**

The authoritative source under NL's UNFCCC submission; finer per substance/
sector/region than CBS. Lets a CBS-derived figure be traced one layer deeper.
- *Watch:* it partly overlaps CBS national totals — keep it as a cross-check /
  provenance layer, **not** a second authority for the same figure. Add a
  reconciliation test against the CBS national total.
- *Touches:* new pipeline + manifest, staging, a provenance/cross-check model.

### 8. EU ETS aviation & maritime verified emissions → transport benchmark axis
**Value: M · Effort: M · Spine-fit: H**

`benchmark_installation_emissions` deliberately excludes aircraft and maritime
operators (`not is_aircraft_operator and not is_maritime_operator`). Surfacing
them as their *own* labelled transport dimension — benchmarked among themselves,
not folded into the stationary NACE sectors — adds a new benchmark axis from the
same pinned snapshot. Read/relabel; the flags are already staged.
- *Watch:* keep them **out** of the stationary national-total reconciliation and
  the EEA stationary `20-99` coverage test (both assume stationary; these
  operators sit outside CBS national totals and that EEA code). Maritime entered
  EU ETS only from the **2024 compliance year**, so coverage is partial and
  recent — document it. They carry no NACE section, so benchmark by operator
  type, never against CBS sectors. Operator flags are nullable — exercise on the
  full snapshot, not just the fixture.
- *Touches:* euets staging (flags present), a sibling mart + its own coverage
  handling/test, `site/sources/cairn/*.sql`, a page, CI fixture check.

### 9. EU ETS carbon leakage list (Delegated Regulation 2019/708) → installation sector-exposure flag
**Value: M · Effort: M · Spine-fit: H**

Commission Delegated Regulation (EU) 2019/708 (OJ L 120, 11.5.2019, and
subsequent amendments) lists the NACE and PRODCOM sectors deemed exposed to
carbon leakage in ETS Phase 4 (2021–2030); exposed sectors receive elevated free
allocation. Pinning the list as a reviewed seed — like `sector_mapping_cbs.csv`
— lets the mart label every installation with its carbon-leakage-exposure status:
a pure policy-context read/relabel, no computation. Answers "why does this sector
receive more free allocation?" directly from official EU law, providing a
provenance bridge between candidate #4 (surrendered allowances) and the
allocation picture shipped in PR #31.
- *Watch:* the list is versioned to a specific Regulation and OJ citation — pin
  it there; if an amending regulation is issued, open a new seed version rather
  than overwriting. Never derive a free-allocation **entitlement** from this flag
  (that requires benchmark production data Cairn does not have); surface it as a
  label only. Every seed change goes through a PR and `benchmark-diff` so the
  numeric impact on the allocation comparison is visible.
- *Touches:* reviewed seed `seeds/carbon_leakage_list.csv` (NACE/PRODCOM codes +
  regulation citation), a mart dimension column, `site/sources/cairn/*.sql`, a page.

### 10. CBS NAMEA air emission accounts — residence-principle sector breakdown
**Value: M · Effort: M · Spine-fit: H**

CBS publishes NAMEA (National Accounting Matrix including Environmental Accounts)
air emission data: annual GHG emissions attributed to Dutch economic actors by
NACE sector, using the **residence principle**. Unlike 85669NED
(territorial/production principle), NAMEA attributes emissions to the industry of
the emitting company's registered residence. The two methodologies diverge for
transport, shipping, and multinationals with cross-border activity. Surfacing
NAMEA as a provenance layer explains why 85669NED and the Eurostat AEA (#2)
diverge for the same sector — it is the Dutch side of the AEA picture, directly
from CBS via the same OData v4 API.
- *Watch:* because it uses the residence principle, NAMEA national totals do
  **not** directly reconcile with 85669NED — document the bridge explicitly in a
  note rather than a `<0.5%` test (the divergence is methodological by design,
  not an error). Avoid duplicating AEA's cross-country story here; keep this as a
  provenance-depth / methodology-bridge layer for NL only. RIVM (#7) also
  deepens NL provenance but from the territorial side — these are complementary,
  not redundant.
- *Touches:* `ingestion/cbs_namea_pipeline.py`, `sources/cbs_namea/manifest.yml`,
  staging model, a provenance/cross-check model, `site/sources/cairn/*.sql`.

### 11. Coverage & completeness observability — surface the reconciliation drift the tests already compute
**Value: M · Effort: L · Spine-fit: M**

The provenance-integrity view (`mart_data_provenance`) and its **Data quality**
site page already answer "is each figure still pinned to its source?". The next
data-quality dimension is **coverage**: `assert_national_total_reconciles` and
`assert_euets_coverage_within_eea` already compute the drift between Cairn's
totals and the official aggregates, and the CBS mart already buckets ~30–35% of
national emissions as `UNMAPPED` — but those numbers are discarded once the test
goes green or stay hidden inside a mart. A read-only observability mart could
surface them as standing facts (per source/year: reconciliation drift %,
`UNMAPPED` share, covered share), extending the Data quality page from "is the
chain pinned?" to "how complete is the coverage?".
- *Watch:* a coverage ratio **is** a computation, so keep it strictly an
  *observation* over figures the marts/tests already produce — never a new
  benchmark figure, never in the ESRS E1 export. It is descriptive ("32% of
  national emissions are UNMAPPED"), **never a confidence/quality score** on any
  single figure (that line stays in _Considered and rejected_). Read the share
  from the existing mart; do not re-derive the national total a second way.
- *Touches:* a read-only mart over `benchmark_sector_emissions` /
  `benchmark_installation_emissions` (+ the EEA aggregate), `site/sources/cairn/*.sql`
  + the existing Data quality page, dbt tests.

### 12. Field-completeness (NULL-rate) observability — how fully are the nullable columns populated?
**Value: M · Effort: L · Spine-fit: H**

Several mart columns are deliberately nullable — `lei`, `allocated_total`,
`surrendered_allowances` on the installation mart; the `UNMAPPED`/NULL NACE on
CBS. Their completeness is itself a data-quality signal a user wants to see
("what fraction of installation-years carry an LEI / a free-allocation figure?").
A read-only mart of per-source/per-year populated-vs-NULL counts surfaces that as
a pure observable fact — counts only, no recomputation — and lets reviewed-seed
coverage (e.g. the LEI mapping) be watched as it grows over time.
- *Watch:* pure counts/shares of populated vs NULL; **never impute or fill a
  NULL**, and never present completeness as a quality verdict on the figures
  themselves. Honour the existing nullability semantics — a NULL LEI / allocation
  / surrender is legitimate (a not-yet-mapped or genuinely-absent value), not an
  error to be "fixed".
- *Touches:* a read-only completeness mart over the existing marts,
  `site/sources/cairn/*.sql` + the Data quality page, dbt tests.

### 13. Freshness / staleness observability — how current is each source?
**Value: M · Effort: L · Spine-fit: H**

The manifests pin each source's release and ingest date; the marts know the
latest covered year. How current the data is — release-to-now lag per source, the
known euets.info-vs-EEA latency, the latest `Definitief` CBS year vs the
provisional one — is a data-quality dimension that today lives only in README
prose and the source quirks. A read-only mart (extending `mart_data_provenance`,
which already reads the manifests) could surface freshness as standing facts on
the Data quality page.
- *Watch:* freshness is **descriptive**, computed from pinned dates and the
  marts' `max(year)` — not a freshness SLA or alarm (that is the weekly
  reproducibility job's / Scout's role) and never a score. Don't invent an
  "expected next release" date for a source with no official cadence; state the
  observed lag, not a verdict.
- *Touches:* extend `mart_data_provenance` (or a sibling), `site/sources/cairn/*.sql`
  + the Data quality page, dbt tests.

---

## Considered and rejected
*(Don't re-propose these. If circumstances change, move an item back up with the
new reason it now fits.)*

- **EU ETS free allocation → verified-vs-allocated benchmark.** Shipped: merged
  in PR #31 (2026-06-24). The `allocated_total` measure is live on
  `benchmark_installation_emissions` and surfaced on the Evidence site.
- **Public read/query API.** Category jump in complexity and maintenance for a
  static, R2-pinned Pages site; solves no current user's problem. (ChatGPT review.)
- **Interactive lineage graph.** Same — the static Architecture page covers the
  story at a fraction of the cost.
- **Confidence / quality badges on figures.** Implies a scoring model Cairn
  doesn't have; risks overclaiming. Provenance is already explicit via the manifest.
- **PBL Klimaat- en Energieverkenning (KEV).** Projections, not measurements —
  a different epistemic category that breaks the "verified" purity.
- **CBAM embedded-import emissions.** Thin data, import-focused, premature.
- **EU Industrial Emissions Portal (E-PRTR successor) as a data axis.** Pulls
  beyond Scope-1 GHG into multi-pollutant territory = scope creep. (Only ever
  useful as a facility-identity *aid*, not a benchmark source.)
- **Energy-intensity metrics (emissions per energy unit).** Derived ratios =
  recompute-adjacent; breaks read/relabel.
