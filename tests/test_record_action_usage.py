"""Tests for the Claude action usage/cost parser. No network -- fixtures
mimic the Claude Code CLI's ``--output-format json`` result object that
``anthropics/claude-code-action`` writes as its ``execution_file``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.record_action_usage import build_summary, parse_result, primary_model

RESULT_JSON = {
    "type": "result",
    "subtype": "success",
    "num_turns": 3,
    "duration_ms": 4005,
    "total_cost_usd": 0.20448,
    "usage": {
        "input_tokens": 2,
        "output_tokens": 4,
        "cache_creation_input_tokens": 34069,
        "cache_read_input_tokens": 0,
    },
    "modelUsage": {
        "claude-sonnet-4-6": {
            "inputTokens": 2,
            "outputTokens": 4,
            "costUSD": 0.20448,
        }
    },
}


def test_parse_result_single_json_object(tmp_path: Path):
    f = tmp_path / "execution.json"
    f.write_text(json.dumps(RESULT_JSON))
    assert parse_result(f) == RESULT_JSON


def test_parse_result_stream_json_picks_last_result(tmp_path: Path):
    f = tmp_path / "execution.jsonl"
    lines = [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": {}}),
        json.dumps(RESULT_JSON),
    ]
    f.write_text("\n".join(lines))
    assert parse_result(f) == RESULT_JSON


def test_parse_result_missing_raises(tmp_path: Path):
    f = tmp_path / "execution.json"
    f.write_text(json.dumps({"type": "assistant"}))
    with pytest.raises(ValueError):
        parse_result(f)


def test_primary_model_picks_highest_cost():
    result = {
        "modelUsage": {
            "claude-haiku-4-5-20251001": {"costUSD": 0.01},
            "claude-sonnet-4-6": {"costUSD": 0.50},
        }
    }
    assert primary_model(result) == "claude-sonnet-4-6"


def test_primary_model_unknown_when_absent():
    assert primary_model({}) == "unknown"


def test_build_summary_fields():
    summary = build_summary(RESULT_JSON)
    assert summary["model"] == "claude-sonnet-4-6"
    assert summary["total_cost_usd"] == 0.2045
    assert summary["input_tokens"] == 2
    assert summary["output_tokens"] == 4
    assert summary["num_turns"] == 3
    assert summary["duration_ms"] == 4005
