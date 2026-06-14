"""Export the benchmark mart from a built DuckDB file to a parquet.

Used by CI to snapshot the mart for the benchmark diff.

    uv run python scripts/export_mart.py <duckdb_path> <out_parquet>
"""

from __future__ import annotations

import sys

import duckdb

MART = "main.benchmark_sector_emissions"


def export_mart(duckdb_path: str, out_parquet: str) -> None:
    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        con.execute(
            f"COPY (SELECT * FROM {MART} ORDER BY year, nace_section) TO ? (FORMAT PARQUET)",
            [out_parquet],
        )
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("usage: export_mart.py <duckdb_path> <out_parquet>", file=sys.stderr)
        return 2
    export_mart(args[0], args[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
