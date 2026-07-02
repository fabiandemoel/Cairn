# BACKLOG.md — curated menu of candidate expansions for Cairn

This file is the **menu** the automation loop draws from. It is curated, not a
dumping ground. Agents read it; a human merges every change to it.

- **Replenish** (weekly, LLM) proposes *new* candidates and re-scores existing
  ones, as a docs-only PR. It may move dead/off-spine ideas into _Considered and
  rejected_ so they don't get re-proposed. It also maintains each candidate's
  `<!-- dispatch -->` block (schema below).
- **Dispatch** (`cairn-dispatch.yml`, no-LLM; on every merge to main + weekly)
  turns the menu into issues deterministically: the weekly freshness check opens
  a `data-refresh` issue per stale source, and the backlog dispatcher opens one
  issue for the top candidate's next not-yet-built layer, driven by the
  `<!-- dispatch -->` blocks.
- **Implement** (LLM) does the work for an issue you've labelled `approved`, on
  a branch, as a PR. The existing CI (dbt build, tests, `benchmark-diff`,
  `evidence-build`) is the gate.

## Dispatch metadata (machine-read — keep it accurate)

Every entry under _Live candidates_ carries an HTML comment directly below its
heading that the no-LLM dispatcher parses:

```
<!-- dispatch
source: <slug>            (optional — lowercase_with_underscores; feeds the
dataset: <slug>            ingestion/staging scaffold in cairn-implement)
layers:
  <layer>: <sentinel path>
-->
```

- `layers:` lists this candidate's remaining work in dependency order. Valid
  layer names: `ingestion`, `staging`, `mart`, `site`, `export`. Each value is
  the layer's **sentinel path**: a *new file* that layer creates (derived from
  the "Touches" line). The dispatcher opens an issue for the first layer whose
  sentinel does not exist on `main` — so if an implement PR names the artifact
  differently, it must update the block in the same PR.
- A candidate that must not be dispatched yet carries `hold: <reason>` instead
  of (or in addition to) `layers:`.
- A candidate without a block is skipped with a note in the dispatch run
  summary — add the block when the candidate is ready to be worked.

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

### 1. EUA carbon price → € valuation overlay
<!-- dispatch
hold: watch note — site-overlay-only, deferred unless commercial positioning becomes the active priority
-->
**Value: H (commercial) · Effort: M · Spine-fit: L**

Adds "these emissions = €X at the current EUA price" — directly addresses the
commercial-positioning gap. **Lowest spine-fit:** the price is volatile and
time-varying, and tonnes × price is a computation, both in tension with the
pinned-snapshot, read/relabel model.
- *Status:* the **ingestion layer shipped** — merged via issue #72 (2026-06-30):
  `ingestion/eua_pipeline.py` + `sources/eua/manifest.yml`, pinned from the EEX
  auction archive. Per CLAUDE.md invariant 5 / the "eua" recurring-maintenance
  entry it stays **ingestion-only by design** — no staging model, no mart
  column, no site overlay, and it must never enter a dbt mart or the ESRS E1
  export. Remaining scope here (the labelled site overlay below) is still
  undone and gated on the watch note, not on missing plumbing.
- *Watch:* keep it strictly as a **labelled context overlay** in the site, sourced
  from official auction results, pinned per release like any other source. Never
  a stored mart figure, never in the ESRS E1 export. Defer unless commercial
  positioning becomes the active priority.

### 2. Emissieregistratie (RIVM) → deepen NL provenance + granularity
<!-- dispatch
source: rivm
dataset: emissieregistratie
layers:
  ingestion: sources/rivm/manifest.yml
  staging: transform/models/staging/stg_rivm__emissieregistratie.sql
  mart: transform/models/marts/mart_rivm_cbs_reconciliation.sql
-->
**Value: M · Effort: M · Spine-fit: H**

The authoritative source under NL's UNFCCC submission; finer per substance/
sector/region than CBS. Lets a CBS-derived figure be traced one layer deeper.
- *Watch:* it partly overlaps CBS national totals — keep it as a cross-check /
  provenance layer, **not** a second authority for the same figure. Add a
  reconciliation test against the CBS national total.
- *Touches:* new pipeline + manifest, staging, a provenance/cross-check model.

### 3. EU ETS aviation & maritime verified emissions → transport benchmark axis
<!-- dispatch
layers:
  mart: transform/models/marts/benchmark_transport_emissions.sql
  site: site/sources/cairn/transport_emissions.sql
-->
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

### 4. EU ETS carbon leakage list (Delegated Regulation 2019/708) → installation sector-exposure flag
<!-- dispatch
layers:
  mart: transform/seeds/carbon_leakage_list.csv
  site: site/sources/cairn/carbon_leakage.sql
-->
**Value: M · Effort: M · Spine-fit: H**

Commission Delegated Regulation (EU) 2019/708 (OJ L 120, 11.5.2019, and
subsequent amendments) lists the NACE and PRODCOM sectors deemed exposed to
carbon leakage in ETS Phase 4 (2021–2030); exposed sectors receive elevated free
allocation. Pinning the list as a reviewed seed — like `sector_mapping_cbs.csv`
— lets the mart label every installation with its carbon-leakage-exposure status:
a pure policy-context read/relabel, no computation. Answers "why does this sector
receive more free allocation?" directly from official EU law, providing a
provenance bridge between the shipped surrendered-vs-verified axis (PR #42/#54)
and the allocation picture shipped in PR #31.
- *Watch:* the list is versioned to a specific Regulation and OJ citation — pin
  it there; if an amending regulation is issued, open a new seed version rather
  than overwriting. Never derive a free-allocation **entitlement** from this flag
  (that requires benchmark production data Cairn does not have); surface it as a
  label only. Every seed change goes through a PR and `benchmark-diff` so the
  numeric impact on the allocation comparison is visible.
- *Touches:* reviewed seed `seeds/carbon_leakage_list.csv` (NACE/PRODCOM codes +
  regulation citation), a mart dimension column, `site/sources/cairn/*.sql`, a page.

### 5. CBS NAMEA air emission accounts — residence-principle sector breakdown
<!-- dispatch
source: cbs_namea
dataset: air_emissions
layers:
  ingestion: sources/cbs_namea/manifest.yml
  staging: transform/models/staging/stg_cbs_namea__air_emissions.sql
  mart: transform/models/marts/mart_namea_bridge.sql
  site: site/sources/cairn/namea_bridge.sql
-->
**Value: M · Effort: M · Spine-fit: H**

CBS publishes NAMEA (National Accounting Matrix including Environmental Accounts)
air emission data: annual GHG emissions attributed to Dutch economic actors by
NACE sector, using the **residence principle**. Unlike 85669NED
(territorial/production principle), NAMEA attributes emissions to the industry of
the emitting company's registered residence. The two methodologies diverge for
transport, shipping, and multinationals with cross-border activity. Surfacing
NAMEA as a provenance layer explains why 85669NED and the Eurostat AEA (shipped,
`benchmark_country_sector_emissions`) diverge for the same sector — it is the
Dutch side of the AEA picture, directly from CBS via the same OData v4 API.
- *Watch:* because it uses the residence principle, NAMEA national totals do
  **not** directly reconcile with 85669NED — document the bridge explicitly in a
  note rather than a `<0.5%` test (the divergence is methodological by design,
  not an error). Avoid duplicating AEA's cross-country story here; keep this as a
  provenance-depth / methodology-bridge layer for NL only. RIVM (#2) also
  deepens NL provenance but from the territorial side — these are complementary,
  not redundant.
- *Touches:* `ingestion/cbs_namea_pipeline.py`, `sources/cbs_namea/manifest.yml`,
  staging model, a provenance/cross-check model, `site/sources/cairn/*.sql`.

### 6. Coverage & completeness observability — surface the reconciliation drift the tests already compute
<!-- dispatch
layers:
  mart: transform/models/marts/mart_coverage_observability.sql
  site: site/sources/cairn/coverage_observability.sql
-->
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

### 7. Field-completeness (NULL-rate) observability — how fully are the nullable columns populated?
<!-- dispatch
layers:
  mart: transform/models/marts/mart_field_completeness.sql
  site: site/sources/cairn/field_completeness.sql
-->
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

### 8. Freshness / staleness observability — how current is each source?
<!-- dispatch
layers:
  mart: transform/models/marts/mart_source_freshness.py
  site: site/sources/cairn/source_freshness.sql
-->
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
  reproducibility job's / the dispatcher's role) and never a score. Don't invent an
  "expected next release" date for a source with no official cadence; state the
  observed lag, not a verdict.
- *Touches:* extend `mart_data_provenance` (or a sibling), `site/sources/cairn/*.sql`
  + the Data quality page, dbt tests.

---

## Considered and rejected
*(Don't re-propose these. If circumstances change, move an item back up with the
new reason it now fits.)*

- **EUTL surrendered allowances → verified-vs-surrendered compliance-integrity
  axis.** Shipped: mart layer merged in PR #42 (2026-06-26), site layer merged in
  PR #54 (2026-06-27). `surrendered_allowances_t_co2eq` is live on
  `benchmark_installation_emissions` and surfaced on the installations page.
- **GLEIF / LEI → installation → legal-entity mapping.** Shipped: merged in
  PR #66 (2026-06-27). The `lei_mapping_euets` seed is live; `benchmark_installation_emissions`
  carries `lei`, `gleif_legal_name`, and `parent_company`; the ESRS E1 export
  carries the LEI for entity-level roll-up. Coverage grows via reviewed PRs.
- **Eurostat Air Emissions Accounts (`env_ac_ainah_r2`) → cross-country sector benchmark.**
  Shipped: merged in PR #61 (2026-06-22). `benchmark_country_sector_emissions` is live,
  sourced from `sources/eurostat/manifest.yml`; the EU sector benchmark page
  (`sectors-eu.md`) is deployed on the Evidence site.
- **EUTL installation identity enrichment (parent company, ETS activity, geo).**
  Shipped: merged in PR #66 (2026-06-27). `parent_company`, `ets_activity_label`,
  `country_label`, `latitude`, and `longitude` are promoted to
  `benchmark_installation_emissions` and surfaced on the installations page.
- **Eurostat `env_air_gge` — EU member-state GHG inventory national totals.**
  Shipped: ingestion pipeline merged in PR #67 (2026-06-28); staging model
  (`stg_eurostat__gge`), cross-check test (`assert_gge_nl_total_within_cbs`, <10%
  tolerance — UNFCCC submission vs CBS revision cycles produce up to ~7% gap in
  recently-revised years), mart (`mart_gge_national_totals`), site source query,
  and country GHG page (`countries-ghg.md`) completed in the 2026-06-30 cleanup.
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
