"""Guard test: every source is wired into the per-source registers.

Each source under ``sources/`` has to be enumerated by hand in a few places
(the ``cairn-ingest`` workflow's dropdown, the freshness check). Those lists
drift silently when a new source is added -- the symptom that motivated this
test: the ``eua`` source shipped its ingestion pipeline but was missing from the
ingest workflow, so a human could never trigger its ingest from the Actions tab.

This test fails loudly when a source exists on disk but is absent from a
register that is supposed to cover *every* source, so the gap is caught at PR
time instead of being discovered the next time someone needs that source.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from scripts.check_freshness import build_report

REPO_ROOT = Path(__file__).resolve().parent.parent
INGEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "cairn-ingest.yml"


def _sources() -> set[str]:
    """Source names = directories under ``sources/`` carrying a manifest."""
    return {d.name for d in (REPO_ROOT / "sources").iterdir() if (d / "manifest.yml").is_file()}


def test_sources_exist() -> None:
    # Sanity: the discovery found something, so an empty set never makes the
    # membership assertions below vacuously pass.
    assert _sources(), "no sources discovered under sources/ -- discovery is broken"


def test_every_source_selectable_in_ingest_workflow() -> None:
    workflow = yaml.safe_load(INGEST_WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML 1.1 parses the bare `on:` key as the boolean True, not the string.
    on = workflow.get("on", workflow.get(True))
    inputs = on["workflow_dispatch"]["inputs"]
    options = set(inputs["source"]["options"])

    missing = _sources() - options
    assert not missing, (
        f"sources {sorted(missing)} have no entry in cairn-ingest.yml's source "
        f"dropdown (options: {sorted(options)}). Add them so a human can trigger "
        "their ingest from the Actions tab."
    )


def test_every_source_has_an_ingest_case_branch() -> None:
    # The run step maps each dropdown value to a pipeline module via a shell
    # `case`. A value in the dropdown with no branch would exit "Unknown source".
    text = INGEST_WORKFLOW.read_text(encoding="utf-8")
    labels = set(re.findall(r"^\s*([\w|]+)\)\s+module=", text, re.M))
    branch_sources = {s for label in labels for s in label.split("|")}

    missing = _sources() - branch_sources
    assert not missing, (
        f"sources {sorted(missing)} have no `case` branch mapping them to a "
        "pipeline module in cairn-ingest.yml's run step."
    )


def test_every_source_appears_in_freshness_report() -> None:
    # build_report probes upstream for some sources; with a fetcher that raises,
    # those rows degrade to "probe failed" but the source is still listed -- so
    # the report is the full register of sources the dispatcher watches.
    def _no_network(_url: str) -> tuple[str, str | None]:
        raise ConnectionError("network disabled in tests")

    report = build_report(REPO_ROOT, fetch=_no_network)
    missing = {name for name in _sources() if f"| {name} |" not in report}
    assert not missing, (
        f"sources {sorted(missing)} are not listed in scripts/check_freshness.py's "
        "report. Add a prober (or a human-watched row) so the dispatcher sees "
        "their freshness."
    )
