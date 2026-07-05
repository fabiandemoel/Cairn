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
   fused (``mart+site``) so a mart and its thin read-only site page ship as one
   issue. The next step to dispatch is simply the first step not yet fully built
   (any sentinel missing); the issue body quotes the candidate's BACKLOG entry
   verbatim (its scope and "watch" caveats) plus a templated scope section, so
   cairn-implement still receives an authoritative spec.

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
# "Scaffold parameters" block (see scripts/scaffold_for_layer.py). These must
# stay their own step: the scaffold + the (ingestion-only) source-research gate
# key off a single-layer issue, so they can never be fused into a combined step.
_SCAFFOLDABLE = {"ingestion", "staging"}

_DISPATCH_BLOCK_RE = re.compile(r"<!--\s*dispatch\b(.*?)-->", re.S)
_CANDIDATE_HEAD_RE = re.compile(r"^### (?:\d+\.\s*)?(.+?)\s*$", re.M)
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


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
        """The lone scaffoldable layer if this is a single ingestion/staging step."""
        if len(self.parts) == 1 and self.parts[0] in _SCAFFOLDABLE:
            return self.parts[0]
        return None

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


def _parse_layer_step(layer_key: str, path_spec: str) -> LayerStep:
    """Parse one ``<layer>: <sentinel>`` line, including a fused ``a+b: p; q`` step.

    A fused key joins two or more layer names with ``+``; its value carries one
    ``;``-separated sentinel per part. Fused parts must be distinct, listed in
    dependency order, and free of scaffoldable layers (ingestion/staging keep
    their own step — see ``_SCAFFOLDABLE``).
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
        scaffoldable = [p for p in parts if p in _SCAFFOLDABLE]
        if scaffoldable:
            raise ValueError(
                f"fused step {layer_key!r} cannot include scaffoldable layer(s) "
                f"{scaffoldable} — ingestion/staging must be their own step"
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
    """Extract the "Live candidates" entries, in menu order."""
    live_start = text.find("## Live candidates")
    if live_start < 0:
        return []
    tail = text[live_start:]
    # The section ends at the next H2 or the `---` rule before it.
    end = re.search(r"^(?:## (?!Live candidates)|---\s*$)", tail[1:], re.M)
    section = tail[: end.start() + 1] if end else tail

    candidates: list[Candidate] = []
    heads = list(_CANDIDATE_HEAD_RE.finditer(section))
    for i, head in enumerate(heads):
        chunk_end = heads[i + 1].start() if i + 1 < len(heads) else len(section)
        chunk = section[head.start() : chunk_end]
        block = _DISPATCH_BLOCK_RE.search(chunk)
        entry_md = _DISPATCH_BLOCK_RE.sub("", chunk).strip()
        cand = Candidate(name=head.group(1).strip(), entry_md=entry_md)
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


def _backlog_issue_body(candidate: Candidate, step: LayerStep) -> str:
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

    return f"""## Executive summary

This issue asks for the **{step.title}** {unit} of the backlog candidate \
"{candidate.name}" from BACKLOG.md (the curated menu of expansions for Cairn, a \
provenance-first emissions data warehouse). Cairn ships each candidate as a series of \
small, independently reviewable steps; this is the next step whose artifact does not \
exist in the repository yet. It was opened automatically by the no-LLM dispatcher \
(`cairn-dispatch.yml`); the full candidate description, including its "watch" caveats, \
is quoted verbatim below.

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
) -> tuple[IssueSpec | None, list[str]]:
    """The single next-layer issue for the highest dispatchable candidate.

    Mirrors the old scout rules: take the top of the menu, one small
    single-layer issue, skip anything already tracked by an open issue or PR.
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
        spec = IssueSpec(title=title, labels=["proposal"], body=_backlog_issue_body(cand, step))
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
) -> tuple[list[IssueSpec], str]:
    """Compute the issues to open plus a human-readable run summary."""
    issue_titles = [i.get("title", "") for i in open_issues]
    pr_titles = [p.get("title", "") for p in open_prs]
    specs: list[IssueSpec] = []
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
            spec, notes = backlog_issue_spec(candidates, root, issue_titles, pr_titles)
            lines += [f"- {n}" for n in notes]
            if spec is not None:
                specs.append(spec)

    lines.append("")
    if specs:
        lines.append(f"**Opening {len(specs)} issue(s):**")
        lines += [f"- {s.title}" for s in specs]
    else:
        lines.append("**No issues to open.**")
    return specs, "\n".join(lines) + "\n"


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
        "-o", "--output", type=Path, help="Write the issues-to-open JSON here (default: stdout)."
    )
    args = parser.parse_args()

    specs, summary = run(
        args.root.resolve(),
        scope=args.scope,
        open_issues=_load_json(args.open_issues),
        open_prs=_load_json(args.open_prs),
        saturation_threshold=args.saturation_threshold,
    )
    payload = json.dumps(
        {"issues": [{"title": s.title, "labels": s.labels, "body": s.body} for s in specs]},
        indent=2,
    )
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    print(summary, end="")


if __name__ == "__main__":
    main()
