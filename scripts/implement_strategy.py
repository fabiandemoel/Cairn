"""No-LLM routing for cairn-implement: orchestrator model + plan-step gate.

Cost analysis of implement runs (e.g. PRs #121/#122) showed the Sonnet
orchestrator is ~83-84% of a run's cost, almost all of it cache-read tokens
re-sent every turn. Haiku's rates are ~3x lower, but feat issues need design
judgement Haiku alone can't be trusted with (mart grain/columns/tests,
methodology within the invariants). The resolution is the same two-step split
already proven by the research step (scripts/source_research.py): put the
judgement in a short, isolated, read-only **Sonnet plan step** whose final
message is injected into the implement prompt, and run the many
write/verify/fix turns of the orchestrator itself on **Haiku**.

Not every issue needs (or can use) a plan:

- ``data-refresh`` — a fixed CLAUDE.md checklist; Haiku alone (the existing
  routing, moved here from inline workflow JS so it is unit-tested).
- ``staging`` — scaffolded (scripts/scaffold_staging.py) and a near-copy of
  the inlined exemplar; Haiku alone.
- ``ingestion`` — keeps the full design weight (new source, manifest,
  invariants 1/2) plus the research brief; stays Sonnet, no plan step.
- ``unknown`` — can't classify, so keep today's conservative behaviour:
  Sonnet, no plan step.
- everything else (``mart``, ``site``, fused ``mart+site``, ``export``) —
  Sonnet plan step, Haiku orchestrator.

``gate``
    Emit ``model=…``, ``plan_needed=true|false`` and ``layers=…`` in
    ``$GITHUB_OUTPUT`` ``key=value`` form, from the issue title/labels.

``plan``
    Extract the plan step's final message from the action's
    ``execution_file`` JSON log and wrap it as the markdown section the
    implement prompt inlines. A missing/unreadable file or an empty result
    degrades to a fallback note — like the research brief, this is a cost
    optimisation, never a correctness gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.ai_cost_summary import extract_result
from scripts.reference_for_layer import infer_layers

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5"

# Layers that run on Haiku without a plan step: the issue body + scaffold +
# exemplar already are the plan.
_HAIKU_ALONE = ({"data-refresh"}, {"staging"})

# Layers that keep the Sonnet orchestrator with no plan step.
_SONNET_ALONE = ("ingestion", "unknown")

PLAN_HEADING = "## Implementation plan"

_FALLBACK_NOTE = (
    f"{PLAN_HEADING}\n\n"
    "_The isolated planning step produced no usable plan (it failed, was "
    "skipped, or returned nothing). Work directly from the issue body and the "
    "canonical layer reference above: keep the design minimal, near-copy the "
    "exemplars, and if a genuine design decision has no obvious answer in the "
    "issue body or the tree, open a draft PR explaining the question rather "
    "than guessing._"
)


def gate(title: str | None, labels: list[str] | None) -> dict[str, str]:
    """The ``key=value`` outputs for the workflow's strategy step."""
    layers = infer_layers(title, labels)
    layer_set = set(layers)
    if layer_set in _HAIKU_ALONE:
        model, plan_needed = HAIKU, False
    elif layer_set.intersection(_SONNET_ALONE):
        model, plan_needed = SONNET, False
    else:
        model, plan_needed = HAIKU, True
    return {
        "model": model,
        "plan_needed": "true" if plan_needed else "false",
        "layers": "+".join(layers),
    }


def extract_plan(execution_file: str | Path) -> str:
    """The markdown plan section for the implement prompt.

    Same mechanics as ``source_research.extract_brief``: the final
    ``type: "result"`` record of the action's execution log carries the plan
    step's final message. Anything short/empty falls back to the note.
    """
    try:
        data = json.loads(Path(execution_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        print(f"implement_strategy: could not read execution file: {err}", file=sys.stderr)
        return _FALLBACK_NOTE

    result = extract_result(data)
    text = (result or {}).get("result")
    if not isinstance(text, str) or not text.strip():
        return _FALLBACK_NOTE
    return (
        f"{PLAN_HEADING} (written this run by a read-only planning step on a stronger "
        "model, from this same issue body, orientation map, and layer reference)\n\n"
        "Follow this plan as the design: it settles file paths, grain, columns, and "
        "tests so you don't re-derive them. Deviate only where the tree contradicts "
        "it, and say so in the PR.\n\n"
        f"{text.strip()}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_gate = sub.add_parser("gate", help="Decide the orchestrator model and the plan step.")
    p_gate.add_argument("--title", default="", help="Issue title (layer inference).")
    p_gate.add_argument("--labels", default="", help="Comma-separated issue labels.")

    p_plan = sub.add_parser("plan", help="Extract the plan from an execution file.")
    p_plan.add_argument(
        "--execution-file",
        required=True,
        help="Path to the plan step's execution_file JSON (may be empty/missing).",
    )

    args = parser.parse_args(argv)
    if args.mode == "gate":
        labels = args.labels.split(",") if args.labels else []
        for key, value in gate(args.title, labels).items():
            print(f"{key}={value}")
    else:
        print(extract_plan(args.execution_file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
