"""Build the committed CI fixtures for the EU ETS sources from local snapshots.

Reads full ingested snapshots (by default the ``--offline`` ``.localstack``
paths) and writes small, NL-focused parquet subsets under ``tests/fixtures/``,
so ``dbt build`` and the dbt tests run on representative data without network
or R2 credentials. Re-run after ingesting a refreshed snapshot and bump the
release dirs (see CLAUDE.md).

    uv run python scripts/build_eu_ets_fixtures.py

The euets subset keeps a spread of NL installations (stationary across NACE
sections, plus a few aircraft and maritime operators) and their compliance for
2019-2023; the NACE reference is trimmed to the ancestor-closure of the codes
used (so the section-letter walk still resolves) plus all section letters. The
EEA subset keeps NL verified-emission and allocation rows for 2018-2023. Every
table is written with ``ORDER BY ALL`` so the fixtures are byte-stable.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

EUETS_SRC = ".localstack/euets/eutl/2024-10"
EUETS_DST = "tests/fixtures/euets/2024-10"
EEA_SRC = ".localstack/eea/eu-ets/2005-2025_v01_r00"
EEA_DST = "tests/fixtures/eea/2005-2025_v01_r00"


def _copy(con: duckdb.DuckDBPyConnection, query: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    con.sql(f"COPY ({query} ORDER BY ALL) TO '{dest.as_posix()}' (FORMAT PARQUET)")
    n = con.sql(f"SELECT count(*) FROM read_parquet('{dest.as_posix()}')").fetchone()[0]
    print(f"  {dest}  ({n} rows)")


def build_euets(con: duckdb.DuckDBPyConnection, src: str, dst: str) -> None:
    print(f"euets: {src} -> {dst}")
    inst = f"read_parquet('{src}/installation.parquet')"
    comp = f"read_parquet('{src}/compliance.parquet')"
    nace = f"read_parquet('{src}/dim_nace.parquet')"

    # A deterministic spread of NL installations: one stationary installation
    # per NACE 2-digit division (so several sectors are represented, not just
    # the lowest codes), plus a few aircraft and maritime operators.
    con.sql(f"""
        CREATE TEMP TABLE chosen AS
        (SELECT * EXCLUDE (rn) FROM (
            SELECT *, row_number() OVER (PARTITION BY left(nace_id, 2) ORDER BY id) AS rn
            FROM {inst}
            WHERE registry_id = 'NL' AND isAircraftOperator = 'False'
              AND isMaritimeOperator = 'False' AND nace_id IS NOT NULL AND nace_id <> ''
         ) WHERE rn = 1 ORDER BY nace_id LIMIT 15)
        UNION ALL
        (SELECT * FROM {inst}
         WHERE registry_id = 'NL' AND isAircraftOperator = 'True' ORDER BY id LIMIT 3)
        UNION ALL
        (SELECT * FROM {inst}
         WHERE registry_id = 'NL' AND isMaritimeOperator = 'True' ORDER BY id LIMIT 3)
    """)

    dst_path = Path(dst)
    _copy(con, "SELECT * FROM chosen", dst_path / "installation.parquet")
    _copy(
        con,
        f"SELECT c.* FROM {comp} c JOIN chosen ON c.installation_id = chosen.id "
        f"WHERE TRY_CAST(c.year AS INTEGER) BETWEEN 2019 AND 2023",
        dst_path / "compliance.parquet",
    )
    # NACE reference trimmed to the ancestor-closure of the codes used + all
    # section letters, so the recursive section-letter walk still resolves.
    con.sql(f"""
        CREATE TEMP TABLE nace_keep AS
        WITH RECURSIVE used AS (
            SELECT DISTINCT nace_id AS id FROM chosen WHERE nace_id IS NOT NULL AND nace_id <> ''
        ),
        walk AS (
            SELECT n.id, n.parent_id FROM {nace} n JOIN used u ON n.id = u.id
            UNION
            SELECT n.id, n.parent_id FROM {nace} n JOIN walk w ON n.id = w.parent_id
        )
        SELECT id FROM walk
    """)
    _copy(
        con,
        f"SELECT * FROM {nace} WHERE id IN (SELECT id FROM nace_keep) OR level = '1'",
        dst_path / "dim_nace.parquet",
    )
    _copy(
        con,
        f"SELECT * FROM read_parquet('{src}/dim_activity_type.parquet') "
        f"WHERE id IN (SELECT DISTINCT activity_id FROM chosen)",
        dst_path / "dim_activity_type.parquet",
    )
    _copy(
        con,
        f"SELECT * FROM read_parquet('{src}/dim_country.parquet') WHERE id = 'NL'",
        dst_path / "dim_country.parquet",
    )
    con.sql("DROP TABLE chosen; DROP TABLE nace_keep")


def build_eea(con: duckdb.DuckDBPyConnection, src: str, dst: str) -> None:
    print(f"eea: {src} -> {dst}")
    data = f"read_parquet('{src}/data.parquet')"
    cats = (
        "'2. Verified emissions', '2.1 EU-ETS Verified Emission', "
        "'1. Total allocated allowances (EUA or EUAA)'"
    )
    # NL rows 2018-2023 are the coverage-test denominator. We deliberately also
    # keep two real-source quirks so the staging tests stay meaningful:
    #   * NL trading-period aggregate rows (non-numeric year) -> exercises the
    #     period-row filter in stg_eea__ets.
    #   * CZ allocated-allowances at the 20-99 aggregate, which the source
    #     duplicates (a spurious 0 alongside the real value) -> exercises the
    #     deduplication. CZ is outside the NL coverage sum, so it is numerically
    #     inert there.
    _copy(
        con,
        f"SELECT * FROM {data} WHERE citl_information IN ({cats}) AND ("
        f"(country_code = 'NL' AND (TRY_CAST(year AS INTEGER) BETWEEN 2018 AND 2023 "
        f"OR TRY_CAST(year AS INTEGER) IS NULL)) "
        f"OR (country_code = 'CZ' AND main_activity_code = '20-99'))",
        Path(dst) / "data.parquet",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build EU ETS CI fixtures from local snapshots.")
    parser.add_argument("--euets-src", default=EUETS_SRC)
    parser.add_argument("--eea-src", default=EEA_SRC)
    args = parser.parse_args(argv)

    con = duckdb.connect()
    build_euets(con, args.euets_src, EUETS_DST)
    build_eea(con, args.eea_src, EEA_DST)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
