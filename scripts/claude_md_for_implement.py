"""Emit an implement-run-trimmed copy of CLAUDE.md.

CLAUDE.md is the single source of truth for both human maintainers and the
agent workflows, so it carries the full recurring-maintenance runbook *and* a
long "Agent automation (CI maintenance loop)" section that describes the
workflows themselves (dispatch, replenish, implement, cost attribution). That
automation section is pure workflow-internals: it is irrelevant to *implementing*
any single issue, yet it is the largest single block in the file, and every
token the implement agent reads from CLAUDE.md rides in every later turn (the
dominant repeated cost in the run logs).

This script reads the committed CLAUDE.md and strips exactly that section --
from the ``### Agent automation`` heading up to (but not including) the next
level-2 (``## ``) heading -- leaving a short pointer in its place. Everything
else is preserved verbatim, including the invariants, the per-source
"Recurring maintenance" checklists a ``data-refresh`` run greps, the Gotchas,
and "How to work here". The workflow overwrites the ephemeral checkout's
CLAUDE.md with this output before the implement step; the committed file is
never touched.

Generated from the tree each run (never a hand-maintained parallel copy), so it
cannot drift. If the heading is absent (someone renamed the section), the file
is emitted unchanged -- a degraded no-op, never a crash, matching the other
priming scripts (repo_orientation, reference_for_layer).

stdlib-only; unit-tested in tests/test_claude_md_for_implement.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path

# The section to drop and the pointer left in its place. The heading match is a
# prefix so a trailing "(CI maintenance loop)" (or a future re-parenthetical)
# still matches; the section ends at the next level-2 heading.
_DROP_HEADING_PREFIX = "### Agent automation"
_POINTER = (
    "### Agent automation (CI maintenance loop)\n"
    "\n"
    "_(This section is omitted from the implement-run copy of CLAUDE.md: it "
    "describes the CI workflows themselves and is not needed to implement an "
    "issue. See the committed `CLAUDE.md` for the full automation runbook.)_\n"
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = REPO_ROOT / "CLAUDE.md"


def trim(text: str) -> str:
    """Return ``text`` with the Agent-automation section replaced by a pointer.

    Drops from the ``### Agent automation`` heading up to (exclusive) the next
    ``## `` (level-2) heading. Returns ``text`` unchanged if the heading is not
    found.
    """
    lines = text.splitlines(keepends=True)
    start = next(
        (i for i, ln in enumerate(lines) if ln.startswith(_DROP_HEADING_PREFIX)),
        None,
    )
    if start is None:
        return text
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    trailing_nl = "\n" if not _POINTER.endswith("\n") else ""
    return "".join(lines[:start]) + _POINTER + trailing_nl + "\n" + "".join(lines[end:])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_PATH,
        help="Path to the source CLAUDE.md (default: repo-root CLAUDE.md).",
    )
    args = parser.parse_args()
    print(trim(args.path.read_text(encoding="utf-8")), end="")


if __name__ == "__main__":
    main()
