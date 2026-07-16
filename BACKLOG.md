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

### 2. Eurostat GGE CRF-sector cross-country benchmark — IPCC sectoral cross-check
<!-- dispatch
layers:
  mart+site: transform/models/marts/mart_gge_sector_totals.sql; site/sources/cairn/gge_sector_totals.sql
-->
**Value: M · Effort: L · Spine-fit: H**

`stg_eurostat__gge` already stages every CRF-sector row (`src_crf` beyond
`TOTXMEMO`) for every EU/EEA country and year — `mart_gge_national_totals`'s
own model doc says the sector-level rows are "kept in the staging layer but
are not surfaced here". Surfacing them is a genuinely new axis: a
cross-country GHG benchmark by **IPCC/UNFCCC CRF top-level category**
(Energy, Industrial processes and product use, Agriculture, Waste, LULUCF),
independent of the NACE-based `benchmark_country_sector_emissions` (Eurostat
AEA) — two different classification systems answering the same "which
sector emits how much, across which countries" question from two
independent EU statistical sources, at zero new-ingestion cost (the source
is already pinned).
- *Layers:*
  - mart+site (fused) — a new mart reading `stg_eurostat__gge` filtered to
    the dataset's top-level CRF codes (confirm the exact `src_crf` code list
    against the pinned parquet before hardcoding a `where src_crf in (...)`
    list; exclude `TOTXMEMO` itself, which `mart_gge_national_totals` already
    owns), grain country × CRF sector × year, `airpol = 'GHG'`,
    `unit = 'MIO_T'`, NULL `obs_value` cells excluded (never zero-filled).
    Guard with a coverage test in the spirit of
    `assert_national_total_reconciles`: the sum of the surfaced CRF sectors
    reconciles against `mart_gge_national_totals`'s own total per
    country-year within a stated tolerance (LULUCF and memo items are
    legitimately excluded from `TOTXMEMO`, so the test must account for that
    gap, not force an exact match). Site query + a new section on the country
    GHG page (`countries-ghg.md`) alongside the existing national totals.
- *Watch:* CRF sectors are an IPCC/UNFCCC classification, not NACE — per
  `mart_gge_national_totals`'s own documented limitation, do not attempt a
  CRF-to-NACE crosswalk here or join it to `benchmark_country_sector_emissions`
  as if they were the same taxonomy. Read/relabel only: filter and rename,
  never recompute a sector total from finer rows.

### 3. RIVM/UNFCCC CRF sectoral tables — IPCC energy-sector breakdown
<!-- dispatch
source: emissieregistratie_energy
dataset: crf_table1a
layers:
  ingestion: sources/emissieregistratie_energy/manifest.yml
  staging: transform/models/staging/stg_emissieregistratie_energy__table1a.sql
  mart+site: transform/models/marts/mart_emissieregistratie_energy_breakdown.sql; site/sources/cairn/emissieregistratie_energy_breakdown.sql
-->
**Value: M · Effort: M · Spine-fit: H**

`ingestion/emissieregistratie_pipeline.py` already pins the Netherlands'
annual UNFCCC CRF submission zip, but reads only each workbook's `Summary1`
sheet (the national total by IPCC category). The same already-pinned
workbooks carry the standard CRF Reporter breakdown of the Energy sector's
sub-categories (IPCC 1.A.1–1.A.4: energy industries, manufacturing
industries and construction, transport, other sectors) — RIVM's own,
independently reported sectoral split of the national inventory, one layer
upstream of CBS's SBI/NACE-mapped sectors. This is a second cross-check axis
alongside the already-shipped `mart_emissieregistratie_cbs_reconciliation`
(which only cross-checks the national *total*), this time at sector
granularity.
- *Layers:*
  - ingestion — a second dataset off the **same** archive URL
    (`ingestion/emissieregistratie_pipeline.py`'s `DEFAULT_URL` — no new
    external source to discover or pin), as its own source/manifest
    (`sources/emissieregistratie_energy/manifest.yml`, dataset
    `crf_table1a`, mirroring how `cbs_namea` is a separate source from `cbs`
    despite sharing an origin): parse the CRF Reporter's `Table1.A(a)s1`–`s4`
    sheets (IPCC 1.A energy sub-categories, by fuel type) from each
    inventory-year workbook already inside the pinned zip. Confirm the exact
    sheet name(s) and data range against the real downloaded workbook before
    coding (mirroring how the existing pipeline verified `Summary1`'s
    `B8:O67` range) — do not assume the layout from this description alone.
  - staging — `stg_emissieregistratie_energy__table1a`, a 1:1 typed view,
    mirroring `stg_emissieregistratie__crf_summary1`'s all-VARCHAR-then-cast
    pattern.
  - mart+site (fused) — `mart_emissieregistratie_energy_breakdown`: RIVM's own
    IPCC 1.A.1–1.A.4 split of the national energy-sector total, per
    inventory year, presented as its own standalone read/relabel figure
    (never summed against or reconciled to CBS's NACE sections — the two are
    independent classification systems, same caveat as `mart_namea_bridge`).
    Site query + a new section on the Data quality page.
- *Watch:* IPCC 1.A sub-categories and NACE/SBI sections are different
  classification systems — present this as an independent RIVM-native view,
  never a forced crosswalk or a tight-tolerance reconciliation test against
  CBS. Read/relabel only, mirroring `crf_summary1`'s "raw faithfulness": keep
  every category row, exclude the units sub-header row in staging, never
  invent a missing category.

### 4. Methodology Sources table documents only 3 of 8 pinned sources (P1)
<!-- dispatch
layers:
  site: site/sources/cairn/methodology_sources.sql
-->
**Value: M · Effort: L · Spine-fit: H**

*(From the 2026-07-15 site review — a provenance-documentation fix rather than a
new benchmark axis, kept here as a dispatchable single-layer site candidate. Its
sibling site-review fixes shipped in PR #140; see _Considered and rejected_.)*

`index.md` promises "the full provenance of every figure on this site", but
`methodology.md`'s Sources table lists only CBS `85669NED`, euets.info, and EEA —
while five more pinned sources feed live pages/marts: Eurostat AEA (`sources/eurostat/`,
/sectors-eu), Eurostat GGE (`sources/eurostat_gge/`, /countries-ghg), CBS NAMEA
`83300NED` (`sources/cbs_namea/`, /namea-bridge), emissieregistratie
(`sources/emissieregistratie/`, the reconciliation mart), and GLEIF/LEI (the LEI
columns on the installation benchmark). For a provenance-first product, the
provenance doc lagging the data is the worst place to drift.
- *Layers:*
  - site — extend the Sources table in `site/pages/methodology.md` so every
    `sources/<slug>/manifest.yml` that feeds a published page or mart has a row
    (source, role, dataset, manifest path), plus a 2–5-bullet method-and-limitations
    subsection per newly documented source in the same register as the existing
    CBS/EU ETS ones (summarise and link the caveats already on /sectors-eu,
    /countries-ghg and /namea-bridge rather than duplicate them). Harden it against
    re-drift by rendering the table from `cairn.data_provenance` via a **new**
    `site/sources/cairn/methodology_sources.sql` query (the sentinel commits the
    candidate to this variant); keep the prose subsections static. Guard:
    `evidence-build` green.
- *Watch:* docs/site only — no mart or manifest changes. This is the *documentation*
  of invariant 1 (pinned provenance) catching up, not a numeric change. If a source
  is intentionally left undocumented, rescope the homepage "every figure" claim
  instead of leaving it false.

### 5. Site chrome: Evidence default `twitter:site @evidence_dev`, no og:image, chart palette off-brand (P2)
<!-- dispatch
layers:
  site: site/static/og-image.png
-->
**Value: L · Effort: L · Spine-fit: H**

*(From the 2026-07-15 site review — a presentation/branding fix rather than a new
benchmark axis, kept here as a dispatchable single-layer site candidate.)*

Two small credibility leaks when the site is shared or compared to the portfolio:
social meta still carries Evidence's default `twitter:site` (`@evidence_dev`) with no
og:image override; and `site/evidence.config.yaml` charts lead with `#236aa4` (light
and dark, lines 9/20) while the homepage pill and fabiandemoel.nl use Tailwind
blue-600 `#2563eb` — two different blues on one brand.
- *Layers:*
  - site — override the social meta via Evidence's head/customization mechanism
    (remove or replace `twitter:site`, set og:image from a **new** static branded card
    asset `site/static/og-image.png` — the sentinel); align the first `colorPalettes`
    entry in `site/evidence.config.yaml` (light + dark) with the brand blue `#2563eb`,
    keeping dark-mode contrast acceptable and leaving the rest of the categorical
    palette unless it clashes. Guard: rendered HTML head no longer advertises
    `@evidence_dev`, og:image resolves, first series colour on /sectors and
    /installations is the brand blue in both themes, `evidence-build` green.
- *Watch:* presentation only — no data or copy changes.

---

## Considered and rejected
*(Don't re-propose these. If circumstances change, move an item back up with the
new reason it now fits.)*

- **Homepage information architecture (site review 6).** Shipped: merged in PR #140
  (2026-07-15). `index.md` reworked into an "NL benchmark spine" tier plus an "EU
  context & cross-checks" tier surfacing /sectors-eu, /countries-ghg, /namea-bridge and
  /transport (previously reachable only via the sidebar); /architecture linked from
  "Why it is auditable"; the misleading "▲ 2024" BigValue comparison slot dropped and
  the year moved to a caption; the audience line no longer names "software vendors".
- **NACE-coverage disclosure on /installations (site review 7).** Shipped: merged in
  PR #140 (2026-07-15). The NACE-null exclusion behind the benchmarked-installation
  count is now disclosed next to the source statement with a /data-quality coverage
  link, and the homepage count is captioned "(stationary, NACE-mapped)". No SQL change
  — the count itself was already correct.
- **Glossary links on the data pages (site review 9).** Shipped: merged in PR #140
  (2026-07-15). First-use glossary terms (NACE section, verified emissions,
  CO₂-equivalent, residence/territorial principle) on /sectors, /installations,
  /transport, /sectors-eu and /countries-ghg now link the /data-dictionary business
  glossary (its `#business-glossary` section anchor, since the glossary renders as a
  searchable table with no per-term anchors).
- **EU ETS excess emissions penalty — compliance-enforcement axis.** Shipped:
  merged in this PR (2026-07-10). `excess_emissions_penalty_eur` is live on
  `benchmark_installation_emissions`, guarded by `assert_penalty_only_on_shortfall`,
  and surfaced in a new "Compliance enforcement" section on the installations page.
- **Emissieregistratie (RIVM) → deepen NL provenance + granularity.** Shipped:
  merged in this PR (2026-07-08). `mart_emissieregistratie_cbs_reconciliation`
  is live, cross-checking the CRF Summary1 national total against CBS
  85669NED's national total, guarded by `assert_emissieregistratie_nl_total_within_cbs`
  (10% tolerance).

- **CBS NAMEA air emission accounts — residence-principle sector breakdown.**
  Shipped: merged in this PR (2026-07-08). `mart_namea_bridge` is live,
  bridging NAMEA (83300NED) residence-principle CO2 emissions against
  `benchmark_sector_emissions`' (85669NED) territorial-principle total GHG
  CO2-eq per NACE section and year, sourced from `sources/cbs_namea/manifest.yml`;
  the `namea_bridge.sql` source query and bridge page (`namea-bridge.md`) are
  deployed on the Evidence site.

- **CBS NAMEA — residence-principle GHG composition by gas.** Shipped: merged
  in this PR (2026-07-15). `mart_namea_gas_composition` and its `namea_gas_composition.sql`
  source query are live, sourced from `sources/cbs_namea/manifest.yml`; the gas
  breakdown is surfaced in a new section on the NAMEA bridge page (`namea-bridge.md`).

- **Field-completeness (NULL-rate) observability — how fully are the nullable
  columns populated?** Shipped: merged in this PR (2026-07-07).
  `mart_field_completeness` (per mart/tracked column/year, populated-vs-NULL
  counts and share) and its `field_completeness.sql` site source query are
  live, surfaced in a new section on the Data quality page.

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
- **GHG composition by gas type per sector.** Shipped: merged in this PR
  (2026-07-10). `mart_sector_gas_composition` and `sector_gas_composition.sql`
  are live, sourced from `sources/cbs/manifest.yml`; the gas-composition
  breakdown is surfaced in a new section on the `sectors.md` page.
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
