"""Tests for the business-glossary mart's pure data-gathering logic.

The dbt build exercises ``mart_business_glossary`` end to end; these tests pin
the ``collect_glossary_rows`` contract directly and assert the committed
``transform/glossary.yml`` stays honest: unique keys, a fixed category taxonomy,
every term defined, and -- like the "keep references honest" invariant -- every
``related_models`` entry naming a real dbt model or seed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MARTS_DIR = REPO_ROOT / "transform" / "models" / "marts"
GLOSSARY_PATH = REPO_ROOT / "transform" / "glossary.yml"

# The fixed taxonomy pinned by the accepted_values test on mart_business_glossary.
ALLOWED_CATEGORIES = {
    "Accounting principle",
    "Classification",
    "Emissions & units",
    "EU ETS / EUTL",
    "Entity identity",
    "Disclosure",
    "Provenance",
}


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, MARTS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load("mart_business_glossary", "mart_business_glossary.py")
dict_mod = _load("mart_data_dictionary", "mart_data_dictionary.py")
COLUMNS = [name for name, _ in mod.COLUMNS]


def _idx(col: str) -> int:
    return COLUMNS.index(col)


def test_slug_and_join_helpers():
    assert mod._slug("ESRS E1-6") == "esrs_e1_6"
    assert mod._slug("EU ETS / EUTL") == "eu_ets_eutl"
    assert mod._join(["a", "b"]) == "a, b"
    assert mod._join([]) is None
    assert mod._join(None) is None


def test_rows_have_full_column_width(tmp_path):
    path = tmp_path / "glossary.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "terms": [
                    {
                        "term": "Demo term",
                        "category": "Provenance",
                        "aliases": ["dt"],
                        "definition": "A\n  demo   definition.",
                        "related_models": ["mart_data_provenance"],
                        "reference": "https://example.org",
                    },
                    {"term": "Bare term", "category": "Classification", "definition": "Bare."},
                ],
            }
        ),
        encoding="utf-8",
    )
    rows = mod.collect_glossary_rows(str(path))
    assert len(rows) == 2
    assert all(len(r) == len(COLUMNS) for r in rows)
    by_term = {r[_idx("term")]: r for r in rows}
    demo = by_term["Demo term"]
    assert demo[_idx("glossary_key")] == "demo_term"
    assert demo[_idx("definition")] == "A demo definition."
    assert demo[_idx("aliases")] == "dt"
    assert demo[_idx("related_models")] == "mart_data_provenance"
    assert demo[_idx("reference_url")] == "https://example.org"
    # Absent optional fields are honest NULL, never an empty placeholder.
    bare = by_term["Bare term"]
    assert bare[_idx("aliases")] is None
    assert bare[_idx("related_models")] is None
    assert bare[_idx("reference_url")] is None


def test_committed_glossary_is_well_formed():
    rows = mod.collect_glossary_rows(str(GLOSSARY_PATH))
    assert rows, "the committed glossary should not be empty"

    keys = [r[_idx("glossary_key")] for r in rows]
    assert len(keys) == len(set(keys)), "glossary keys must be unique"

    for row in rows:
        assert row[_idx("term")], "every entry has a term"
        assert row[_idx("definition")], f"{row[_idx('term')]} must be defined"
        assert row[_idx("category")] in ALLOWED_CATEGORIES, row[_idx("category")]


def test_related_models_reference_real_models():
    """Every related_models entry must name a real dbt model or seed."""
    # collect_dictionary_rows yields (key, layer, model_name, ...) tuples; index 2.
    real_models = {r[2] for r in dict_mod.collect_dictionary_rows(dict_mod.DEFAULT_SCHEMA_FILES)}

    raw = yaml.safe_load(GLOSSARY_PATH.read_text(encoding="utf-8"))
    for entry in raw["terms"]:
        for model_name in entry.get("related_models") or []:
            assert model_name in real_models, (
                f"glossary term '{entry['term']}' references unknown model '{model_name}'"
            )
