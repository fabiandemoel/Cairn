"""Tests for cairn-implement's model routing + plan extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.implement_strategy import (
    HAIKU,
    PLAN_HEADING,
    SONNET,
    extract_plan,
    gate,
    main,
)

# ---- gate ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "labels", "model", "plan_needed"),
    [
        # data-refresh: a fixed checklist, Haiku alone (the pre-existing routing).
        ("data: cbs new release — run the ingest pipeline", ["data-refresh"], HAIKU, "false"),
        # staging: scaffolded near-copy of the exemplar, Haiku alone.
        ("feat: CBS NAMEA air emission accounts — dbt staging layer", ["proposal"], HAIKU, "false"),
        # ingestion: design weight stays on Sonnet, research brief covers discovery.
        ("feat: Eurostat NAMEA — ingestion", ["proposal"], SONNET, "false"),
        # plan-eligible feat layers: Sonnet plans, Haiku executes.
        ("feat(mart): carbon leakage exposure — dbt mart", ["proposal"], HAIKU, "true"),
        ("feat(site): surface carbon leakage on installations page", ["proposal"], HAIKU, "true"),
        ("feat: NAMEA bridge — dbt mart + site", ["proposal"], HAIKU, "true"),
        ("feat: ESRS E1 export tweak", ["proposal"], HAIKU, "true"),
        # unclassifiable: keep today's conservative behaviour (Sonnet, no plan).
        ("feat: something unclassifiable", ["proposal"], SONNET, "false"),
        # a hand-written title mixing ingestion into a fused set stays Sonnet.
        ("feat: new source ingestion + mart", ["proposal"], SONNET, "false"),
    ],
)
def test_gate_routing(title: str, labels: list[str], model: str, plan_needed: str) -> None:
    out = gate(title, labels)
    assert out["model"] == model
    assert out["plan_needed"] == plan_needed


def test_gate_reports_fused_layers() -> None:
    out = gate("feat: NAMEA bridge — dbt mart + site", ["proposal"])
    assert out["layers"] == "mart+site"


def test_gate_data_refresh_label_beats_title() -> None:
    # The label decides even when the title smells like another layer.
    out = gate("data: refresh the euets mart fixtures", ["data-refresh"])
    assert out == {"model": HAIKU, "plan_needed": "false", "layers": "data-refresh"}


def test_gate_empty_title_is_conservative() -> None:
    # A failed issue fetch leaves title/labels empty: today's behaviour (Sonnet).
    assert gate("", []) == {"model": SONNET, "plan_needed": "false", "layers": "unknown"}


# ---- plan ---------------------------------------------------------------------


def _execution_log(result_text) -> list[dict]:
    return [
        {"type": "system", "subtype": "init"},
        {"type": "result", "subtype": "success", "total_cost_usd": 0.30, "result": result_text},
    ]


def test_extract_plan_wraps_final_message(tmp_path: Path) -> None:
    exec_file = tmp_path / "run.json"
    exec_file.write_text(json.dumps(_execution_log("1. Create transform/models/x.sql")), "utf-8")
    plan = extract_plan(exec_file)
    assert plan.startswith(PLAN_HEADING)
    assert "Follow this plan" in plan
    assert "1. Create transform/models/x.sql" in plan


def test_extract_plan_missing_file_falls_back(tmp_path: Path) -> None:
    plan = extract_plan(tmp_path / "nope.json")
    assert plan.startswith(PLAN_HEADING)
    assert "no usable plan" in plan


def test_extract_plan_empty_path_falls_back() -> None:
    # A skipped plan step leaves the workflow expression empty.
    assert "no usable plan" in extract_plan("")


def test_extract_plan_empty_or_missing_result_falls_back(tmp_path: Path) -> None:
    for payload in (_execution_log("   "), _execution_log(None), [{"type": "system"}]):
        exec_file = tmp_path / "run.json"
        exec_file.write_text(json.dumps(payload), "utf-8")
        assert "no usable plan" in extract_plan(exec_file)


# ---- CLI ----------------------------------------------------------------------


def test_main_gate_prints_github_output_lines(capsys) -> None:
    rc = main(["gate", "--title", "feat: NAMEA bridge — dbt mart + site", "--labels", "proposal"])
    assert rc == 0
    out = capsys.readouterr().out
    assert f"model={HAIKU}" in out
    assert "plan_needed=true" in out
    assert "layers=mart+site" in out


def test_main_plan_prints_fallback_for_missing_file(capsys, tmp_path: Path) -> None:
    rc = main(["plan", "--execution-file", str(tmp_path / "nope.json")])
    assert rc == 0
    assert "no usable plan" in capsys.readouterr().out
