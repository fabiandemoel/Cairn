# Cairn

Cairn is a queryable benchmark layer on top of official EU/NL climate data
(CBS, EEA, EU ETS). It connects fragmented public sources and answers, per
sector: "how do your emissions compare to the sector average?"

> **Status**: Phase 1 — one CBS dataset, end-to-end (ingestion, transformation,
> manifest-based versioning, tests, CI). No agent automation, EEA/ETS, Evidence
> site, or CSRD export yet.

## Contents

- [What Cairn is](#what-cairn-is)
- [Architecture principles](#architecture-principles)
- [Local quickstart](#local-quickstart)
- [Reproducibility](#reproducibility)
- [Source quirks](#source-quirks)
- [R2 setup](#r2-setup)
- [Branch protection](#branch-protection)

## What Cairn is

Cairn turns scattered official climate data into an auditable, queryable
benchmark. Phase 1 ingests one CBS dataset end-to-end:

- **Source**: CBS StatLine table
  [`85669NED`](https://opendata.cbs.nl/statline/#/CBS/nl/dataset/85669NED) —
  *"Emissies van broeikasgassen berekend volgens IPCC-voorschriften"*
  (greenhouse-gas emissions per climate sector, IPCC method, annual, 1990–2025).
- **Ingestion** ([`ingestion/`](ingestion/)): a `dlt` pipeline pulls the table
  from the CBS OData v4 API, writes immutable per-release parquet, and pins the
  snapshot in a manifest.
- **Transformation** ([`transform/`](transform/)): a dbt + DuckDB project that
  decodes the raw data, maps CBS source categories to **NACE** sections via a
  version-controlled seed, and builds `benchmark_sector_emissions` — emissions
  and national share per NACE section and year.
- **CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): lint, tests,
  a fixture `dbt build`, a benchmark-diff PR comment, and a weekly
  reproducibility check.

Every benchmark figure traces back to **a git commit + a manifest entry + an
immutable raw file** (see [Reproducibility](#reproducibility)).

## Architecture principles

1. Git is the single source of truth for code, mappings, and manifests. Raw
   data lives in object storage (Cloudflare R2), never in git.
2. Raw data is immutable — every ingest writes to a new, versioned path.
   Nothing is ever overwritten.
3. Manifests pin everything — a manifest entry in git records dataset,
   release version/date, storage URL, SHA256, and ingest timestamp for every
   snapshot.
4. Mappings are code — sector mapping tables are version-controlled seed
   files, reviewed via PRs.
5. CI guards the methodology — tests fail the build, and a benchmark diff
   makes the impact of any change visible at review time.

## Local quickstart

Prerequisites: [`uv`](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync --all-groups          # install locked dependencies
```

**Run the dbt project against the committed fixture** (no credentials needed):

```bash
uv run dbt build --project-dir transform --profiles-dir transform
```

This builds the staging view, the sector-mapping seed and the
`benchmark_sector_emissions` mart, and runs every test against a small fixture
under [`tests/fixtures/`](tests/fixtures/). Query the result:

```bash
uv run python -c "import duckdb; \
  print(duckdb.connect('cairn.duckdb').sql( \
  'SELECT year, nace_section, round(sector_emissions_mt_co2eq,1), round(emissions_share,3) \
   FROM main.benchmark_sector_emissions ORDER BY year, nace_section').fetchall())"
```

**Run the full ingestion pipeline offline** (hits the CBS API, writes raw files
to `./.localstack/` instead of R2 — no credentials needed):

```bash
uv run python -m ingestion.cbs_pipeline --offline
```

It fetches the table, and **if the CBS `Modified` date already matches the
latest manifest snapshot it exits with "no new release"** and changes nothing.
To build the mart against a freshly-ingested local snapshot:

```bash
uv run dbt build --project-dir transform --profiles-dir transform \
  --vars "{raw_dir: .localstack/cbs/85669NED/<release-date>}"
```

**Run the tests and linters** (what CI runs):

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run sqlfluff lint transform/models transform/tests
```

## Reproducibility

Any benchmark number can be traced back to three things, all under version
control or content-addressed:

1. **A git commit** — the SQL models, the `sector_mapping_cbs` seed, and the
   ingestion code are all in git. Change a mapping and the diff is reviewable;
   CI posts a benchmark diff so the numeric impact is visible before merge.
2. **A manifest entry** — [`sources/cbs/manifest.yml`](sources/cbs/manifest.yml)
   pins each snapshot: the CBS release date, the storage URL, the **SHA256 of
   the raw parquet**, the row count, and the periods covered. The manifest is
   append-only by construction (`ingestion/manifest.py` refuses to modify or
   delete entries), and the ingestion pipeline's final, unconditional step is
   the manifest write — so raw data cannot change without a manifest change.
3. **An immutable raw file** — the raw parquet lives at a versioned R2 path
   (`cbs/<table>/<release>/data.parquet`) that is never overwritten.

[`scripts/verify_reproducibility.py`](scripts/verify_reproducibility.py) closes
the loop: it picks a manifest snapshot, re-downloads the raw file, recomputes
the SHA256 and compares it to the pin, then rebuilds the mart from that exact
file. CI runs it weekly and on demand (`workflow_dispatch`); it skips cleanly
when R2 secrets are absent.

```bash
uv run python scripts/verify_reproducibility.py            # latest snapshot
uv run python scripts/verify_reproducibility.py --release 2026-03-11
```

## Source quirks

Documenting what the CBS source actually does, so the modeling choices are
auditable rather than hidden.

- **Table choice (`85669NED`, not `84979NED`).** Phase 1 planning named
  `84979NED` as a likely candidate, but on verification that table is
  *"Emissies broeikasgassen (IPCC); klimaatsector, kwartaal"* — quarterly data
  from 2019 broken down into only the **six** broad Klimaatakkoord sectors,
  which do not map to NACE. `85669NED` is the table whose title actually matches
  the IPCC brief, with **annual data from 1990** and **52 climate-sector
  categories carrying SBI (= NACE Rev.2) codes**, which is what the NACE
  benchmark needs. Both tables are active (`Status: Regulier`).
- **OData v4, not v3.** CBS retired the v3 `TypedDataSet` feed
  (`opendata.cbs.nl/ODataApi`); it returns `HTTP 406` here. The pipeline targets
  the v4 API at `datasets.cbs.nl/odata/v1/CBS/<table>`. v4 does not return one
  denormalised table: it exposes coded `Observations` plus a `*Codes` entity set
  per dimension. The pipeline persists the observations as `data.parquet` (the
  hashed artifact) and the decode tables as `dim_*.parquet` alongside it.
- **The climate-sector dimension is a hierarchy.** The 52 categories mix a grand
  total (`Totaal klimaatsectoren`), subtotals (`Stationaire bronnen; totaal`,
  `Industrie`, `Wegverkeer; totaal`, …) and leaves (SBI-coded industries,
  transport modes). Stationary + mobile sources sum to the national total. The
  seed flags totals/subtotals with `aggregate = true`; the mart sums **only leaf
  categories** so the total is partitioned exactly once (no double counting).
  The `assert_national_total_reconciles` test guards this (<0.5% drift).
- **Bunkers are excluded.** `Afzet voor bunkers` (international aviation and
  shipping) are IPCC memo items **outside** the national total. They are flagged
  `aggregate = true` and excluded, matching CBS's own national-total definition.
- **Provisional years lack the full breakdown.** The latest year (2025,
  `Voorlopig`) publishes the national total but not yet the detailed sector
  split, so its leaf sum is far below the total. The mart restricts to
  `period_status = 'Definitief'` (final figures), which also suits CSRD
  auditability.
- **Not everything maps to a NACE section.** Households, land use (LULUCF),
  on-road/rail/water/air transport (classified by vehicle type, not operator
  sector), and the CBS `G-U Dienstverlening` aggregate (which spans many NACE
  sections) are left **NULL with a note** in the seed and bucketed as
  `UNMAPPED` in the mart — about 30–35% of national emissions. They are still
  counted so the total reconciles; they are simply not attributed to a single
  NACE section. See [`transform/seeds/sector_mapping_cbs.csv`](transform/seeds/sector_mapping_cbs.csv).
- **Units.** The source measure is `miljard kg CO2-equivalent` (billion kg =
  megatonnes); columns are named `*_mt_co2eq`. CBS rounds to 0.1 Mt, which is
  why reconciliation tolerates small (<0.5%) drift.

## R2 setup

Raw data is stored in a Cloudflare R2 bucket (S3-compatible). The ingestion
pipeline and the reproducibility script read these env vars:

| Variable | Meaning |
| --- | --- |
| `R2_ENDPOINT` | R2 S3 endpoint, e.g. `https://<account>.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` | R2 access key id |
| `R2_SECRET_ACCESS_KEY` | R2 secret access key |
| `R2_BUCKET` | bucket name, e.g. `cairn-raw` |

```bash
export R2_ENDPOINT="https://<account>.r2.cloudflarestorage.com"
export R2_ACCESS_KEY_ID="..."
export R2_SECRET_ACCESS_KEY="..."
export R2_BUCKET="cairn-raw"

uv run python -m ingestion.cbs_pipeline      # ingest to R2 + update manifest
```

The pipeline writes to the immutable path `cbs/<table>/<release>/` and never
overwrites. For CI, store the same four values as repository secrets; the
reproducibility job reads them and skips gracefully if they are unset. Run
`--offline` to exercise the whole pipeline locally without any of this.

## Branch protection

Branch protection is configured manually. After CI has run once on `main` (so
the check names exist), require the CI jobs and one review with these `gh`
commands — **run them yourself; this repo's automation does not**:

```bash
gh api -X PUT repos/:owner/:repo/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "checks": [
      {"context": "lint"},
      {"context": "test"},
      {"context": "dbt-build"}
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 1 },
  "restrictions": null
}
JSON
```

(The `benchmark-diff` job posts a comment and is intentionally **not** a
required check, so a legitimate methodology change is never blocked — it is made
visible for review instead.)
