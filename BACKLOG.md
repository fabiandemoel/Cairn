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

### 1. EU ETS free allocation → verified-vs-allocated benchmark
**Value: H · Effort: L · Spine-fit: H**

Freely allocated allowances per installation-year is, after verified emissions
itself, the most interesting ETS axis: who emits above/below their free grant.
**No new source** — the field is already staged: `stg_euets__compliance`
exposes `allocated_total` (cast from the pinned euets.info snapshot's
`allocatedTotal`). Add a measure on `benchmark_installation_emissions` (or a
sibling mart) and surface via `site/sources/cairn/`. Pure read/relabel.
- *Watch:* the allocation column is **confirmed present** in the pinned snapshot
  (`allocated_total`), so the EEA / DG-CLIMA NIM fallback is no longer needed.
  Keep it read/relabel: the verified-vs-allocated comparison is a labelled
  measure, never an invented figure; missing values stay `NULL` + a note.
- *Touches:* one mart, `site/sources/cairn/*.sql`, a page, CI fixture (column
  already in the fixture's `compliance.parquet`).
- *Status:* dispatched and approved as issue #27 — implementation in flight.

### 2. GLEIF / LEI → installation → legal-entity mapping
**Value: H · Effort: M · Spine-fit: H**

Open, authoritative entity IDs. Makes the benchmark meaningful at company level
("all of operator X's installations") and is the natural bridge to the ESRS E1
export, whose disclosures are entity-level, not installation-level.
- *Watch:* the mapping **is** the methodology — a reviewed seed like
  `sector_mapping_cbs.csv`. Never invent an LEI; unmatched operators get `NULL`
  + a `notes` entry. The mapping change shows its impact via `benchmark-diff`.
  The source's free-text `parent_company` (see candidate #6) is a useful *match
  aid*, not the authority.
- *Touches:* a reviewed seed, an entity dimension on the installation mart,
  optional entity rollup in the ESRS export.

### 3. Eurostat Air Emissions Accounts (`env_ac_ainah_r2`) → cross-country sector benchmark
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

### 4. EUA carbon price → € valuation overlay
**Value: H (commercial) · Effort: M · Spine-fit: L**

Adds "these emissions = €X at the current EUA price" — directly addresses the
commercial-positioning gap. **Lowest spine-fit:** the price is volatile and
time-varying, and tonnes × price is a computation, both in tension with the
pinned-snapshot, read/relabel model.
- *Watch:* keep it strictly as a **labelled context overlay** in the site, sourced
  from official auction results, pinned per release like any other source. Never
  a stored mart figure, never in the ESRS E1 export. Defer unless commercial
  positioning becomes the active priority.

### 5. EUTL surrendered allowances → verified-vs-surrendered compliance-integrity axis
**Value: M · Effort: L · Spine-fit: H**

The third leg of the EUTL triple, after allocation (#1) and verified emissions:
allowances actually surrendered per installation-year. Already staged —
`stg_euets__compliance` exposes `surrendered`. Surfacing "surrendered vs
verified" is a pure read/relabel provenance axis over the pinned snapshot; no
new source, no recomputation. Natural to ship alongside #1.
- *Watch:* surrender can lag and a single surrender may cover multiple years —
  present it as a **labelled measure**, not a recomputed running balance, and
  never as a compliance *verdict* (that would drift toward the assurance scope
  rule 4 forbids). Missing values stay `NULL` + a note.
- *Touches:* one mart measure on `benchmark_installation_emissions` (or sibling),
  `site/sources/cairn/*.sql`, a page. Column already in the fixture's
  `compliance.parquet`.

### 6. EUTL installation identity enrichment (parent company, ETS activity, geo)
**Value: M · Effort: L · Spine-fit: H**

`stg_euets__installations` already stages `parent_company`, `ets_activity_label`,
`country_label`, and `latitude`/`longitude`, but the marts surface only
`installation_name` + NACE section. Promoting these adds **identity/provenance
depth** (admission rule 3) at near-zero cost — and `parent_company` lets a
rough company rollup exist from the pinned snapshot even before the GLEIF/LEI
seed (#4) lands.
- *Watch:* `parent_company` is **free text, not an authoritative ID** — surface
  it as descriptive context only; the authoritative entity mapping stays the
  reviewed LEI seed (#4). Do **not** normalise/dedupe names into a synthesised
  entity (that's invention). Geo is euets.info's `latitudeGoogle/longitudeGoogle`
  — label it source-provided and approximate.
- *Touches:* installation mart dimension columns, `site/sources/cairn/*.sql`,
  a page (table/map). Fields already present in the fixture's `installation.parquet`.

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

---

## Considered and rejected
*(Don't re-propose these. If circumstances change, move an item back up with the
new reason it now fits.)*

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
