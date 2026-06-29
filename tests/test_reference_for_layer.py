"""Tests for the per-layer reference implementation injected into cairn-implement."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.reference_for_layer import build_reference, infer_layer


@pytest.mark.parametrize(
    ("title", "labels", "expected"),
    [
        ("data: cbs new release 2026-03-15", ["proposal", "data-refresh"], "data-refresh"),
        ("feat: Eurostat env_air_gge — ingestion", ["feat"], "ingestion"),
        ("feat: Eurostat AEA ingestion pipeline", ["feat"], "ingestion"),
        ("feat: new source — dbt staging model", ["feat"], "staging"),
        ("feat: verified-vs-allocated — dbt mart", ["feat"], "mart"),
        ("feat: EU sector benchmark — site", ["feat"], "site"),
        ("feat: ESRS E1 export tweak", ["feat"], "export"),
        ("feat: something unclassifiable", ["feat"], "unknown"),
    ],
)
def test_infer_layer(title: str, labels: list[str], expected: str) -> None:
    assert infer_layer(title, labels) == expected


def test_data_refresh_label_wins_over_title() -> None:
    # A data-refresh issue routes to its checklist even if the title says "mart".
    assert infer_layer("data: refresh the mart fixture", ["data-refresh"]) == "data-refresh"


def _make_repo(tmp_path: Path) -> Path:
    ingestion = tmp_path / "ingestion"
    ingestion.mkdir()
    (ingestion / "eurostat_aea_pipeline.py").write_text(
        "DEFAULT_URL = 'https://example/aea.csv'\n\n\ndef run() -> None:\n    pass\n"
    )
    src = tmp_path / "sources" / "eurostat"
    src.mkdir(parents=True)
    (src / "manifest.yml").write_text("source: eurostat\ndataset: aea\nsnapshots: []\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_eurostat_aea_pipeline.py").write_text("def test_smoke():\n    assert True\n")
    return tmp_path


def test_ingestion_reference_inlines_exemplars(tmp_path: Path) -> None:
    out = build_reference(_make_repo(tmp_path), "ingestion")
    # Each exemplar path and its content is inlined with a fenced block.
    assert "### `ingestion/eurostat_aea_pipeline.py`" in out
    assert "DEFAULT_URL" in out
    assert "### `sources/eurostat/manifest.yml`" in out
    assert "snapshots: []" in out
    assert "```python" in out and "```yaml" in out
    # It tells the agent not to re-read them.
    assert "do NOT spend turns" in out


def test_data_refresh_emits_checklist_pointer_not_a_template(tmp_path: Path) -> None:
    out = build_reference(_make_repo(tmp_path), "data-refresh")
    assert "Recurring maintenance" in out
    assert "```" not in out  # no inlined code template


def test_missing_exemplars_degrade_gracefully(tmp_path: Path) -> None:
    # An empty repo (no exemplar files) must not crash; it falls back to a note.
    (tmp_path / "ingestion").mkdir()
    out = build_reference(tmp_path, "ingestion")
    assert "closest existing example" in out
    assert "```" not in out


def test_per_file_line_cap_truncates(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    big = "\n".join(f"line {i}" for i in range(500)) + "\n"
    (repo / "ingestion" / "eurostat_aea_pipeline.py").write_text(big)
    out = build_reference(repo, "ingestion", max_lines=50)
    assert "truncated at 50 lines" in out
    assert "line 49" in out
    assert "line 60" not in out


def test_unknown_layer_falls_back(tmp_path: Path) -> None:
    out = build_reference(_make_repo(tmp_path), "unknown")
    assert "closest existing example" in out
