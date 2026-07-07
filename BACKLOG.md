# BACKLOG.md — curated menu of candidate expansions for Cairn

This file is the **menu** the automation loop draws from. It is curated, not a
dumping ground. Agents read it; a human merges every change to it.

- **Replenish** (weekly, LLM) proposes *new* candidates and re-scores existing
  ones, as a docs-only PR. It may move dead/off-spine ideas into _Considered and
  rejected_ so they don't get re-proposed. It also maintains each candidate's
  `<!-- dispatch -->` block and *Layers* plan (schema and format below).
- **Dispatch** (`cairn-dispatch.yml`, no-LLM; on every merge to main + weekly)
  turns the menu into issues deterministically: the weekly freshness check opens
  a `data-refresh` issue per stale source, and the backlog dispatcher opens one
  issue for the top candidate's next not-yet-built layer, driven by the
  `<!-- dispatch -->` blocks. The issue body quotes the candidate's entry
  **verbatim** — no LLM rewrites or reinterprets it on the way.
- **Implement** (LLM) does the work for an issue you've labelled `approved`, on
  a branch, as a PR. The existing CI (dbt build, tests, `benchmark-diff`,
  `evidence-build`) is the gate.

Because no LLM sits between this file and the implement agent anymore, each
candidate entry **is** the spec the implementer receives. Write entries so a
single layer can be built from them without re-deriving context: what each
layer delivers, which test guards it, and the caveats that aren't visible from
the tree.

## Dispatch metadata (machine-read — keep it accurate)

Every entry under _Live candidates_ carries an HTML comment directly below its
heading that the no-LLM dispatcher parses:

```
<!-- dispatch
source: <slug>            (required when the candidate adds a new source; both
dataset: <slug>            slugs are lowercase_with_underscores and drive the
                           no-LLM ingestion/staging scaffold in cairn-implement,
                           which derives sources/<source>/manifest.yml and
                           stg_<source>__<dataset>.sql from them)
layers:
  <layer>: <sentinel path>
  <layer>+<layer>: <sentinel path>; <sentinel path>   (a fused step — see below)
-->
```

- `layers:` lists the candidate's dispatch steps in dependency order. Valid
  layer names: `ingestion`, `staging`, `mart`, `site`, `export`. Each value is
  the step's **sentinel path**: a *new file* that step creates, mirroring the
  entry's *Layers* plan. The dispatcher opens an issue for the first step
  whose sentinel does not exist on `main`. Shipped steps **stay in the block**
  (their sentinels exist, so they are skipped, and the generated issue lists
  them as already merged). If an implement PR names the artifact differently,
  it must update the block in the same PR, or the step will be re-dispatched.
- **Fused step (one issue, several layers).** Join two or more layer names with
  `+` (e.g. `mart+site`) to dispatch them as a **single** issue/PR, with one
  `;`-separated sentinel per part (in the same order as the joined names). The
  fused step is only "done" once **every** sentinel exists, so the one issue
  delivers all its layers. Use this for a `mart+site` pair: the site page is a
  thin read-only query over the mart, can't be built before it, and a separate
  approve→PR→CI round-trip buys little review value. Constraints the parser
  enforces: the fused names must be **distinct**, in **dependency order**, and
  **not scaffoldable** — `ingestion`/`staging` keep their own step because the
  scaffold and the (ingestion-only) source-research gate key off a single-layer
  issue. So fuse `mart+site` (and `mart+site+export` if ever), never anything
  touching ingestion/staging. Only fuse layers that are **both still pending**;
  once a layer has shipped, leave it as its own recorded sentinel rather than
  retroactively fusing a done layer with a pending one (that would re-surface
  the shipped layer in the new issue's scope).
- Sentinel paths must match what actually ships, including the repo's naming
  conventions (for a new source, the paths the scaffold derives from the
  slugs). A stale sentinel makes the dispatcher re-open a done step — check
  the blocks against the tree when curating.
- A candidate that must not be dispatched yet carries `hold: <reason>` instead
  of (or in addition to) `layers:`.
- A candidate whose ingestion hinges on an upstream identifier that is not yet
  verified (a catalogue table id, a dataset code, a download URL) carries
  `hold: needs <identifier> — <where to look>` until a human resolves it and
  writes the identifier into the entry. A "the exact id must be identified
  first" caveat in the *Watch* prose alone does **not** stop the no-LLM
  dispatcher — issue #95 / PR #103 shipped a blocked scaffold exactly that way.
- A candidate without a block is skipped with a note in the dispatch run
  summary — add the block when the candidate is ready to be worked.

## Entry format (the entry is the spec)

Every live candidate follows the same shape, so the verbatim quote in the
dispatched issue reads as a per-layer spec:

1. `### <n>. <name>` heading, then the `<!-- dispatch -->` block, then the
   score line (`**Value: · Effort: · Spine-fit:**`).
2. One short paragraph: what the candidate adds and why it belongs on the
   spine.
3. `*Layers:*` — one bullet per dispatch step, in the same order: the
   artifact to build, the test(s) that guard it, and any naming / fixture /
   discovery notes specific to that step. A **fused** step (e.g. `mart+site`)
   gets one bullet that describes **all** its artifacts (both sentinels), since
   they ship in one PR. A shipped step keeps a one-line bullet recording where
   it landed (issue/PR and the pointers the later steps need).
4. `*Watch:*` — the caveats an implementer must not violate: methodology
   limits, what stays out of which test, what must never be computed.

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
hold: site-overlay-only; deferred unless commercial positioning becomes the active priority
layers:
  ingestion: sources/eua/manifest.yml
  staging: transform/models/staging/stg_eua__auction_results.sql
  site: site/sources/cairn/eua_price.sql
-->
**Value: H (commercial) · Effort: M · Spine-fit: L**

Adds "these emissions = €X at the current EUA price" — directly addresses the
commercial-positioning gap. Lowest spine-fit: the price is volatile and
time-varying, and tonnes × price is a computation, both in tension with the
pinned-snapshot, read/relabel model.
- *Layers:*
  - ingestion — **shipped** (issue #72, 2026-06-30): `ingestion/eua_pipeline.py`
    + `sources/eua/manifest.yml`, pinned from the EEX auction-report archive.
  - staging — **shipped** (issue #84, this PR): `stg_eua__auction_results`, a
    read-only read/relabel view over the pinned auction parquet via the
    `eua_raw_dir` var (CI fixture under `tests/fixtures/eua/<release>/`, `not_null`/
    `unique` on the natural key, and `eua` added to `verify_reproducibility.py`).
    Deliberately **not** `ref`'d by any mart — a strictly-labelled context table,
    not a benchmark figure (this was the "revisit invariant 5 first" the site
    layer was gated behind; the price still never enters a mart or the export).
  - site (the only remaining scope, gated on the hold) — a strictly **labelled
    context overlay** on the site, sourced from the pinned auction results (now
    queryable via `stg_eua__auction_results`) and versioned per release.
- *Watch:* never a stored mart figure, never in the ESRS E1 export, and no
  `tonnes × price` / currency computation anywhere — the staging view is a plain
  typed pass-through. The hold is positioning, not missing plumbing — lift it
  only when the € overlay becomes the active priority.

### 2. Emissieregistratie (RIVM) → deepen NL provenance + granularity
<!-- dispatch
source: emissieregistratie
dataset: crf_summary1
layers:
  ingestion: sources/emissieregistratie/manifest.yml
  staging: transform/models/staging/stg_emissieregistratie__crf_summary1.sql
  mart: transform/models/marts/mart_emissieregistratie_cbs_reconciliation.sql
-->
**Value: M · Effort: M · Spine-fit: H**

The authoritative inventory under NL's UNFCCC submission; finer per substance/
sector than CBS. Lets a CBS-derived figure be traced one layer deeper on the
territorial side (complementary to NAMEA's residence-side story, candidate #5).
- *Layers:*
  - ingestion — **shipped** (issue #83, merged 2026-07-01):
    `ingestion/emissieregistratie_pipeline.py` pins the CRF "Summary1" workbook
    from the UNFCCC national-inventory submission archive
    (emissieregistratie.nl's own portal has no headless-fetchable data API —
    see the pipeline's module docstring). The manifest ships unpinned
    (`snapshots: []`); the first real `cairn-ingest.yml` run establishes the pin.
  - staging — `stg_emissieregistratie__crf_summary1`: stage the pinned parquet
    into one row per CRF category/gas/year with clearly labelled units, plus
    the usual schema tests (`not_null`/`unique` on the grain). Add the
    `emissieregistratie_crf_summary1_raw_dir` var to `transform/dbt_project.yml`
    pointing at the committed fixture
    (`tests/fixtures/emissieregistratie/crf_summary1/<release>/`, rebuilt via
    `scripts/build_emissieregistratie_fixture.py`).
  - mart — `mart_emissieregistratie_cbs_reconciliation`: a cross-check model
    reconciling the CRF national total against the CBS national total, guarded
    by a tolerance test in the `assert_gge_nl_total_within_cbs` mould. UNFCCC
    submission timing vs CBS revision cycles applies here too — set the
    tolerance from the observed gap and justify it in the test, don't default
    to 0.5%.
- *Watch:* it partly overlaps CBS national totals — keep it a cross-check /
  provenance layer, **not** a second authority for the same figure. No site
  layer is planned; if one turns out to be warranted, add it to the dispatch
  block and this plan first.

### 3. CBS NAMEA air emission accounts — residence-principle sector breakdown
<!-- dispatch
source: cbs_namea
dataset: air_emissions
layers:
  ingestion: sources/cbs_namea/manifest.yml
  staging: transform/models/staging/stg_cbs_namea__air_emissions.sql
  mart+site: transform/models/marts/mart_namea_bridge.sql; site/sources/cairn/namea_bridge.sql
-->
**Value: M · Effort: M · Spine-fit: H**

CBS publishes NAMEA (National Accounting Matrix including Environmental
Accounts) air emission data: annual GHG emissions by NACE sector under the
**residence principle**, unlike 85669NED (territorial/production principle).
The two diverge for transport, shipping, and multinationals with cross-border
activity. NAMEA is the Dutch side of the Eurostat AEA picture (shipped:
`benchmark_country_sector_emissions`) and explains why AEA and 85669NED diverge
for the same sector — directly from CBS via the same OData v4 API.
- *Layers:*
  - ingestion — `ingestion/cbs_namea_pipeline.py` + `sources/cbs_namea/manifest.yml`,
    following `cbs_pipeline.py` (OData v4, `Modified`-based release detection,
    idempotent no-new-release exit). The NAMEA table is **83300NED** ("Emissies
    naar lucht door de Nederlandse economie; nationale rekeningen", annual
    November update, verified live 2026-07-05); the v3-API-returns-406 gotcha
    applies here too.
  - staging — `stg_cbs_namea__air_emissions`: NACE sector code, year, gas,
    value, with the `cbs_namea_air_emissions_raw_dir` var and a small committed
    fixture like the other CBS source.
  - mart + site (fused — one PR) — `mart_namea_bridge`: the NL
    residence-vs-territorial bridge per sector/year, presented as a
    provenance/methodology layer; **plus** its read-only site layer in the same
    PR — a `namea_bridge.sql` source query + a page explaining the two
    attribution principles side by side. The site only reads the mart; keep the
    bridge logic in the mart, tested there.
- *Watch:* residence-principle totals do **not** reconcile with 85669NED — the
  divergence is methodological by design, so document the bridge explicitly in
  a note, never a `<0.5%` test. Don't duplicate AEA's cross-country story:
  keep this NL-only, provenance-depth. RIVM (#2) deepens NL provenance from
  the territorial side — complementary, not redundant.

### 4. Field-completeness (NULL-rate) observability — how fully are the nullable columns populated?
<!-- dispatch
layers:
  mart+site: transform/models/marts/mart_field_completeness.sql; site/sources/cairn/field_completeness.sql
-->
**Value: M · Effort: L · Spine-fit: H**

Several mart columns are deliberately nullable — `lei`, `allocated_total`,
`surrendered_allowances` on the installation mart; the `UNMAPPED`/NULL NACE on
CBS. Their completeness is itself a data-quality signal ("what fraction of
installation-years carry an LEI / a free-allocation figure?") and lets
reviewed-seed coverage (e.g. the LEI mapping) be watched as it grows over time.
- *Layers:*
  - mart + site (fused — one PR) — `mart_field_completeness`: per
    mart/column/year, populated-vs-NULL counts and the resulting share,
    computed over the existing marts. Counts only; enumerate the tracked columns
    explicitly in the model rather than introspecting the schema, so a new
    nullable column is a reviewed addition. **Plus** its read-only site layer in
    the same PR — a `field_completeness.sql` source query + a section on the
    Data quality page.
- *Watch:* pure counts/shares of populated vs NULL; **never impute or fill a
  NULL**, and never present completeness as a quality verdict on the figures
  themselves. Honour the existing nullability semantics — a NULL LEI /
  allocation / surrender is legitimate (not-yet-mapped or genuinely absent),
  not an error to "fix".

---

## Considered and rejected
*(Don't re-propose these. If circumstances change, move an item back up with the
new reason it now fits.)*

- **Freshness / staleness observability — how current is each source?**
  Shipped: merged in this PR (2026-07-07). `mart_source_freshness` (per source,
  pinned release/ingest date, latest covered year, and the observed
  ingest-age/coverage-lag) and its `source_freshness.sql` site source query are
  live, surfaced in a new section on the Data quality page.

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
- **EU ETS aviation & maritime verified emissions → transport benchmark axis.**
  Shipped: merged in this PR (2026-07-05). `benchmark_transport_emissions` is
  live, sourced from `sources/euets/manifest.yml`; the transport benchmark page
  (`transport.md`) is deployed on the Evidence site.
- **EU ETS carbon leakage list (Delegated Decision 2019/708) → installation
  sector-exposure flag.** Shipped: mart layer merged in PR #101 (issue #93);
  site layer merged in this PR (2026-07-05). `carbon_leakage_exposed` and its
  supporting sector description/OJ citation are live on
  `benchmark_installation_emissions` and surfaced on the installations page.
- **Coverage & completeness observability — surface the reconciliation drift
  the tests already compute.** Shipped: merged in this PR (2026-07-05).
  `mart_coverage_observability` is live, surfacing the reconciliation drift,
  UNMAPPED share, and covered share on the Data quality site page.
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
