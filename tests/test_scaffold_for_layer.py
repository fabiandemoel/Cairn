"""Tests for the per-issue layer-scaffold dispatcher used by cairn-implement."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.scaffold_for_layer import build_note, extract_slugs

GOOD_BODY = """## Executive summary

Some prose about the candidate.

Scaffold parameters:
- source: rivm
- dataset: emissieregistratie

More prose below.
"""


def test_extract_slugs_from_well_formed_block() -> None:
    assert extract_slugs(GOOD_BODY) == ("rivm", "emissieregistratie")


def test_extract_slugs_missing_block_returns_none() -> None:
    assert extract_slugs("## Executive summary\n\nJust prose, no block.\n") is None


def test_extract_slugs_none_body_returns_none() -> None:
    assert extract_slugs(None) is None


def test_extract_slugs_does_not_match_unrelated_source_dataset_mentions() -> None:
    body = (
        "This issue touches the `sources/rivm/manifest.yml` and the "
        "`stg_rivm__emissieregistratie` dataset. source: not-a-real-slug-context\n"
        "dataset: also-not-real\n"
    )
    # No "Scaffold parameters" header anywhere -> must not match stray mentions.
    assert extract_slugs(body) is None


def test_extract_slugs_incomplete_block_returns_none() -> None:
    body = "Scaffold parameters:\n- source: rivm\n(no dataset line here)\n"
    assert extract_slugs(body) is None


def test_extract_slugs_stops_looking_beyond_window() -> None:
    filler = "\n".join(f"line {i}" for i in range(10))
    body = f"Scaffold parameters:\n{filler}\n- source: rivm\n- dataset: emissieregistratie\n"
    assert extract_slugs(body) is None


def test_build_note_empty_for_layers_without_a_scaffolder() -> None:
    for title in (
        "feat: EU sector benchmark — dbt mart",
        "feat: EU sector benchmark — site",
        "feat: ESRS E1 export tweak",
        "feat: something unclassifiable",
    ):
        assert build_note(Path("/nonexistent"), title, ["feat"], GOOD_BODY) == ""


def test_build_note_data_refresh_is_empty(tmp_path: Path) -> None:
    assert build_note(tmp_path, "data: cbs new release", ["data-refresh"], GOOD_BODY) == ""


def test_build_note_ingestion_without_slug_block(tmp_path: Path) -> None:
    note = build_note(tmp_path, "feat: RIVM — ingestion", ["feat"], "no block here")
    assert "no `Scaffold parameters`" in note
    assert "write the file(s) yourself" in note


def test_build_note_ingestion_success_writes_files(tmp_path: Path) -> None:
    note = build_note(tmp_path, "feat: RIVM — ingestion", ["feat"], GOOD_BODY)
    assert "already been written to" in note
    assert "ingestion/rivm_pipeline.py" in note
    assert (tmp_path / "ingestion" / "rivm_pipeline.py").is_file()
    assert (tmp_path / "sources" / "rivm" / "manifest.yml").is_file()


def test_build_note_scaffolds_staging_part_of_fused_issue(tmp_path: Path) -> None:
    """A fused staging+mart(+site) issue still gets its staging boilerplate."""
    staging = tmp_path / "transform" / "models" / "staging"
    staging.mkdir(parents=True)
    (staging / "_staging.yml").write_text("version: 2\n\nmodels:\n")
    (tmp_path / "transform" / "dbt_project.yml").write_text(
        "name: cairn\n\nvars:\n  raw_dir: x\n\nmodels:\n  cairn:\n    +materialized: view\n"
    )
    note = build_note(tmp_path, "feat: RIVM — dbt staging + dbt mart + site", ["feat"], GOOD_BODY)
    assert "already been written to" in note
    assert (tmp_path / "transform/models/staging/stg_rivm__emissieregistratie.sql").is_file()
    # The note is explicit that only staging was scaffolded.
    assert "Only the `staging` part of this fused issue" in note
    assert "`mart`" in note and "`site`" in note


def test_build_note_staging_success_writes_files(tmp_path: Path) -> None:
    staging = tmp_path / "transform" / "models" / "staging"
    staging.mkdir(parents=True)
    (staging / "_staging.yml").write_text("version: 2\n\nmodels:\n")
    (tmp_path / "transform" / "dbt_project.yml").write_text("vars:\n  raw_dir: x\n\nmodels:\n")

    note = build_note(tmp_path, "feat: RIVM — dbt staging model", ["feat"], GOOD_BODY)
    assert "already been written to" in note
    assert "stg_rivm__emissieregistratie.sql" in note


def test_build_note_already_scaffolded_is_left_untouched(tmp_path: Path) -> None:
    build_note(tmp_path, "feat: RIVM — ingestion", ["feat"], GOOD_BODY)
    pipeline = tmp_path / "ingestion" / "rivm_pipeline.py"
    pipeline.write_text("# hand-written progress, do not clobber\n")

    note = build_note(tmp_path, "feat: RIVM — ingestion", ["feat"], GOOD_BODY)
    assert "already exists on disk" in note
    assert "left untouched" in note
    assert pipeline.read_text() == "# hand-written progress, do not clobber\n"


def test_build_note_malformed_slug_falls_back(tmp_path: Path) -> None:
    body = "Scaffold parameters:\n- source: NOT-VALID\n- dataset: emissieregistratie\n"
    # NOT-VALID fails the slug regex itself, so extract_slugs returns None here --
    # exercise the ValueError path directly via a slug that passes extraction but
    # fails scaffold_ingestion's own validation (e.g. a reserved uppercase form
    # is already filtered by the regex, so use one that slips through: a slug
    # that is syntactically a valid identifier per the regex but is empty after
    # trimming is not reachable here -- so instead assert the not-found path).
    assert extract_slugs(body) is None
    note = build_note(tmp_path, "feat: RIVM — ingestion", ["feat"], body)
    assert "no `Scaffold parameters`" in note


@pytest.mark.parametrize(
    ("title", "expected_layer_in_note"),
    [
        ("feat: RIVM — ingestion pipeline", "ingestion"),
        ("feat: RIVM — dbt staging model", "staging"),
    ],
)
def test_build_note_names_the_layer(
    tmp_path: Path, title: str, expected_layer_in_note: str
) -> None:
    staging = tmp_path / "transform" / "models" / "staging"
    staging.mkdir(parents=True)
    (staging / "_staging.yml").write_text("version: 2\n\nmodels:\n")
    (tmp_path / "transform" / "dbt_project.yml").write_text("vars:\n  raw_dir: x\n\nmodels:\n")

    note = build_note(tmp_path, title, ["feat"], GOOD_BODY)
    assert f"`{expected_layer_in_note}`" in note
