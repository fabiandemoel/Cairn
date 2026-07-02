"""Precompute the upstream-freshness diff for cairn-dispatch (no-LLM).

The weekly freshness task is to compare each source's live upstream release
token against the pin in ``sources/<name>/manifest.yml`` and open a
``data-refresh`` issue when a newer release exists. This used to be an agent
task; run-log analysis showed the agent spent the bulk of a run *discovering*
those live tokens by hand — and for euets.info, which has no upstream index, it
brute-forced dozens of candidate S3 filenames before concluding there was
nothing to find (run 28368467174: ~20 of 33 turns).

This stdlib-only helper does that diff deterministically. ``collect_statuses``
returns the structured per-source result that ``scripts/dispatch.py`` turns
into ``data-refresh`` issues; ``build_report`` renders the same result as the
compact markdown table (used in job logs/summaries). A probe failure (network,
source layout change) marks that one source "probe failed" and never crashes
the run — a human sees it in the weekly job summary.

Design notes:

* The source-specific bits that a human bumps when ingesting a new release — the
  CBS table id, the Eurostat dataset id, and the euets/EEA ``DEFAULT_URL`` — are
  read from the pipeline source files at runtime, so this script can never drift
  from the pin of record. The stable API base URLs are inlined.
* The small token parsers mirror the ones in the matching ``ingestion/*`` module
  (referenced per source); keep them in sync if a source's token format changes.
* **euets.info has no upstream release index.** Its "current release" is encoded
  only in ``DEFAULT_URL`` in ``ingestion/euets_pipeline.py``; a human points that
  at a newer zip when euets.info publishes one. So the live token equals the pin
  by construction — euets is *human-watched*, never probed.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Stable upstream API bases (the parts that don't change between releases).
CBS_ODATA_BASE = "https://datasets.cbs.nl/odata/v1/CBS"
EUROSTAT_DATAFLOW = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT"

# Fetcher signature: (url) -> (body_text, content_disposition_filename | None).
Fetcher = Callable[[str], "tuple[str, str | None]"]


def _http_get(url: str, *, timeout: int = 25) -> tuple[str, str | None]:
    """Fetch a URL; return (body, Content-Disposition filename or None)."""
    req = urllib.request.Request(url, headers={"User-Agent": "cairn-dispatch-freshness"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        filename = resp.headers.get_filename()
        body = resp.read().decode("utf-8", errors="replace")
    return body, filename


def _read_const(root: Path, rel: str, name: str) -> str | None:
    """Read a ``NAME = "value"`` string constant out of a source file.

    Handles both a single-line literal and a parenthesised multi-line
    concatenation (``NAME = (\\n "a"\\n "b"\\n)``) -- the latter is how the
    longer EEX/Eurostat URLs are written.
    """
    path = root / rel
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(rf'^{name}\s*=\s*[\'"]([^\'"]+)[\'"]', text, re.M)
    if m:
        return m.group(1)
    block = re.search(rf"^{name}\s*=\s*\((.*?)\)", text, re.M | re.S)
    if block:
        parts = re.findall(r'[\'"]([^\'"]*)[\'"]', block.group(1))
        if parts:
            return "".join(parts)
    return None


# ---- pure parsers (mirrored from the ingestion pipelines) -------------------


def parse_pin(manifest_text: str) -> str | None:
    """Latest pinned release from a manifest's YAML text, or None if unpinned.

    Snapshots are append-only, so the last ``release:`` in the file is the most
    recent. ``snapshots: []`` (the committed, unpinned state) yields None.
    """
    releases = re.findall(r"^\s*-?\s*release:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", manifest_text, re.M)
    return releases[-1].strip() if releases else None


def token_from_euets_url(url: str) -> str | None:
    """``eutl_2024_202410.zip`` -> ``2024-10``; ``eutl_2023.zip`` -> ``2023``.

    Mirrors ``ingestion.euets_pipeline._release_from_url``.
    """
    name = url.rsplit("/", 1)[-1]
    pub = re.search(r"_(\d{4})(\d{2})\.zip$", name)
    if pub:
        return f"{pub.group(1)}-{pub.group(2)}"
    year = re.search(r"_(\d{4})\.zip$", name)
    return year.group(1) if year else None


def token_from_eea_filename(filename: str) -> str | None:
    """``eea_..._p_2005-2025_v01_r00.zip`` -> ``2005-2025_v01_r00``.

    Mirrors ``ingestion.eea_ets_pipeline._release_from_filename``.
    """
    stem = filename[:-4] if filename.lower().endswith(".zip") else filename
    match = re.search(r"_p_(.+)$", stem)
    return match.group(1) if match else None


def token_from_eua_url(url: str) -> str | None:
    """``...-auction-report-2012-2025-data.zip`` -> ``2012-2025``.

    Mirrors ``ingestion.eua_pipeline._release_from_url``.
    """
    name = url.rstrip("/").rsplit("/", 1)[-1]
    stem = name[:-4] if name.lower().endswith(".zip") else name
    match = re.search(r"(\d{4}-\d{4})", stem)
    return match.group(1) if match else None


def normalize_eurostat_date(raw: str) -> str | None:
    """Normalise a Eurostat date to YYYY-MM-DD / YYYY-MM.

    Mirrors ``ingestion.eurostat_aea_pipeline._parse_release``.
    """
    s = raw.strip()
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", s)
    if m:
        day, month, year = m.groups()
        return f"{year}-{month}-{day}"
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    m = re.match(r"^(\d{4}-\d{2})$", s)
    return s if m else None


def cbs_token_from_modified(modified: str) -> str | None:
    """CBS ``Modified`` ISO timestamp -> YYYY-MM-DD.

    Mirrors ``ingestion.cbs_pipeline._release_from_properties``.
    """
    try:
        return datetime.fromisoformat(modified).date().isoformat()
    except (ValueError, TypeError):
        return None


def _eurostat_update_date(payload: dict) -> str | None:
    """Pull the UPDATE_DATA annotation date from an SDMX dataflow payload."""
    for ann in payload.get("extension", {}).get("annotation", []):
        if ann.get("type") == "UPDATE_DATA" and ann.get("date"):
            return str(ann["date"])
    return None


# ---- per-source live-token discovery ----------------------------------------


def _live_cbs(root: Path, fetch: Fetcher) -> str:
    table = _read_const(root, "ingestion/cbs_pipeline.py", "TABLE_ID") or "85669NED"
    body, _ = fetch(f"{CBS_ODATA_BASE}/{table}/Properties")
    token = cbs_token_from_modified(json.loads(body).get("Modified", ""))
    if not token:
        raise ValueError("no Modified date in CBS Properties response")
    return token


def _live_eurostat(root: Path, fetch: Fetcher) -> str:
    dataset = _read_const(root, "ingestion/eurostat_aea_pipeline.py", "DATASET")
    if not dataset:
        raise ValueError("could not read Eurostat DATASET constant")
    body, _ = fetch(f"{EUROSTAT_DATAFLOW}/{dataset}?format=json")
    raw = _eurostat_update_date(json.loads(body))
    token = normalize_eurostat_date(raw) if raw else None
    if not token:
        raise ValueError("no UPDATE_DATA annotation in Eurostat dataflow response")
    return token


def _live_eurostat_gge(root: Path, fetch: Fetcher) -> str:
    dataset = _read_const(root, "ingestion/eurostat_gge_pipeline.py", "DATASET")
    if not dataset:
        raise ValueError("could not read Eurostat GGE DATASET constant")
    body, _ = fetch(f"{EUROSTAT_DATAFLOW}/{dataset}?format=json")
    raw = _eurostat_update_date(json.loads(body))
    token = normalize_eurostat_date(raw) if raw else None
    if not token:
        raise ValueError("no UPDATE_DATA annotation in Eurostat GGE dataflow response")
    return token


def _live_eea(root: Path, fetch: Fetcher) -> str:
    url = _read_const(root, "ingestion/eea_ets_pipeline.py", "DEFAULT_URL")
    if not url:
        raise ValueError("could not read EEA DEFAULT_URL")
    _, filename = fetch(url)
    token = token_from_eea_filename(filename) if filename else None
    if not token:
        raise ValueError("EEA response carried no Content-Disposition filename")
    return token


@dataclass(frozen=True)
class SourceStatus:
    """Structured freshness verdict for one source.

    ``state`` is one of: ``current``, ``stale``, ``unpinned``, ``probe-failed``,
    ``human-watched``. ``note`` carries the free-text status cell rendered in the
    markdown table.
    """

    source: str
    pinned: str | None
    live: str | None
    state: str
    note: str


def collect_statuses(root: Path, *, fetch: Fetcher = _http_get) -> list[SourceStatus]:
    """Compare every source's live upstream release token against its pin."""
    statuses: list[SourceStatus] = []

    def manifest_pin(name: str) -> str | None:
        path = root / "sources" / name / "manifest.yml"
        return parse_pin(path.read_text(encoding="utf-8")) if path.is_file() else None

    # CBS / Eurostat (AEA + GGE) / EEA: probe the live token and compare to the pin.
    for name, prober in (
        ("cbs", _live_cbs),
        ("eurostat", _live_eurostat),
        ("eurostat_gge", _live_eurostat_gge),
        ("eea", _live_eea),
    ):
        pin = manifest_pin(name)
        try:
            live = prober(root, fetch)
        except Exception as err:  # noqa: BLE001 — any probe failure degrades, never crashes
            statuses.append(
                SourceStatus(
                    name, pin, None, "probe-failed", f"probe failed ({type(err).__name__}) — verify"
                )
            )
            continue
        if pin is None:
            statuses.append(
                SourceStatus(name, None, live, "unpinned", "unpinned (CI uses fixture) — no action")
            )
        elif live == pin:
            statuses.append(SourceStatus(name, pin, live, "current", "current"))
        else:
            statuses.append(
                SourceStatus(name, pin, live, "stale", f"**STALE — new release {live}**")
            )

    # euets.info: no upstream index; the live token IS the pinned DEFAULT_URL.
    # eua (EEX auction reports): no upstream release index either; the live token
    # is encoded in DEFAULT_URL's filename, bumped by a human when EEX publishes
    # a new archive. Live equals the pin by construction — never probe either.
    for name, rel, tokenizer, never in (
        ("euets", "ingestion/euets_pipeline.py", token_from_euets_url, "S3"),
        ("eua", "ingestion/eua_pipeline.py", token_from_eua_url, "EEX"),
    ):
        url = _read_const(root, rel, "DEFAULT_URL")
        statuses.append(
            SourceStatus(
                name,
                manifest_pin(name),
                tokenizer(url) if url else None,
                "human-watched",
                f"human-watched (no upstream index) — never probe {never}",
            )
        )

    return statuses


def build_report(root: Path, *, fetch: Fetcher = _http_get) -> str:
    """Render the freshness table + a one-line stale summary."""
    statuses = collect_statuses(root, fetch=fetch)
    stale = [f"{s.source} → {s.live}" for s in statuses if s.state == "stale"]

    def row(s: SourceStatus) -> tuple[str, str, str, str]:
        if s.state == "probe-failed":
            return (s.source, s.pinned or "—", "?", s.note)
        if s.state == "unpinned":
            return (s.source, "unpinned", s.live or "?", s.note)
        # current / stale / human-watched all show pin + live verbatim.
        return (s.source, s.pinned or "unpinned", s.live or "?", s.note)

    table = "\n".join(
        [
            "| Source | Pinned | Live upstream | Status |",
            "| --- | --- | --- | --- |",
            *(f"| {s} | {p} | {live} | {st} |" for s, p, live, st in map(row, statuses)),
        ]
    )
    summary = (
        "**No source is stale** — open NO data-refresh issue."
        if not stale
        else "**Stale sources (open ONE data-refresh issue each):** " + "; ".join(stale)
    )
    return (
        "## Upstream freshness (generated — already compared live vs pinned)\n\n"
        + table
        + "\n\n"
        + summary
        + "\n\nA `data-refresh` issue is warranted ONLY for a source marked **STALE** "
        "above. Never probe euets.info/EEX directly or guess their zip filenames.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repo root (default: cwd).")
    args = parser.parse_args()
    print(build_report(args.root.resolve()), end="")


if __name__ == "__main__":
    main()
