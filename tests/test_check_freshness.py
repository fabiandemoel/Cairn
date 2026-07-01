"""Tests for the no-LLM upstream-freshness check consumed by cairn-dispatch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_freshness import (
    build_report,
    cbs_token_from_modified,
    normalize_eurostat_date,
    parse_pin,
    token_from_eea_filename,
    token_from_euets_url,
)

# ---- pure parsers -----------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x/eutl_2024_202410.zip", "2024-10"),
        ("https://x/eutl_2023.zip", "2023"),
        ("https://x/not-a-zip", None),
    ],
)
def test_token_from_euets_url(url: str, expected: str | None) -> None:
    assert token_from_euets_url(url) == expected


def test_token_from_eea_filename() -> None:
    assert token_from_eea_filename("eea_x_p_2005-2025_v01_r00.zip") == "2005-2025_v01_r00"
    assert token_from_eea_filename("no-marker.zip") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-10-23T23:00:00+0200", "2024-10-23"),
        ("23.10.2024", "2024-10-23"),
        ("2024-10", "2024-10"),
        ("garbage", None),
    ],
)
def test_normalize_eurostat_date(raw: str, expected: str | None) -> None:
    assert normalize_eurostat_date(raw) == expected


def test_cbs_token_from_modified() -> None:
    assert cbs_token_from_modified("2026-03-11T00:00:00+0100") == "2026-03-11"
    assert cbs_token_from_modified("not-a-date") is None


def test_parse_pin_takes_last_release_and_handles_empty() -> None:
    pinned = (
        "source: cbs\ndataset: x\nsnapshots:\n  - release: 2025-03-11\n  - release: 2026-03-11\n"
    )
    assert parse_pin(pinned) == "2026-03-11"
    assert parse_pin("source: cbs\ndataset: x\nsnapshots: []\n") is None


# ---- build_report integration with a fake fetcher ---------------------------


def _make_repo(tmp_path: Path, *, cbs_modified: str, eurostat_date: str, pins: dict):
    """Build a temp repo and return (root, fake_fetch)."""
    ing = tmp_path / "ingestion"
    ing.mkdir()
    (ing / "cbs_pipeline.py").write_text('TABLE_ID = "85669NED"\n')
    (ing / "eurostat_aea_pipeline.py").write_text('DATASET = "env_ac_ainah_r2"\n')
    (ing / "eea_ets_pipeline.py").write_text('DEFAULT_URL = "https://eea/download"\n')
    (ing / "euets_pipeline.py").write_text('DEFAULT_URL = "https://s3/eutl_2024_202410.zip"\n')
    for name, pin in pins.items():
        d = tmp_path / "sources" / name
        d.mkdir(parents=True)
        body = (
            f"source: {name}\ndataset: x\nsnapshots:\n  - release: {pin}\n"
            if pin
            else f"source: {name}\ndataset: x\nsnapshots: []\n"
        )
        (d / "manifest.yml").write_text(body)

    def fake_fetch(url: str) -> tuple[str, str | None]:
        if "datasets.cbs.nl" in url:
            return json.dumps({"Modified": cbs_modified}), None
        if "eurostat" in url:
            payload = {
                "extension": {"annotation": [{"type": "UPDATE_DATA", "date": eurostat_date}]}
            }
            return json.dumps(payload), None
        if "eea" in url:
            return "", "eea_x_p_2005-2025_v01_r00.zip"
        raise AssertionError(f"unexpected url {url}")

    return tmp_path, fake_fetch


def test_report_marks_current_and_stale(tmp_path: Path) -> None:
    repo, fetch = _make_repo(
        tmp_path,
        cbs_modified="2026-03-11T00:00:00+0100",  # equals pin -> current
        eurostat_date="2025-01-15T23:00:00+0100",  # newer than pin -> stale
        pins={
            "cbs": "2026-03-11",
            "eurostat": "2024-10-23",
            "eea": "2005-2025_v01_r00",
            "euets": "2024-10",
        },
    )
    out = build_report(repo, fetch=fetch)
    assert "| cbs | 2026-03-11 | 2026-03-11 | current |" in out
    assert "STALE — new release 2025-01-15" in out
    assert "Stale sources" in out and "eurostat → 2025-01-15" in out
    # EEA pin matches the fake filename token -> current.
    assert "2005-2025_v01_r00" in out
    # euets is always human-watched, never stale.
    assert "human-watched" in out


def test_report_handles_unpinned_and_probe_failure(tmp_path: Path) -> None:
    repo, fetch = _make_repo(
        tmp_path,
        cbs_modified="2026-03-11T00:00:00+0100",
        eurostat_date="2025-01-15",
        pins={
            "cbs": "2026-03-11",
            "eurostat": None,
            "eea": "2005-2025_v01_r00",
            "euets": "2024-10",
        },
    )

    def flaky_fetch(url: str) -> tuple[str, str | None]:
        if "datasets.cbs.nl" in url:
            raise TimeoutError("cbs down")
        return fetch(url)

    out = build_report(repo, fetch=flaky_fetch)
    assert "probe failed" in out  # cbs degraded, did not crash
    assert "unpinned (CI uses fixture)" in out  # eurostat unpinned
    # A run where nothing is stale says so explicitly.
    assert "No source is stale" in out


def test_euets_never_probes_and_is_listed(tmp_path: Path) -> None:
    repo, fetch = _make_repo(
        tmp_path,
        cbs_modified="2026-03-11T00:00:00+0100",
        eurostat_date="2024-10-23",
        pins={
            "cbs": "2026-03-11",
            "eurostat": "2024-10-23",
            "eea": "2005-2025_v01_r00",
            "euets": "2024-10",
        },
    )

    def fetch_no_s3(url: str) -> tuple[str, str | None]:
        assert "s3" not in url and "euets" not in url, "euets must never be probed over the network"
        return fetch(url)

    out = build_report(repo, fetch=fetch_no_s3)
    assert "| euets | 2024-10 | 2024-10 | human-watched" in out
