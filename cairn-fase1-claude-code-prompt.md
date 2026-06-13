# Cairn — Phase 1 Build Instructions

> **Hoe te gebruiken:** start Claude Code in een lege directory en geef dit hele document als opdracht (plak het, of verwijs ernaar met `@cairn-fase1-claude-code-prompt.md`). De prompt is in het Engels geschreven omdat dat voor code, configs en commit-conventies de minste ruis geeft. Reviewen doe je per commit — laat Claude Code na elke milestone (zie "Build order") committen zodat je diffs behapbaar blijven.

---

## Context

You are building **Cairn**: a queryable benchmark layer on top of official EU/NL climate data (CBS, EEA, EU ETS). Cairn connects fragmented public sources and answers, per sector: "how do your emissions compare to the sector average?" The end product feeds CSRD-ready exports, which means **auditability and reproducibility are hard requirements, not nice-to-haves**. Every benchmark figure must be traceable to: a git commit + a source manifest + an immutable raw file.

Phase 1 scope: **one CBS dataset, end-to-end** — ingestion via dlt, transformation via dbt on DuckDB, a manifest-based versioning mechanism, dbt tests, and CI in GitHub Actions. No agent automation yet, no EEA/ETS, no Evidence site, no CSRD export. Those come later; do not scaffold placeholder code for them.

## Architecture principles (do not violate these)

1. **Git is the single source of truth for code, mappings, and manifests.** Raw data lives in object storage (Cloudflare R2), never in git.
2. **Raw data is immutable.** Every ingest writes to a new path containing the source release version/date (e.g. `raw/cbs/{table_id}/{release_date}/data.parquet`). Nothing is ever overwritten.
3. **Manifests pin everything.** A manifest file in git records, per source snapshot: dataset identifier, source release version/date, storage URL, SHA256 of the raw file, ingest timestamp. A data change without a manifest change must be impossible.
4. **Mappings are code.** Sector mapping tables (source category → NACE sector) live as version-controlled seed files in the repo, reviewed via PRs.
5. **CI guards the methodology.** Tests must fail the build, and a benchmark diff must make the impact of any change visible at review time.

## Tech stack

- **Python 3.12**, managed with `uv` (pyproject.toml, locked deps)
- **dlt** for ingestion from the CBS OData API
- **dbt-core + dbt-duckdb** for transformations
- **DuckDB** as the engine; outputs as parquet + a `.duckdb` file
- **Cloudflare R2** (S3-compatible) for raw data storage
- **GitHub Actions** for CI
- Linting: `ruff` (format + lint), `sqlfluff` for dbt SQL

## Repo structure

```
cairn/
├── pyproject.toml
├── README.md                  # what Cairn is, how to run locally, how reproducibility works
├── .github/workflows/
│   └── ci.yml
├── ingestion/
│   ├── cbs_pipeline.py        # dlt pipeline: CBS OData → parquet → R2
│   └── manifest.py            # manifest read/write/verify logic (hashing, schema validation)
├── sources/
│   └── cbs/
│       └── manifest.yml       # the pinned source snapshots (see spec below)
├── transform/                 # dbt project
│   ├── dbt_project.yml
│   ├── profiles.yml           # duckdb profile, paths via env vars
│   ├── seeds/
│   │   └── sector_mapping_cbs.csv   # CBS category → NACE sector mapping
│   ├── models/
│   │   ├── staging/           # 1:1 with raw, typed, renamed
│   │   └── marts/
│   │       └── benchmark_sector_emissions.sql
│   └── tests/                 # singular tests beyond schema yml tests
├── scripts/
│   ├── verify_reproducibility.py   # pick manifest entry → download → verify hash → dbt build
│   └── benchmark_diff.py            # compare mart output between two builds, emit markdown
└── tests/                     # pytest for ingestion + manifest logic
```

## Step 0 — Verify the CBS dataset (do this first, do not skip)

Use the CBS StatLine OData catalog (`https://opendata.cbs.nl/ODataCatalog/Tables?$format=json`) to find the current table for **greenhouse gas emissions per sector according to IPCC guidelines** (Dutch: "Emissies van broeikasgassen berekend volgens IPCC-voorschriften"). A likely candidate is table `84979NED`, but **verify it exists, is not discontinued, and check its actual schema** (dimensions, measures, available periods) before writing any pipeline code. If it has been replaced by a newer table, use the replacement and note this in the README. Print the table metadata and pause for my confirmation before continuing.

## Manifest specification

`sources/cbs/manifest.yml` — append-only list of snapshots:

```yaml
source: cbs
dataset: "84979NED"            # verified table id
snapshots:
  - release: "2026-05-15"      # CBS 'Modified' date of the table
    ingested_at: "2026-06-12T06:00:00Z"
    storage_url: "r2://cairn-raw/cbs/84979NED/2026-05-15/data.parquet"
    sha256: "<hash of the parquet file>"
    row_count: 12345
    periods_covered: ["1990", "2024"]
```

Requirements for `ingestion/manifest.py`:
- Pydantic model for the manifest schema; loading an invalid manifest raises.
- `add_snapshot()` refuses to modify or delete existing entries (append-only).
- `verify_snapshot()` downloads the object, recomputes SHA256, compares.
- The dlt pipeline must call manifest logic as its final step — ingestion without a manifest update must be impossible by construction.

## Ingestion (dlt)

- Pull the verified CBS table via OData (TypedDataSet + the dimension metadata endpoints needed to decode codes into labels).
- Write raw data as parquet locally, upload to R2 using the immutable path scheme, then append the manifest entry.
- Idempotency: if the CBS `Modified` date matches the latest manifest entry, exit cleanly with "no new release" — no upload, no manifest change.
- Config via env vars: `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`. Provide an `--offline` flag that skips R2 and writes to a local `./.localstack/` directory so the full pipeline is testable without credentials.

## Transformation (dbt)

- **Staging model** `stg_cbs__emissions`: reads the parquet for the manifest's latest snapshot (path passed via dbt var), types columns, decodes CBS dimension codes to labels, renames to clear English column names.
- **Seed** `sector_mapping_cbs.csv`: columns `cbs_category_code, cbs_category_label, nace_section, nace_label, notes`. Populate it with a real, defensible mapping for the actual categories in the verified table — if a category is ambiguous, map it to NULL and add a note rather than guessing silently.
- **Mart** `benchmark_sector_emissions`: per NACE sector and year — total emissions, number of underlying source categories, and emissions share of national total. Keep the math simple and explicit; no clever SQL.
- **Tests** (must all be present):
  - `unique` + `not_null` on natural keys of staging and mart
  - relationship test: every staged category code exists in the seed mapping
  - singular test: national total in the mart deviates <0.5% from the source total (catches mapping gaps)
  - `accepted_values` on `nace_section`
- A `meta` block on the mart model documenting: source manifest reference, methodology summary, known limitations.

## Benchmark diff (`scripts/benchmark_diff.py`)

Takes two mart parquet outputs (e.g. `main` build vs PR build), joins on sector+year, and emits a markdown table: sector | year | old value | new value | Δ%. Sort by absolute Δ% descending, show top 20, flag anything >10% with a warning emoji. This output gets posted as a PR comment by CI.

## CI (`.github/workflows/ci.yml`)

On every PR and push to `main`:
1. `ruff check` + `ruff format --check` + `sqlfluff lint`
2. `pytest` (manifest logic: append-only enforcement, hash verification, schema validation — use small fixture parquet files, no network)
3. `dbt build` against a small fixture dataset committed under `tests/fixtures/` (a few hundred rows extracted from the real table), so CI never needs R2 credentials
4. Benchmark diff job: build mart on `main` and on the PR branch from the same fixture, run `benchmark_diff.py`, post result as a PR comment (use `peter-evans/create-or-update-comment` or equivalent)
5. A separate `reproducibility` job, manually triggerable via `workflow_dispatch` and weekly via cron, that runs `verify_reproducibility.py` against the real manifest + R2 (uses repo secrets; skip gracefully with a clear message if secrets are absent)

Branch protection setup is manual — at the end, print the exact `gh api` commands for me to run to require CI checks and one review on `main`. Do not run them yourself.

## Guardrails for you (Claude Code) during this build

- Commit per milestone (see build order), conventional commit messages, no giant single commit.
- Do not add dependencies beyond: dlt, dbt-core, dbt-duckdb, duckdb, pydantic, boto3, pyyaml, pytest, ruff, sqlfluff. Ask if you think you need more.
- Do not scaffold EEA/ETS/Evidence/agent code. Phase 1 only.
- Where the CBS API surprises you (schema oddities, weird category codes), document what you found in the README under "Source quirks" instead of silently working around it.
- Never invent emission figures or mapping entries. Real data from the API, or explicit NULL + note.

## Build order (commit after each)

1. Repo scaffold: pyproject, ruff/sqlfluff config, README skeleton, empty CI that runs lint
2. Step 0: verify CBS table, show me the metadata, wait for confirmation
3. `manifest.py` + pytest suite
4. dlt pipeline with `--offline` mode + fixture extraction (create `tests/fixtures/` from a real API pull)
5. dbt project: staging, seed (real mapping), mart, all tests passing on the fixture
6. `benchmark_diff.py` + `verify_reproducibility.py`
7. Full CI wiring incl. PR comment job
8. README completion: local quickstart, reproducibility story, R2 setup instructions, the `gh` branch-protection commands

## Definition of done

- `uv run python ingestion/cbs_pipeline.py --offline` runs end-to-end locally without credentials
- `dbt build` passes with all tests green on the fixture
- CI is green and posts a benchmark diff comment on a test PR
- I can read the README and explain to a third party how any benchmark number traces back to commit + manifest + immutable raw file
