"""Tests for the ingestion-layer scaffold generator."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.scaffold_ingestion import scaffold_ingestion


def test_scaffold_writes_three_files(tmp_path: Path) -> None:
    written = scaffold_ingestion(tmp_path, "rivm", "emissieregistratie")
    assert written == [
        tmp_path / "ingestion" / "rivm_pipeline.py",
        tmp_path / "sources" / "rivm" / "manifest.yml",
        tmp_path / "tests" / "test_rivm_pipeline.py",
    ]
    for path in written:
        assert path.is_file()


def test_manifest_stub_is_unpinned(tmp_path: Path) -> None:
    scaffold_ingestion(tmp_path, "rivm", "emissieregistratie")
    manifest = (tmp_path / "sources" / "rivm" / "manifest.yml").read_text()
    assert manifest == "source: rivm\ndataset: emissieregistratie\nsnapshots: []\n"


def test_refuses_to_overwrite_by_default(tmp_path: Path) -> None:
    scaffold_ingestion(tmp_path, "rivm", "emissieregistratie")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        scaffold_ingestion(tmp_path, "rivm", "emissieregistratie")


def test_force_overwrites(tmp_path: Path) -> None:
    scaffold_ingestion(tmp_path, "rivm", "emissieregistratie")
    written = scaffold_ingestion(tmp_path, "rivm", "emissieregistratie", force=True)
    assert len(written) == 3


@pytest.mark.parametrize("bad", ["RIVM", "rivm-2", "2rivm", "riv m", ""])
def test_rejects_malformed_identifiers(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError, match="lowercase identifier"):
        scaffold_ingestion(tmp_path, bad, "dataset")
    with pytest.raises(ValueError, match="lowercase identifier"):
        scaffold_ingestion(tmp_path, "source", bad)


def test_generated_pipeline_module_is_importable_and_stubs_raise(tmp_path: Path) -> None:
    """The generated file must be valid, loadable Python whose TODO stubs fail loudly."""
    scaffold_ingestion(tmp_path, "rivm", "emissieregistratie")
    module_path = tmp_path / "ingestion" / "rivm_pipeline.py"

    spec = importlib.util.spec_from_file_location("rivm_pipeline", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.SOURCE == "rivm"
    assert module.DATASET == "emissieregistratie"
    with pytest.raises(NotImplementedError, match="release detection"):
        module._fetch_release()
    with pytest.raises(NotImplementedError, match="download\\+convert"):
        module._download_and_convert("http://example", tmp_path)
    with pytest.raises(NotImplementedError, match="periods_covered"):
        module._periods_covered(tmp_path)


def test_generated_files_pass_ruff(tmp_path: Path) -> None:
    scaffold_ingestion(tmp_path, "rivm", "emissieregistratie")
    for rel in ("ingestion/rivm_pipeline.py", "tests/test_rivm_pipeline.py"):
        cmd = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select",
            "E,F,I,UP,B,SIM",
            str(tmp_path / rel),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, f"ruff failed for {rel}:\n{result.stdout}{result.stderr}"


def test_generated_test_file_has_reusable_idempotency_test(tmp_path: Path) -> None:
    scaffold_ingestion(tmp_path, "rivm", "emissieregistratie")
    content = (tmp_path / "tests" / "test_rivm_pipeline.py").read_text()
    assert "def test_run_skips_when_release_already_pinned" in content
    assert "TODO(scaffold)" in content
