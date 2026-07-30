"""Tests for the no-LLM dispatcher behind cairn-dispatch.yml."""

from __future__ import annotations

from pathlib import Path

from scripts.check_freshness import SourceStatus
from scripts.dispatch import (
    LAYER_RANK,
    backlog_issue_spec,
    freshness_issue_specs,
    next_missing_step,
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
  mart+site: transform/models/marts/mart_coverage.sql; site/sources/cairn/coverage.sql
-->
Surface the reconciliation drift.

---

### Grouping note (organisational — not a candidate)

Prose that belongs to no candidate; the stray `---` above once silently hid
everything below it from the dispatcher.

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
    assert [s.key for s in rivm.layers] == ["ingestion", "staging", "mart"]
    # #3 fuses mart+site into a single step with two sentinels.
    assert cov.dispatchable and cov.source is None
    assert [s.key for s in cov.layers] == ["mart+site"]
    assert cov.layers[0].parts == ("mart", "site")
    assert cov.layers[0].sentinels == (
        "transform/models/marts/mart_coverage.sql",
        "site/sources/cairn/coverage.sql",
    )
    assert none.parse_error == "no <!-- dispatch --> block"
    # The dispatch comment is stripped from the quoted entry.
    assert "<!--" not in rivm.entry_md and "Watch:" in rivm.entry_md


def test_parse_backlog_survives_stray_rules_and_organisational_headings() -> None:
    """A `---` rule / unnumbered heading must never hide later candidates.

    Regression guard for the bug PR #144 found in the live file: the parser
    used to end the "Live candidates" section at the first `---`, silently
    hiding every candidate after it from the dispatcher for weeks.
    """
    cands = parse_backlog(BACKLOG)
    # "No block yet" sits BELOW a stray `---` and an unnumbered `###` heading
    # and is still parsed; the unnumbered heading is not a candidate.
    assert [c.name for c in cands][-1] == "No block yet"
    assert all("Grouping note" not in c.name for c in cands)
    # The organisational prose does not leak into any candidate's verbatim
    # entry (the chunk ends at the rule/heading).
    cov = next(c for c in cands if c.name == "Coverage observability")
    assert "Grouping note" not in cov.entry_md and "silently hid" not in cov.entry_md


def test_parse_backlog_ignores_rejected_section_and_malformed_blocks() -> None:
    text = BACKLOG.replace("mart+site:", "warehouse+site:")  # unknown layer in a fused key
    cands = parse_backlog(text)
    cov = next(c for c in cands if c.name == "Coverage observability")
    assert cov.parse_error and "unknown layer" in cov.parse_error
    # Nothing from "Considered and rejected" leaks in.
    assert all("Old idea" not in c.name for c in cands)


def test_fused_step_parser_rejects_bad_shapes() -> None:
    # A fused key may never include ingestion — a new source pin keeps its own
    # step (research gate, new-source guidance, and the manual approval tier
    # all key off a single-layer ingestion issue).
    with_ingestion = BACKLOG.replace(
        "mart+site: transform/models/marts/mart_coverage.sql; site/sources/cairn/coverage.sql",
        "ingestion+staging: a.yml; b.sql",
    )
    cov = next(c for c in parse_backlog(with_ingestion) if c.name == "Coverage observability")
    assert cov.parse_error and "ingestion must be its own step" in cov.parse_error

    # Fused parts must be in dependency order.
    bad_order = BACKLOG.replace("mart+site:", "site+mart:")
    cov = next(c for c in parse_backlog(bad_order) if c.name == "Coverage observability")
    assert cov.parse_error and "dependency order" in cov.parse_error

    # One sentinel per fused part, or it's malformed.
    mismatch = BACKLOG.replace(
        "mart+site: transform/models/marts/mart_coverage.sql; site/sources/cairn/coverage.sql",
        "mart+site: only-one-sentinel.sql",
    )
    cov = next(c for c in parse_backlog(mismatch) if c.name == "Coverage observability")
    assert cov.parse_error and "one ';'-separated sentinel" in cov.parse_error


def test_fused_step_may_include_staging() -> None:
    """staging+mart(+site) fuses into one step — one PR round-trip, not three.

    Staging is a scaffolded near-copy; forcing it into its own approve→PR→CI
    round-trip bought review value only in theory (the human latency between
    rounds dominated: agent runs take ~10 minutes, merges took days). The
    scaffold still runs — LayerStep.scaffoldable_part surfaces the staging
    part of a fused step.
    """
    fused = BACKLOG.replace(
        "mart+site: transform/models/marts/mart_coverage.sql; site/sources/cairn/coverage.sql",
        "staging+mart+site: a.sql; b.sql; c.sql",
    )
    cov = next(c for c in parse_backlog(fused) if c.name == "Coverage observability")
    assert cov.parse_error is None
    step = cov.layers[0]
    assert step.parts == ("staging", "mart", "site")
    assert step.title == "dbt staging + dbt mart + site"
    assert step.scaffoldable_part == "staging"
    assert step.auto_approvable


def test_next_missing_step_walks_sentinels(tmp_path: Path) -> None:
    cands = parse_backlog(BACKLOG)
    rivm = cands[1]
    step = next_missing_step(rivm, tmp_path)
    assert step is not None
    assert step.parts == ("ingestion",) and step.sentinels == ("sources/rivm/manifest.yml",)
    (tmp_path / "sources/rivm").mkdir(parents=True)
    (tmp_path / "sources/rivm/manifest.yml").write_text("snapshots: []\n")
    assert next_missing_step(rivm, tmp_path).key == "staging"
    for step in rivm.layers:
        for sentinel in step.sentinels:
            (tmp_path / sentinel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / sentinel).write_text("x")
    assert next_missing_step(rivm, tmp_path) is None


def test_fused_step_is_built_only_when_all_sentinels_exist(tmp_path: Path) -> None:
    cov = next(c for c in parse_backlog(BACKLOG) if c.name == "Coverage observability")
    step = cov.layers[0]
    mart, site = step.sentinels
    # Building only the mart leaves the fused step incomplete → still dispatched.
    (tmp_path / mart).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / mart).write_text("x")
    assert next_missing_step(cov, tmp_path) is step
    (tmp_path / site).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / site).write_text("x")
    assert next_missing_step(cov, tmp_path) is None


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


def test_backlog_dispatches_fused_mart_site_as_one_issue(tmp_path: Path) -> None:
    from scripts.reference_for_layer import infer_layers

    cov = next(c for c in parse_backlog(BACKLOG) if c.name == "Coverage observability")
    step = cov.layers[0]
    assert step.title == "dbt mart + site"

    spec, _ = backlog_issue_spec([cov], tmp_path, [], [])
    assert spec is not None
    assert spec.title == "feat: Coverage observability — dbt mart + site"
    # The body asks for one PR delivering both layers and names both sentinels.
    assert "Deliver the fused **dbt mart + site** step" in spec.body
    assert "`transform/models/marts/mart_coverage.sql`" in spec.body
    assert "`site/sources/cairn/coverage.sql`" in spec.body
    assert "Scaffold parameters" not in spec.body  # mart+site is never scaffoldable
    # The fused title round-trips through implement's layer inference to both
    # exemplars, in dependency order.
    assert infer_layers(spec.title, ["proposal"]) == list(step.parts)


def test_backlog_auto_approves_non_ingestion_steps_only(tmp_path: Path) -> None:
    """The approval tiers: ingestion keeps the manual gate, the rest pre-approve.

    A non-ingestion step's spec carries the `approved` label from creation plus
    auto_approve=True (the workflow then triggers cairn-implement directly);
    its body says so. An ingestion step — where new trust enters the system —
    stays a plain `proposal` for a human to label.
    """
    cands = parse_backlog(BACKLOG)
    rivm = cands[1]

    # RIVM's next step is ingestion -> manual gate.
    spec, _ = backlog_issue_spec([rivm], tmp_path, [], [])
    assert spec is not None and spec.title.endswith("— ingestion")
    assert spec.labels == ["proposal"] and spec.auto_approve is False
    assert "pre-authorized" not in spec.body

    # Coverage's mart+site step -> auto-approved.
    cov = next(c for c in cands if c.name == "Coverage observability")
    spec, _ = backlog_issue_spec([cov], tmp_path, [], [])
    assert spec is not None and spec.title.endswith("— dbt mart + site")
    assert spec.labels == ["proposal", "approved"] and spec.auto_approve is True
    assert "pre-authorized" in spec.body

    # The kill switch (DISPATCH_AUTO_APPROVE=false) restores label-gating.
    spec, _ = backlog_issue_spec([cov], tmp_path, [], [], auto_approve=False)
    assert spec is not None
    assert spec.labels == ["proposal"] and spec.auto_approve is False
    assert "pre-authorized" not in spec.body


def test_backlog_fused_staging_issue_scaffolds_and_round_trips(tmp_path: Path) -> None:
    """A fused staging+mart step still gets Scaffold parameters and the right exemplars."""
    from scripts.implement_strategy import HAIKU, gate
    from scripts.reference_for_layer import infer_layers

    fused = BACKLOG.replace(
        """layers:
  ingestion: sources/rivm/manifest.yml
  staging: transform/models/staging/stg_rivm__emissieregistratie.sql
  mart: transform/models/marts/mart_rivm_cbs_reconciliation.sql""",
        """layers:
  ingestion: sources/rivm/manifest.yml
  staging+mart: staging/stg_rivm__emissieregistratie.sql; marts/mart_rivm.sql""",
    )
    rivm = parse_backlog(fused)[1]
    assert rivm.parse_error is None
    # Ship the ingestion sentinel so the fused step is next.
    (tmp_path / "sources/rivm").mkdir(parents=True)
    (tmp_path / "sources/rivm/manifest.yml").write_text("snapshots: []\n")

    spec, _ = backlog_issue_spec([rivm], tmp_path, [], [])
    assert spec is not None
    assert spec.title.endswith("— dbt staging + dbt mart")
    # The staging part is scaffoldable, so the slug block rides along.
    assert "Scaffold parameters:" in spec.body
    assert "- source: rivm" in spec.body and "- dataset: emissieregistratie" in spec.body
    # Non-ingestion -> pre-approved.
    assert spec.auto_approve is True
    # Round-trips through implement's layer inference and strategy routing:
    # both fused exemplars injected, Haiku orchestrator behind a Sonnet plan.
    assert infer_layers(spec.title, ["proposal", "approved"]) == ["staging", "mart"]
    strategy = gate(spec.title, ["proposal", "approved"])
    assert strategy["model"] == HAIKU and strategy["plan_needed"] == "true"


def test_backlog_title_suffix_matches_implements_layer_inference(tmp_path: Path) -> None:
    from scripts.reference_for_layer import infer_layers

    cands = parse_backlog(BACKLOG)
    rivm = cands[1]
    # Walk every step: the generated title must round-trip through implement's
    # infer_layers so the right exemplar/scaffold is injected on the other side.
    for idx, step in enumerate(rivm.layers):
        for done in rivm.layers[:idx]:
            for sentinel in done.sentinels:
                p = tmp_path / sentinel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x")
        for later in rivm.layers[idx:]:
            for sentinel in later.sentinels:
                (tmp_path / sentinel).unlink(missing_ok=True)
        spec, _ = backlog_issue_spec([rivm], tmp_path, [], [])
        assert spec is not None
        assert infer_layers(spec.title, ["proposal"]) == list(step.parts)


def test_backlog_dedups_on_open_issue_and_pr(tmp_path: Path) -> None:
    cands = parse_backlog(BACKLOG)
    open_issue = ["feat: Emissieregistratie (RIVM) → deepen NL provenance — ingestion"]
    spec, notes = backlog_issue_spec(cands, tmp_path, open_issue, [])
    # RIVM is tracked -> falls through to the next candidate (#3, a fused step).
    assert spec is not None and spec.title.startswith("feat: Coverage observability")
    assert spec.title.endswith("— dbt mart + site")
    assert "Scaffold parameters" not in spec.body  # mart+site layer: no scaffold block

    pr_titles = ["feat(mart): coverage observability mart (Coverage observability)"]
    spec, notes = backlog_issue_spec(cands, tmp_path, open_issue, pr_titles)
    assert spec is None  # #3 blocked by the PR, #4 has no block
    assert any("open PR references it" in n for n in notes)


def test_backlog_skips_fully_shipped_candidate(tmp_path: Path) -> None:
    cands = parse_backlog(BACKLOG)
    rivm = cands[1]
    for step in rivm.layers:
        for sentinel in step.sentinels:
            (tmp_path / sentinel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / sentinel).write_text("x")
    spec, notes = backlog_issue_spec([rivm], tmp_path, [], [])
    assert spec is None
    assert any("fully shipped" in n for n in notes)


# ---- run() orchestration -----------------------------------------------------------


def test_run_combines_scopes_and_saturation(tmp_path: Path) -> None:
    (tmp_path / "BACKLOG.md").write_text(BACKLOG, encoding="utf-8")

    specs, summary, _ = run(
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
    # The freshness issue keeps the manual gate; the feat issue (ingestion
    # layer here) does too, so nothing in this run is auto-approved.
    assert all(not s.auto_approve for s in specs)

    # Saturated queue: backlog dispatch skipped, freshness still opens.
    saturated = [{"title": f"t{i}", "labels": ["proposal"]} for i in range(5)]
    specs, summary, replenish_needed = run(
        tmp_path,
        scope="both",
        open_issues=saturated,
        open_prs=[],
        saturation_threshold=5,
        statuses=_statuses(),
    )
    assert [s.title for s in specs] == ["data: eurostat new release 2025-01-15"]
    assert "saturated" in summary
    assert replenish_needed is False  # skipped backlog scope never signals

    # Approved proposals do not count against the gate.
    approved = [{"title": f"t{i}", "labels": ["proposal", "approved"]} for i in range(5)]
    specs, _, _ = run(
        tmp_path,
        scope="backlog",
        open_issues=approved,
        open_prs=[],
        saturation_threshold=5,
    )
    assert len(specs) == 1 and specs[0].title.startswith("feat:")


def test_run_signals_replenish_when_menu_runs_low(tmp_path: Path) -> None:
    (tmp_path / "BACKLOG.md").write_text(BACKLOG, encoding="utf-8")
    # The fixture has exactly 2 candidates with undispatched work (RIVM and
    # Coverage; the EUA one is held, "No block yet" doesn't parse).
    _, summary, needed = run(
        tmp_path, scope="backlog", open_issues=[], open_prs=[], saturation_threshold=5
    )
    assert needed is True  # 2 < default threshold 3
    assert "triggering replenish" in summary

    _, summary, needed = run(
        tmp_path,
        scope="backlog",
        open_issues=[],
        open_prs=[],
        saturation_threshold=5,
        replenish_threshold=2,
    )
    assert needed is False
    assert "2 candidate(s) with undispatched work" in summary


def test_run_backlog_scope_never_probes_the_network(tmp_path: Path) -> None:
    (tmp_path / "BACKLOG.md").write_text(BACKLOG, encoding="utf-8")
    # No statuses injected: scope="backlog" must not call collect_statuses (which
    # would hit the network from a tmp repo with no pipeline files and fail loudly
    # in the summary as probe-failed rows).
    specs, summary, _ = run(
        tmp_path, scope="backlog", open_issues=[], open_prs=[], saturation_threshold=5
    )
    assert len(specs) == 1 and specs[0].title.startswith("feat:")
    assert "freshness:" not in summary


def test_live_backlog_dispatch_blocks_are_valid() -> None:
    """Guard the real BACKLOG.md: every live candidate must parse cleanly.

    The dispatcher degrades a malformed block to a skip-with-reason at runtime,
    which silently starves the loop; catching it here keeps a bad edit (by
    replenish or a human) from merging. Sentinel *paths* can't be checked for
    existence (an undone layer's sentinel is supposed to be missing), but the
    block schema and the dependency order of the layers (flattened across any
    fused steps) are testable.
    """
    root = Path(__file__).resolve().parent.parent
    cands = parse_backlog((root / "BACKLOG.md").read_text(encoding="utf-8"))
    assert cands, "no live candidates parsed from BACKLOG.md"
    for cand in cands:
        assert cand.parse_error is None, f"{cand.name}: {cand.parse_error}"
        ranks = [LAYER_RANK[part] for step in cand.layers for part in step.parts]
        assert ranks == sorted(ranks), f"{cand.name}: layers out of dependency order"


def test_live_backlog_every_numbered_heading_is_a_visible_candidate() -> None:
    """Guard against dispatcher-invisible candidates in the real BACKLOG.md.

    PR #144 found that a stray `---` had silently hidden every candidate after
    it from the dispatcher for weeks — the file claimed they were dispatchable
    while parse_backlog never saw them. The parser no longer stops at rules,
    and this asserts the invariant end-to-end: every numbered `### <n>.`
    heading anywhere in the file must surface as a parsed candidate (numbered
    headings are reserved for live candidates; organisational subheadings use
    `####` or no number).
    """
    import re

    root = Path(__file__).resolve().parent.parent
    text = (root / "BACKLOG.md").read_text(encoding="utf-8")
    numbered = re.findall(r"^### \d+\.\s*(.+?)\s*$", text, re.M)
    parsed = [c.name for c in parse_backlog(text)]
    assert parsed == numbered, (
        "candidates invisible to the dispatcher (numbered heading not parsed): "
        f"{sorted(set(numbered) - set(parsed))}"
    )
