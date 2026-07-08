#!/usr/bin/env bash
# One-shot verify wrapper — the whole CI gate in one command, in the right order.
#
# Mirrors ci.yml's lint / test / dbt-build / evidence-build jobs so a local run
# is the same gate the PR faces. The point is to collapse the agent's
# edit→verify loop: the orchestrator hands `runner` ONE task ("run
# scripts/verify.sh") instead of orchestrating six commands and reasoning about
# their order — including the export-before-build:strict ordering, which is
# baked in here (the disclosure page links to the ESRS bundle, so a stale/missing
# export 404s the strict build). A green run comes back in one round trip.
#
#   scripts/verify.sh          run the gate, print a compact PASS/FAIL summary
#   scripts/verify.sh --fix    first apply the deterministic auto-fixers
#                              (ruff format, ruff check --fix, sqlfluff fix),
#                              then run the gate — so formatting nits never
#                              bounce back as failures to hand-fix
#
# Streams each step's full output (so `runner` can diagnose a failure in its own
# isolated context) and ends with a one-line-per-step summary. Exits non-zero if
# any step failed. Independent checks (ruff/format/sqlfluff/pytest) all run so
# every failure surfaces in one pass; the dbt→export→build:strict chain skips
# downstream links once one fails (they would only cascade).
#
# Assumes the environment is already set up (`uv sync`, `npm ci` in site/) — the
# cairn-implement pre-build step guarantees that. Kept in sync with ci.yml by
# hand, like scripts/repo_orientation.py's BUILD_SEQUENCE.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

FIX=0
for arg in "$@"; do
  case "$arg" in
    --fix) FIX=1 ;;
    -h | --help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "usage: scripts/verify.sh [--fix]" >&2; exit 2 ;;
  esac
done

names=()
statuses=()
fail=0

add() {
  names+=("$1")
  statuses+=("$2")
}

# step <label> <shell command>: run it, stream output, record PASS/FAIL.
step() {
  printf '\n===== %s =====\n' "$1"
  if bash -c "$2"; then
    add "$1" PASS
  else
    add "$1" FAIL
    fail=1
  fi
}

if [ "$FIX" = 1 ]; then
  printf '\n===== auto-fix (ruff format, ruff check --fix, sqlfluff fix) =====\n'
  # Best-effort: the check steps below are the real gate. sqlfluff fix returns
  # non-zero when it cannot fully fix a file, which must not abort the run.
  uv run ruff format . || true
  uv run ruff check --fix . || true
  uv run sqlfluff fix transform/models transform/tests || true
fi

# Independent checks — run all so every failure shows up in one pass.
step "ruff check"    "uv run ruff check ."
step "ruff format"   "uv run ruff format --check ."
step "sqlfluff lint" "uv run sqlfluff lint transform/models transform/tests"
step "pytest"        "uv run pytest -q"

# Build chain — dbt writes ./cairn.duckdb, the export reads it and writes the
# site's download bundle, build:strict reads that. Skip downstream on failure.
printf '\n===== dbt build =====\n'
if bash -c "uv run dbt build --project-dir transform --profiles-dir transform"; then
  add "dbt build" PASS
  printf '\n===== esrs export =====\n'
  if bash -c "uv run python scripts/export_esrs_e1.py --out-dir site/static/downloads/esrs_e1"; then
    add "esrs export" PASS
    printf '\n===== build:strict =====\n'
    if bash -c "cd site && npm run build:strict"; then
      add "build:strict" PASS
    else
      add "build:strict" FAIL
      fail=1
    fi
  else
    add "esrs export" FAIL
    fail=1
    add "build:strict" SKIP
  fi
else
  add "dbt build" FAIL
  fail=1
  add "esrs export" SKIP
  add "build:strict" SKIP
fi

printf '\n===== verify summary =====\n'
for i in "${!names[@]}"; do
  printf '  %-14s %s\n' "${names[$i]}" "${statuses[$i]}"
done
if [ "$fail" = 0 ]; then
  echo "ALL GREEN"
else
  echo "FAILURES ABOVE — see the step output for the failing command(s)"
fi
exit "$fail"
