# Cairn — Evidence site

The presentation layer for [Cairn](../README.md): an [Evidence](https://evidence.dev)
project that renders the dbt benchmark marts as a queryable, auditable site.

It reads the local DuckDB warehouse (`../cairn.duckdb`) that dbt builds — it
does **not** ingest or transform anything itself. Build the warehouse first, then
the site.

## Pages

- `pages/index.md` — overview + headline figures, and the auditability rules.
- `pages/sectors.md` — CBS sector benchmark (whole-economy denominator).
- `pages/installations.md` — EU ETS installation benchmark (large-emitter
  numerator), with a per-installation dropdown.
- `pages/methodology.md` — provenance and limitations of every figure.

## Data source

`sources/cairn/` connects to the dbt warehouse and exposes two queries
(`sector_emissions`, `installation_emissions`) that select straight from the
marts `benchmark_sector_emissions` and `benchmark_installation_emissions`.

## Run it locally

From the repo root, build the warehouse, then run the site:

```bash
# 1. build the DuckDB warehouse (defaults to the committed CI fixtures)
uv run dbt build --project-dir transform --profiles-dir transform

# 2. install + run the site
cd site
npm ci            # uses the committed lockfile (Evidence has known peer-dep quirks)
npm run sources   # materialise the source queries from cairn.duckdb
npm run dev       # http://localhost:3000
```

To build the static production site: `npm run build` → output in `site/build/`.
`npm run build:strict` fails on any query error (what CI runs).

## Notes

- `npm ci` (not `npm install`) — install from the committed lockfile. A fresh
  re-resolve hits Evidence's known `svelte2tsx`/`typescript` peer mismatch.
- The DuckDB connection path in `sources/cairn/connection.yaml` is resolved
  relative to that source directory, so it points three levels up
  (`../../../cairn.duckdb`) to the repo root.
- `node_modules/`, `build/`, `.svelte-kit/`, and `.evidence/` are gitignored.
