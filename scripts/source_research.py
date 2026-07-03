"""No-LLM plumbing around cairn-implement's isolated live-source research step.

Live-source discovery used to happen *inside* the implement run, delegated to a
`legwork` subagent. Prompt-only enforcement of "do it in one synchronous task"
failed twice (implement runs #42 and #43: the orchestrator parked discovery in
background subagents, scheduled a wakeup that can never fire in a one-shot CI
job, and ended its turn having shipped nothing). Discovery therefore moved to a
separate, isolated Haiku step that runs *before* the orchestrator and whose
final message is injected into the implement prompt like the orientation map —
in context from turn 1, at Haiku prices, with nothing mid-run to wait on.

This module is the stdlib-only glue on either side of that step:

``gate``
    Decide whether the issue needs live research at all. Only an
    ingestion-layer issue does — every other layer works from the pinned
    fixtures and the tree. Emits ``needed=true|false`` plus any ``urls=…``
    found in the issue body (GitHub links excluded) in ``$GITHUB_OUTPUT``
    ``key=value`` form.

``brief``
    Extract the research step's final message from the action's
    ``execution_file`` JSON log and wrap it as the markdown section the
    implement prompt inlines. A missing/unreadable file or an empty result
    degrades to a fallback note telling the implementer how to proceed
    without a brief — this is a cost/robustness optimisation, never a
    correctness gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts.ai_cost_summary import extract_result
from scripts.reference_for_layer import infer_layer

# Layers that need live-source discovery. Staging/mart/site/export work from
# the committed fixtures and the tree; data-refresh pipelines self-detect their
# release (or get the new URL as a workflow input), so none of them qualify.
_RESEARCH_LAYERS = {"ingestion"}

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")

# Hosts that never point at the data source itself (repo/issue cross-links).
_EXCLUDED_HOSTS = ("github.com", "githubusercontent.com")

BRIEF_HEADING = "## Live-source research brief"

_FALLBACK_NOTE = (
    f"{BRIEF_HEADING}\n\n"
    "_The isolated research step produced no usable brief (it failed, was "
    "skipped, or returned nothing). Work from the issue body and the layer "
    "reference. If one specific fact about the live source is genuinely "
    "indispensable, hand `legwork` ONE narrowly scoped fetch (an explicit "
    "curl via Bash) rather than exploring; if that fails too, open a draft "
    "PR explaining the blocker._"
)


def extract_urls(body: str | None) -> list[str]:
    """Deduped http(s) URLs from an issue body, minus GitHub cross-links."""
    urls: list[str] = []
    for match in _URL_RE.findall(body or ""):
        url = match.rstrip(".,;:!?`")
        host = url.split("/", 3)[2].lower() if url.count("/") >= 2 else ""
        if any(host == h or host.endswith("." + h) for h in _EXCLUDED_HOSTS):
            continue
        if url not in urls:
            urls.append(url)
    return urls


def gate(title: str | None, labels: list[str] | None, body: str | None) -> dict[str, str]:
    """The ``key=value`` outputs for the workflow's research-gate step."""
    layer = infer_layer(title, labels)
    needed = layer in _RESEARCH_LAYERS
    return {
        "needed": "true" if needed else "false",
        "layer": layer,
        "urls": " ".join(extract_urls(body)) if needed else "",
    }


def extract_brief(execution_file: str | Path) -> str:
    """The markdown brief section for the implement prompt.

    The action's ``execution_file`` is the same JSON log ``ai_cost_summary.py``
    parses; its final ``type: "result"`` record carries the agent's final
    message in ``result``. Anything short/empty means the step yielded no
    usable brief, so fall back to the explanatory note.
    """
    try:
        data = json.loads(Path(execution_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        print(f"source_research: could not read execution file: {err}", file=sys.stderr)
        return _FALLBACK_NOTE

    result = extract_result(data)
    text = (result or {}).get("result")
    if not isinstance(text, str) or not text.strip():
        return _FALLBACK_NOTE
    return f"{BRIEF_HEADING} (generated this run by an isolated research step)\n\n{text.strip()}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_gate = sub.add_parser("gate", help="Decide whether the issue needs live research.")
    p_gate.add_argument("--title", default="", help="Issue title (layer inference).")
    p_gate.add_argument("--labels", default="", help="Comma-separated issue labels.")
    p_gate.add_argument("--body", default="", help="Issue body (URL extraction).")

    p_brief = sub.add_parser("brief", help="Extract the research brief from an execution file.")
    p_brief.add_argument(
        "--execution-file",
        required=True,
        help="Path to the research step's execution_file JSON (may be empty/missing).",
    )

    args = parser.parse_args(argv)
    if args.mode == "gate":
        labels = args.labels.split(",") if args.labels else []
        for key, value in gate(args.title, labels, args.body).items():
            print(f"{key}={value}")
    else:
        print(extract_brief(args.execution_file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
