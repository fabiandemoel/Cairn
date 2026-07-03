# CLAUDE.md — guidance for agents working on Cairn

This file is read automatically at the start of each session. It tells future
agents how to **keep Cairn correct and up to date**. Read it before changing
anything; keep it current when the project's invariants or routines change.

For *what Cairn is* and how to run it, see [`README.md`](README.md). This file
is about *maintenance and guardrails*, not a duplicate of the README.

## Non-negotiable invariants (do not violate)

These are the architecture's load-bearing rules. Breaking one silently breaks
auditability, which is the whole point of Cairn.

1. **Raw data is immutable.** Every ingest writes to a new, versioned path
   (`<source>/<dataset>/<release>/`). Never overwrite a raw file.
2. **The manifest is append-only.** Each source has its own manifest under
   `sources/` (`cbs/`, `euets/`, `eea/`) — the pin of record. `ingestion/manifest.py`
   refuses to modify/delete entries — keep it that way. A data change without a
   manifest change must stay impossible. The committed manifests ship unpinned
   (`snapshots: []`); the first real R2 ingest establishes the pin — never
   commit a machine-specific `file://` snapshot from an `--offline` run.
3. **Mappings are code, reviewed via PRs.** `transform/seeds/sector_mapping_cbs.csv`
   is the single source of truth for CBS category → NACE. Change it in a PR so
   the CI benchmark diff makes the numeric impact visible. Never invent figures
   or mappings — use real source categories, or explicit `NULL` + a `notes`
   entry. (EU ETS needs no such seed — euets.info carries native NACE.)
4. **CI guards the methodology.** Tests must fail the build. Don't weaken a test
   to make a change pass; fix the change or, if the source genuinely changed,
   update the test deliberately and say so in the PR.
5. **Phase 4 scope.** Sources: CBS + EU ETS (installation level), plus the
   **Evidence site** (`site/`) — a read-only presentation layer over the dbt
   marts — plus the **CSRD/ESRS E1 export** (`mart_esrs_e1`): a read/relabel
   mart over `benchmark_installation_emissions` that provides verified EU ETS
   emissions as the verified basis for the ESRS E1-6 "gross Scope 1 GHG
   emissions" datapoint. The site
   must never ingest or transform; it only *reads* `cairn.duckdb`. The export
   recomputes nothing and must never **invent** figures — Cairn has no Scope 2/3
   source, so those datapoints are omitted, never filled with placeholder zeros.
   Still **no** agent automation — don't scaffold placeholder code for it.

## Recurring maintenance (the reason this file exists)

### When CBS publishes a new release of `85669NED`
CBS recalculates the full time series ~yearly (mid-March, when Q4 of the latest
year is published) and revises provisional years. Trigger: the table's
`Modified` date changes (visible via the `Properties` singleton, or the
reproducibility job).

Checklist:
1. Run the ingest: `uv run python -m ingestion.cbs_pipeline` (with R2 creds) or
   `--offline` to dry-run locally, or trigger `cairn-ingest.yml` (source `cbs`)
   to run it in CI and open the manifest-pin PR for you. It is idempotent — it
   exits "no new release" if `Modified` already matches the latest snapshot.
2. Confirm a **new** append-only snapshot landed in `sources/cbs/manifest.yml`
   (new `release`, new `sha256`). The old snapshot stays.
3. Refresh the CI fixture so tests run on representative data:
   `tests/fixtures/85669NED/<release>/` (a few hundred rows; keep ≥2 final years
   + 1 provisional year so the `Definitief` filter stays exercised). Update the
   default `raw_dir` in `transform/dbt_project.yml` and the fixture path in the
   `benchmark-diff` CI job to the new release date.
4. **Re-verify the sector hierarchy.** CBS occasionally adds/renames/regroups
   climate-sector categories. If `KlimaatsectorenCodes` changed, the leaf vs
   aggregate split in the seed may be stale. The `relationships` test (every
   staged code is in the seed) and `assert_national_total_reconciles` (<0.5%)
   will fail loudly if so — fix the seed, don't suppress the test.
5. `uv run dbt build --project-dir transform --profiles-dir transform` green,
   `uv run pytest -q` green, linters green.
6. Note the release date in the README (`What Cairn is` + Source quirks).

### When euets.info or the EEA bulk publishes a new release
The two EU ETS sources update on their own cadences (euets.info roughly yearly,
trailing ~a year; the EEA bulk after the spring compliance cycle). There is no
`Modified` endpoint — the release is the source filename's version token.

Checklist:
1. Find the new URL and ingest:
   - euets.info: the current zip is hard-coded as `DEFAULT_URL` in
     `ingestion/euets_pipeline.py`; point `--url` at the newer zip (the filename
     carries the publication token, e.g. `eutl_2025_2026xx.zip`).
   - EEA: the datashare link is `DEFAULT_URL` in `ingestion/eea_ets_pipeline.py`;
     update it if EEA issues a new share. Run with R2 creds, or `--offline`.
   - Either way, `cairn-ingest.yml` (source `euets` or `eea`, with the new URL
     as the workflow's `url` input) can run the ingest in CI and open the
     manifest-pin PR for you.
   Both are idempotent — they exit "no new release" if the token is already pinned.
2. Confirm a **new** append-only snapshot landed in `sources/euets/manifest.yml`
   / `sources/eea/manifest.yml` (new `release`, new `sha256`).
3. Refresh the CI fixtures and bump the release dirs:
   `uv run python scripts/build_eu_ets_fixtures.py` (it reads the local
   `.localstack/` snapshots), then update the `euets_raw_dir` / `eea_raw_dir`
   defaults in `transform/dbt_project.yml`, the fixture release dirs, and the
   per-source `files`/paths in `scripts/verify_reproducibility.py` if the
   release changed.
4. **Re-check the assumptions the staging/mart lean on.** If the EUTL schema
   changed: the compliance grain (`installation|year|system`), the NACE
   hierarchy walk, the operator flags, or the EEA stationary-total code
   (`20-99`, in `assert_euets_coverage_within_eea`). The coverage test (<0.5%
   one-sided) and the relationships/unique tests fail loudly — fix the model,
   don't suppress the test.
5. `dbt build`, `pytest`, linters green. Note the release in the README.

### When Eurostat publishes a new release of `env_ac_ainah_r2` (AEA)
Eurostat publishes Air Emissions Accounts roughly annually (the last-update date
is available via the SDMX metadata API). The pipeline detects the release
automatically from that date.

Checklist:
1. Run `uv run python -m ingestion.eurostat_aea_pipeline` (with R2 creds, or
   `--offline` to dry-run locally). The pipeline fetches `METADATA_URL` in
   `ingestion/eurostat_aea_pipeline.py` for the current last-update date and exits
   "no new release" if it matches the latest manifest snapshot.
   `cairn-ingest.yml` (source `eurostat_aea`) can run this in CI and open the
   manifest-pin PR.
2. Confirm a **new** append-only snapshot landed in `sources/eurostat/manifest.yml`
   (new `release`, new `sha256`). The old snapshot stays.
3. Update the `eurostat_aea_raw_dir` default in `transform/dbt_project.yml` and
   the matching fixture path in `scripts/verify_reproducibility.py` to the new
   release date. Refresh the CI fixture under
   `tests/fixtures/eurostat/env_ac_ainah_r2/<release>/` if columns or available
   countries changed (keep a small, representative slice — NL, DE, FR at minimum).
4. **Re-check the AEA schema assumptions.** If Eurostat changed column names,
   available NACE codes, or the country dimension, `stg_eurostat__aea` and
   `benchmark_country_sector_emissions` may drift. The `assert_eurostat_aea_nl_within_cbs`
   tolerance test (<5% for the NL total) will surface unit errors or gross
   pipeline mistakes; fix the model rather than suppressing the test.
5. `dbt build`, `pytest`, linters green. Note the release in the README
   (`Source quirks` section if a new quirk appears).

### When Eurostat publishes a new release of `env_air_gge` (GGE)
Eurostat publishes GHG emission national totals (from UNFCCC submissions)
annually; the last-update date is available via the same SDMX metadata API.

Checklist:
1. Run `uv run python -m ingestion.eurostat_gge_pipeline` (with R2 creds, or
   `--offline` to dry-run). The pipeline reads `METADATA_URL` in
   `ingestion/eurostat_gge_pipeline.py` for the current last-update date and exits
   "no new release" if it matches the latest manifest snapshot.
   `cairn-ingest.yml` (source `eurostat_gge`) can run this in CI.
2. Confirm a **new** append-only snapshot landed in `sources/eurostat_gge/manifest.yml`
   (new `release`, new `sha256`).
3. Update `eurostat_gge_raw_dir` in `transform/dbt_project.yml` and the matching
   path in `scripts/verify_reproducibility.py`. Refresh the CI fixture under
   `tests/fixtures/eurostat/env_air_gge/<release>/` if the schema or coverage
   changed (keep NL, DE, FR × TOTXMEMO+CRF1 at minimum so the staging tests
   and cross-check test still exercise the right rows).
4. **Verify the cross-check test.** `assert_gge_nl_total_within_cbs` must still
   pass at its 10% tolerance (set wide to accommodate UNFCCC submission lag vs.
   CBS revision cycles — the observed gap for recently-revised years can reach ~7%).
   If a newly released year shows >10%, investigate before widening — it likely
   indicates a genuine revision rather than a timing artefact.
5. `dbt build`, `pytest`, linters green. Note the release in the README
   (UNFCCC submissions trail by 1–2 years; update the "latest available year" note
   in the `env_air_gge` Source quirks).

### When EEX publishes a new EU ETS auction report (`eua`)
EEX (the appointed Phase 4 auctioneer) republishes the historical
*Emission Spot Primary Market Auction Report* archive on its own cadence. There
is no `Modified` endpoint or upstream index — the release is the year-range
token in the archive filename (e.g. `...-2012-2025-data.zip` → `2012-2025`), so
`eua` is **human-watched** like euets: bump `DEFAULT_URL` when EEX publishes a
newer archive. The freshness check derives the live token from that URL by
construction; it must never probe EEX.

Checklist:
1. Find the new archive URL on EEX and ingest with it:
   `uv run python -m ingestion.eua_pipeline --url <new zip>` (with R2 creds, or
   `--offline` to dry-run locally). Point `DEFAULT_URL` in
   `ingestion/eua_pipeline.py` at the newer zip. It is idempotent — it exits
   "no new release" if the filename token is already pinned. `cairn-ingest.yml`
   (source `eua`, with the new URL as the `url` input) can run the ingest in CI
   and open the manifest-pin PR for you.
2. Confirm a **new** append-only snapshot landed in `sources/eua/manifest.yml`
   (new `release`, new `sha256`). The old snapshot stays.
3. **Refresh the staging layer's fixture.** `eua` now has a read-only transform
   layer — `stg_eua__auction_results` (a straight read/relabel view over the
   pinned auction parquet via the `eua_raw_dir` var), a CI fixture under
   `tests/fixtures/eua/<release>/`, and an entry in `verify_reproducibility.py`.
   So when the release token changes, refresh that fixture and bump the
   `eua_raw_dir` default in `transform/dbt_project.yml`, the fixture release dir,
   and the `verify_reproducibility.py` path — the same fixture/`*_raw_dir` steps
   as the other sources.
4. **Scope note (invariant 5).** The auction *clearing price* the staging view
   exposes is context for a future site overlay only — it must **never** appear
   in a dbt **mart** figure or the ESRS E1 export. `stg_eua__auction_results` is
   deliberately not `ref`'d by any benchmark mart; keep it that way (no
   `tonnes × price`, no currency conversion — a straight typed pass-through).
5. `dbt build`, `pytest`, linters green. Note the release in the README (Source quirks).

### Classification updates (medium-term, real)
The mapping rests on SBI 2008 ⊃ NACE Rev.2. Both are migrating:
- **NACE Rev.2.1** — EU statistics move to it from 2025.
- **SBI 2025** — CBS introduces it gradually from 2026, alongside SBI 2008.
When CBS switches `85669NED` to SBI 2025 / NACE Rev.2.1 codes, revisit the seed
mapping and the NACE section letters in the mart's `accepted_values` test, and
update the references. Treat it as a reviewed methodology change (PR + diff).

### Working on the Evidence site (`site/`)
The site is a **read-only** view of the dbt marts — it never ingests or
transforms. It reads `cairn.duckdb` (built by dbt at the repo root) via the
`sources/cairn/` DuckDB connection.

- A new column or mart only shows up after you add it to a `sources/cairn/*.sql`
  query (or a page query) — the site does not auto-discover mart columns.
- If a mart's columns/grain change, update the matching source query and any
  page that references the renamed column; `npm run build:strict` fails on a bad
  query, so CI catches a drift.
- Don't move business logic into the site. Benchmarks are computed in dbt and
  tested there; the site only shapes and displays. New numbers belong in a mart.
- **The version badge on the homepage** (`Cairn v…` on `index.md`) is kept in
  step with `package.json`'s `version`. Bump both together when the site version
  changes.

### Working on the CSRD/ESRS E1 export (`mart_esrs_e1`)
The export is a **read/relabel** mart over `benchmark_installation_emissions` —
it `ref`s that mart and renames the verified EU ETS figure to the ESRS E1-6
"gross Scope 1 GHG emissions" datapoint, carrying the sector benchmark as
context. It computes no new emissions.

`scripts/export_esrs_e1.py` ships it as the actual deliverable: it reads the
built warehouse and writes a git-ignored bundle under `exports/esrs_e1/` (CSV +
`meta.json` audit trail + README). The metadata chains the disclosure back to
the EU ETS source pin, the methodology git commit, and a SHA256 of the CSV. Like
the site, it only **reads** `cairn.duckdb` — no transform logic lives there.
`tests/test_export_esrs_e1.py` guards the bundle (integrity hash matches, sort
order, coverage); the `DATA_DICTIONARY` order is the CSV column contract, so if
the mart's columns change, update both together.

- **Don't recompute or aggregate emissions here.** If the underlying numbers
  need to change, change the source mart; the export only reframes them. New
  emission logic belongs upstream, tested there.
- **Never invent missing datapoints.** ESRS E1-6 also wants Scope 2/3; Cairn
  has no source for them, so they are **omitted**, not zero-filled. If a real
  Scope 2/3 source is ever added, model it upstream and surface it as its own
  datapoint rows — don't synthesize figures.
- The `esrs_datapoint`/`ghg_scope`/`unit` literals make the export
  self-describing; their `accepted_values` tests pin them. If the ESRS
  taxonomy version or datapoint id changes, update the literals and those tests
  together.

### Keep references honest
`README.md` (References & methodology) and the mart `meta.references` in
`transform/models/marts/_marts.yml` cite the sources that justify the data and
the mapping. If you change methodology, update both. Don't add a citation you
haven't verified resolves.

### Reproducibility
`scripts/verify_reproducibility.py` runs weekly + on demand in CI. With no args
it verifies **every source** (CBS, euets.info, EEA), skipping cleanly per source
when unpinned or when the `R2_*` secrets are absent. If R2 is set up, confirm
the weekly job is green — a failure means a pinned raw file changed or vanished,
which is a real integrity alarm, not flakiness.


### Agent automation (CI maintenance loop)
Two workflows run Claude against this repo (implement, replenish), plus two
non-LLM workflows: the manually triggered ingest that performs the actual R2
write, and the deterministic dispatcher that turns freshness diffs and the
backlog into issues. None of them ever bypass the invariants above, and the
existing CI (lint, test, dbt-build, evidence-build, benchmark-diff) is the
gate for every code change.

- **`cairn-ingest.yml`** — manual only (`workflow_dispatch`, pick a source from
  the dropdown). No LLM runs in this job; it directly invokes that source's
  existing idempotent `ingestion/*_pipeline.py` with the `R2_*` secrets, so an
  agent never holds R2 write-credentials. If the pipeline pins a new release,
  the job opens a PR carrying only the manifest diff (via
  `peter-evans/create-pull-request`); it never merges. The PR's checklist
  reminds the reviewer that fixtures/`*_raw_dir` defaults/model assumptions
  (the rest of the matching "Recurring maintenance" checklist below) still
  need doing before it's safe to merge — a bare manifest bump alone is
  expected to fail `dbt build`/`pytest` in that PR's CI run. A `data-refresh`
  issue from `cairn-dispatch.yml` is the usual trigger to run this by hand.
- **`cairn-dispatch.yml`** (on every merge to main + weekly Monday cron) —
  **no LLM at all**; it replaced the former cairn-scout agent once both scout
  tasks turned out to be deterministic. `scripts/dispatch.py` (stdlib-only,
  unit-tested in `tests/test_dispatch.py`) makes every decision: the weekly
  freshness check turns `scripts/check_freshness.py`'s live-vs-pinned diff
  into one templated `data-refresh` issue per STALE source (euets/eua stay
  human-watched, never probed), and the backlog dispatcher opens at most one
  issue per run for the top BACKLOG.md candidate's next not-yet-built layer,
  determined by the sentinel paths in that candidate's `<!-- dispatch -->`
  block (schema in BACKLOG.md's "Dispatch metadata" section, maintained by
  replenish). Dedup against open issues/PRs and the saturation gate (Actions
  variable `DISPATCH_BACKLOG_SATURATION`, default 5 un-approved proposals) live
  in the same tested script. Output is GitHub issues labelled `proposal` —
  never code, never a PR. Event-driven on purpose: the next layer becomes
  dispatchable exactly when the previous one merges, so `push` to main is the
  trigger and no daily polling (or LLM spend) is needed.
- **`cairn-implement.yml`** — runs only when a human adds the `approved` label
  to an issue (or via manual dispatch). Implements that one issue on an
  `agent/*` branch and opens a PR against main. It must pass the full local CI
  command set before opening the PR, and it never merges. PRs are opened with
  `CAIRN_BOT_TOKEN` (not `GITHUB_TOKEN`) so CI actually fires on them.
- **`cairn-replenish.yml`** (weekly) — curates BACKLOG.md only, as a docs-only
  PR: new candidates, re-scoring, retiring off-spine ideas to "Considered and
  rejected". Never merges. Its docs-only PRs skip ci.yml's matrix
  (paths-ignore), so `backlog-check.yml` gates them instead: on any BACKLOG.md
  change it runs the dispatch-block guard test (`tests/test_dispatch.py`),
  catching a malformed `<!-- dispatch -->` block before it can silently starve
  the dispatcher. **Data-quality observability is a standing candidate
  theme here** alongside new sources and benchmark axes: read-only marts that
  surface coverage/completeness, field-completeness (NULL-rates), and freshness
  as *observable facts* over the manifests and existing marts. The shipped
  `mart_data_provenance` provenance-integrity view and its **Data quality** site
  page are the established pattern (read-only, reads the manifests, recomputes
  nothing). Keep such candidates to observable facts — never confidence/quality
  *scores* on individual figures; that line stays in BACKLOG's _Considered and
  rejected_.

**Prompt priming (cost optimisation).** Both agent workflows run no-LLM steps
*before* the Claude step so the agent never has to re-derive stable facts turn
by turn (the dominant repeated cost in the run logs):
- **Pre-build (implement only).** A `continue-on-error` step runs `uv sync`,
  `dbt build`, `scripts/export_esrs_e1.py`, and `npm ci && npm run sources` —
  mirroring ci.yml — so the agent starts from a built warehouse
  (`./cairn.duckdb`), an existing ESRS export bundle, and installed site deps,
  and only re-runs what it changes. It's `continue-on-error` because a failure
  just falls back to the agent building it itself; it's an optimisation, not a
  gate.
- **Orientation map.** `scripts/repo_orientation.py` (stdlib-only, unit-tested
  in `tests/test_repo_orientation.py`) emits a compact map — the build/verify
  sequence, the warehouse↔Evidence wiring, and a filesystem-scanned inventory of
  which sources / staging models / marts / site queries / pages exist — captured
  into a step output and injected into the prompt. It scans the tree each run, so
  it never goes stale. It's the single rendered source for the build sequence
  (the prompt points at it rather than hardcoding the command list), and it
  gives replenish the layer inventory it uses to retire shipped candidates and
  score remaining effort. Injected into both agent prompts. Keep the map
  tight: it is re-sent on every agent turn. (The dispatcher does not need it —
  it checks the candidate's sentinel paths against the tree directly.)
- **Per-layer reference (implement only).** `scripts/reference_for_layer.py`
  (stdlib-only, unit-tested in `tests/test_reference_for_layer.py`) infers the
  issue's layer from its title/labels and inlines the canonical in-tree
  exemplar(s) for that layer (e.g. for an ingestion issue: the Eurostat AEA
  pipeline, its manifest, and its test) straight into the prompt. Cairn's work
  is templated — each single-layer issue is a near-copy of an existing exemplar
  — so the agent should copy the pattern, not re-derive it by reading (and
  re-reading) the references itself. Run-log analysis showed that read-recon
  front end was the dominant cost (one run spent 42 of 73 tool calls on recon
  before writing a line). Exemplars are read from the tree each run (never
  stale) and per-file line-capped (it is re-sent every turn); a missing exemplar
  or an unrecognised layer degrades to a "find the closest example" note rather
  than failing the step. The prompt also tells the agent to treat the issue body
  as the authoritative spec and never to run the real `--offline` ingest — it
  mutates the manifest with a `file://` snapshot.
- **Live-source research (implement only, gated).** The implement agent does no
  mid-run web discovery at all. `scripts/source_research.py` (stdlib-only,
  unit-tested in `tests/test_source_research.py`) gates it: only an
  ingestion-layer issue emits `needed=true`, and then an isolated Haiku
  research step (WebFetch/WebSearch only — no shell, no files, no subagents)
  investigates the source *before* the orchestrator starts; the same script
  extracts that step's final message from the action's execution log and the
  workflow injects it into the implement prompt as the "research brief"
  (missing/failed research degrades to a fallback note, never a job failure).
  The implement step consequently carries **no** WebFetch/WebSearch in its
  allowlist, and the background/wakeup tools (`ScheduleWakeup` and the
  agent-messaging/background-task tools) are blocked via `--disallowedTools`,
  with the prompt requiring `run_in_background: false` on every subagent Task.
  This is mechanical enforcement of "stay synchronous": prompt-only enforcement
  failed twice (implement runs #42 and #43 both parked work in background
  subagents, scheduled a wakeup that can never fire in a one-shot CI job, and
  ended their turn having shipped nothing — and `ScheduleWakeup` bypasses the
  `--allowedTools` allowlist, so only `--disallowedTools` actually stops it).
- **Upstream freshness (now fully no-LLM).** `scripts/check_freshness.py`
  (stdlib-only, unit-tested in `tests/test_check_freshness.py`) computes the
  live-vs-pinned diff per source; `scripts/dispatch.py` consumes its structured
  `collect_statuses` output directly, so no agent is involved anywhere in the
  freshness path anymore. It reads the source-specific bits a human bumps (CBS
  table id, Eurostat dataset id, euets/EEA `DEFAULT_URL`) from the pipeline
  files so it can't drift from the pin of record, and treats **euets.info and
  eua as human-watched** — they have no upstream index, so their live token
  equals the pin by construction and must never be probed (the former scout
  agent used to brute-force dozens of S3 filenames discovering exactly that).
  A failed probe marks that one source "probe failed" in the dispatch run
  summary for a human to verify — it never opens an issue and never crashes
  the run.

The human stays out of the doing for code changes; the manual acts are
labelling an issue `approved`, manually running `cairn-ingest.yml` when a
source needs a new pin, and merging a green PR. That merge is the audit
checkpoint — keep it. BACKLOG.md is the curated menu these agents draw from;
its "Rules of the game" restate these invariants as admission criteria for new
sources.

**Cost visibility.** Both agent workflows end with two best-effort steps
that surface what the run cost (the dispatcher runs no model, so it has no
cost step). `scripts/ai_cost_summary.py` (stdlib-only, unit-tested in
`tests/test_ai_cost_summary.py`) parses the action's
`execution_file` output — its `total_cost_usd`, `usage`, `modelUsage`,
`num_turns`, `duration_ms` — into a markdown comment and the total cost in USD.
It accepts `--execution-file` more than once and merges them, so implement's
research + implement steps surface as one total (an empty path from a skipped
research step is ignored).
The shared `.github/scripts/attribute_run_cost.js` github-script module then
posts that comment and sets a Projects v2 Number field for the PR the run
opened, resolved by branch prefix (`agent/<issue>-*`, `replenish/*`).
Both steps run `if: always()` and the Projects v2 update is
wrapped in try/catch, so a missing board/field or a token without `project`
scope **warns** rather than failing the run. Configuration:
  - Board defaults to `fabiandemoel` project **#1** ("AI Management"), field
    **"AI cost (USD)"** (a NUMBER field). Override per repo via the Actions
    variables `AI_COST_PROJECT_OWNER`, `AI_COST_PROJECT_NUMBER`,
    `AI_COST_FIELD_NAME`.
  - The GraphQL calls need a token with the `project` scope: add a
    `PROJECTS_TOKEN` secret (a fine-grained PAT or classic token with
    `project`). It falls back to `CAIRN_BOT_TOKEN` then `GITHUB_TOKEN`, which
    usually lack `project` — without `PROJECTS_TOKEN` the comment still posts and
    the field update just warns.

These workflows reference the labels `proposal`, `data-refresh`, `feat`, and
`approved` — create them in the repo's Issues → Labels settings before
enabling the workflows; GitHub's label API will not auto-create a label that
doesn't exist.

## How to work here

- **Setup:** `uv sync --all-groups`. Python 3.12.
- **Build/test/lint (what CI runs):**
  - `uv run dbt build --project-dir transform --profiles-dir transform`
  - `uv run pytest -q`
  - `uv run ruff check . && uv run ruff format --check .`
  - `uv run sqlfluff lint transform/models transform/tests`
  - **Evidence site:** after a dbt build, `cd site && npm ci && npm run
    build:strict` (CI's `evidence-build` job). `npm run dev` for a live preview.
- **Dependencies (Python):** stay within dlt, dbt-core, dbt-duckdb, duckdb,
  pydantic, boto3, pyyaml (+ dev: pytest, ruff, sqlfluff). Ask before adding
  more. (The EEA xlsx is read via DuckDB's autoloaded `excel` extension — a
  DuckDB extension, not a new Python dependency.)
- **Dependencies (site):** the `site/` Evidence project has its own Node
  toolchain, pinned in `site/package-lock.json`. Install with `npm ci`, not
  `npm install` (a re-resolve trips Evidence's known peer-dep mismatch). Keep it
  to the Evidence core + the DuckDB datasource; ask before adding npm packages.
- **Commits:** conventional commits, one logical change per commit, descriptive
  messages. Commit per milestone, not one giant blob.
- **Source quirks:** when a source surprises you, document it in the README
  "Source quirks" section rather than silently working around it.

## Gotchas (already learned — don't rediscover the hard way)

- **Use the OData v4 API** (`datasets.cbs.nl/odata/v1/CBS/<table>`). The v3
  `TypedDataSet` feed (`opendata.cbs.nl/ODataApi`) returns HTTP 406 here.
- **`85669NED`, not `84979NED`.** The latter is quarterly with only 6 broad
  Klimaatakkoord sectors that don't map to NACE. See README Source quirks.
- **Provisional years lack the full sector breakdown** — the mart filters to
  `period_status = 'Definitief'`. Don't "fix" the reconciliation test by
  including provisional years.
- **Bunkers are memo items outside the national total** — flagged `aggregate`
  and excluded. Including them double-counts.
- **dbt needs the profile** — pass `--profiles-dir transform` (or set
  `DBT_PROFILES_DIR=transform`); CI sets it at the workflow level.
- **EU ETS installation data comes from euets.info, not the EEA bulk.** The EEA
  bulk is aggregated only (`active_installation` = `all entities`); it is the
  denominator/cross-check, not the installation pin. Don't try to get
  installation rows out of it.
- **euets compliance grain is `installation|year|system`.** Linked registries
  duplicate the same installation-year under `euets` and Swiss `chets`; the mart
  keeps only `euets`. A 2-part key is not unique.
- **euets operator flags are nullable.** A few installations have no
  `isAircraftOperator`/`isMaritimeOperator`; the fixture has none, so the full
  snapshot is the real test. The mart's `not is_aircraft_operator` excludes a
  NULL (not-confirmed-stationary) — that's intended; don't add a `not_null` test
  on those flags.
- **euets.info source columns are camelCase; SBI/sqlfluff want lowercase.**
  Reference them unquoted and lowercase (`isaircraftoperator`) — DuckDB resolves
  case-insensitively, and quoting trips `RF06` while uppercase trips `CP02`.
- **Evidence's DuckDB `filename` is resolved relative to the source directory**
  (`site/sources/cairn/`), not the project root — hence `../../../cairn.duckdb`
  to reach the repo root. Build the warehouse (`dbt build`) before the site.
- **Install the site with `npm ci`, never `npm install`.** A fresh resolve hits
  Evidence's `svelte2tsx`/`typescript` peer-dep mismatch; the committed
  `site/package-lock.json` is the working tree.
