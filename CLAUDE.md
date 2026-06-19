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
5. **Phase 3 scope.** Sources: CBS + EU ETS (installation level), plus the
   **Evidence site** (`site/`) — a read-only presentation layer over the dbt
   marts. The site must never ingest or transform; it only *reads*
   `cairn.duckdb`. Still **no** CSRD export or agent automation — don't scaffold
   placeholder code for them.

## Recurring maintenance (the reason this file exists)

### When CBS publishes a new release of `85669NED`
CBS recalculates the full time series ~yearly (mid-March, when Q4 of the latest
year is published) and revises provisional years. Trigger: the table's
`Modified` date changes (visible via the `Properties` singleton, or the
reproducibility job).

Checklist:
1. Run the ingest: `uv run python -m ingestion.cbs_pipeline` (with R2 creds) or
   `--offline` to dry-run locally. It is idempotent — it exits "no new release"
   if `Modified` already matches the latest snapshot.
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
