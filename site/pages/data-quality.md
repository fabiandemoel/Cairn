---
title: Data quality — provenance, coverage & freshness
description: Is every figure on this site still chained, by hash, to an immutable official source, how completely does each source's data cover the official aggregate it derives from, and how current is it? Straight from the manifests and the marts' own reconciliation tests.
---

Cairn's data quality is, before anything else, a **provenance** property: every
figure traces back to an immutable official source, pinned by `sha256` in an
append-only manifest. This page reports that chain's integrity for each source —
**observable facts from the manifests, not a confidence score**. It deliberately
does not rate how "good" a number is; it shows whether the number is still pinned
to the source it came from.

```sql provenance_summary
select
    count(*) filter (where is_latest) as sources,
    count(*) filter (where is_latest and pin_status = 'pinned_r2') as pinned_r2,
    count(*) filter (where is_latest and pin_status = 'pinned_local') as pinned_local,
    count(*) filter (where is_latest and pin_status = 'unpinned') as unpinned,
    sum(row_count) filter (where is_latest) as total_rows
from cairn.data_provenance
```

<div class="grid grid-cols-1 md:grid-cols-3 gap-4">

<BigValue
    data={provenance_summary}
    value=sources
    fmt='#,##0'
    title="Configured sources"
/>

<BigValue
    data={provenance_summary}
    value=pinned_r2
    fmt='#,##0'
    title="Pinned to immutable storage"
/>

<BigValue
    data={provenance_summary}
    value=total_rows
    fmt='#,##0'
    title="Raw rows pinned by hash"
/>

</div>

## What each status means

The pin status is derived deterministically from where a source's raw file is
stored — it is a fact about the snapshot, not a judgement about the data:

- **`pinned_r2`** — the raw file sits in immutable object storage and is pinned
  by `sha256`. This is the auditable pin of record: the figure cannot drift
  without a manifest change and a failing build.
- **`pinned_local`** — a `file://` pin from an `--offline` run. Useful locally,
  but it is **never** the committed pin of record, so a `pinned_local` row in a
  published build is an integrity flag worth investigating.
- **`unpinned`** — the source is configured but has no snapshot yet. It is shown
  honestly as unpinned, never filled in with a placeholder hash or row count.

## Current pin of record per source

```sql current_pins
select
    source,
    dataset,
    pin_status,
    release,
    ingested_at,
    row_count,
    period_start,
    period_end,
    sha256_short
from cairn.data_provenance
where is_latest
order by is_pinned desc, source
```

<DataTable data={current_pins} rows=all rowShading={true}>
    <Column id=source title="Source" />
    <Column id=dataset title="Dataset" />
    <Column id=pin_status title="Pin status" />
    <Column id=release title="Release" />
    <Column id=ingested_at title="Ingested" fmt='yyyy-mm-dd' />
    <Column id=row_count title="Raw rows" fmt='#,##0' />
    <Column id=period_start title="From" />
    <Column id=period_end title="To" />
    <Column id=sha256_short title="SHA256 (first 12)" />
</DataTable>

<Alert status="info">

**The hash shown is the claim; CI verifies it.** This page reports the SHA256
each source is *pinned* to. A weekly reproducibility job re-downloads each raw
file, recomputes its SHA256, and rebuilds the warehouse from it — so a silently
mutated source file is a failing build, not a number that quietly drifts. See
**[Architecture →](/architecture)** for the full CI rail and
**[Methodology & sources →](/methodology)** for per-figure provenance.

</Alert>

## How complete is the coverage?

Provenance answers "is the number still pinned?". Coverage answers a different
question: how much of each source's official aggregate does Cairn's mart
actually capture, and how much of the CBS national total can be attributed to
a NACE sector? These are the same reconciliation figures the CI benchmark
already computes — `assert_national_total_reconciles` (CBS) and
`assert_euets_coverage_within_eea` (EU ETS) — surfaced here as standing facts
rather than discarded once the test goes green.

```sql coverage
select
    source,
    year,
    reconciliation_drift,
    unmapped_share,
    covered_share
from cairn.coverage_observability
order by source desc, year desc
```

<DataTable data={coverage} rows=all rowShading={true}>
    <Column id=source title="Source" />
    <Column id=year title="Year" />
    <Column id=reconciliation_drift title="Reconciliation drift" fmt='0.0%' />
    <Column id=unmapped_share title="UNMAPPED share (CBS only)" fmt='0.0%' />
    <Column id=covered_share title="Covered share" fmt='0.0%' />
</DataTable>

<Alert status="info">

**Descriptive, not a score.** `covered_share` describes how completely each
source's official aggregate is captured, and — for CBS — `unmapped_share`
describes how much of the national total cannot be attributed to a single
NACE section. Neither is a confidence or quality score on any individual
figure. `reconciliation_drift` near zero confirms the mart's own total still
matches the official aggregate it derives from.

</Alert>

## How current is the data?

Provenance and coverage answer "is it pinned?" and "how much does it capture?".
This section answers a third question: how current is it? For each source, the
pinned release and ingest date, the latest calendar year its benchmark mart
actually covers, and the observed lag between "now" (this page's own build
time) and those two facts.

```sql freshness
select
    source,
    dataset,
    is_pinned,
    release,
    ingested_at,
    ingest_age_days,
    latest_covered_year,
    coverage_lag_years
from cairn.source_freshness
order by source
```

<DataTable data={freshness} rows=all rowShading={true}>
    <Column id=source title="Source" />
    <Column id=dataset title="Dataset" />
    <Column id=is_pinned title="Pinned?" />
    <Column id=release title="Release" />
    <Column id=ingested_at title="Ingested" fmt='yyyy-mm-dd' />
    <Column id=ingest_age_days title="Age since ingest (days)" fmt='#,##0' />
    <Column id=latest_covered_year title="Latest covered year" />
    <Column id=coverage_lag_years title="Coverage lag (years)" />
</DataTable>

<Alert status="info">

**Descriptive, not an SLA or alarm.** `ingest_age_days` and `coverage_lag_years`
are measured against this page's own build time, so they drift with every
rebuild — they are not pinned figures. `latest_covered_year` is NULL for a
source with no benchmark mart yet. No "expected next release" date is ever
computed: several sources publish on no fixed cadence, so only the *observed*
lag is shown, never a predicted one. Watching for an actually new upstream
release is the weekly reproducibility job's and the no-LLM dispatcher's job
(`scripts/check_freshness.py`), not this page.

</Alert>
