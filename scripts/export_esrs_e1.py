"""Export the ESRS E1 disclosure bundle from the built DuckDB warehouse.

This turns the ``mart_esrs_e1`` mart into an *auditable end product* a third
party (an auditor, a data consumer, a regulator) can pick up on its own. It
recomputes nothing -- it reads the mart and writes a self-describing bundle:

    exports/esrs_e1/
      esrs_e1_disclosure.csv        the data (E1-6 gross Scope 1 GHG emissions)
      esrs_e1_disclosure.meta.json  provenance + integrity + data dictionary
      README.md                     how to read and verify the bundle

The audit trail in ``meta.json`` chains the disclosure back to its origin:
the EU ETS source pin (release + SHA256 from sources/euets/manifest.yml), the
reviewed methodology (the git commit), the warehouse version, and a SHA256 of
the CSV itself so a consumer can prove the file was not altered after export.

    uv run python scripts/export_esrs_e1.py
    uv run python scripts/export_esrs_e1.py --duckdb cairn.duckdb --out-dir exports/esrs_e1

Build the warehouse first (``dbt build`` for fixtures, or
``scripts/materialize_warehouse.py`` for the R2-pinned real data).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ingestion.manifest import load_manifest  # noqa: E402

MART = "main.mart_esrs_e1"
EUETS_MANIFEST = REPO_ROOT / "sources" / "euets" / "manifest.yml"
DBT_PROJECT = REPO_ROOT / "transform" / "dbt_project.yml"

# The export's column contract. Order matters -- it is the CSV column order.
# Kept here (not parsed from _marts.yml) so the published disclosure has a
# stable, human-curated dictionary independent of internal model docs.
DATA_DICTIONARY: list[dict[str, str]] = [
    {
        "column": "esrs_e1_key",
        "unit": "",
        "description": "Surrogate key (installation_id|reporting_year).",
    },
    {
        "column": "reporting_year",
        "unit": "year",
        "description": "ESRS reporting year (the EU ETS compliance year).",
    },
    {"column": "installation_id", "unit": "", "description": "EUTL installation identifier."},
    {
        "column": "installation_name",
        "unit": "",
        "description": "Installation name as registered in the EUTL.",
    },
    {
        "column": "lei",
        "unit": "",
        "description": (
            "GLEIF Legal Entity Identifier (ISO 17442) of the operating legal entity, "
            "from the reviewed lei_mapping_euets seed; the key for entity-level roll-up. "
            "Empty where no confident GLEIF match exists (never invented)."
        ),
    },
    {
        "column": "gleif_legal_name",
        "unit": "",
        "description": "GLEIF-registered legal name the LEI resolves to. Empty where lei is empty.",
    },
    {
        "column": "nace_section",
        "unit": "",
        "description": "NACE Rev.2 section letter the installation belongs to.",
    },
    {
        "column": "nace_section_label",
        "unit": "",
        "description": "Human-readable NACE section name.",
    },
    {
        "column": "esrs_datapoint",
        "unit": "",
        "description": "ESRS datapoint identifier; constant 'E1-6'.",
    },
    {"column": "ghg_scope", "unit": "", "description": "GHG Protocol scope; constant 'Scope 1'."},
    {
        "column": "unit",
        "unit": "",
        "description": "Unit of the emissions figure; constant 't CO2eq'.",
    },
    {
        "column": "gross_scope_1_ghg_emissions",
        "unit": "t CO2eq",
        "description": "Gross Scope 1 GHG emissions for the installation-year (verified EU ETS).",
    },
    {
        "column": "sector_installation_count",
        "unit": "count",
        "description": "Installations in the NACE-section ETS population for the year.",
    },
    {
        "column": "sector_mean_emissions_t_co2eq",
        "unit": "t CO2eq",
        "description": "Mean Scope 1 emissions across the sector-year population (context).",
    },
    {
        "column": "sector_median_emissions_t_co2eq",
        "unit": "t CO2eq",
        "description": "Median Scope 1 emissions across the sector-year population (context).",
    },
    {
        "column": "emissions_vs_sector_mean",
        "unit": "ratio",
        "description": "Installation emissions divided by the sector mean for the year.",
    },
]

REFERENCES = {
    "esrs_e1": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202302772",
    "csrd_directive": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2464",
    "eu_ets_directive": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32003L0087",
    "installation_source": "https://www.euets.info/",
}


def _sha256(path: Path, *, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str | None:
    """Best-effort current commit -- pins the reviewed methodology/mappings."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _cairn_version() -> str:
    project = yaml.safe_load(DBT_PROJECT.read_text())
    return str(project.get("version", "unknown"))


def export(duckdb_path: Path, out_dir: Path) -> dict:
    """Write the disclosure bundle and return its metadata dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "esrs_e1_disclosure.csv"
    meta_path = out_dir / "esrs_e1_disclosure.meta.json"
    readme_path = out_dir / "README.md"

    column_order = ", ".join(col["column"] for col in DATA_DICTIONARY)
    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        con.execute(
            f"COPY (SELECT {column_order} FROM {MART} "
            "ORDER BY reporting_year, nace_section, gross_scope_1_ghg_emissions DESC) "
            "TO ? (FORMAT CSV, HEADER)",
            [str(csv_path)],
        )
        summary = con.execute(
            f"""
            SELECT
                count(*) AS row_count,
                count(DISTINCT installation_id) AS installation_count,
                min(reporting_year) AS first_year,
                max(reporting_year) AS last_year,
                sum(gross_scope_1_ghg_emissions) AS total_scope_1_t_co2eq
            FROM {MART}
            """
        ).fetchone()
    finally:
        con.close()

    snapshot = load_manifest(EUETS_MANIFEST).latest
    provenance: dict = {
        "source": "EU ETS / EUTL via euets.info",
        "manifest": "sources/euets/manifest.yml",
        "note": (
            "scripts/verify_reproducibility.py proves this raw file -> mart. EU ETS "
            "verified emissions are the regulated Scope 1 figure; Scope 2 and Scope 3 "
            "are not in source scope and are omitted, never estimated."
        ),
    }
    if snapshot is None:
        provenance["release"] = None
        provenance["warning"] = "euets source is UNPINNED -- this export is not reproducible."
    else:
        provenance.update(
            release=snapshot.release,
            raw_sha256=snapshot.sha256,
            raw_storage_url=snapshot.storage_url,
            raw_row_count=snapshot.row_count,
            raw_periods_covered=snapshot.periods_covered,
        )

    meta = {
        "disclosure": {
            "standard": "ESRS E1 (Delegated Regulation (EU) 2023/2772)",
            "datapoint": "E1-6 - Gross Scope 1 greenhouse gas emissions",
            "generated_at": datetime.now(UTC).isoformat(),
            "generated_by": f"Cairn v{_cairn_version()}",
            "git_commit": _git_commit(),
            "dbt_mart": MART,
        },
        "coverage": {
            "row_count": summary[0],
            "installation_count": summary[1],
            "reporting_years": [summary[2], summary[3]],
            "total_scope_1_t_co2eq": summary[4],
            "registry": "NL",
            "trading_system": "euets",
            "unit": "t CO2eq",
        },
        "provenance": provenance,
        "integrity": {
            "csv_file": csv_path.name,
            "csv_sha256": _sha256(csv_path),
            "csv_row_count": summary[0],
        },
        "data_dictionary": DATA_DICTIONARY,
        "references": REFERENCES,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    readme_path.write_text(_render_readme(meta))
    return meta


def _render_readme(meta: dict) -> str:
    cov = meta["coverage"]
    prov = meta["provenance"]
    disc = meta["disclosure"]
    years = cov["reporting_years"]
    return f"""# ESRS E1 disclosure export

This bundle is a machine-readable **{disc["datapoint"]}** disclosure under
{disc["standard"]}, generated by {disc["generated_by"]} on
{disc["generated_at"]}.

## Files

- `esrs_e1_disclosure.csv` -- the data, one row per installation per reporting
  year (NL registry, EU ETS stationary installations).
- `esrs_e1_disclosure.meta.json` -- provenance, integrity hashes, and the full
  column data dictionary. **Read this to audit the figures.**
- `README.md` -- this file.

## What it contains

Verified EU ETS emissions provided as the verified basis for the ESRS E1-6
*gross Scope 1 GHG emissions* datapoint (in tonnes CO2-equivalent), with each
installation's NACE-section benchmark (count, mean, median, ratio) alongside
as context.

- Coverage: {cov["row_count"]} rows, {cov["installation_count"]} installations,
  reporting years {years[0]}-{years[1]}.
- **Scope 1 only.** ESRS E1-6 also requires Scope 2 and Scope 3; Cairn has no
  source for them, so they are omitted -- never filled with placeholder zeros.

## How to verify (audit trail)

1. **File integrity** -- recompute the CSV hash and compare to
   `integrity.csv_sha256` in the metadata:

   ```sh
   shasum -a 256 esrs_e1_disclosure.csv
   ```

2. **Source provenance** -- the figures trace to a pinned raw EU ETS release:
   `{prov.get("release")}` (raw SHA256 `{prov.get("raw_sha256", "UNPINNED")}`),
   recorded in `sources/euets/manifest.yml`. The weekly reproducibility job
   re-downloads that exact file and re-derives the mart.

3. **Methodology** -- the mapping and transform logic are pinned by the git
   commit `{disc["git_commit"]}` and reviewed via pull request.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the ESRS E1 disclosure bundle.")
    parser.add_argument(
        "--duckdb",
        default=str(REPO_ROOT / "cairn.duckdb"),
        help="Path to the built DuckDB warehouse (default: cairn.duckdb at repo root).",
    )
    parser.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "exports" / "esrs_e1"),
        help="Output directory for the bundle (default: exports/esrs_e1).",
    )
    args = parser.parse_args(argv)

    duckdb_path = Path(args.duckdb)
    if not duckdb_path.exists():
        print(
            f"warehouse not found: {duckdb_path}\nbuild it first (dbt build, or "
            "scripts/materialize_warehouse.py)",
            file=sys.stderr,
        )
        return 1

    meta = export(duckdb_path, Path(args.out_dir))
    cov = meta["coverage"]
    print(
        f"wrote {cov['row_count']} rows ({cov['installation_count']} installations, "
        f"{cov['reporting_years'][0]}-{cov['reporting_years'][1]}) to {args.out_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
