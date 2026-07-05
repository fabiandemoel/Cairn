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
-->
```

- `layers:` lists the candidate's full chain in dependency order. Valid layer
  names: `ingestion`, `staging`, `mart`, `site`, `export`. Each value is the
  layer's **sentinel path**: a *new file* that layer creates, mirroring the
  entry's *Layers* plan. The dispatcher opens an issue for the first layer
  whose sentinel does not exist on `main`. Shipped layers **stay in the block**
  (their sentinels exist, so they are skipped, and the generated issue lists
  them as already merged). If an implement PR names the artifact differently,
  it must update the block in the same PR, or the layer will be re-dispatched.
- Sentinel paths must match what actually ships, including the repo's naming
  conventions (for a new source, the paths the scaffold derives from the
  slugs). A stale sentinel makes the dispatcher re-open a done layer — check
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
3. `*Layers:*` — one bullet per layer in the dispatch block, in the same
   order: the artifact to build, the test(s) that guard it, and any naming /
   fixture / discovery notes specific to that layer. A shipped layer keeps a
   one-line bullet recording where it landed (issue/PR and the pointers the
   later layers need).
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

### 3. EU ETS aviation & maritime verified emissions → transport benchmark axis
<!-- dispatch
layers:
  mart: transform/models/marts/benchmark_transport_emissions.sql
  site: site/sources/cairn/transport_emissions.sql
-->
**Value: M · Effort: M · Spine-fit: H**

`benchmark_installation_emissions` deliberately excludes aircraft and maritime
operators (`not is_aircraft_operator and not is_maritime_operator`). Surfacing
them as their *own* labelled transport dimension — benchmarked among
themselves, not folded into the stationary NACE sectors — adds a new benchmark
axis from the already-pinned euets snapshot. Pure read/relabel: the flags are
already staged.
- *Layers:*
  - mart — **shipped** (issue #91, this PR): `benchmark_transport_emissions`, a
    sibling of `benchmark_installation_emissions` over the same euets staging
    models, filtered **to** the aviation/maritime flags instead of away from
    them, with an `operator_type` label column (`accepted_values`:
    aircraft/maritime), benchmarked by operator type, never by NACE section.
  - site (the only remaining scope) — a `transport_emissions.sql` source query
    + a page. State on the page that maritime entered EU ETS only from the
    **2024 compliance year**, so its coverage is partial and recent.
- *Watch:* keep these operators **out** of the stationary national-total
  reconciliation and the EEA stationary `20-99` coverage test — both assume
  stationary, and these operators sit outside CBS national totals and that EEA
  code. Operator flags are nullable and the CI fixture contains no NULLs —
  verify on the full snapshot; a NULL flag means not-confirmed and stays
  excluded from both marts (see the CLAUDE.md gotcha).

### 4. EU ETS carbon leakage list (Delegated Decision 2019/708) → installation sector-exposure flag
<!-- dispatch
layers:
  mart: transform/seeds/carbon_leakage_list.csv
  site: site/sources/cairn/carbon_leakage.sql
-->
**Value: M · Effort: M · Spine-fit: H**

Commission Delegated Decision (EU) 2019/708 of 15 February 2019 (OJ L 120,
8.5.2019, p. 20, and subsequent amendments) lists the NACE and Prodcom sectors
deemed exposed to carbon leakage in ETS Phase 4 (2021–2030); exposed sectors
receive elevated free allocation. Pinning the list as a reviewed seed — like
`sector_mapping_cbs.csv` — lets the mart label every installation with its
exposure status: a pure policy-context read/relabel, no computation. It bridges
the shipped surrendered-vs-verified axis (PRs #42/#54) and the allocation
picture (PR #31), answering "why does this sector receive more free
allocation?" directly from official EU law.
- *Layers:*
  - mart — **shipped** (issue #93, PR #101): the reviewed seed
    `transform/seeds/carbon_leakage_list.csv` (63 rows transcribed verbatim
    from the Decision's Annex points 1–4: NACE code or Prodcom code, sector
    description, the OJ citation per row), registered in `_seeds.yml` with
    schema tests, joined into `benchmark_installation_emissions` as an
    exposure label column on the installation's NACE code (Annex points 1–3
    only — point 4's Prodcom sub-sector rows can't be matched at euets.info's
    grain).
  - site (the only remaining scope) — a `carbon_leakage.sql` source query and
    the flag surfaced on the installations page (a column or filter), reading
    the mart column only.
- *Watch:* the list is versioned to a specific Decision and OJ citation — pin
  it there; if an amending act is issued, add a new seed version rather than
  overwriting. Never derive a free-allocation **entitlement** from this
  flag (that requires benchmark production data Cairn does not have) — surface
  it as a label only.

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
  - mart — `mart_namea_bridge`: the NL residence-vs-territorial bridge per
    sector/year, presented as a provenance/methodology layer.
  - site — a `namea_bridge.sql` source query + a page explaining the two
    attribution principles side by side.
- *Watch:* residence-principle totals do **not** reconcile with 85669NED — the
  divergence is methodological by design, so document the bridge explicitly in
  a note, never a `<0.5%` test. Don't duplicate AEA's cross-country story:
  keep this NL-only, provenance-depth. RIVM (#2) deepens NL provenance from
  the territorial side — complementary, not redundant.

### 6. Coverage & completeness observability — surface the reconciliation drift the tests already compute
<!-- dispatch
layers:
  mart: transform/models/marts/mart_coverage_observability.sql
  site: site/sources/cairn/coverage_observability.sql
-->
**Value: M · Effort: L · Spine-fit: M**

`mart_data_provenance` and the **Data quality** site page already answer "is
each figure still pinned to its source?". The next data-quality dimension is
**coverage**: `assert_national_total_reconciles` and
`assert_euets_coverage_within_eea` already compute the drift between Cairn's
totals and the official aggregates, and the CBS mart already buckets ~30–35% of
national emissions as `UNMAPPED` — but those numbers are discarded once the
test goes green. A read-only mart can surface them as standing facts.
- *Layers:*
  - mart — `mart_coverage_observability`: per source/year, the reconciliation
    drift %, `UNMAPPED` share, and covered share, read from
    `benchmark_sector_emissions` / `benchmark_installation_emissions` (+ the
    EEA aggregate staging) — the same figures the assert tests compare, never a
    re-derivation of a national total by a second route. Guard with
    accepted-range tests, not exact values.
  - site — a `coverage_observability.sql` source query + a section on the
    existing Data quality page, extending it from "is the chain pinned?" to
    "how complete is the coverage?".
- *Watch:* a coverage ratio **is** a computation, so keep it strictly an
  *observation* over figures the marts/tests already produce — never a new
  benchmark figure, never in the ESRS E1 export. It is descriptive ("32% of
  national emissions are UNMAPPED"), **never a confidence/quality score** on
  any single figure (that line stays in _Considered and rejected_).

### 7. Field-completeness (NULL-rate) observability — how fully are the nullable columns populated?
<!-- dispatch
layers:
  mart: transform/models/marts/mart_field_completeness.sql
  site: site/sources/cairn/field_completeness.sql
-->
**Value: M · Effort: L · Spine-fit: H**

Several mart columns are deliberately nullable — `lei`, `allocated_total`,
`surrendered_allowances` on the installation mart; the `UNMAPPED`/NULL NACE on
CBS. Their completeness is itself a data-quality signal ("what fraction of
installation-years carry an LEI / a free-allocation figure?") and lets
reviewed-seed coverage (e.g. the LEI mapping) be watched as it grows over time.
- *Layers:*
  - mart — `mart_field_completeness`: per mart/column/year, populated-vs-NULL
    counts and the resulting share, computed over the existing marts. Counts
    only; enumerate the tracked columns explicitly in the model rather than
    introspecting the schema, so a new nullable column is a reviewed addition.
  - site — a `field_completeness.sql` source query + a section on the Data
    quality page.
- *Watch:* pure counts/shares of populated vs NULL; **never impute or fill a
  NULL**, and never present completeness as a quality verdict on the figures
  themselves. Honour the existing nullability semantics — a NULL LEI /
  allocation / surrender is legitimate (not-yet-mapped or genuinely absent),
  not an error to "fix".

### 8. Freshness / staleness observability — how current is each source?
<!-- dispatch
layers:
  mart: transform/models/marts/mart_source_freshness.py
  site: site/sources/cairn/source_freshness.sql
-->
**Value: M · Effort: L · Spine-fit: H**

The manifests pin each source's release and ingest date; the marts know the
latest covered year. How current the data is — release-to-now lag per source,
the known euets.info-vs-EEA latency, the latest `Definitief` CBS year vs the
provisional one — is a data-quality dimension that today lives only in README
prose and the source quirks.
- *Layers:*
  - mart — `mart_source_freshness`: a Python dbt model (like
    `mart_data_provenance.py`, which already reads the manifests — hence the
    `.py` sentinel): per source, the pinned release and ingest date, the latest
    covered year from the matching mart, and the observed lag between them.
  - site — a `source_freshness.sql` source query + a section on the Data
    quality page.
- *Watch:* freshness is **descriptive**, computed from pinned dates and the
  marts' `max(year)` — not a freshness SLA or alarm (that is the weekly
  reproducibility job's / the dispatcher's role) and never a score. Don't
  invent an "expected next release" date for a source with no official
  cadence; state the observed lag, not a verdict.

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
