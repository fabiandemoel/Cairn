"""Tests for the research gate + brief extraction around cairn-implement's research step."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.source_research import (
    BRIEF_HEADING,
    extract_brief,
    extract_urls,
    gate,
    main,
)

# ---- gate ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "labels", "needed"),
    [
        ("feat: Eurostat NAMEA — ingestion", ["proposal"], "true"),
        ("feat: RIVM emissieregistratie ingestion pipeline", ["proposal"], "true"),
        ("feat: new source — dbt staging", ["proposal"], "false"),
        ("feat: verified-vs-allocated — dbt mart", ["proposal"], "false"),
        ("feat: EU sector benchmark — site", ["proposal"], "false"),
        ("feat: ESRS E1 export tweak", ["proposal"], "false"),
        # data-refresh wins over an ingestion-flavoured title: the pipelines
        # self-detect their release, so no live research is needed.
        ("data: cbs new release — run the ingest pipeline", ["data-refresh"], "false"),
        ("feat: something unclassifiable", ["proposal"], "false"),
    ],
)
def test_gate_needed_only_for_ingestion(title: str, labels: list[str], needed: str) -> None:
    out = gate(title, labels, "")
    assert out["needed"] == needed


def test_gate_reports_layer_and_urls() -> None:
    body = "See https://www.rivm.nl/data and https://github.com/x/y/issues/1 ."
    out = gate("feat: RIVM — ingestion", ["proposal"], body)
    assert out == {
        "needed": "true",
        "layer": "ingestion",
        "urls": "https://www.rivm.nl/data",
    }


def test_gate_suppresses_urls_when_not_needed() -> None:
    out = gate("feat: benchmark — dbt mart", ["proposal"], "https://example.org/data")
    assert out["needed"] == "false"
    assert out["urls"] == ""


def test_extract_urls_dedupes_strips_and_excludes_github() -> None:
    body = (
        "Data at https://ec.europa.eu/eurostat/api/data.csv, again "
        "https://ec.europa.eu/eurostat/api/data.csv. Repo: "
        "https://github.com/fabiandemoel/Cairn and raw "
        "https://raw.githubusercontent.com/x/y/f.csv plus (https://eea.europa.eu/share)"
    )
    assert extract_urls(body) == [
        "https://ec.europa.eu/eurostat/api/data.csv",
        "https://eea.europa.eu/share",
    ]


def test_extract_urls_empty_body() -> None:
    assert extract_urls(None) == []
    assert extract_urls("no links here") == []


# ---- brief --------------------------------------------------------------------


def _execution_log(result_text) -> list[dict]:
    return [
        {"type": "system", "subtype": "init"},
        {"type": "result", "subtype": "success", "total_cost_usd": 0.01, "result": result_text},
    ]


def test_extract_brief_wraps_final_message(tmp_path: Path) -> None:
    exec_file = tmp_path / "run.json"
    exec_file.write_text(json.dumps(_execution_log("1. URL: https://x/data.csv")), "utf-8")
    brief = extract_brief(exec_file)
    assert brief.startswith(BRIEF_HEADING)
    assert "1. URL: https://x/data.csv" in brief


def test_extract_brief_missing_file_falls_back(tmp_path: Path) -> None:
    brief = extract_brief(tmp_path / "nope.json")
    assert brief.startswith(BRIEF_HEADING)
    assert "no usable brief" in brief


def test_extract_brief_empty_path_falls_back() -> None:
    # A skipped research step leaves the workflow expression empty.
    assert "no usable brief" in extract_brief("")


def test_extract_brief_empty_or_missing_result_falls_back(tmp_path: Path) -> None:
    for payload in (_execution_log("   "), _execution_log(None), [{"type": "system"}]):
        exec_file = tmp_path / "run.json"
        exec_file.write_text(json.dumps(payload), "utf-8")
        assert "no usable brief" in extract_brief(exec_file)


# ---- CLI ----------------------------------------------------------------------


def test_main_gate_prints_github_output_lines(capsys) -> None:
    rc = main(
        [
            "gate",
            "--title",
            "feat: Eurostat NAMEA — ingestion",
            "--labels",
            "proposal",
            "--body",
            "see https://ec.europa.eu/data",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "needed=true" in out
    assert "layer=ingestion" in out
    assert "urls=https://ec.europa.eu/data" in out


def test_main_brief_prints_fallback_for_missing_file(capsys, tmp_path: Path) -> None:
    rc = main(["brief", "--execution-file", str(tmp_path / "nope.json")])
    assert rc == 0
    assert "no usable brief" in capsys.readouterr().out
