---
title: Architecture
description: How an official figure becomes an auditable number on this site — the full pipeline, stage by stage.
---

Cairn is built like a data pipeline, not a dashboard. Every figure on this site is
the output of one fixed chain: an official source, pinned by hash, transformed by
reviewed code, into a versioned warehouse the site reads from. This is the
**structural** view — where each stage lives in the repo. For the provenance and
limitations of individual figures, see **[Methodology & sources →](/methodology)**.

## The pipeline

<div class="my-6 flex flex-col items-stretch gap-0 max-w-2xl">

<div class="rounded-lg border border-gray-300 dark:border-gray-700 p-4">
<div class="text-xs font-medium uppercase tracking-wide text-gray-500">1 · Official sources</div>
<div class="mt-1 font-medium">CBS StatLine 85669NED · euets.info · EEA Union Registry</div>
<div class="mt-1 text-sm text-gray-600 dark:text-gray-400">Public, official datasets. Nothing is hand-entered or estimated.</div>
</div>

<div class="self-center text-gray-400 py-1">↓</div>

<div class="rounded-lg border border-gray-300 dark:border-gray-700 p-4">
<div class="text-xs font-medium uppercase tracking-wide text-gray-500">2 · Ingestion</div>
<div class="mt-1 font-mono text-sm">ingestion/*.py</div>
<div class="mt-1 text-sm text-gray-600 dark:text-gray-400">Each run writes a new, versioned raw path. Raw data is immutable — never overwritten.</div>
</div>

<div class="self-center text-gray-400 py-1">↓</div>

<div class="rounded-lg border border-gray-300 dark:border-gray-700 p-4">
<div class="text-xs font-medium uppercase tracking-wide text-gray-500">3 · Manifest</div>
<div class="mt-1 font-mono text-sm">sources/cbs|euets|eea/manifest.yml</div>
<div class="mt-1 text-sm text-gray-600 dark:text-gray-400">Each release is pinned by <code>sha256</code> in an append-only manifest. A data change without a manifest change is impossible.</div>
</div>

<div class="self-center text-gray-400 py-1">↓</div>

<div class="rounded-lg border border-gray-300 dark:border-gray-700 p-4">
<div class="text-xs font-medium uppercase tracking-wide text-gray-500">4 · Transform (dbt)</div>
<div class="mt-1 font-mono text-sm">transform/ · seed: sector_mapping_cbs</div>
<div class="mt-1 text-sm text-gray-600 dark:text-gray-400">Mappings are code. The CBS category → NACE mapping is a reviewed seed, so its numeric impact shows up in a CI benchmark diff.</div>
</div>

<div class="self-center text-gray-400 py-1">↓</div>

<div class="rounded-lg border border-gray-300 dark:border-gray-700 p-4">
<div class="text-xs font-medium uppercase tracking-wide text-gray-500">5 · Warehouse</div>
<div class="mt-1 font-mono text-sm">cairn.duckdb (R2-pinned)</div>
<div class="mt-1 text-sm text-gray-600 dark:text-gray-400">Materialised by <code>scripts/materialize_warehouse.py</code>. The single source the exports and the site read from.</div>
</div>

<div class="self-center text-gray-400 py-1">↓</div>

<div class="rounded-lg border border-gray-300 dark:border-gray-700 p-4">
<div class="text-xs font-medium uppercase tracking-wide text-gray-500">6 · Exports</div>
<div class="mt-1 font-mono text-sm">scripts/export_esrs_e1.py · export_mart.py</div>
<div class="mt-1 text-sm text-gray-600 dark:text-gray-400">The ESRS E1 bundle: CSV plus a <code>meta.json</code> audit trail (source pin, methodology commit, warehouse version, SHA256 of the CSV).</div>
</div>

<div class="self-center text-gray-400 py-1">↓</div>

<div class="rounded-lg border border-gray-300 dark:border-gray-700 p-4">
<div class="text-xs font-medium uppercase tracking-wide text-gray-500">7 · Site</div>
<div class="mt-1 font-mono text-sm">site/ (Evidence)</div>
<div class="mt-1 text-sm text-gray-600 dark:text-gray-400">Reads only the warehouse. This site.</div>
</div>

</div>

## The CI rail

Running alongside every stage, not as an afterthought:

- A **weekly job re-verifies** the pinned raw files against their manifest hashes — a mismatch is an integrity alarm, not flakiness.
- A **reconciliation test** checks the ETS total against the EEA Union Registry aggregate; both derive from the EUTL and match to ~0.02%.
- <code>scripts/verify_reproducibility.py</code> confirms the warehouse rebuilds identically from the pinned sources.
- <code>scripts/benchmark_diff.py</code> surfaces the numeric impact of any mapping change in the pull request that makes it.

## The guarantee

Because each stage consumes only a hash-pinned input from the stage before it, **no
number can drift from its source without a manifest change and a failing CI build.**
That property — not the benchmark itself — is what separates Cairn from a dashboard.

See **[Methodology & sources →](/methodology)** for per-figure provenance, or the
[repository](https://github.com/fabiandemoel/Cairn) for the code behind each stage.
