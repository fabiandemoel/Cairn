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
   (`cbs/<table>/<release>/`). Never overwrite a raw file.
2. **The manifest is append-only.** `sources/cbs/manifest.yml` is the pin of
   record. `ingestion/manifest.py` refuses to modify/delete entries — keep it
   that way. A data change without a manifest change must stay impossible.
3. **Mappings are code, reviewed via PRs.** `transform/seeds/sector_mapping_cbs.csv`
   is the single source of truth for category → NACE. Change it in a PR so the
   CI benchmark diff makes the numeric impact visible. Never invent figures or
   mappings — use real source categories, or explicit `NULL` + a `notes` entry.
4. **CI guards the methodology.** Tests must fail the build. Don't weaken a test
   to make a change pass; fix the change or, if the source genuinely changed,
   update the test deliberately and say so in the PR.
5. **Phase 1 scope only.** No EEA/ETS, Evidence site, CSRD export, or agent
   automation yet. Don't scaffold placeholder code for them.

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

### Classification updates (medium-term, real)
The mapping rests on SBI 2008 ⊃ NACE Rev.2. Both are migrating:
- **NACE Rev.2.1** — EU statistics move to it from 2025.
- **SBI 2025** — CBS introduces it gradually from 2026, alongside SBI 2008.
When CBS switches `85669NED` to SBI 2025 / NACE Rev.2.1 codes, revisit the seed
mapping and the NACE section letters in the mart's `accepted_values` test, and
update the references. Treat it as a reviewed methodology change (PR + diff).

### Keep references honest
`README.md` (References & methodology) and the mart `meta.references` in
`transform/models/marts/_marts.yml` cite the sources that justify the data and
the mapping. If you change methodology, update both. Don't add a citation you
haven't verified resolves.

### Reproducibility
`scripts/verify_reproducibility.py` runs weekly + on demand in CI. It needs the
`R2_*` repo secrets; it skips cleanly without them. If R2 is set up, confirm the
weekly job is green — a failure means a pinned raw file changed or vanished,
which is a real integrity alarm, not flakiness.

## How to work here

- **Setup:** `uv sync --all-groups`. Python 3.12.
- **Build/test/lint (what CI runs):**
  - `uv run dbt build --project-dir transform --profiles-dir transform`
  - `uv run pytest -q`
  - `uv run ruff check . && uv run ruff format --check .`
  - `uv run sqlfluff lint transform/models transform/tests`
- **Dependencies:** stay within dlt, dbt-core, dbt-duckdb, duckdb, pydantic,
  boto3, pyyaml (+ dev: pytest, ruff, sqlfluff). Ask before adding more.
- **Commits:** conventional commits, one logical change per commit, descriptive
  messages. Commit per milestone, not one giant blob.
- **Source quirks:** when the CBS API surprises you, document it in the README
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
