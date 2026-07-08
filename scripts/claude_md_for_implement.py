"""Emit an implement-run-trimmed copy of CLAUDE.md.

CLAUDE.md is the single source of truth for both human maintainers and the
agent workflows, so it carries the full recurring-maintenance runbook *and* a
long "Agent automation (CI maintenance loop)" section that describes the
workflows themselves (dispatch, replenish, implement, cost attribution). Every
token the implement agent reads from CLAUDE.md rides in every later turn (the
dominant repeated cost in the run logs), so this strips what a given run does
not need, from the ephemeral checkout only.

Two profiles:

* ``data-refresh`` (default, safest): drops only the "Agent automation" section
  -- pure workflow-internals, irrelevant to implementing any issue and the
  file's largest single block. A data-refresh run still needs the per-source
  "When <source> publishes a new release" checklists, so those stay.

* ``feat``: additionally drops those per-source refresh checklists (the
  contiguous ``### When ...`` subsections) -- a feat issue implements one new
  layer and never runs a source refresh. The invariants, the still-relevant
  guidance (Classification, Evidence site, ESRS export, references,
  reproducibility), "How to work here", and the Gotchas all stay.

Each dropped block is replaced by a short pointer back to the committed
CLAUDE.md. Everything else is preserved verbatim. Generated from the tree each
run (never a hand-maintained parallel copy) so it cannot drift; if a heading is
absent (someone renamed a section) that block is simply left in place -- a
degraded no-op, never a crash, matching the other priming scripts
(repo_orientation, reference_for_layer).

stdlib-only; unit-tested in tests/test_claude_md_for_implement.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path

_AUTOMATION_PREFIX = "### Agent automation"
_AUTOMATION_POINTER = (
    "### Agent automation (CI maintenance loop)\n"
    "\n"
    "_(This section is omitted from the implement-run copy of CLAUDE.md: it "
    "describes the CI workflows themselves and is not needed to implement an "
    "issue. See the committed `CLAUDE.md` for the full automation runbook.)_\n"
    "\n"
)

_WHEN_PREFIX = "### When "
_WHEN_POINTER = (
    "### Recurring per-source refresh checklists\n"
    "\n"
    '_(The per-source "When <source> publishes a new release" checklists are '
    "omitted from the feat-run copy of CLAUDE.md: they are data-refresh "
    "mechanics, not needed to implement a feat issue. See the committed "
    "`CLAUDE.md` for them.)_\n"
    "\n"
)

PROFILES = ("data-refresh", "feat")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = REPO_ROOT / "CLAUDE.md"


def _is_heading(line: str, max_level: int) -> bool:
    """True if ``line`` is a Markdown ATX heading of level 1..``max_level``."""
    body = line.lstrip("#")
    level = len(line) - len(body)
    return 1 <= level <= max_level and body.startswith(" ")


def _drop_section(
    lines: list[str], start_prefix: str, boundary_level: int, pointer: str
) -> list[str]:
    """Replace the single section starting at ``start_prefix`` with ``pointer``.

    The section ends at the next heading of level <= ``boundary_level``. Returns
    the list unchanged if no line starts with ``start_prefix``.
    """
    start = next((i for i, ln in enumerate(lines) if ln.startswith(start_prefix)), None)
    if start is None:
        return lines
    end = next(
        (i for i in range(start + 1, len(lines)) if _is_heading(lines[i], boundary_level)),
        len(lines),
    )
    return lines[:start] + [pointer] + lines[end:]


def _drop_repeated_sections(lines: list[str], start_prefix: str, pointer: str) -> list[str]:
    """Drop every section starting at ``start_prefix``; emit ``pointer`` once.

    Each section runs until the next level-<=3 heading (which may be another
    matching section). The pointer is emitted at the first match's position;
    later matches are dropped silently so a contiguous run collapses to one
    pointer.
    """
    out: list[str] = []
    i = 0
    emitted = False
    while i < len(lines):
        if lines[i].startswith(start_prefix):
            j = i + 1
            while j < len(lines) and not _is_heading(lines[j], 3):
                j += 1
            if not emitted:
                out.append(pointer)
                emitted = True
            i = j
        else:
            out.append(lines[i])
            i += 1
    return out


def trim(text: str, profile: str = "data-refresh") -> str:
    """Return ``text`` trimmed for the given implement ``profile``."""
    lines = text.splitlines(keepends=True)
    lines = _drop_section(lines, _AUTOMATION_PREFIX, boundary_level=2, pointer=_AUTOMATION_POINTER)
    if profile == "feat":
        lines = _drop_repeated_sections(lines, _WHEN_PREFIX, pointer=_WHEN_POINTER)
    return "".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_PATH,
        help="Path to the source CLAUDE.md (default: repo-root CLAUDE.md).",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILES,
        default="data-refresh",
        help="Which implement profile to trim for (default: data-refresh, the safest).",
    )
    args = parser.parse_args()
    print(trim(args.path.read_text(encoding="utf-8"), profile=args.profile), end="")


if __name__ == "__main__":
    main()
