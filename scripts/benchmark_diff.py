"""Compare two benchmark mart outputs and emit a markdown diff.

Takes two parquet exports of ``benchmark_sector_emissions`` (e.g. the ``main``
build vs a PR build, both from the same fixture), joins on sector + year, and
prints a markdown table: sector | year | old | new | Δ%. Rows are sorted by
absolute Δ% descending; the top 20 are shown and anything above 10% is flagged
with a warning emoji. CI posts this as a PR comment so the methodology impact
of a change is visible at review time.

    uv run python scripts/benchmark_diff.py OLD.parquet NEW.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

VALUE_COLUMN = "sector_emissions_mt_co2eq"
WARN_THRESHOLD_PCT = 10.0
TOP_N = 20


def _load(con: duckdb.DuckDBPyConnection, name: str, path: str) -> None:
    con.execute(
        f"create temp table {name} as "
        f"select nace_section, year, {VALUE_COLUMN} as value "
        f"from read_parquet(?)",
        [path],
    )


def compute_diff(old_path: str, new_path: str) -> list[tuple]:
    """Return joined rows: (sector, year, old, new, abs_delta_pct, delta_pct)."""
    con = duckdb.connect()
    _load(con, "old_m", old_path)
    _load(con, "new_m", new_path)
    # full outer join so appearing/disappearing sector-years are visible too
    return con.sql(
        """
        with joined as (
            select
                coalesce(o.nace_section, n.nace_section) as nace_section,
                coalesce(o.year, n.year) as year,
                o.value as old_value,
                n.value as new_value
            from old_m o
            full outer join new_m n
                on o.nace_section = n.nace_section and o.year = n.year
        )
        select
            nace_section,
            year,
            old_value,
            new_value,
            case
                when old_value is null or new_value is null then null
                when old_value = 0 then null
                else 100.0 * (new_value - old_value) / old_value
            end as delta_pct
        from joined
        order by case when delta_pct is null then 1 else 0 end,
                 abs(delta_pct) desc nulls last,
                 nace_section, year
        """
    ).fetchall()


def _fmt(value) -> str:
    return "—" if value is None else f"{value:.1f}"


def render_markdown(rows: list[tuple]) -> str:
    shown = rows[:TOP_N]
    lines = [
        "### Benchmark diff: `benchmark_sector_emissions`",
        "",
        f"Sector emissions (Mt CO2-eq), old vs new. Top {TOP_N} by |Δ%|; "
        f"⚠️ flags |Δ%| > {WARN_THRESHOLD_PCT:.0f}%.",
        "",
        "| Sector | Year | Old | New | Δ% |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    if not shown:
        lines.append("| _(no rows)_ | | | | |")
    for nace_section, year, old_value, new_value, delta_pct in shown:
        if delta_pct is None:
            kind = "new" if old_value is None else "removed"
            delta_cell = f"_{kind}_"
        else:
            warn = " ⚠️" if abs(delta_pct) > WARN_THRESHOLD_PCT else ""
            delta_cell = f"{delta_pct:+.1f}%{warn}"
        lines.append(
            f"| {nace_section} | {year} | {_fmt(old_value)} | {_fmt(new_value)} | {delta_cell} |"
        )

    flagged = sum(1 for r in rows if r[4] is not None and abs(r[4]) > WARN_THRESHOLD_PCT)
    new_or_removed = sum(1 for r in rows if r[4] is None)
    lines += [
        "",
        f"_{len(rows)} sector-years compared · {flagged} above {WARN_THRESHOLD_PCT:.0f}% "
        f"· {new_or_removed} appeared/disappeared._",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Markdown diff of two benchmark marts.")
    parser.add_argument("old", help="Path to the OLD mart parquet (e.g. main build).")
    parser.add_argument("new", help="Path to the NEW mart parquet (e.g. PR build).")
    parser.add_argument("--output", "-o", help="Write markdown here instead of stdout.")
    args = parser.parse_args(argv)

    rows = compute_diff(args.old, args.new)
    markdown = render_markdown(rows)
    if args.output:
        Path(args.output).write_text(markdown + "\n", encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
