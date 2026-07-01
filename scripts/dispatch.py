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
   header) declaring, per layer, a *sentinel path* — a new file that layer
   creates. The next layer to dispatch is simply the first layer whose sentinel
   does not exist in the tree; the issue body quotes the candidate's BACKLOG
   entry verbatim (its scope and "watch" caveats) plus a templated scope
   section, so cairn-implement still receives an authoritative spec.

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
# reference_for_layer.infer_layer maps back onto the same layer.
LAYER_TITLES: dict[str, str] = {
    "ingestion": "ingestion",
    "staging": "dbt staging",
    "mart": "dbt mart",
    "site": "site",
    "export": "export",
}

# Layers whose fixed boilerplate cairn-implement can pre-scaffold from the
# "Scaffold parameters" block (see scripts/scaffold_for_layer.py).
_SCAFFOLDABLE = {"ingestion", "staging"}

_DISPATCH_BLOCK_RE = re.compile(r"<!--\s*dispatch\b(.*?)-->", re.S)
_CANDIDATE_HEAD_RE = re.compile(r"^### (?:\d+\.\s*)?(.+?)\s*$", re.M)
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class Candidate:
    """One BACKLOG.md "Live candidates" entry plus its parsed dispatch block."""

    name: str
    entry_md: str  # the candidate's section, dispatch comment stripped
    hold: str | None = None
    source: str | None = None
    dataset: str | None = None
    layers: list[tuple[str, str]] = field(default_factory=list)  # (layer, sentinel)
    parse_error: str | None = None  # block missing/malformed -> skip with reason

    @property
    def dispatchable(self) -> bool:
        return self.parse_error is None and self.hold is None and bool(self.layers)


@dataclass(frozen=True)
class IssueSpec:
    title: str
    labels: list[str]
    body: str


def _parse_dispatch_block(text: str) -> dict:
    """Parse the tiny two-level ``key: value`` / ``layers:`` format.

    Deliberately not YAML-the-library: the workflow runs before ``uv sync``, so
    only the stdlib is available, and the schema is small enough to hand-parse.
    """
    top: dict[str, str] = {}
    layers: list[tuple[str, str]] = []
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
            layer, sep, path = line.partition(":")
            layer = layer.strip().lower()
            if not sep or not path.strip():
                raise ValueError(f"expected '<layer>: <sentinel path>', got {line!r}")
            if layer not in LAYER_TITLES:
                raise ValueError(f"unknown layer {layer!r} (known: {', '.join(LAYER_TITLES)})")
            if any(existing == layer for existing, _ in layers):
                raise ValueError(f"duplicate layer {layer!r}")
            layers.append((layer, path.strip()))
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


def next_missing_layer(candidate: Candidate, root: Path) -> tuple[str, str] | None:
    """First (layer, sentinel) whose sentinel path does not exist under *root*."""
    for layer, sentinel in candidate.layers:
        if not (root / sentinel).exists():
            return layer, sentinel
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


def _backlog_issue_body(candidate: Candidate, layer: str, sentinel: str) -> str:
    layer_title = LAYER_TITLES[layer]
    idx = [lyr for lyr, _ in candidate.layers].index(layer)
    done = candidate.layers[:idx]
    remaining = candidate.layers[idx + 1 :]

    scaffold = ""
    if layer in _SCAFFOLDABLE and candidate.source and candidate.dataset:
        scaffold = (
            "Scaffold parameters:\n"
            f"- source: {candidate.source}\n"
            f"- dataset: {candidate.dataset}\n\n"
        )

    done_line = (
        "; ".join(f"{lyr} (`{p}`)" for lyr, p in done) if done else "none — this is the first layer"
    )
    remaining_line = (
        "; ".join(f"{lyr} (`{p}`)" for lyr, p in remaining)
        if remaining
        else "none — this is the candidate's final layer"
    )

    return f"""## Executive summary

This issue asks for the **{layer_title}** layer of the backlog candidate \
"{candidate.name}" from BACKLOG.md (the curated menu of expansions for Cairn, a \
provenance-first emissions data warehouse). Cairn ships each candidate as a series of \
small, independently reviewable layers; this is the next layer whose artifact does not \
exist in the repository yet. It was opened automatically by the no-LLM dispatcher \
(`cairn-dispatch.yml`); the full candidate description, including its "watch" caveats, \
is quoted verbatim below.

{scaffold}## Scope: this layer only

- Deliver the **{layer_title}** layer. Its sentinel artifact is `{sentinel}` — the
  dispatcher decides "this layer is done" by that file existing on `main`. If you
  deliberately name the artifact differently, update the candidate's
  `<!-- dispatch -->` block in BACKLOG.md in the same PR, or this layer will be
  re-dispatched.
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
        nxt = next_missing_layer(cand, root)
        if nxt is None:
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
        layer, sentinel = nxt
        title = f"feat: {cand.name} — {LAYER_TITLES[layer]}"
        spec = IssueSpec(
            title=title, labels=["proposal"], body=_backlog_issue_body(cand, layer, sentinel)
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
