"""Tests for the Claude Code run-cost summariser."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.ai_cost_summary import (
    extract_result,
    main,
    render_markdown,
    summarize,
)

RESULT = {
    "type": "result",
    "subtype": "success",
    "total_cost_usd": 0.1234,
    "num_turns": 12,
    "duration_ms": 34500,
    "usage": {
        "input_tokens": 1200,
        "output_tokens": 560,
        "cache_read_input_tokens": 8900,
        "cache_creation_input_tokens": 100,
    },
    "modelUsage": {
        "claude-sonnet-5": {
            "inputTokens": 1000,
            "outputTokens": 500,
            "cacheReadInputTokens": 8000,
            "cacheCreationInputTokens": 80,
            "costUSD": 0.10,
        },
        "claude-haiku-4-5": {
            "inputTokens": 200,
            "outputTokens": 60,
            "cacheReadInputTokens": 900,
            "cacheCreationInputTokens": 20,
            "costUSD": 0.0234,
        },
    },
}


def test_extract_result_from_message_array() -> None:
    log = [
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {}},
        RESULT,
    ]
    assert extract_result(log) is RESULT


def test_extract_result_from_bare_object_and_wrappers() -> None:
    assert extract_result(RESULT) is RESULT
    assert extract_result({"messages": [RESULT]}) is RESULT
    assert extract_result({"nothing": 1}) is None
    assert extract_result([]) is None


def test_summarize_pulls_figures_and_model_breakdown() -> None:
    s = summarize(RESULT)
    assert s.has_cost
    assert s.total_cost_usd == 0.1234
    assert s.num_turns == 12
    assert s.duration_ms == 34500
    assert s.input_tokens == 1200
    assert s.cache_read == 8900
    assert [m.model for m in s.models] == ["claude-haiku-4-5", "claude-sonnet-5"]
    sonnet = next(m for m in s.models if m.model == "claude-sonnet-5")
    assert sonnet.cost_usd == 0.10
    assert sonnet.cache_write == 80


def test_summarize_sums_models_when_usage_totals_missing() -> None:
    result = {"total_cost_usd": 0.5, "modelUsage": RESULT["modelUsage"]}
    s = summarize(result)
    assert s.input_tokens == 1200  # 1000 + 200
    assert s.output_tokens == 560  # 500 + 60


def test_render_markdown_has_cost_and_table_and_footer() -> None:
    md = render_markdown(summarize(RESULT), label="Cairn Implement", run_url="https://x/run")
    assert "$0.1234" in md
    assert "12 turns" in md
    assert "34.5s" in md
    assert "| claude-sonnet-5 |" in md
    assert "Cairn Implement" in md
    assert "[run](https://x/run)" in md


def test_render_markdown_missing_result_is_graceful() -> None:
    s = summarize(None)
    assert not s.has_cost
    md = render_markdown(s, label="Cairn Scout")
    assert "Cost unavailable" in md
    assert "Cairn Scout" in md


def test_main_writes_comment_and_github_output(tmp_path: Path, monkeypatch) -> None:
    exec_file = tmp_path / "run.json"
    exec_file.write_text(json.dumps([{"type": "system"}, RESULT]), encoding="utf-8")
    out = tmp_path / "comment.md"
    gh_out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))

    rc = main(["--execution-file", str(exec_file), "--label", "Cairn Scout", "-o", str(out)])
    assert rc == 0
    assert "$0.1234" in out.read_text(encoding="utf-8")
    gh = gh_out.read_text(encoding="utf-8")
    assert "cost_usd=0.1234" in gh
    assert "has_cost=true" in gh


def test_main_missing_file_does_not_fail(tmp_path: Path, monkeypatch) -> None:
    gh_out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    rc = main(["--execution-file", str(tmp_path / "nope.json"), "-o", str(tmp_path / "c.md")])
    assert rc == 0
    gh = gh_out.read_text(encoding="utf-8")
    assert "cost_usd=\n" in gh
    assert "has_cost=false" in gh
