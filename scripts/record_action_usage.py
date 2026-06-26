"""Parse a Claude Code action's execution file into a cost/usage summary.

``anthropics/claude-code-action`` writes one ``execution_file`` per run: the
Claude Code CLI's ``--output-format json`` result object (or, for
``stream-json``, one JSON object per line -- this picks out the last
``type: "result"`` line). That object carries ``total_cost_usd``, token
``usage``, and a per-model ``modelUsage`` breakdown (a subagent on a
different model, e.g. the ``legwork`` Haiku subagent, shows up as its own
entry).

This turns that into a markdown block for the job's ``$GITHUB_STEP_SUMMARY``
and the same fields as ``key=value`` lines for ``$GITHUB_OUTPUT``, so later
workflow steps (comment on the issue/PR, set the GitHub Projects cost field)
can use them without re-parsing anything.

It only reads the execution file and writes plain output files -- no GitHub
API calls -- so it has no network dependency and is easy to unit test.

    uv run python scripts/record_action_usage.py \\
        --execution-file /tmp/claude-execution-output.json \\
        --workflow cairn-implement \\
        --summary-file "$GITHUB_STEP_SUMMARY" \\
        --github-output "$GITHUB_OUTPUT"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_result(execution_file: Path) -> dict:
    """Find the CLI's terminal ``type: "result"`` object in an execution file.

    Handles both ``--output-format json`` (the whole file is one object) and
    ``stream-json`` (one JSON object per line, result is the last one).
    """
    text = execution_file.read_text()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("type") == "result":
            return obj
        if isinstance(obj, list):
            for item in reversed(obj):
                if isinstance(item, dict) and item.get("type") == "result":
                    return item
    except json.JSONDecodeError:
        pass

    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("type") == "result":
            return item

    raise ValueError(f"no result object found in {execution_file}")


def primary_model(result: dict) -> str:
    """The model with the highest cost in modelUsage, or 'unknown'."""
    model_usage = result.get("modelUsage") or {}
    if not model_usage:
        return "unknown"
    return max(model_usage, key=lambda m: model_usage[m].get("costUSD", 0))


def build_summary(result: dict) -> dict:
    usage = result.get("usage") or {}
    return {
        "model": primary_model(result),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_cost_usd": round(result.get("total_cost_usd", 0.0), 4),
        "num_turns": result.get("num_turns", 0),
        "duration_ms": result.get("duration_ms", 0),
    }


def render_summary(workflow: str, summary: dict) -> str:
    return (
        f"### Claude action usage -- {workflow}\n\n"
        f"| model | input tokens | output tokens | cost (USD) | turns | duration |\n"
        f"|---|---|---|---|---|---|\n"
        f"| {summary['model']} | {summary['input_tokens']} | {summary['output_tokens']} | "
        f"${summary['total_cost_usd']} | {summary['num_turns']} | {summary['duration_ms']} ms |\n"
    )


def write_github_output(output_path: Path, summary: dict) -> None:
    with output_path.open("a") as f:
        for key, value in summary.items():
            f.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-file", required=True, type=Path)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--summary-file", type=Path, default=None)
    parser.add_argument("--github-output", type=Path, default=None)
    args = parser.parse_args()

    if not args.execution_file.exists():
        print(f"execution file not found: {args.execution_file}", file=sys.stderr)
        return 1

    result = parse_result(args.execution_file)
    summary = build_summary(result)

    text = render_summary(args.workflow, summary)
    print(text)
    if args.summary_file:
        with args.summary_file.open("a") as f:
            f.write(text)
    if args.github_output:
        write_github_output(args.github_output, summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
