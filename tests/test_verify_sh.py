"""Guards for scripts/verify.sh, the one-shot CI-gate wrapper.

verify.sh is the single command the cairn-implement pre-build and the `runner`
subagent use, so it must (a) parse, (b) be executable, and (c) actually mirror
ci.yml's gate — if a step is dropped here, a run would go green locally and red
in CI. A hand-maintained mirror of ci.yml, like repo_orientation's
BUILD_SEQUENCE, so this test is the thing that catches drift.
"""

from __future__ import annotations

import shlex
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY = REPO_ROOT / "scripts" / "verify.sh"


def test_exists_and_executable():
    assert VERIFY.is_file()
    assert VERIFY.stat().st_mode & stat.S_IXUSR, "verify.sh must be executable"


def test_parses():
    # bash -n: syntax check without running anything.
    proc = subprocess.run(["bash", "-n", str(VERIFY)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_mirrors_ci_gate():
    body = VERIFY.read_text(encoding="utf-8")
    # Each gate step from ci.yml's lint/test/dbt-build/evidence-build jobs.
    for needed in (
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run sqlfluff lint transform/models transform/tests",
        "uv run pytest -q",
        "uv run dbt build --project-dir transform",
        "scripts/export_esrs_e1.py",
        "npm run build:strict",
    ):
        assert needed in body, f"verify.sh no longer runs: {needed}"


def test_fix_mode_runs_the_deterministic_fixers():
    body = VERIFY.read_text(encoding="utf-8")
    for fixer in ("ruff format .", "ruff check --fix .", "sqlfluff fix"):
        assert fixer in body, f"--fix must run: {fixer}"
    # Safe fixes only — never --unsafe-fixes.
    assert "--unsafe-fixes" not in body


def test_bad_flag_is_rejected():
    proc = subprocess.run([str(VERIFY), "--nope"], capture_output=True, text=True)
    assert proc.returncode == 2
    assert "usage" in proc.stderr.lower()


def test_orientation_build_sequence_stays_in_sync():
    """The verify half of repo_orientation's BUILD_SEQUENCE must be in verify.sh."""
    from scripts.repo_orientation import BUILD_SEQUENCE

    body = VERIFY.read_text(encoding="utf-8")
    for cmd in BUILD_SEQUENCE:
        bare = cmd.split("#")[0].strip()
        # verify.sh assumes deps are installed, so it omits the env-setup steps.
        if bare.startswith("uv sync") or "npm ci" in bare:
            continue
        # Compare on the invariant tail (verify.sh adds --profiles-dir to dbt and
        # splits the `cd site && ...` build step), so match on the salient token.
        token = shlex.split(bare)[2] if bare.startswith("uv run") else "build:strict"
        assert token in body, f"BUILD_SEQUENCE step not reflected in verify.sh: {cmd}"
