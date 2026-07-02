"""Tests for the staging-layer scaffold generator."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.scaffold_staging import scaffold_staging


def _make_repo(tmp_path: Path) -> Path:
    staging = tmp_path / "transform" / "models" / "staging"
    staging.mkdir(parents=True)
    (staging / "_staging.yml").write_text(
        "version: 2\n\nmodels:\n  - name: stg_cbs__emissions\n    description: existing\n"
    )
    (tmp_path / "transform" / "dbt_project.yml").write_text(
        "name: cairn\n"
        'require-dbt-version: ">=1.8.0"\n'
        "\n"
        "vars:\n"
        '  raw_dir: "tests/fixtures/85669NED/2026-03-11"\n'
        '  euets_raw_dir: "tests/fixtures/euets/2024-10"\n'
        "\n"
        "models:\n"
        "  cairn:\n"
        "    +materialized: view\n"
    )
    real_sqlfluff = Path(__file__).resolve().parent.parent / ".sqlfluff"
    if real_sqlfluff.is_file():
        (tmp_path / ".sqlfluff").write_text(real_sqlfluff.read_text())
    return tmp_path


def test_scaffold_writes_model_and_extends_shared_files(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    written = scaffold_staging(root, "rivm", "emissieregistratie")
    assert written == [
        root / "transform" / "models" / "staging" / "stg_rivm__emissieregistratie.sql",
        root / "transform" / "models" / "staging" / "_staging.yml",
        root / "transform" / "dbt_project.yml",
    ]
    for path in written:
        assert path.is_file()


def test_staging_yml_gets_new_entry_without_disturbing_existing_ones(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    scaffold_staging(root, "rivm", "emissieregistratie")
    content = (root / "transform" / "models" / "staging" / "_staging.yml").read_text()
    assert "- name: stg_cbs__emissions" in content
    assert "description: existing" in content
    assert "- name: stg_rivm__emissieregistratie" in content


def test_staging_yml_append_is_idempotent(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    scaffold_staging(root, "rivm", "emissieregistratie")
    content_after_first = (root / "transform" / "models" / "staging" / "_staging.yml").read_text()
    # A second scaffold for the same source/dataset must not duplicate the entry.
    (root / "transform" / "models" / "staging" / "stg_rivm__emissieregistratie.sql").unlink()
    scaffold_staging(root, "rivm", "emissieregistratie")
    content_after_second = (root / "transform" / "models" / "staging" / "_staging.yml").read_text()
    assert content_after_first == content_after_second
    assert content_after_second.count("stg_rivm__emissieregistratie") == 1


def test_dbt_project_gets_new_raw_dir_var(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    scaffold_staging(root, "rivm", "emissieregistratie")
    content = (root / "transform" / "dbt_project.yml").read_text()
    assert "rivm_emissieregistratie_raw_dir:" in content
    # Existing vars must survive untouched.
    assert 'raw_dir: "tests/fixtures/85669NED/2026-03-11"' in content
    assert 'euets_raw_dir: "tests/fixtures/euets/2024-10"' in content


def test_dbt_project_var_insert_is_idempotent(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    scaffold_staging(root, "rivm", "emissieregistratie")
    first = (root / "transform" / "dbt_project.yml").read_text()
    (root / "transform" / "models" / "staging" / "stg_rivm__emissieregistratie.sql").unlink()
    scaffold_staging(root, "rivm", "emissieregistratie")
    second = (root / "transform" / "dbt_project.yml").read_text()
    assert first == second
    assert second.count("rivm_emissieregistratie_raw_dir") == 1


def test_refuses_to_overwrite_model_by_default(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    scaffold_staging(root, "rivm", "emissieregistratie")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        scaffold_staging(root, "rivm", "emissieregistratie")


def test_force_overwrites_model(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    scaffold_staging(root, "rivm", "emissieregistratie")
    written = scaffold_staging(root, "rivm", "emissieregistratie", force=True)
    # The model file is rewritten; the shared files are untouched (already present).
    assert written == [
        root / "transform" / "models" / "staging" / "stg_rivm__emissieregistratie.sql"
    ]


@pytest.mark.parametrize("bad", ["RIVM", "rivm-2", "2rivm", "riv m", ""])
def test_rejects_malformed_identifiers(tmp_path: Path, bad: str) -> None:
    root = _make_repo(tmp_path)
    with pytest.raises(ValueError, match="lowercase identifier"):
        scaffold_staging(root, bad, "dataset")
    with pytest.raises(ValueError, match="lowercase identifier"):
        scaffold_staging(root, "source", bad)


def test_missing_vars_block_raises(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    (root / "transform" / "dbt_project.yml").write_text("name: cairn\n")
    with pytest.raises(ValueError, match="Could not find a 'vars:' block"):
        scaffold_staging(root, "rivm", "emissieregistratie")


@pytest.mark.skipif(shutil.which("sqlfluff") is None, reason="requires sqlfluff installed")
def test_generated_model_passes_sqlfluff(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    scaffold_staging(root, "rivm", "emissieregistratie")
    model = root / "transform" / "models" / "staging" / "stg_rivm__emissieregistratie.sql"
    cmd = [sys.executable, "-m", "sqlfluff", "lint", str(model)]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    assert result.returncode == 0, f"sqlfluff failed:\n{result.stdout}{result.stderr}"
