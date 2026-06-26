"""Summarise a Claude Code action run's cost into a markdown comment + a number.

`anthropics/claude-code-action` exposes an `execution_file` output: the path to a
JSON log of the run. Its final ``type: "result"`` record carries the billing
figures (``total_cost_usd``, ``usage``, ``modelUsage``, ``num_turns``,
``duration_ms``). The three Cairn agent workflows (scout, implement, replenish)
call this script to turn that record into:

  * a markdown block, written to ``--out``, posted as an issue/PR comment, and
  * the run's total cost in USD, written to ``$GITHUB_OUTPUT`` as ``cost_usd``
    so a follow-up step can set it on the Projects v2 board.

Cost visibility is best-effort: a missing or malformed execution file yields a
"cost unavailable" note and an empty ``cost_usd`` rather than failing the run.

    uv run python scripts/ai_cost_summary.py --execution-file run.json \
        --label "Cairn Implement" --run-url https://… -o comment.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _first(d: dict, *keys: str):
    """Return the first present, non-None value among ``keys`` (camel or snake)."""
    for key in keys:
        if isinstance(d, dict) and d.get(key) is not None:
            return d[key]
    return None


def extract_result(data) -> dict | None:
    """Find the billing ``result`` record in a parsed execution file.

    The file is normally a JSON array of stream messages whose last element is
    ``{"type": "result", ...}``; tolerate it also being that object directly, or
    a ``{"messages": [...]}`` / ``{"result": {...}}`` wrapper.
    """
    if isinstance(data, dict):
        if "total_cost_usd" in data or data.get("type") == "result":
            return data
        for key in ("result", "messages", "logs"):
            inner = data.get(key)
            if isinstance(inner, (list, dict)):
                found = extract_result(inner)
                if found is not None:
                    return found
        return None
    if isinstance(data, list):
        for item in reversed(data):
            if isinstance(item, dict) and (
                item.get("type") == "result" or "total_cost_usd" in item
            ):
                return item
    return None


@dataclass
class ModelLine:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost_usd: float | None = None


@dataclass
class CostSummary:
    total_cost_usd: float | None = None
    num_turns: int | None = None
    duration_ms: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    models: list[ModelLine] = field(default_factory=list)

    @property
    def has_cost(self) -> bool:
        return self.total_cost_usd is not None


def summarize(result: dict | None) -> CostSummary:
    """Reduce a result record to the figures the comment + field need."""
    if not result:
        return CostSummary()

    usage = result.get("usage") or {}
    summary = CostSummary(
        total_cost_usd=_first(result, "total_cost_usd", "totalCostUsd", "cost_usd"),
        num_turns=_first(result, "num_turns", "numTurns"),
        duration_ms=_first(result, "duration_ms", "durationMs"),
        input_tokens=_first(usage, "input_tokens", "inputTokens") or 0,
        output_tokens=_first(usage, "output_tokens", "outputTokens") or 0,
        cache_read=_first(usage, "cache_read_input_tokens", "cacheReadInputTokens") or 0,
        cache_write=_first(usage, "cache_creation_input_tokens", "cacheCreationInputTokens") or 0,
    )

    model_usage = result.get("modelUsage") or result.get("model_usage") or {}
    if isinstance(model_usage, dict):
        for name, mu in sorted(model_usage.items()):
            if not isinstance(mu, dict):
                continue
            summary.models.append(
                ModelLine(
                    model=name,
                    input_tokens=_first(mu, "inputTokens", "input_tokens") or 0,
                    output_tokens=_first(mu, "outputTokens", "output_tokens") or 0,
                    cache_read=_first(mu, "cacheReadInputTokens", "cache_read_input_tokens") or 0,
                    cache_write=_first(
                        mu, "cacheCreationInputTokens", "cache_creation_input_tokens"
                    )
                    or 0,
                    cost_usd=_first(mu, "costUSD", "cost_usd", "costUsd"),
                )
            )

    # If usage totals were absent but per-model figures exist, sum them up so the
    # totals row is still meaningful.
    if summary.models and not (summary.input_tokens or summary.output_tokens):
        summary.input_tokens = sum(m.input_tokens for m in summary.models)
        summary.output_tokens = sum(m.output_tokens for m in summary.models)
        summary.cache_read = sum(m.cache_read for m in summary.models)
        summary.cache_write = sum(m.cache_write for m in summary.models)

    return summary


def _usd(value: float | None) -> str:
    return "—" if value is None else f"${value:,.4f}"


def _int(value) -> str:
    return f"{int(value):,}" if value else "0"


def render_markdown(
    summary: CostSummary, *, label: str | None = None, run_url: str | None = None
) -> str:
    heading = "### 🤖 Claude Code run cost"
    if not summary.has_cost:
        lines = [heading, "", "_Cost unavailable: no result record in the execution log._"]
        footer = _footer(label, run_url)
        if footer:
            lines += ["", footer]
        return "\n".join(lines)

    duration_s = None if summary.duration_ms is None else summary.duration_ms / 1000.0
    facts = [f"**Total: {_usd(summary.total_cost_usd)}**"]
    if summary.num_turns is not None:
        facts.append(f"{summary.num_turns} turns")
    if duration_s is not None:
        facts.append(f"{duration_s:,.1f}s")

    lines = [heading, "", " · ".join(facts), ""]

    if summary.models:
        lines += [
            "| Model | Input | Output | Cache read | Cache write | Cost |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for m in summary.models:
            lines.append(
                f"| {m.model} | {_int(m.input_tokens)} | {_int(m.output_tokens)} | "
                f"{_int(m.cache_read)} | {_int(m.cache_write)} | {_usd(m.cost_usd)} |"
            )
        lines.append("")

    lines.append(
        "_Tokens — input "
        f"{_int(summary.input_tokens)} · output {_int(summary.output_tokens)} · "
        f"cache read {_int(summary.cache_read)} · cache write {_int(summary.cache_write)}._"
    )

    footer = _footer(label, run_url)
    if footer:
        lines += ["", footer]
    return "\n".join(lines)


def _footer(label: str | None, run_url: str | None) -> str:
    bits = []
    if label:
        bits.append(label)
    if run_url:
        bits.append(f"[run]({run_url})")
    return "_" + " · ".join(bits) + "_" if bits else ""


def _write_github_output(summary: CostSummary) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    cost = "" if summary.total_cost_usd is None else f"{summary.total_cost_usd}"
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(f"cost_usd={cost}\n")
        fh.write(f"has_cost={'true' if summary.has_cost else 'false'}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execution-file", required=True, help="Path to the action's execution_file JSON."
    )
    parser.add_argument("--label", help="Workflow label for the comment footer.")
    parser.add_argument("--run-url", help="URL of the workflow run, linked in the footer.")
    parser.add_argument("--out", "-o", help="Write the markdown comment here (else stdout).")
    args = parser.parse_args(argv)

    path = Path(args.execution_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = summarize(extract_result(data))
    except (OSError, json.JSONDecodeError) as err:
        print(f"ai_cost_summary: could not read execution file: {err}", file=sys.stderr)
        summary = CostSummary()

    markdown = render_markdown(summary, label=args.label, run_url=args.run_url)
    if args.out:
        Path(args.out).write_text(markdown + "\n", encoding="utf-8")
    else:
        print(markdown)
    _write_github_output(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
