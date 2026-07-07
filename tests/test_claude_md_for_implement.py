"""Guards for scripts/claude_md_for_implement.py.

The implement workflow overwrites the ephemeral checkout's CLAUDE.md with this
script's output, so it must (a) drop the Agent-automation section, (b) keep the
invariants / recurring-maintenance checklists / gotchas the implement and
data-refresh runs rely on, and (c) degrade to an unchanged copy if the section
heading is ever renamed -- never crash.
"""

from __future__ import annotations

from pathlib import Path

from scripts.claude_md_for_implement import DEFAULT_PATH, trim

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_drops_only_the_agent_automation_section():
    text = (
        "# CLAUDE.md\n\n"
        "## Non-negotiable invariants (do not violate)\n"
        "1. Raw data is immutable.\n\n"
        "### Agent automation (CI maintenance loop)\n"
        "Two workflows run Claude against this repo...\n"
        "**Cost visibility.** blah blah\n\n"
        "## How to work here\n"
        "- Setup: uv sync.\n"
    )
    out = trim(text)
    # The automation prose is gone...
    assert "Two workflows run Claude against this repo" not in out
    assert "Cost visibility" not in out
    # ...replaced by a pointer to the committed file...
    assert "omitted from the implement-run copy" in out
    # ...while the sections on either side survive verbatim.
    assert "1. Raw data is immutable." in out
    assert "## How to work here" in out
    assert "- Setup: uv sync." in out


def test_unchanged_when_heading_absent():
    text = "# CLAUDE.md\n\n## Non-negotiable invariants\n1. Raw data is immutable.\n"
    assert trim(text) == text


def test_real_claude_md_trims_and_preserves():
    """Run against the committed CLAUDE.md, the file the workflow actually feeds."""
    assert DEFAULT_PATH == REPO_ROOT / "CLAUDE.md"
    original = DEFAULT_PATH.read_text(encoding="utf-8")
    out = trim(original)

    # The automation section's tell-tale prose is dropped.
    assert "### Agent automation (CI maintenance loop)" in out  # heading kept as pointer
    assert "cairn-dispatch.yml" not in out
    assert "Cost visibility" not in out
    assert "DISPATCH_BACKLOG_SATURATION" not in out

    # Load-bearing sections the implement/data-refresh runs read are preserved.
    assert "## Non-negotiable invariants (do not violate)" in out
    assert "Raw data is immutable." in out
    assert "## Recurring maintenance" in out
    assert "When CBS publishes a new release" in out  # data-refresh checklist
    assert "## How to work here" in out
    assert "## Gotchas" in out

    # It genuinely shrank the file.
    assert len(out) < len(original)
