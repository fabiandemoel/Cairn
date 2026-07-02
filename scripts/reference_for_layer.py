"""Emit the canonical reference implementation for an issue's layer.

This is a no-LLM, stdlib-only helper run as a workflow step *before* the Claude
step in cairn-implement.yml. Its stdout is injected into the agent's prompt so
the agent starts with the *exact pattern it must copy* already in context —
instead of spending many turns reading the reference files itself to re-derive
the pattern.

Run-log analysis of cairn-implement runs showed the dominant cost was the
"recon" front end: before writing a single line, the agent read the canonical
example for the layer (and usually re-read it two or three times), plus the
neighbouring models that are out of scope for the issue. Because every agent
turn re-sends the whole conversation so far, that read-recon phase inflated the
cost of every later turn. Cairn's work is highly templated — each single-layer
issue is a near-copy of an existing exemplar (an ingestion pipeline follows
another pipeline, a mart follows another mart, a site page follows another
page) — so the pattern is deterministic and can be materialised once per run as
plain text, ~free, rather than re-discovered by the LLM.

The exemplars are read from the filesystem on each run, so they never go stale:
they always reflect the current shape of the repo. Missing files are skipped
gracefully (a renamed/removed exemplar degrades to "no template" rather than
crashing the step). Keep the output reasonably tight — it is re-sent on every
agent turn — hence the per-file line cap.
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Per-layer canonical exemplars: the file(s) a new contribution to that layer
# should be modelled on. Ordered most-illustrative first. Paths that don't
# exist are skipped, so this list can name a preferred exemplar without risking
# a crash if it is later renamed. These mirror the layers cairn-dispatch splits
# a candidate into (ingestion -> staging -> mart -> site/export).
EXEMPLARS: dict[str, list[str]] = {
    "ingestion": [
        "ingestion/eurostat_aea_pipeline.py",
        "sources/eurostat/manifest.yml",
        "tests/test_eurostat_aea_pipeline.py",
    ],
    "staging": [
        "transform/models/staging/stg_eurostat__aea.sql",
        "transform/models/staging/_staging.yml",
    ],
    "mart": [
        "transform/models/marts/benchmark_country_sector_emissions.sql",
        "transform/models/marts/_marts.yml",
    ],
    "site": [
        "site/sources/cairn/country_sector_emissions.sql",
        "site/pages/sectors-eu.md",
    ],
    "export": [
        "scripts/export_esrs_e1.py",
    ],
}

# data-refresh issues are a fixed checklist, not a copy-an-exemplar task, so they
# get a pointer rather than an inlined template.
_NO_TEMPLATE_NOTE = {
    "data-refresh": (
        "This is a `data-refresh` issue: there is no single-file template. Follow "
        'the matching CLAUDE.md "Recurring maintenance" checklist exactly (idempotent '
        "ingest, new append-only snapshot, refresh the CI fixture, bump the `*_raw_dir` "
        "defaults, re-check the model assumptions)."
    ),
    "unknown": (
        "Could not infer a single layer from the issue title. Identify the closest "
        "existing example named in the issue body and model your change on it; consult "
        "the orientation map's layer inventory for what already exists."
    ),
}

_FENCE = {".py": "python", ".sql": "sql", ".yml": "yaml", ".yaml": "yaml", ".md": "markdown"}


def infer_layer(title: str | None, labels: list[str] | None) -> str:
    """Infer the repo layer an issue targets from its title and labels.

    data-refresh is label-driven; the feature layers are encoded in the issue
    title suffix the dispatcher writes (e.g. "… — ingestion", "… — dbt mart",
    "… — site"; see LAYER_TITLES in scripts/dispatch.py, which round-trips
    through this function).
    """
    labs = {label.lower() for label in (labels or [])}
    if "data-refresh" in labs:
        return "data-refresh"

    t = (title or "").lower()
    # Order matters: check the more specific tokens first.
    if "export" in t or "esrs" in t:
        return "export"
    if "site" in t or "evidence" in t or "page" in t:
        return "site"
    if "mart" in t:
        return "mart"
    if "staging" in t or "stg_" in t or "staging model" in t:
        return "staging"
    if "ingest" in t or "pipeline" in t or "manifest" in t:
        return "ingestion"
    return "unknown"


def _render_file(root: Path, rel: str, max_lines: int) -> str | None:
    """Render one exemplar as a fenced block, or None if it doesn't exist."""
    path = root / rel
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = text.splitlines()
    truncated = len(lines) > max_lines
    if truncated:
        lines = lines[:max_lines]
    body = "\n".join(lines)
    fence = _FENCE.get(path.suffix, "")
    note = (
        f"\n… (truncated at {max_lines} lines — read `{rel}` directly only if you need the rest)"
        if truncated
        else ""
    )
    return f"### `{rel}`\n\n```{fence}\n{body}{note}\n```"


def build_reference(root: Path, layer: str, max_lines: int = 250) -> str:
    heading = "## Canonical reference for this layer (generated — copy this pattern)"

    if layer in _NO_TEMPLATE_NOTE:
        return f"{heading}\n\n{_NO_TEMPLATE_NOTE[layer]}\n"

    blocks = [b for rel in EXEMPLARS.get(layer, []) if (b := _render_file(root, rel, max_lines))]
    if not blocks:
        return f"{heading}\n\n{_NO_TEMPLATE_NOTE['unknown']}\n"

    intro = (
        f"The files below are the canonical, in-tree exemplar(s) for the **{layer}** layer. "
        "Your change is a near-copy of this pattern — model the new file(s) on these and adapt "
        "only the source-specific parts. This is the authoritative template: do NOT spend turns "
        "re-reading these files, and do NOT read neighbouring layers' files that are out of scope "
        "for this issue."
    )
    return heading + "\n\n" + intro + "\n\n" + "\n\n".join(blocks) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repo root to scan (default: current working directory).",
    )
    parser.add_argument(
        "--layer",
        help="Layer to emit a reference for. If omitted, inferred from --title/--labels.",
    )
    parser.add_argument(
        "--title", help="Issue title (used to infer the layer when --layer is absent)."
    )
    parser.add_argument(
        "--labels", default="", help="Comma-separated issue labels (used to infer data-refresh)."
    )
    parser.add_argument(
        "--max-lines", type=int, default=250, help="Per-file line cap to keep the prompt bounded."
    )
    args = parser.parse_args()

    layer = args.layer or infer_layer(args.title, args.labels.split(",") if args.labels else [])
    print(build_reference(args.root.resolve(), layer, max_lines=args.max_lines), end="")


if __name__ == "__main__":
    main()
