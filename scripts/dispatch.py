"""No-LLM issue dispatcher: upstream freshness + backlog next-layer (cairn-dispatch).

This replaces the cairn-scout *agent*. Both of scout's tasks turned out to be
deterministic once their inputs were precomputed, so no LLM runs here at all:

1. **Freshness** (weekly): ``scripts/check_freshness.py`` already computes the
   live-vs-pinned diff per source. Every source marked ``stale`` becomes one
   ``data-refresh`` issue with a fixed, templated body — after a duplicate check
   against the open issues.
2. **Backlog dispatch** (on every merge to main + weekly): each BACKLOG.md
   "Live candidates" entry carries a machine-readable ``<!-- dispatch -->``
   block (maintained by cairn-replenish, schema documented in BACKLOG.md's
   header) declaring, per step, a *sentinel path* — a new file that step
   creates. Most steps are a single layer, but non-scaffoldable layers can be
   fused (``mart+site``, ``staging+mart+site``) so layers that ship together
   need only one PR round-trip. The next step to dispatch is simply the first
   step not yet fully built (any sentinel missing); the issue body quotes the
   candidate's BACKLOG entry verbatim (its scope and "watch" caveats) plus a
   templated scope section, so cairn-implement still receives an authoritative
   spec. Non-ingestion steps are **auto-approved**: their entry was already
   human-reviewed when the replenish PR merged, so the issue is labelled
   ``approved`` at creation and the workflow triggers cairn-implement for it
   directly — the implementation PR's human merge stays the audit checkpoint.
   Ingestion steps (new source, new manifest) keep the manual label gate.

Design rules, matching the sibling ``scripts/*.py`` helpers:

* stdlib-only (the workflow runs it with plain ``python3``, before any
  ``uv sync``), unit-tested in ``tests/test_dispatch.py``.
* This script never talks to the GitHub API. The workflow dumps the open
  issues/PRs to JSON first and creates the issues afterwards; every *decision*
  (dedup, saturation, layer selection) lives here, where it is testable.
* Malformed input degrades to a skip-with-reason in the run summary, never a
  crash: a candidate without a dispatch block, an unknown layer name, or a
  held candidate is reported and passed over.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from scripts.check_freshness import SourceStatus, collect_statuses

# The repo's natural layers, in dependency order. Keys are the dispatch-block
# layer names; values are the title suffixes cairn-implement's
# reference_for_layer.infer_layers maps back onto the same layer(s).
LAYER_TITLES: dict[str, str] = {
    "ingestion": "ingestion",
    "staging": "dbt staging",
    "mart": "dbt mart",
    "site": "site",
    "export": "export",
}

# Dependency rank per layer, used to reject an out-of-order fused key.
LAYER_RANK: dict[str, int] = {name: i for i, name in enumerate(LAYER_TITLES)}

# Layers whose fixed boilerplate cairn-implement can pre-scaffold from the
# "Scaffold parameters" block (see scripts/scaffold_for_layer.py).
_SCAFFOLDABLE = {"ingestion", "staging"}

# Layers that may never be fused into a combined step. Ingestion keeps its own
# step because the source-research gate and the new-source guidance in
# cairn-implement key off a single-layer ingestion issue, and because a new
# source pin is where a human should look at exactly one thing. Staging *may*
# fuse (staging+mart, staging+mart+site): it is a scaffolded near-copy, and
# scaffold_for_layer scaffolds the staging part of a fused issue too.
_NEVER_FUSED = {"ingestion"}

_DISPATCH_BLOCK_RE = re.compile(r"<!--\s*dispatch\b(.*?)-->", re.S)
# A live candidate heading is `### <n>. <name>` — the number is required.
# Unnumbered `###`/`####` headings inside the section are organisational and
# invisible to the dispatcher (they end the previous candidate's chunk, see
# _CHUNK_BOUNDARY_RE, but never become candidates themselves).
_CANDIDATE_HEAD_RE = re.compile(r"^### (\d+)\.\s*(.+?)\s*$", re.M)
# Ends a candidate's chunk early: any other heading or a horizontal rule. This
# keeps prose that belongs to no candidate (a subsection intro, a `---` rule)
# out of the previous candidate's verbatim-quoted entry — and, crucially, a
# stray `---` no longer truncates the whole section (which once silently hid
# every candidate after it from the dispatcher).
_CHUNK_BOUNDARY_RE = re.compile(r"^(?:#{2,}\s|---\s*$)", re.M)
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Layers whose dispatched issue keeps the manual `approved`-label gate even
# when auto-approval is on. Ingestion is where new trust enters the system (a
# new source, a new append-only manifest, live-web research feeding the run).
_MANUAL_APPROVAL = {"ingestion"}


@dataclass(frozen=True)
class LayerStep:
    """One dispatchable unit of work — one issue, one PR.

    Usually a single repo layer, but two or more *non-scaffoldable* layers can be
    **fused** into one step (declared ``mart+site`` in the dispatch block) so a
    mart and the thin site page that only reads it ship together, instead of two
    approve→PR→CI round-trips for what is often a ~30-line source query. ``parts``
    are the fused layer names in dependency order; ``sentinels`` pairs one
    sentinel path with each part. The step is "built" only when *every* sentinel
    exists, so a fused step delivers all its layers before it is considered done.
    """

    parts: tuple[str, ...]
    sentinels: tuple[str, ...]

    @property
    def key(self) -> str:
        """The dispatch-block key, e.g. ``mart`` or ``mart+site``."""
        return "+".join(self.parts)

    @property
    def title(self) -> str:
        """The issue-title suffix, e.g. ``dbt mart`` or ``dbt mart + site``."""
        return " + ".join(LAYER_TITLES[p] for p in self.parts)

    @property
    def scaffoldable_part(self) -> str | None:
        """The scaffoldable layer of this step, if any.

        A single ingestion/staging step is its own scaffoldable part; a fused
        step can carry at most `staging` (ingestion is never fused), and the
        scaffold then pre-writes the staging boilerplate while the other fused
        layers are written by hand.
        """
        for part in self.parts:
            if part in _SCAFFOLDABLE:
                return part
        return None

    @property
    def auto_approvable(self) -> bool:
        """Whether this step may skip the human `approved`-label gate.

        The BACKLOG.md entry a dispatched issue quotes verbatim was already
        human-reviewed when its replenish PR merged, so a second approval of
        the same text adds latency without information — except where new
        trust enters the system: an **ingestion** step (new source, new
        manifest, live-web research) keeps the manual gate. The implementation
        PR's human merge remains the audit checkpoint for every step.
        """
        return not any(part in _MANUAL_APPROVAL for part in self.parts)

    def is_built(self, root: Path) -> bool:
        return all((root / sentinel).exists() for sentinel in self.sentinels)


@dataclass
class Candidate:
    """One BACKLOG.md "Live candidates" entry plus its parsed dispatch block."""

    name: str
    entry_md: str  # the candidate's section, dispatch comment stripped
    hold: str | None = None
    source: str | None = None
    dataset: str | None = None
    layers: list[LayerStep] = field(default_factory=list)  # dispatch steps, in order
    parse_error: str | None = None  # block missing/malformed -> skip with reason

    @property
    def dispatchable(self) -> bool:
        return self.parse_error is None and self.hold is None and bool(self.layers)


@dataclass(frozen=True)
class IssueSpec:
    title: str
    labels: list[str]
    body: str
    # True when the workflow should trigger cairn-implement for this issue
    # immediately after creating it (the issue also carries the `approved`
    # label from birth). The explicit workflow_dispatch is required because
    # issues created with GITHUB_TOKEN fire no label events.
    auto_approve: bool = False


def _parse_layer_step(layer_key: str, path_spec: str) -> LayerStep:
    """Parse one ``<layer>: <sentinel>`` line, including a fused ``a+b: p; q`` step.

    A fused key joins two or more layer names with ``+``; its value carries one
    ``;``-separated sentinel per part. Fused parts must be distinct, listed in
    dependency order, and free of never-fused layers (ingestion keeps its own
    step — see ``_NEVER_FUSED``; staging may fuse with the layers above it).
    """
    parts = [p.strip().lower() for p in layer_key.split("+")]
    sentinels = [s.strip() for s in path_spec.split(";")]
    if any(not p for p in parts):
        raise ValueError(f"empty layer name in {layer_key!r}")
    for p in parts:
        if p not in LAYER_TITLES:
            raise ValueError(f"unknown layer {p!r} (known: {', '.join(LAYER_TITLES)})")
    if len(sentinels) != len(parts) or any(not s for s in sentinels):
        raise ValueError(
            f"fused step {layer_key!r} needs one ';'-separated sentinel per layer, "
            f"got {path_spec!r}"
        )
    if len(parts) > 1:
        if len(set(parts)) != len(parts):
            raise ValueError(f"fused step {layer_key!r} repeats a layer")
        if [LAYER_RANK[p] for p in parts] != sorted(LAYER_RANK[p] for p in parts):
            raise ValueError(f"fused step {layer_key!r} lists layers out of dependency order")
        never_fused = [p for p in parts if p in _NEVER_FUSED]
        if never_fused:
            raise ValueError(
                f"fused step {layer_key!r} cannot include layer(s) "
                f"{never_fused} — ingestion must be its own step"
            )
    return LayerStep(parts=tuple(parts), sentinels=tuple(sentinels))


def _parse_dispatch_block(text: str) -> dict:
    """Parse the tiny two-level ``key: value`` / ``layers:`` format.

    Deliberately not YAML-the-library: the workflow runs before ``uv sync``, so
    only the stdlib is available, and the schema is small enough to hand-parse.
    """
    top: dict[str, str] = {}
    layers: list[LayerStep] = []
    in_layers = False
    for raw in text.splitlines():
        if not raw.strip():
            continue
        indented = raw[:1] in (" ", "\t")
        line = raw.strip()
        if not indented:
            in_layers = False
            key, sep, value = line.partition(":")
            if not sep:
                raise ValueError(f"expected 'key: value', got {line!r}")
            key = key.strip().lower()
            if key == "layers":
                if value.strip():
                    raise ValueError("'layers:' must start an indented block")
                in_layers = True
            else:
                top[key] = value.strip()
        else:
            if not in_layers:
                raise ValueError(f"unexpected indented line outside 'layers:': {line!r}")
            layer_key, sep, path = line.partition(":")
            if not sep or not path.strip():
                raise ValueError(f"expected '<layer>: <sentinel path>', got {line!r}")
            step = _parse_layer_step(layer_key.strip(), path.strip())
            for p in step.parts:
                if any(p in existing.parts for existing in layers):
                    raise ValueError(f"duplicate layer {p!r}")
            layers.append(step)
    return {"top": top, "layers": layers}


def parse_backlog(text: str) -> list[Candidate]:
    """Extract the "Live candidates" entries, in menu order.

    The section runs from ``## Live candidates`` to the next H2 heading —
    deliberately **not** to the first ``---`` rule: a stray rule once silently
    hid every candidate after it from the dispatcher (fixed in PR #144's
    BACKLOG edit; fixed here structurally). Only numbered ``### <n>.``
    headings are candidates; other headings and rules merely end the previous
    candidate's chunk so unrelated prose never rides along in the verbatim
    quote.
    """
    live_start = text.find("## Live candidates")
    if live_start < 0:
        return []
    tail = text[live_start:]
    end = re.search(r"^## (?!Live candidates)", tail[1:], re.M)
    section = tail[: end.start() + 1] if end else tail

    candidates: list[Candidate] = []
    heads = list(_CANDIDATE_HEAD_RE.finditer(section))
    for i, head in enumerate(heads):
        chunk_end = heads[i + 1].start() if i + 1 < len(heads) else len(section)
        chunk = section[head.start() : chunk_end]
        # Truncate at the first non-candidate heading or `---` rule after the
        # candidate's own heading line: that content belongs to no candidate.
        boundary = _CHUNK_BOUNDARY_RE.search(chunk, head.end() - head.start())
        if boundary:
            chunk = chunk[: boundary.start()]
        block = _DISPATCH_BLOCK_RE.search(chunk)
        entry_md = _DISPATCH_BLOCK_RE.sub("", chunk).strip()
        cand = Candidate(name=head.group(2).strip(), entry_md=entry_md)
        if block is None:
            cand.parse_error = "no <!-- dispatch --> block"
            candidates.append(cand)
            continue
        try:
            parsed = _parse_dispatch_block(block.group(1))
        except ValueError as exc:
            cand.parse_error = f"malformed dispatch block: {exc}"
            candidates.append(cand)
            continue
        top, cand.layers = parsed["top"], parsed["layers"]
        cand.hold = top.get("hold") or None
        cand.source = top.get("source") or None
        cand.dataset = top.get("dataset") or None
        if cand.hold is None and not cand.layers:
            cand.parse_error = "dispatch block declares no layers and no hold"
        for slug in (cand.source, cand.dataset):
            if slug is not None and not _SLUG_RE.match(slug):
                cand.parse_error = f"invalid slug {slug!r} (want lowercase_with_underscores)"
        candidates.append(cand)
    return candidates


def next_missing_step(candidate: Candidate, root: Path) -> LayerStep | None:
    """First step not yet fully built under *root* (any of its sentinels missing)."""
    for step in candidate.layers:
        if not step.is_built(root):
            return step
    return None


def _title_matches(titles: list[str], prefix: str) -> bool:
    p = prefix.casefold()
    return any(t.casefold().startswith(p) for t in titles)


# ---- freshness -> data-refresh issues ---------------------------------------


def freshness_issue_specs(
    statuses: list[SourceStatus], open_issue_titles: list[str]
) -> tuple[list[IssueSpec], list[str]]:
    """One templated data-refresh issue per stale source, deduped by title prefix."""
    specs: list[IssueSpec] = []
    notes: list[str] = []
    for s in statuses:
        if s.state == "probe-failed":
            notes.append(f"freshness: {s.source} probe failed — verify by hand ({s.note})")
            continue
        if s.state != "stale":
            continue
        prefix = f"data: {s.source} new release"
        if _title_matches(open_issue_titles, prefix):
            notes.append(f"freshness: {s.source} is stale but an open issue already tracks it")
            continue
        title = f"data: {s.source} new release {s.live}"
        body = f"""## Executive summary

The upstream source **{s.source}** has published a new release (`{s.live}`) that is \
newer than the release Cairn currently pins (`{s.pinned}`). Cairn (a provenance-first \
emissions data warehouse) never updates data silently: a human triggers the ingest \
workflow, which pins the new release as an append-only snapshot in the manifest (the \
file that records exactly which source data Cairn uses), and the CI fixtures and model \
assumptions are then refreshed to match. This issue was opened automatically by the \
no-LLM freshness check in `cairn-dispatch.yml`.

## What to do

1. Trigger the **Cairn Ingest** workflow (Actions → Cairn Ingest) with source
   `{s.source}` — it runs the idempotent ingest with the R2 credentials and opens
   the manifest-pin PR.
2. Follow the matching "Recurring maintenance" checklist in CLAUDE.md for
   `{s.source}`: refresh the CI fixture, bump the `*_raw_dir` default in
   `transform/dbt_project.yml`, re-check the assumptions the staging/mart models
   lean on, run the build/verify sequence, and note the release in the README.

| Pinned | Live upstream |
| --- | --- |
| `{s.pinned}` | `{s.live}` |
"""
        specs.append(IssueSpec(title=title, labels=["proposal", "data-refresh"], body=body))
    return specs, notes


# ---- backlog -> next-layer feat issue ----------------------------------------


def _fmt_steps(steps: list[LayerStep]) -> str:
    return "; ".join(f"{s.key} (`{'`, `'.join(s.sentinels)}`)" for s in steps)


_AUTO_APPROVE_NOTE = (
    "This step was **pre-authorized**: the BACKLOG.md entry quoted below was "
    "human-reviewed when its replenish PR merged, so this issue carries the "
    "`approved` label from creation and implementation starts immediately. The "
    "implementation PR's human merge remains the audit checkpoint. (Remove the "
    "label and close the PR to veto.)"
)


def _backlog_issue_body(candidate: Candidate, step: LayerStep, auto_approved: bool) -> str:
    idx = candidate.layers.index(step)
    done = candidate.layers[:idx]
    remaining = candidate.layers[idx + 1 :]
    fused = len(step.parts) > 1
    unit = "step" if fused else "layer"

    scaffold = ""
    part = step.scaffoldable_part
    if part is not None and candidate.source and candidate.dataset:
        scaffold = (
            "Scaffold parameters:\n"
            f"- source: {candidate.source}\n"
            f"- dataset: {candidate.dataset}\n\n"
        )

    done_line = _fmt_steps(done) if done else "none — this is the first layer"
    remaining_line = (
        _fmt_steps(remaining) if remaining else "none — this is the candidate's final layer"
    )

    if fused:
        sentinels = ", ".join(f"`{s}`" for s in step.sentinels)
        scope_bullet = (
            f"Deliver the fused **{step.title}** step — build **all** of its layers in one "
            f"PR ({' and '.join(step.parts)}). Its sentinel artifacts are {sentinels}; the "
            "dispatcher considers the step done only when every one of those files exists on "
            "`main`. If you deliberately name an artifact differently, update the candidate's "
            "`<!-- dispatch -->` block in BACKLOG.md in the same PR, or the step will be "
            "re-dispatched."
        )
    else:
        scope_bullet = (
            f"Deliver the **{step.title}** layer. Its sentinel artifact is "
            f'`{step.sentinels[0]}` — the dispatcher decides "this layer is done" by that '
            "file existing on `main`. If you deliberately name the artifact differently, "
            "update the candidate's `<!-- dispatch -->` block in BACKLOG.md in the same PR, "
            "or this layer will be re-dispatched."
        )

    approval_note = f"\n{_AUTO_APPROVE_NOTE}\n" if auto_approved else ""

    return f"""## Executive summary

This issue asks for the **{step.title}** {unit} of the backlog candidate \
"{candidate.name}" from BACKLOG.md (the curated menu of expansions for Cairn, a \
provenance-first emissions data warehouse). Cairn ships each candidate as a series of \
small, independently reviewable steps; this is the next step whose artifact does not \
exist in the repository yet. It was opened automatically by the no-LLM dispatcher \
(`cairn-dispatch.yml`); the full candidate description, including its "watch" caveats, \
is quoted verbatim below.
{approval_note}
{scaffold}## Scope: this {unit} only

- {scope_bullet}
- Earlier layers (already merged — do not redo): {done_line}.
- Later layers (out of scope — separate issues once this merges): {remaining_line}.

## Candidate entry (verbatim from BACKLOG.md)

{candidate.entry_md}
"""


def backlog_issue_spec(
    candidates: list[Candidate],
    root: Path,
    open_issue_titles: list[str],
    open_pr_titles: list[str],
    *,
    auto_approve: bool = True,
) -> tuple[IssueSpec | None, list[str]]:
    """The single next-layer issue for the highest dispatchable candidate.

    Mirrors the old scout rules: take the top of the menu, one small
    single-layer issue, skip anything already tracked by an open issue or PR.

    With *auto_approve* on (the default; the workflow can switch it off via
    the ``DISPATCH_AUTO_APPROVE`` Actions variable), a non-ingestion step's
    issue carries the ``approved`` label from creation and the workflow
    triggers cairn-implement for it directly — the entry was already
    human-reviewed when its replenish PR merged, and the implementation PR's
    merge stays the human checkpoint. Ingestion steps always keep the manual
    ``approved``-label gate (see ``LayerStep.auto_approvable``).
    """
    notes: list[str] = []
    for cand in candidates:
        if cand.parse_error is not None:
            notes.append(f"backlog: skipped {cand.name!r} — {cand.parse_error}")
            continue
        if cand.hold is not None:
            notes.append(f"backlog: skipped {cand.name!r} — held ({cand.hold})")
            continue
        step = next_missing_step(cand, root)
        if step is None:
            notes.append(
                f"backlog: skipped {cand.name!r} — all sentinel artifacts exist "
                "(fully shipped; replenish should retire it)"
            )
            continue
        # Dedup at candidate level: an open `feat: <name> …` issue means a layer
        # is dispatched/approved/in progress (issues auto-close on PR merge), and
        # an open PR naming the candidate means work is in flight.
        if _title_matches(open_issue_titles, f"feat: {cand.name}"):
            notes.append(f"backlog: skipped {cand.name!r} — an open feat issue already tracks it")
            continue
        if any(cand.name.casefold() in t.casefold() for t in open_pr_titles):
            notes.append(f"backlog: skipped {cand.name!r} — an open PR references it")
            continue
        title = f"feat: {cand.name} — {step.title}"
        auto = auto_approve and step.auto_approvable
        labels = ["proposal", "approved"] if auto else ["proposal"]
        spec = IssueSpec(
            title=title,
            labels=labels,
            body=_backlog_issue_body(cand, step, auto),
            auto_approve=auto,
        )
        return spec, notes
    notes.append("backlog: nothing to dispatch")
    return None, notes


# ---- CLI ----------------------------------------------------------------------


def _load_json(path: Path | None) -> list:
    if path is None or not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def run(
    root: Path,
    *,
    scope: str,
    open_issues: list[dict],
    open_prs: list[dict],
    saturation_threshold: int,
    statuses: list[SourceStatus] | None = None,
    auto_approve: bool = True,
    replenish_threshold: int = 3,
) -> tuple[list[IssueSpec], str, bool]:
    """Compute the issues to open, a run summary, and a replenish-needed flag.

    The third return value is True when fewer than *replenish_threshold*
    candidates still have undispatched work — the workflow then triggers
    cairn-replenish directly instead of waiting for its weekly cron, so the
    menu refills when it actually runs low (replenish itself skips the run if
    its previous PR is still open, so this can't stack PRs).
    """
    issue_titles = [i.get("title", "") for i in open_issues]
    pr_titles = [p.get("title", "") for p in open_prs]
    specs: list[IssueSpec] = []
    replenish_needed = False
    lines: list[str] = ["## Cairn dispatch (no-LLM)", ""]

    if scope in ("both", "freshness"):
        if statuses is None:
            statuses = collect_statuses(root)
        fresh_specs, notes = freshness_issue_specs(statuses, issue_titles)
        specs.extend(fresh_specs)
        lines += [f"- freshness: {s.source} — {s.state}" for s in statuses]
        lines += [f"- {n}" for n in notes]

    if scope in ("both", "backlog"):
        # Saturation gate: opening more proposals is pointless while the human
        # triage queue is already full (freshness issues are exempt, as before).
        untriaged = sum(
            1
            for i in open_issues
            if "proposal" in i.get("labels", []) and "approved" not in i.get("labels", [])
        )
        if untriaged >= saturation_threshold:
            lines.append(
                f"- backlog: saturated ({untriaged} un-approved proposals ≥ "
                f"threshold {saturation_threshold}) — nothing dispatched"
            )
        else:
            backlog_path = root / "BACKLOG.md"
            candidates = (
                parse_backlog(backlog_path.read_text(encoding="utf-8"))
                if backlog_path.is_file()
                else []
            )
            spec, notes = backlog_issue_spec(
                candidates, root, issue_titles, pr_titles, auto_approve=auto_approve
            )
            lines += [f"- {n}" for n in notes]
            if spec is not None:
                specs.append(spec)
            remaining = sum(
                1 for c in candidates if c.dispatchable and next_missing_step(c, root) is not None
            )
            replenish_needed = remaining < replenish_threshold
            lines.append(
                f"- backlog: {remaining} candidate(s) with undispatched work "
                f"(replenish threshold {replenish_threshold}"
                f"{' — triggering replenish' if replenish_needed else ''})"
            )

    lines.append("")
    if specs:
        lines.append(f"**Opening {len(specs)} issue(s):**")
        lines += [f"- {s.title}" + (" *(auto-approved)*" if s.auto_approve else "") for s in specs]
    else:
        lines.append("**No issues to open.**")
    return specs, "\n".join(lines) + "\n", replenish_needed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repo root (default: cwd).")
    parser.add_argument(
        "--scope",
        choices=["both", "freshness", "backlog"],
        default="both",
        help="Which checks to run (freshness probes the network; backlog is offline).",
    )
    parser.add_argument(
        "--open-issues",
        type=Path,
        help='JSON file: [{"title": ..., "labels": [...]}] for the repo\'s open issues.',
    )
    parser.add_argument(
        "--open-prs", type=Path, help='JSON file: [{"title": ...}] for the repo\'s open PRs.'
    )
    parser.add_argument(
        "--saturation-threshold",
        type=int,
        default=5,
        help="Skip backlog dispatch when this many un-approved proposal issues are open.",
    )
    parser.add_argument(
        "--auto-approve",
        choices=["true", "false"],
        default="true",
        help="Label non-ingestion feat issues `approved` at creation and have the "
        "workflow trigger cairn-implement for them directly (default: true).",
    )
    parser.add_argument(
        "--replenish-threshold",
        type=int,
        default=3,
        help="Signal replenish_needed when fewer candidates than this still have "
        "undispatched work.",
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="Write the issues-to-open JSON here (default: stdout)."
    )
    args = parser.parse_args()

    specs, summary, replenish_needed = run(
        args.root.resolve(),
        scope=args.scope,
        open_issues=_load_json(args.open_issues),
        open_prs=_load_json(args.open_prs),
        saturation_threshold=args.saturation_threshold,
        auto_approve=args.auto_approve == "true",
        replenish_threshold=args.replenish_threshold,
    )
    payload = json.dumps(
        {
            "issues": [
                {
                    "title": s.title,
                    "labels": s.labels,
                    "body": s.body,
                    "auto_approve": s.auto_approve,
                }
                for s in specs
            ],
            "replenish_needed": replenish_needed,
        },
        indent=2,
    )
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    print(summary, end="")


if __name__ == "__main__":
    main()
