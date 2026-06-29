"""Tests for the repo-orientation map injected into the agent workflows."""

from __future__ import annotations

from pathlib import Path

from scripts.repo_orientation import BUILD_SEQUENCE, build_orientation


def _make_repo(tmp_path: Path) -> Path:
    """A minimal repo tree the generator scans."""
    (tmp_path / "sources" / "cbs").mkdir(parents=True)
    (tmp_path / "sources" / "euets").mkdir(parents=True)
    staging = tmp_path / "transform" / "models" / "staging"
    staging.mkdir(parents=True)
    (staging / "_staging.yml").write_text("version: 2\n")
    (staging / "stg_cbs__emissions.sql").write_text("select 1\n")
    marts = tmp_path / "transform" / "models" / "marts"
    marts.mkdir(parents=True)
    (marts / "_marts.yml").write_text("version: 2\n")
    (marts / "benchmark_sector_emissions.sql").write_text("select 1\n")
    (marts / "mart_data_provenance.py").write_text("# model\n")
    site_sources = tmp_path / "site" / "sources" / "cairn"
    site_sources.mkdir(parents=True)
    (site_sources / "connection.yaml").write_text("name: cairn\n")
    (site_sources / "sector_emissions.sql").write_text("select 1\n")
    pages = tmp_path / "site" / "pages"
    pages.mkdir(parents=True)
    (pages / "index.md").write_text("# home\n")
    return tmp_path


def test_lists_each_layer(tmp_path: Path) -> None:
    out = build_orientation(_make_repo(tmp_path))
    # Sources, staging, marts (.sql and .py), site queries, pages all surface.
    assert "- cbs" in out and "- euets" in out
    assert "- stg_cbs__emissions.sql" in out
    assert "- benchmark_sector_emissions.sql" in out
    assert "- mart_data_provenance.py" in out
    assert "- sector_emissions.sql" in out
    assert "- index.md" in out


def test_excludes_dbt_underscore_yml_and_connection(tmp_path: Path) -> None:
    out = build_orientation(_make_repo(tmp_path))
    # dbt's `_staging.yml` / `_marts.yml` are config, not models.
    assert "_staging.yml" not in out
    assert "_marts.yml" not in out
    # connection.yaml is wiring, not a query (it is referenced in the prose but
    # must never be listed as a site source query).
    assert "- connection.yaml" not in out


def test_includes_build_sequence_and_wiring_facts(tmp_path: Path) -> None:
    out = build_orientation(_make_repo(tmp_path))
    for cmd in BUILD_SEQUENCE:
        # The bare command (minus inline comment) must appear in the rendered map.
        assert cmd.split("#")[0].strip() in out
    assert "../../../cairn.duckdb" in out
    assert "npm run sources" in out


def test_empty_layer_renders_placeholder(tmp_path: Path) -> None:
    # A repo with no marts dir at all still renders, with a placeholder.
    (tmp_path / "sources").mkdir()
    out = build_orientation(tmp_path)
    assert "_(none yet)_" in out
