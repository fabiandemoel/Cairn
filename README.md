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

## What Cairn is

_TODO: filled in as the pipeline takes shape._

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

_TODO: filled in once the ingestion pipeline and dbt project exist._

## Reproducibility

_TODO: filled in once the manifest and verification script exist — will
explain how any benchmark number traces back to a commit + manifest entry +
immutable raw file._

## Source quirks

_None documented yet._

## R2 setup

_TODO: filled in once the ingestion pipeline exists._
