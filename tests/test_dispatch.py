"""Tests for the no-LLM dispatcher behind cairn-dispatch.yml."""

from __future__ import annotations

from pathlib import Path

from scripts.check_freshness import SourceStatus
from scripts.dispatch import (
    backlog_issue_spec,
    freshness_issue_specs,
    next_missing_layer,
    parse_backlog,
    run,
)

BACKLOG = """\
# BACKLOG.md

## Rules of the game

1. Official source only.

## Live candidates

### 1. EUA carbon price → € valuation overlay
<!-- dispatch
hold: deferred by the watch note — site overlay only
-->
**Value: H · Effort: M · Spine-fit: L**

Adds a € valuation.

### 2. Emissieregistratie (RIVM) → deepen NL provenance
<!-- dispatch
source: rivm
dataset: emissieregistratie
layers:
  ingestion: sources/rivm/manifest.yml
  staging: transform/models/staging/stg_rivm__emissieregistratie.sql
  mart: transform/models/marts/mart_rivm_cbs_reconciliation.sql
-->
**Value: M · Effort: M · Spine-fit: H**

The authoritative source under NL's UNFCCC submission.
- *Watch:* keep it a cross-check, not a second authority.

### 3. Coverage observability
<!-- dispatch
layers:
  mart: transform/models/marts/mart_coverage_observability.sql
  site: site/sources/cairn/coverage_observability.sql
-->
Surface the reconciliation drift.

### 4. No block yet
Prose only.

---

## Considered and rejected

- **Old idea.** Rejected.
"""


def _statuses(**overrides) -> list[SourceStatus]:
    base = {
        "cbs": SourceStatus("cbs", "2026-03-11", "2026-03-11", "current", "current"),
        "eurostat": SourceStatus(
            "eurostat", "2024-10-23", "2025-01-15", "stale", "**STALE — new release 2025-01-15**"
        ),
        "eea": SourceStatus("eea", "2005-2025_v01_r00", None, "probe-failed", "probe failed"),
        "euets": SourceStatus("euets", "2024-10", "2024-10", "human-watched", "human-watched"),
    }
    base.update(overrides)
    return list(base.values())


# ---- backlog parsing ----------------------------------------------------------


def test_parse_backlog_reads_blocks_holds_and_errors() -> None:
    cands = parse_backlog(BACKLOG)
    assert [c.name for c in cands] == [
        "EUA carbon price → € valuation overlay",
        "Emissieregistratie (RIVM) → deepen NL provenance",
        "Coverage observability",
        "No block yet",
    ]
    eua, rivm, cov, none = cands
    assert eua.hold and not eua.dispatchable
    assert rivm.dispatchable and rivm.source == "rivm" and rivm.dataset == "emissieregistratie"
    assert [lyr for lyr, _ in rivm.layers] == ["ingestion", "staging", "mart"]
    assert cov.dispatchable and cov.source is None
    assert none.parse_error == "no <!-- dispatch --> block"
    # The dispatch comment is stripped from the quoted entry.
    assert "<!--" not in rivm.entry_md and "Watch:" in rivm.entry_md


def test_parse_backlog_ignores_rejected_section_and_malformed_blocks() -> None:
    text = BACKLOG.replace("layers:\n  mart:", "layers:\n  warehouse:")  # unknown layer
    cands = parse_backlog(text)
    cov = next(c for c in cands if c.name == "Coverage observability")
    assert cov.parse_error and "unknown layer" in cov.parse_error
    # Nothing from "Considered and rejected" leaks in.
    assert all("Old idea" not in c.name for c in cands)


def test_next_missing_layer_walks_sentinels(tmp_path: Path) -> None:
    cands = parse_backlog(BACKLOG)
    rivm = cands[1]
    assert next_missing_layer(rivm, tmp_path) == ("ingestion", "sources/rivm/manifest.yml")
    (tmp_path / "sources/rivm").mkdir(parents=True)
    (tmp_path / "sources/rivm/manifest.yml").write_text("snapshots: []\n")
    layer, sentinel = next_missing_layer(rivm, tmp_path)
    assert layer == "staging"
    for _, p in rivm.layers:
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("x")
    assert next_missing_layer(rivm, tmp_path) is None


# ---- freshness ------------------------------------------------------------------


def test_freshness_specs_only_for_stale_with_dedup() -> None:
    specs, notes = freshness_issue_specs(_statuses(), open_issue_titles=[])
    assert [s.title for s in specs] == ["data: eurostat new release 2025-01-15"]
    assert specs[0].labels == ["proposal", "data-refresh"]
    assert "## Executive summary" in specs[0].body
    assert "Cairn Ingest" in specs[0].body and "`2024-10-23`" in specs[0].body
    assert any("probe failed" in n for n in notes)  # eea surfaced for a human

    # An open issue with the same prefix (any token) suppresses a duplicate.
    specs, notes = freshness_issue_specs(
        _statuses(), open_issue_titles=["data: eurostat new release 2025-01-15"]
    )
    assert specs == [] and any("already tracks" in n for n in notes)


def test_freshness_never_flags_human_watched_or_current() -> None:
    specs, _ = freshness_issue_specs(
        [
            SourceStatus("euets", "2024-10", "2025-01", "human-watched", "human-watched"),
            SourceStatus("cbs", "a", "a", "current", "current"),
            SourceStatus("x", None, "b", "unpinned", "unpinned"),
        ],
        open_issue_titles=[],
    )
    assert specs == []


# ---- backlog dispatch -------------------------------------------------------------


def test_backlog_dispatches_top_candidates_next_layer(tmp_path: Path) -> None:
    cands = parse_backlog(BACKLOG)
    spec, notes = backlog_issue_spec(cands, tmp_path, [], [])
    # #1 is held; #2 RIVM's first missing layer is ingestion.
    assert spec is not None
    assert spec.title == "feat: Emissieregistratie (RIVM) → deepen NL provenance — ingestion"
    assert spec.labels == ["proposal"]
    assert "Scaffold parameters:" in spec.body
    assert "- source: rivm" in spec.body and "- dataset: emissieregistratie" in spec.body
    assert "`sources/rivm/manifest.yml`" in spec.body
    assert "this is the first layer" in spec.body
    assert "staging (`transform/models/staging/stg_rivm__emissieregistratie.sql`)" in spec.body
    assert "Watch:" in spec.body  # verbatim entry rides along
    assert any("held" in n for n in notes)


def test_backlog_title_suffix_matches_implements_layer_inference(tmp_path: Path) -> None:
    from scripts.reference_for_layer import infer_layer

    cands = parse_backlog(BACKLOG)
    rivm = cands[1]
    # Walk every layer: the generated title must round-trip through implement's
    # infer_layer so the right exemplar/scaffold is injected on the other side.
    for idx, (layer, _sentinel) in enumerate(rivm.layers):
        for _done_layer, done_path in rivm.layers[:idx]:
            p = tmp_path / done_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")
        for _, later_path in rivm.layers[idx:]:
            (tmp_path / later_path).unlink(missing_ok=True)
        spec, _ = backlog_issue_spec([rivm], tmp_path, [], [])
        assert spec is not None
        assert infer_layer(spec.title, ["proposal"]) == layer


def test_backlog_dedups_on_open_issue_and_pr(tmp_path: Path) -> None:
    cands = parse_backlog(BACKLOG)
    open_issue = ["feat: Emissieregistratie (RIVM) → deepen NL provenance — ingestion"]
    spec, notes = backlog_issue_spec(cands, tmp_path, open_issue, [])
    # RIVM is tracked -> falls through to the next candidate (#3).
    assert spec is not None and spec.title.startswith("feat: Coverage observability")
    assert spec.title.endswith("— dbt mart")
    assert "Scaffold parameters" not in spec.body  # mart layer: no scaffold block

    pr_titles = ["feat(mart): coverage observability mart (Coverage observability)"]
    spec, notes = backlog_issue_spec(cands, tmp_path, open_issue, pr_titles)
    assert spec is None  # #3 blocked by the PR, #4 has no block
    assert any("open PR references it" in n for n in notes)


def test_backlog_skips_fully_shipped_candidate(tmp_path: Path) -> None:
    cands = parse_backlog(BACKLOG)
    rivm = cands[1]
    for _, p in rivm.layers:
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("x")
    spec, notes = backlog_issue_spec([rivm], tmp_path, [], [])
    assert spec is None
    assert any("fully shipped" in n for n in notes)


# ---- run() orchestration -----------------------------------------------------------


def test_run_combines_scopes_and_saturation(tmp_path: Path) -> None:
    (tmp_path / "BACKLOG.md").write_text(BACKLOG, encoding="utf-8")

    specs, summary = run(
        tmp_path,
        scope="both",
        open_issues=[],
        open_prs=[],
        saturation_threshold=5,
        statuses=_statuses(),
    )
    titles = [s.title for s in specs]
    assert "data: eurostat new release 2025-01-15" in titles
    assert any(t.startswith("feat: Emissieregistratie") for t in titles)
    assert "Opening 2 issue(s)" in summary

    # Saturated queue: backlog dispatch skipped, freshness still opens.
    saturated = [{"title": f"t{i}", "labels": ["proposal"]} for i in range(5)]
    specs, summary = run(
        tmp_path,
        scope="both",
        open_issues=saturated,
        open_prs=[],
        saturation_threshold=5,
        statuses=_statuses(),
    )
    assert [s.title for s in specs] == ["data: eurostat new release 2025-01-15"]
    assert "saturated" in summary

    # Approved proposals do not count against the gate.
    approved = [{"title": f"t{i}", "labels": ["proposal", "approved"]} for i in range(5)]
    specs, _ = run(
        tmp_path,
        scope="backlog",
        open_issues=approved,
        open_prs=[],
        saturation_threshold=5,
    )
    assert len(specs) == 1 and specs[0].title.startswith("feat:")


def test_run_backlog_scope_never_probes_the_network(tmp_path: Path) -> None:
    (tmp_path / "BACKLOG.md").write_text(BACKLOG, encoding="utf-8")
    # No statuses injected: scope="backlog" must not call collect_statuses (which
    # would hit the network from a tmp repo with no pipeline files and fail loudly
    # in the summary as probe-failed rows).
    specs, summary = run(
        tmp_path, scope="backlog", open_issues=[], open_prs=[], saturation_threshold=5
    )
    assert len(specs) == 1 and specs[0].title.startswith("feat:")
    assert "freshness:" not in summary
