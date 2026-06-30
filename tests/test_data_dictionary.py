"""Tests for the data-dictionary mart's pure data-gathering logic.

The dbt build exercises ``mart_data_dictionary`` end to end; these tests pin the
``collect_dictionary_rows`` contract directly (column order, test-name joining,
accepted_values extraction, layer labelling) without spinning up dbt, and assert
it reflects the repo's real committed dbt schema files.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "transform" / "models" / "marts" / "mart_data_dictionary.py"


def _load_model_module():
    spec = importlib.util.spec_from_file_location("mart_data_dictionary", MODEL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_model_module()
COLUMNS = [name for name, _ in mod.COLUMNS]


def _idx(col: str) -> int:
    return COLUMNS.index(col)


def _write_schema(directory: Path, name: str, payload: dict) -> Path:
    path = directory / name
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_helpers_parse_test_items():
    assert mod._test_name("not_null") == "not_null"
    assert mod._test_name({"accepted_values": {"values": ["A", "B"]}}) == "accepted_values"
    assert mod._test_name({"relationships": {"to": "ref('x')"}}) == "relationships"
    assert mod._accepted_values([{"accepted_values": {"values": ["A", "B"]}}]) == "A, B"
    assert mod._accepted_values(["unique", "not_null"]) is None


def test_clean_collapses_folded_scalar():
    assert mod._clean("foo\n  bar   baz\n") == "foo bar baz"
    assert mod._clean(None) is None
    assert mod._clean("   ") is None


def test_rows_have_full_column_width_and_contract(tmp_path):
    schema = _write_schema(
        tmp_path,
        "_marts.yml",
        {
            "version": 2,
            "models": [
                {
                    "name": "demo_mart",
                    "description": "A\n  demo   mart.",
                    "columns": [
                        {
                            "name": "id",
                            "description": "Surrogate key.",
                            "tests": ["unique", "not_null"],
                        },
                        {
                            "name": "section",
                            "description": "Section letter.",
                            "tests": [
                                "not_null",
                                {"accepted_values": {"values": ["A", "B"]}},
                            ],
                        },
                        {"name": "note"},
                    ],
                }
            ],
        },
    )
    rows = mod.collect_dictionary_rows([(str(schema), "mart")])
    assert len(rows) == 3
    assert all(len(r) == len(COLUMNS) for r in rows)

    by_col = {r[_idx("column_name")]: r for r in rows}
    assert by_col["id"][_idx("dictionary_key")] == "demo_mart|id"
    assert by_col["id"][_idx("layer")] == "mart"
    assert by_col["id"][_idx("model_description")] == "A demo mart."
    assert by_col["id"][_idx("data_tests")] == "unique, not_null"
    assert by_col["id"][_idx("is_tested")] is True
    assert by_col["id"][_idx("accepted_values")] is None

    assert by_col["section"][_idx("data_tests")] == "not_null, accepted_values"
    assert by_col["section"][_idx("accepted_values")] == "A, B"

    # A column without tests/description is honest NULL, never a placeholder.
    assert by_col["note"][_idx("column_description")] is None
    assert by_col["note"][_idx("data_tests")] is None
    assert by_col["note"][_idx("is_tested")] is False


def test_seeds_block_is_collected(tmp_path):
    schema = _write_schema(
        tmp_path,
        "_seeds.yml",
        {
            "version": 2,
            "seeds": [
                {
                    "name": "demo_seed",
                    "description": "A seed.",
                    "columns": [{"name": "code", "tests": ["unique", "not_null"]}],
                }
            ],
        },
    )
    rows = mod.collect_dictionary_rows([(str(schema), "seed")])
    assert len(rows) == 1
    assert rows[0][_idx("layer")] == "seed"
    assert rows[0][_idx("model_name")] == "demo_seed"


def test_reflects_committed_schema():
    rows = mod.collect_dictionary_rows(mod.DEFAULT_SCHEMA_FILES)
    keys = [r[_idx("dictionary_key")] for r in rows]
    # Keys are unique (model|column is a natural key across the warehouse).
    assert len(keys) == len(set(keys))

    models_by_layer: dict[str, set[str]] = {}
    for row in rows:
        models_by_layer.setdefault(row[_idx("layer")], set()).add(row[_idx("model_name")])

    # Every committed staging model, mart, and seed is documented and present.
    assert {
        "stg_cbs__emissions",
        "stg_euets__installations",
        "stg_euets__compliance",
        "stg_eurostat__aea",
        "stg_eurostat__gge",
        "stg_eea__ets",
    } <= models_by_layer["staging"]
    assert {
        "benchmark_sector_emissions",
        "benchmark_installation_emissions",
        "mart_esrs_e1",
        "benchmark_country_sector_emissions",
        "mart_gge_national_totals",
        "mart_data_provenance",
        "mart_data_dictionary",
        "mart_business_glossary",
    } <= models_by_layer["mart"]
    assert {"sector_mapping_cbs", "lei_mapping_euets"} <= models_by_layer["seed"]

    assert set(models_by_layer) == {"staging", "mart", "seed"}
