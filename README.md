# Cairn

Cairn builds reproducible climate datasets from official EU/NL public sources
(CBS, EEA, EU ETS) with full lineage — every figure traces back to a versioned,
pinned source. It answers, per sector: "how do your emissions compare to the
sector average?", and supports ESRS E1-6 reporting as one application of that
auditability.

[![Live site](https://img.shields.io/badge/live%20site-cairn.fabiandemoel.net-2563eb?logo=githubpages&logoColor=white)](https://cairn.fabiandemoel.net/)
[![Version](https://img.shields.io/badge/version-v1.1.0%20%C2%B7%20Phase%204-45a1bf)](https://github.com/fabiandemoel/Cairn)

**Live site:** <https://cairn.fabiandemoel.net/>

> **Status**: Phases 1–4 complete; automated maintenance running. Phase 1
> delivered CBS `85669NED` end-to-end (sector averages, the *denominator*). Phase 2
> added **EU ETS at installation level** (the *numerator*): per Dutch installation,
> its verified emissions benchmarked against its NACE-sector peers. Phase 3 added
> the **Evidence site** (`site/`). Phase 4 added the **CSRD/ESRS E1 export**
> (`mart_esrs_e1`). Additional sources since added: **Eurostat AEA**
> (`env_ac_ainah_r2`, cross-country NACE sector benchmarks) and **Eurostat GGE**
> (`env_air_gge`, national GHG totals cross-check). Automation: a no-LLM
> dispatcher (weekly freshness check + per-merge backlog dispatch) opens the
> issues, and two agent workflows handle implement (issue → PR on approval)
> and replenish (weekly backlog curation) — see [`CLAUDE.md`](CLAUDE.md).

> **Maintainers & agents**: see [`CLAUDE.md`](CLAUDE.md) for the upkeep routine
> (handling new CBS releases, refreshing fixtures, the classification migration
> ahead) and the architecture invariants that must not be broken.

## Contents

- [What Cairn is](#what-cairn-is)
- [Architecture principles](#architecture-principles)
- [Local quickstart](#local-quickstart)
- [The Evidence site](#the-evidence-site)
- [The CSRD/ESRS E1 export](#the-csrdesrs-e1-export)
- [Reproducibility](#reproducibility)
- [Source quirks](#source-quirks)
- [References & methodology](#references--methodology)
- [R2 setup](#r2-setup)
- [Branch protection](#branch-protection)

## What Cairn is

Cairn builds reproducible climate datasets from official public sources with
complete lineage. CSRD/ESRS reporting is one application of that auditability —
the same data answers, per sector: "how do your emissions compare to the
sector average?" It ingests four sources end-to-end.

**Source 1 — CBS (sector averages, the denominator).**

- CBS StatLine table
  [`85669NED`](https://opendata.cbs.nl/statline/#/CBS/nl/dataset/85669NED) —
  *"Emissies van broeikasgassen berekend volgens IPCC-voorschriften"*
  (greenhouse-gas emissions per climate sector, IPCC method, annual, 1990–2025).
- **Ingestion**: a `dlt` pipeline pulls the table from the CBS OData v4 API.
- **Transformation**: maps CBS source categories to **NACE** sections via a
  version-controlled seed, and builds `benchmark_sector_emissions` — emissions
  and national share per NACE section and year.

**Source 2 — EU ETS (installation level, the numerator).**

- **Pin of record**: [euets.info](https://www.euets.info/) (Jan Abrell / EUI),
  a reprocessing of the EU Transaction Log with per-installation verified
  emissions and a native NACE code. Ingested as a versioned zip from a stable
  S3 URL.
- **Cross-check & denominator**: the EEA
  [EU ETS data from the Union Registry](https://www.eea.europa.eu/en/datahub/datahubitem-view/98f04097-26de-4fca-86c4-63834818c0c0)
  bulk — the official, current aggregate by country × activity × year.
- **Transformation**: `benchmark_installation_emissions` — per NL stationary
  installation and year, its verified emissions versus its NACE-section mean
  and median, plus its free allocation (`allocated_total`, read straight from
  the pinned snapshot) and the verified-vs-allocated ratio — who emits above or
  below their free grant. A coverage test reconciles the ETS total against the
  EEA aggregate (both derive from the EUTL; they match to ~0.02%).

**Source 3 — Eurostat AEA (`env_ac_ainah_r2`, cross-country sector benchmark).**

- Eurostat dataset
  [`env_ac_ainah_r2`](https://ec.europa.eu/eurostat/databrowser/view/env_ac_ainah_r2)
  — *Air emissions accounts by NACE Rev. 2 activity*: GHG and air-pollutant
  emissions per country, NACE section and year, covering all EU member states
  plus Norway, Iceland and the UK.
- **Principle:** residence (emissions by resident producers, regardless of where
  they occur). Diverges from the territorial CBS/ETS total for sectors with
  significant cross-border activity (transport, multinationals).
- **Transformation**: `benchmark_country_sector_emissions` — national GHG per
  NACE section and year for each country, enabling cross-country sector
  comparison.

**Source 4 — Eurostat GGE (`env_air_gge`, national GHG cross-check).**

- Eurostat dataset
  [`env_air_gge`](https://ec.europa.eu/eurostat/databrowser/view/env_air_gge)
  — *Greenhouse gas emissions by source sector*: national GHG totals from UNFCCC
  national inventory submissions, by country, CRF sector and year.
- **Principle:** territorial (same as CBS 85669NED), enabling a direct
  cross-check of the NL national total (`assert_gge_nl_total_within_cbs`,
  ±10% tolerance to accommodate UNFCCC submission-vs-CBS revision cycles).
- **Transformation**: `mart_gge_national_totals` — national GHG per country and
  year (`TOTXMEMO`, GHG, MIO_T), used on the country GHG page.

**Common spine** ([`ingestion/`](ingestion/), [`transform/`](transform/)): every
source writes immutable per-release parquet and pins each snapshot in its own
manifest under [`sources/`](sources/). **CI**
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): lint, tests, a fixture
`dbt build`, a benchmark-diff PR comment (CBS mart), and a weekly
reproducibility check across all sources.

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

**The EU ETS sources** work the same way (download to `./.localstack/`, no
credentials):

```bash
uv run python -m ingestion.euets_pipeline --offline    # installation level (euets.info)
uv run python -m ingestion.eea_ets_pipeline --offline  # official aggregate (EEA)
```

Both derive their release from the source filename and exit cleanly if it is
already pinned. After ingesting, refresh the small committed CI fixtures from
the local snapshots and build the installation mart:

```bash
uv run python scripts/build_eu_ets_fixtures.py
uv run dbt build --project-dir transform --profiles-dir transform \
  --vars "{euets_raw_dir: .localstack/euets/eutl/<release>, eea_raw_dir: .localstack/eea/eu-ets/<release>}"
```

**The Eurostat sources** work the same way:

```bash
uv run python -m ingestion.eurostat_aea_pipeline --offline  # AEA (cross-country sector benchmark)
uv run python -m ingestion.eurostat_gge_pipeline --offline  # GGE (national GHG cross-check)
```

Each fetches the dataset's last-update date from the Eurostat SDMX API and
exits cleanly if that release is already pinned. Build against a freshly
ingested local AEA or GGE snapshot by passing the matching `--vars`:

```bash
uv run dbt build --project-dir transform --profiles-dir transform \
  --vars "{eurostat_aea_raw_dir: .localstack/eurostat/env_ac_ainah_r2/<release>}"

uv run dbt build --project-dir transform --profiles-dir transform \
  --vars "{eurostat_gge_raw_dir: .localstack/eurostat/env_air_gge/<release>}"
```

**Run the tests and linters** (what CI runs):

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run sqlfluff lint transform/models transform/tests
```

## The Evidence site

[`site/`](site/) is the presentation layer: an [Evidence](https://evidence.dev)
project that renders the dbt marts as a queryable, auditable site. It is
**read-only** — it reads the `cairn.duckdb` warehouse that dbt builds and never
ingests or transforms anything itself.

```bash
# 1. build the warehouse (above) so cairn.duckdb exists, then:
cd site
npm ci             # install from the committed lockfile (not npm install)
npm run sources    # materialise the source queries from cairn.duckdb
npm run dev        # live preview at http://localhost:3000
```

`npm run build` produces the static site in `site/build/`; CI's `evidence-build`
job runs `npm run build:strict`, which fails on any query error. Pages: an
overview, the **CBS sector benchmark**, the interactive **EU ETS installation
benchmark**, a **methodology & sources** page documenting the provenance of
every figure, a **data quality** page reporting the live pin status of each
source (from `mart_data_provenance`, a read-only view over the manifests), and a
**data dictionary & glossary** page listing every model and column with the
tests that guard it (from `mart_data_dictionary`, generated from the dbt schema
files) alongside definitions of the cross-cutting concepts (from
`mart_business_glossary`, a read-only view over the reviewed
[`transform/glossary.yml`](transform/glossary.yml)). See
[`site/README.md`](site/README.md) for details.

### Live deployment (GitHub Pages)

The site is live at **<https://cairn.fabiandemoel.net/>** (a version badge
sits at the top of the homepage), served from GitHub Pages on a custom subdomain.

The [`pages.yml`](.github/workflows/pages.yml) workflow publishes the site to
GitHub Pages on every push to `main`. It does **not** use the committed fixtures:
[`scripts/materialize_warehouse.py`](scripts/materialize_warehouse.py) downloads
every source's pinned snapshot from R2, **verifies each SHA256 against the
manifest**, and builds the warehouse from that — so the published numbers carry
the same provenance guarantee as the reproducibility check. It fails loudly if
the `R2_*` secrets are absent or any source is unpinned, so the site is never
published from incomplete or unverified data.

The site is served at the **root** of the custom subdomain
`cairn.fabiandemoel.net` (no base path), pinned by
[`site/static/CNAME`](site/static/CNAME) — Evidence copies it into the build, so
each Actions deploy reapplies the custom domain. DNS: a `CNAME` record for
`cairn` → `fabiandemoel.github.io`.

All four sources are pinned to R2 (CBS `85669NED`, euets.info, the EEA bulk,
Eurostat AEA, and Eurostat GGE), so every push to `main` republishes the site
from the pinned data. When a source publishes a new release, re-run its pipeline
to establish the new pin and commit the manifest change in a PR — see the
per-source checklists in [`CLAUDE.md`](CLAUDE.md):

```bash
uv run python -m ingestion.euets_pipeline             # -> R2 + sources/euets/manifest.yml
uv run python -m ingestion.eea_ets_pipeline           # -> R2 + sources/eea/manifest.yml
uv run python -m ingestion.eurostat_aea_pipeline      # -> R2 + sources/eurostat/manifest.yml
uv run python -m ingestion.eurostat_gge_pipeline      # -> R2 + sources/eurostat_gge/manifest.yml
```

Each pipeline is idempotent — it exits "no new release" if the current release
is already pinned, so it is safe to re-run.

## The CSRD/ESRS E1 export

[`scripts/export_esrs_e1.py`](scripts/export_esrs_e1.py) turns the
`mart_esrs_e1` mart into a self-contained, **auditable disclosure bundle** a
third party (an auditor, a data consumer, a regulator) can pick up on its own.
It recomputes nothing — it reads the warehouse and writes:

```bash
# build the warehouse first (dbt build, or scripts/materialize_warehouse.py)
uv run python scripts/export_esrs_e1.py        # -> exports/esrs_e1/
```

- `esrs_e1_disclosure.csv` — verified EU ETS emissions provided as the verified
  basis for the ESRS E1-6 *gross Scope 1 GHG emissions* datapoint (t CO₂eq), one
  row per installation-year, with the NACE-section benchmark as context.
- `esrs_e1_disclosure.meta.json` — the audit trail: the EU ETS source pin
  (release + SHA256 from the manifest), the methodology git commit, the
  warehouse version, a data dictionary, and a SHA256 of the CSV so a consumer
  can prove the file was not altered after export.
- `README.md` — how to read and verify the bundle.

**Scope 1 only.** ESRS E1-6 also requires Scope 2 and Scope 3; Cairn has no
source for them, so they are omitted — never filled with placeholder figures.
The export is generated on demand (it is git-ignored), so the disclosure always
traces to the warehouse it was built from.

## Reproducibility

Any benchmark number can be traced back to three things, all under version
control or content-addressed:

1. **A git commit** — the SQL models, the `sector_mapping_cbs` seed, and the
   ingestion code are all in git. Change a mapping and the diff is reviewable;
   CI posts a benchmark diff so the numeric impact is visible before merge.
2. **A manifest entry** — each source has its own append-only manifest under
   [`sources/`](sources/) (`cbs/`, `euets/`, `eea/`). It pins every snapshot:
   the release, the storage URL, the **SHA256 of the primary raw file**, the row
   count, and the periods covered. The manifest is append-only by construction
   (`ingestion/manifest.py` refuses to modify or delete entries), and each
   pipeline's final, unconditional step is the manifest write — so raw data
   cannot change without a manifest change.
3. **An immutable raw file** — the raw parquet lives at a versioned R2 path
   (`<source>/<dataset>/<release>/…`) that is never overwritten.

[`scripts/verify_reproducibility.py`](scripts/verify_reproducibility.py) closes
the loop: for each source it picks a manifest snapshot, re-downloads the raw
files, recomputes the SHA256 of the primary file and compares it to the pin,
then rebuilds the project from that exact file. CI runs it weekly and on demand
(`workflow_dispatch`); it skips cleanly, per source, when R2 secrets are absent
or when no snapshot is pinned yet.

```bash
uv run python scripts/verify_reproducibility.py                      # all sources, latest
uv run python scripts/verify_reproducibility.py --source euets --release 2024-10
```

> The manifests ship with **no snapshots pinned** — the first real ingest to R2
> (below) establishes the pin of record. Until then there is nothing to verify.

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
  `aggregate = true` and excluded, matching the national-total definition in the
  [2006 IPCC Guidelines](https://www.ipcc.ch/report/2006-ipcc-guidelines-for-national-greenhouse-gas-inventories/)
  that the table follows (reported via the Dutch
  [UNFCCC National Inventory](https://unfccc.int/ghg-inventories-annex-i-parties/2025)).
- **Provisional years lack the full breakdown.** The latest year (2025,
  `Voorlopig`) publishes the national total but not yet the detailed sector
  split, so its leaf sum is far below the total. The mart restricts to
  `period_status = 'Definitief'` (final figures), which also suits CSRD
  auditability.
- **The SBI → NACE mapping is well-founded.** The stationary categories carry
  Dutch [SBI 2008](https://www.cbs.nl/nl-nl/onze-diensten/methoden/classificaties/activiteiten/sbi-2008-standaard-bedrijfsindeling-2008)
  codes, whose first four digits are by construction equal to
  [NACE Rev.2](https://ec.europa.eu/eurostat/web/nace) (Regulation
  [(EC) No 1893/2006](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32006R1893)).
  So mapping each SBI category to its NACE **section** letter is a documented
  classification crosswalk, not a guess.
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

The **EU ETS** source has its own quirks:

- **No installation-level API; two sources by design.** The EEA "EU ETS data
  from the Union Registry" bulk is **aggregated only** (country × main activity
  × year; `active_installation` is always `all entities`) — it cannot answer an
  installation-level question. So the installation pin of record is
  **euets.info** (a reprocessing of the EU Transaction Log, shipped as a
  versioned zip of normalised CSVs at a stable S3 URL), and the EEA bulk is kept
  as the official, current aggregate and a cross-check. Ingestion is
  download + hash, not a feed; the release is the source filename's version
  token.
- **euets.info lags the EEA release.** Its latest vintage has verified emissions
  through ~2023; the EEA bulk runs to 2025. Use the EEA figures when currency
  matters.
- **ETS "main activity" ≠ NACE — but euets.info carries native NACE.** The raw
  EUTL activity classification is not NACE, but euets.info already attaches a
  NACE code per installation (and a full NACE hierarchy), so the section letter
  is resolved by walking that hierarchy — no invented crosswalk. Installations
  with no NACE code cannot be sector-benchmarked and are excluded.
- **ETS is a subset, not a national total.** It covers only large emitters, so
  there is no national-total reconciliation. Instead `assert_euets_coverage_within_eea`
  checks (one-sided) that the installation total does not exceed the EEA
  stationary aggregate (`20-99`, verified emissions); both derive from the EUTL
  and match to ~0.02% on real data.
- **The compliance grain includes the trading system.** Linked registries
  report the same installation-year under both `euets` and the Swiss `chets`,
  so the natural key is installation × year × system; the mart keeps only
  `euets`.
- **Aircraft, maritime, and missing-flag operators are excluded.** The
  installation benchmark is stationary only; aircraft and maritime operators are
  classified by vehicle, and the few installations with a NULL operator flag are
  treated as not-confirmed-stationary and left out.
- **Legal-entity (LEI) matching is a reviewed mapping, not an automatic join.**
  The EUTL `parentCompany` field is free text and the installation name is often
  a site label, so there is no authoritative installation → company key in the
  source. The
  [`lei_mapping_euets.csv`](transform/seeds/lei_mapping_euets.csv) seed pins each
  installation to its operating entity's GLEIF LEI **only where the GLEIF
  legalName confidently matches** (NL jurisdiction); unmatched installations keep
  a `NULL` LEI with a note — never an invented identifier — and coverage grows
  via reviewed PRs (so `benchmark-diff` shows each change). `assert_lei_format_valid`
  fails the build if any seeded LEI is not a 20-character ISO 17442 code.
- **The EEA bulk is an Excel workbook.** Only the data sheet is ingested (read
  via the DuckDB `excel` extension, all-VARCHAR); the manuals/PDFs in the zip
  are not.
- **The EEA `year` column mixes years with trading-period totals.** Alongside
  per-year rows it carries aggregate rows whose `year` is a label like
  `Total 1st trading period (05-07)`. Those are sums over years (they would
  double-count) and are non-numeric, so `stg_eea__ets` keeps only true per-year
  rows before casting `year` to integer.
- **The EEA bulk has a known duplicate (Czechia).** CZ's allocated-allowances at
  the `20-99` aggregate appears twice — a spurious `0` alongside the real value.
  `stg_eea__ets` collapses exact-grain duplicates, keeping the larger value. It
  sits outside the NL coverage sum, so it does not affect the benchmark.

The **Eurostat `env_air_gge`** source has its own quirks:

- **UNFCCC submission lag: latest available year is 2024 (as of the 2026-06-02
  release).** UNFCCC national inventory submissions trail the current calendar
  year by 1–2 years. When CBS has already published a more recent year, the GHG
  cross-check will be behind by that lag — this is expected. The staging model
  must filter to the intersection of years available in both sources before
  running the cross-check test.
- **CRF sectors are not NACE economic sectors.** `env_air_gge` uses the IPCC
  Common Reporting Format (CRF) classification (`CRF1` = Energy, `CRF2` =
  Industrial processes, etc.), which cannot be mapped to NACE without significant
  assumptions. The national totals (`src_crf = 'TOTXMEMO'`, excluding memo items)
  are the only grain used for the CBS cross-check; sector-level CRF rows are kept
  raw for completeness but are not used in any mart.
- **Territorial principle — same as CBS.** Unlike the AEA (`env_ac_ainah_r2`,
  which uses the residence principle), `env_air_gge` uses the territorial
  principle, so the Netherlands total is a direct cross-check of CBS 85669NED
  without any residence/territorial bridge correction.
- **Do not conflate with AEA (`env_ac_ainah_r2`).** AEA provides NACE-sector
  breakdowns for the EU-wide sector benchmark and uses the residence principle;
  `env_air_gge` provides national GHG totals by CRF sector and uses the
  territorial principle. They serve different purposes and come from different
  inventories.

The **CBS NAMEA `83300NED`** source (air emission accounts) has its own quirks:

- **Residence principle — diverges from `85669NED` by design.** `83300NED`
  (*Emissies naar lucht door de Nederlandse economie; nationale rekeningen*)
  attributes emissions to Dutch-resident economic activity: Dutch operators
  abroad count, non-residents on Dutch territory do not. Its totals therefore
  do **not** reconcile with the territorial `85669NED` — the gap is
  methodological (largest for transport/shipping), to be documented as a bridge,
  never "fixed" with a reconciliation test. It is the Dutch side of the
  Eurostat AEA (residence-principle) picture.
- **Same OData v4 shape as `85669NED`.** Annual update (November), release
  detected via the `Properties` singleton's `Modified` date; coded
  `Observations` plus `NederlandseEconomieCodes` / `PeriodenCodes` /
  `MeasureCodes` decode tables. The v3-API-returns-406 gotcha applies here too.

## References & methodology

The data, the methodology and the classification logic are all grounded in
public, authoritative sources.

**Source data & emission methodology**

- CBS StatLine table `85669NED`, *Emissies van broeikasgassen berekend volgens
  IPCC-voorschriften* —
  [dataset](https://opendata.cbs.nl/statline/#/CBS/nl/dataset/85669NED) ·
  [OData v4 API](https://datasets.cbs.nl/odata/v1/CBS/85669NED) ·
  [CBS Dossier Broeikasgassen](https://www.cbs.nl/nl-nl/dossier/dossier-broeikasgassen).
- [2006 IPCC Guidelines for National Greenhouse Gas Inventories](https://www.ipcc.ch/report/2006-ipcc-guidelines-for-national-greenhouse-gas-inventories/)
  ([IPCC-NGGIP](https://www.ipcc-nggip.iges.or.jp/)) — the accounting framework
  (sector scope, national-total definition, bunkers as memo items) the table
  implements.
- [Netherlands UNFCCC National Inventory submission](https://unfccc.int/ghg-inventories-annex-i-parties/2025)
  and [RIVM Emissieregistratie](https://www.emissieregistratie.nl/) — the
  upstream inventory and emission factors behind the CBS figures.
- [CBS method note: maand- en kwartaalraming broeikasgasemissies conform IPCC](https://www.cbs.nl/nl-nl/maatwerk/2020/37/maand-en-kwartaalraming-broeikasgasemissies-conform-ipcc).

**Eurostat Air Emissions Accounts**

- Eurostat dataset [`env_ac_ainah_r2`](https://ec.europa.eu/eurostat/databrowser/view/env_ac_ainah_r2)
  — *Air emissions accounts by NACE Rev. 2 activity*: GHG and air-pollutant
  emissions per country, NACE section and year, covering all EU member states.
  The source of `benchmark_country_sector_emissions`.
- Eurostat dataset [`env_ac_aibrid_r2`](https://ec.europa.eu/eurostat/databrowser/view/env_ac_aibrid_r2)
  — *Bridge between air emissions accounts and national inventories*: quantifies
  the legitimate residual between the AEA (residence principle — emissions by
  resident producers regardless of where they occur) and the national inventory
  (territorial principle — emissions occurring within the country's borders
  regardless of the producer's nationality). CBS 85669NED and the EU ETS both
  use the territorial principle, so NL totals from the two sources will differ
  by this bridge amount. Cairn cites `env_ac_aibrid_r2` as the documented
  explanation; it is not ingested.
- [Eurostat Air Emissions Accounts methodology](https://ec.europa.eu/eurostat/web/environment/air-emissions-accounts)
  — background on the residence-vs-territorial accounting distinction and the
  NACE breakdown used in `env_ac_ainah_r2`.

**EU ETS source data**

- [euets.info](https://www.euets.info/) (Jan Abrell, EUI) — the installation
  pin of record;
  [EUTL database description](https://euets-info-public.s3.eu-central-1.amazonaws.com/Description_EUTL_database.pdf)
  and the [`pyeutl`](https://github.com/jabrell/pyeutl) processing routines
  document how the raw EU Transaction Log is rebuilt and how NACE is attached.
- EEA [EU ETS data from the Union Registry](https://www.eea.europa.eu/en/datahub/datahubitem-view/98f04097-26de-4fca-86c4-63834818c0c0)
  and the [EU ETS data viewer](https://www.eea.europa.eu/data-and-maps/dashboards/emissions-trading-viewer-1)
  — the official aggregate and cross-check.
- [EU ETS Directive 2003/87/EC](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32003L0087)
  — the scheme that defines which installations report verified emissions.
- [GLEIF — the Global Legal Entity Identifier Foundation](https://www.gleif.org/en/about-lei/introducing-the-legal-entity-identifier-lei)
  ([open LEI API](https://www.gleif.org/en/lei-data/gleif-api)) — the ISO 17442
  registration authority behind the reviewed
  [`lei_mapping_euets.csv`](transform/seeds/lei_mapping_euets.csv) seed, which
  attaches each installation's operating legal entity's LEI so the benchmark can
  roll up to company level.

**Classification (the sector mapping)**

- [NACE Rev.2](https://ec.europa.eu/eurostat/web/nace), Regulation
  [(EC) No 1893/2006](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32006R1893)
  — the benchmark's target sector classification.
- [SBI 2008](https://www.cbs.nl/nl-nl/onze-diensten/methoden/classificaties/activiteiten/sbi-2008-standaard-bedrijfsindeling-2008)
  — CBS's activity classification; its first four digits equal NACE Rev.2, which
  is what makes the CBS-category → NACE-section crosswalk defensible.

**Sector framing & intended use**

- [Klimaatakkoord](https://www.klimaatakkoord.nl/) and its
  [sectortafels](https://www.klimaatakkoord.nl/organisatie/hoe-het-klimaatakkoord-tot-stand-kwam/sectortafels)
  ([Rijksoverheid](https://www.rijksoverheid.nl/documenten/2019/06/28/klimaatakkoord))
  — the six climate sectors used by CBS for this table.
- [CSRD (Directive (EU) 2022/2464)](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2464)
  and the climate standard
  [ESRS E1 (Delegated Regulation (EU) 2023/2772)](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202302772)
  — the disclosure context Cairn's benchmarks are ultimately built to serve.

## R2 setup

Raw data is stored in a Cloudflare R2 bucket (S3-compatible). You only need this
to ingest for real and to run the reproducibility check against stored data;
`--offline` runs and the fixture `dbt build` need none of it.

**1. Create the bucket and credentials (Cloudflare dashboard).**

- R2 → *Create bucket* → name it **`cairn-raw`** (the pipeline writes under this
  bucket; pick another name only if you also pass `R2_BUCKET` accordingly).
- R2 → *Manage R2 API Tokens* → *Create API token* with **Object Read & Write**,
  scoped to that bucket. Copy the **Access Key ID** and **Secret Access Key**
  (the secret is shown once).
- Your **Account ID** is on the R2 overview page; the S3 endpoint is
  `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.

**2. Provide the four values.**

| Variable | Meaning |
| --- | --- |
| `R2_ENDPOINT` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` | R2 access key id |
| `R2_SECRET_ACCESS_KEY` | R2 secret access key |
| `R2_BUCKET` | bucket name, e.g. `cairn-raw` |

Locally, export them; for CI, add the same four as repository **Actions
secrets** (Settings → Secrets and variables → Actions) so the weekly
reproducibility job can read them.

**3. Run the first ingest — this establishes the pin of record.**

```bash
export R2_ENDPOINT="https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
export R2_ACCESS_KEY_ID="..."
export R2_SECRET_ACCESS_KEY="..."
export R2_BUCKET="cairn-raw"

uv run python -m ingestion.cbs_pipeline              # CBS -> R2 + append manifest snapshot
uv run python -m ingestion.euets_pipeline            # EU ETS installations (euets.info)
uv run python -m ingestion.eea_ets_pipeline          # EU ETS official aggregate (EEA)
uv run python -m ingestion.eurostat_aea_pipeline     # Eurostat AEA (cross-country sector benchmark)
uv run python -m ingestion.eurostat_gge_pipeline     # Eurostat GGE (national GHG cross-check)
uv run python scripts/verify_reproducibility.py      # re-download, check SHA256, rebuild (all sources)
```

Each pipeline uploads its immutable raw files to `<source>/<dataset>/<release>/`
(never overwriting) and **appends** the first snapshot to its manifest under
`sources/`. Commit those manifest changes in a PR. From then on each run is
idempotent: if the source release is unchanged it exits "no new release" and
touches nothing.

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
