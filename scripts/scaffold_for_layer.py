"""No-LLM: scaffold this issue's layer skeleton, when applicable.

Wires ``scaffold_ingestion.py`` / ``scaffold_staging.py`` into cairn-implement's
per-issue precompute sequence, alongside ``reference_for_layer.py``. The layer is
inferred exactly as ``reference_for_layer.infer_layer`` does; only "ingestion" and
"staging" have a scaffold generator today -- a mart or site change is a judgement
call (business logic, not boilerplate), so those layers get no scaffold and no
note (see CLAUDE.md's "Mappings are code, reviewed via PRs").

The source/dataset slugs are never guessed from the issue title's prose -- the
no-LLM dispatcher (``scripts/dispatch.py``) embeds them deterministically, from
the candidate's ``<!-- dispatch -->`` block in BACKLOG.md, for ingestion/staging
issues only, as a fenced block near the top of the issue body::

    Scaffold parameters:
    - source: rivm
    - dataset: emissieregistratie

This module looks for that block within a few lines of its header -- not a
whole-body search -- so it can't accidentally latch onto an unrelated "source"/
"dataset" mention elsewhere in the issue's prose.

Missing/malformed slugs, an out-of-scope layer, or a target that already exists
(partial progress from a previous run) all degrade to either no note (out of
scope layer) or a plain "nothing scaffolded, write it yourself" note -- this is a
pure cost optimisation, never a correctness gate; the agent falls back to
today's copy-the-exemplar path exactly as if this step did not exist.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from scripts.reference_for_layer import infer_layer
from scripts.scaffold_ingestion import scaffold_ingestion
from scripts.scaffold_staging import scaffold_staging

_SCAFFOLDERS = {
    "ingestion": scaffold_ingestion,
    "staging": scaffold_staging,
}

_HEADER_RE = re.compile(r"scaffold parameters", re.IGNORECASE)
_SOURCE_RE = re.compile(r"(?im)^\s*-?\s*source:\s*([a-z][a-z0-9_]*)\s*$")
_DATASET_RE = re.compile(r"(?im)^\s*-?\s*dataset:\s*([a-z][a-z0-9_]*)\s*$")
_WINDOW = 6  # lines to look at after the header before giving up


def extract_slugs(body: str | None) -> tuple[str, str] | None:
    """Pull (source, dataset) out of the issue body's "Scaffold parameters" block.

    Only scans the few lines right after a "Scaffold parameters" header line, so
    it can't match an unrelated "source"/"dataset" mention elsewhere in the body.
    Returns None if no such block exists, or it exists but lacks either slug.
    """
    if not body:
        return None
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if _HEADER_RE.search(line):
            window = "\n".join(lines[i + 1 : i + 1 + _WINDOW])
            source_match = _SOURCE_RE.search(window)
            dataset_match = _DATASET_RE.search(window)
            if source_match and dataset_match:
                return source_match.group(1), dataset_match.group(1)
            return None
    return None


def build_note(root: Path, title: str | None, labels: list[str], body: str | None) -> str:
    """Scaffold the layer (if applicable) and return a prompt note describing the result.

    Returns "" for any layer without a scaffold generator, so the common case
    (mart/site/export/data-refresh issues) adds nothing to the prompt.
    """
    layer = infer_layer(title, labels)
    scaffolder = _SCAFFOLDERS.get(layer)
    if scaffolder is None:
        return ""

    heading = "## Layer scaffold (generated)"

    slugs = extract_slugs(body)
    if slugs is None:
        return (
            f"{heading}\n\n"
            f"This is a `{layer}` issue but no `Scaffold parameters` (source/dataset slug) "
            "block was found in the issue body -- write the file(s) yourself, modelled on "
            "the reference above.\n"
        )

    source, dataset = slugs
    try:
        written = scaffolder(root, source, dataset)
    except FileExistsError:
        return (
            f"{heading}\n\n"
            f"A `{layer}` scaffold for `{source}`/`{dataset}` already exists on disk "
            "(likely partial progress from an earlier run) -- it was left untouched. "
            "Continue from what's there instead of re-scaffolding.\n"
        )
    except ValueError as exc:
        return (
            f"{heading}\n\n"
            f"Could not scaffold the `{layer}` layer: {exc}. Write the file(s) yourself, "
            "modelled on the reference above.\n"
        )

    paths = "\n".join(f"- `{p.relative_to(root)}`" for p in written)
    return (
        f"{heading}\n\n"
        f"The fixed boilerplate for this `{layer}` layer (`{source}`/`{dataset}`) has "
        f"already been written to:\n{paths}\n\n"
        "Every `TODO(scaffold)` marker in those files is a real judgement call you still "
        "need to make (release detection, column mapping, the surrogate key) -- confirm "
        "each against the live source, never invent one. Do NOT rewrite the fixed plumbing "
        "around them; it already matches the canonical pattern above.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repo root to scaffold into (default: current working directory).",
    )
    parser.add_argument("--title", default="", help="Issue title.")
    parser.add_argument("--labels", default="", help="Comma-separated issue labels.")
    parser.add_argument("--body", default="", help="Issue body.")
    args = parser.parse_args()

    labels = args.labels.split(",") if args.labels else []
    print(build_note(args.root.resolve(), args.title, labels, args.body), end="")


if __name__ == "__main__":
    main()
