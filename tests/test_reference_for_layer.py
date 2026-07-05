"""Tests for the per-layer reference implementation injected into cairn-implement."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.reference_for_layer import build_reference, infer_layer, infer_layers


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


@pytest.mark.parametrize(
    ("title", "labels", "expected"),
    [
        ("data: cbs new release", ["proposal", "data-refresh"], ["data-refresh"]),
        ("feat: X — ingestion", ["feat"], ["ingestion"]),
        ("feat: X — dbt mart", ["feat"], ["mart"]),
        ("feat: X — site", ["feat"], ["site"]),
        # A fused dispatch step yields both layers, in dependency order.
        ("feat: Coverage observability — dbt mart + site", ["feat"], ["mart", "site"]),
        ("feat: something unclassifiable", ["feat"], ["unknown"]),
    ],
)
def test_infer_layers(title: str, labels: list[str], expected: list[str]) -> None:
    assert infer_layers(title, labels) == expected


def test_data_refresh_label_wins_over_title() -> None:
    # A data-refresh issue routes to its checklist even if the title says "mart".
    assert infer_layer("data: refresh the mart fixture", ["data-refresh"]) == "data-refresh"
    assert infer_layers("data: refresh the mart fixture", ["data-refresh"]) == ["data-refresh"]


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
    # And it names the per-source registers a new source must be wired into.
    assert "test_source_wiring" in out
    assert "check_freshness" in out


def test_layer_note_only_for_ingestion(tmp_path: Path) -> None:
    # The register-wiring note is ingestion-specific noise for other layers.
    repo = _make_repo(tmp_path)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "export_esrs_e1.py").write_text("def main():\n    pass\n")
    out = build_reference(repo, "export")
    assert "test_source_wiring" not in out


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


def test_fused_layers_inline_every_exemplar(tmp_path: Path) -> None:
    # A fused mart+site step injects the exemplars for both layers in one block.
    marts = tmp_path / "transform" / "models" / "marts"
    marts.mkdir(parents=True)
    (marts / "benchmark_country_sector_emissions.sql").write_text("select 1 as mart_example\n")
    (marts / "_marts.yml").write_text("models: []\n")
    site = tmp_path / "site" / "sources" / "cairn"
    site.mkdir(parents=True)
    (site / "country_sector_emissions.sql").write_text("select 1 as site_example\n")
    pages = tmp_path / "site" / "pages"
    pages.mkdir(parents=True)
    (pages / "sectors-eu.md").write_text("# example page\n")

    out = build_reference(tmp_path, ["mart", "site"])
    assert "fuses" in out and "deliver all of them together" in out
    assert "### Fused layer: mart" in out and "### Fused layer: site" in out
    assert "mart_example" in out and "site_example" in out
    # A single-element list behaves exactly like the scalar form (no fused framing).
    scalar = build_reference(tmp_path, "mart")
    assert build_reference(tmp_path, ["mart"]) == scalar
    assert "fuses" not in scalar


def test_unknown_layer_falls_back(tmp_path: Path) -> None:
    out = build_reference(_make_repo(tmp_path), "unknown")
    assert "closest existing example" in out
