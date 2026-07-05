"""Tests for the cbs_namea air_emissions ingestion pipeline.

No network access: all tests use an in-memory DuckDB shaped like the dlt load
(the entity-set tables plus the ``_dlt_*`` bookkeeping columns) so CI runs
offline. Exercises the Modified-date release parsing, the parquet export
(column faithfulness, _dlt column stripping, determinism), period detection,
and the idempotency short-circuit that prevents duplicate manifest entries.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from ingestion import cbs_namea_pipeline as ep
from ingestion.manifest import Manifest, Snapshot, compute_sha256, save_manifest

RAW = "cbs_namea_raw"


def _load_fake_dlt_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Create the entity-set tables the way dlt loads them (snake_case + _dlt_*)."""
    con.sql(f"CREATE SCHEMA {RAW}")
    con.sql(
        f"""
        CREATE TABLE {RAW}.observations AS
        SELECT * FROM (VALUES
            (1, 'A044109_2', NULL, 180789.0, NULL, 'B000579', '1990JJ00', 'l1', 'r1'),
            (0, 'A044109_2', NULL, 200123.0, NULL, 'B000579', '2024JJ00', 'l1', 'r0')
        ) AS t(id, measure, value_attribute, value, string_value,
               nederlandse_economie, perioden, _dlt_load_id, _dlt_id)
        """
    )
    con.sql(
        f"""
        CREATE TABLE {RAW}.periodencodes AS
        SELECT * FROM (VALUES
            ('2024JJ00', 1, '2024', 'l1', 'r1'),
            ('1990JJ00', 0, '1990', 'l1', 'r0')
        ) AS t(identifier, index, title, _dlt_load_id, _dlt_id)
        """
    )
    for table in ("nederlandseeconomiecodes", "measurecodes"):
        con.sql(
            f"""
            CREATE TABLE {RAW}.{table} AS
            SELECT * FROM (VALUES
                ('X1', 0, 'label', 'l1', 'r0')
            ) AS t(identifier, index, title, _dlt_load_id, _dlt_id)
            """
        )


# --- release parsing ----------------------------------------------------------


def test_release_from_properties_iso_with_tz() -> None:
    props = {"Modified": "2025-11-12T02:00:00+01:00"}
    assert ep._release_from_properties(props) == "2025-11-12"


def test_release_from_properties_plain_date() -> None:
    assert ep._release_from_properties({"Modified": "2025-11-12"}) == "2025-11-12"


def test_release_from_properties_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        ep._release_from_properties({"Modified": "November 2025"})


# --- exports register ----------------------------------------------------------


def test_exports_hash_target_is_observations() -> None:
    # data.parquet (the hashed raw artifact) must be the Observations export.
    assert ep.EXPORTS["Observations"] == ep.PRIMARY


def test_exports_cover_all_dimension_code_sets() -> None:
    # 83300NED's dimensions: sector (NederlandseEconomie), period, measure.
    assert {"NederlandseEconomieCodes", "PeriodenCodes", "MeasureCodes"} <= set(ep.EXPORTS)


# --- parquet export ------------------------------------------------------------


def test_export_parquets_strips_dlt_columns(tmp_path: Path) -> None:
    con = duckdb.connect()
    _load_fake_dlt_tables(con)
    ep._export_parquets(con, RAW, tmp_path)
    dest = tmp_path / ep.PRIMARY
    cols = [
        c[0]
        for c in duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{dest.as_posix()}')").fetchall()
    ]
    # Source columns survive verbatim; dlt bookkeeping columns do not.
    assert "measure" in cols
    assert "nederlandse_economie" in cols
    assert "perioden" in cols
    assert "value" in cols
    assert "_dlt_load_id" not in cols
    assert "_dlt_id" not in cols


def test_export_parquets_writes_every_export(tmp_path: Path) -> None:
    con = duckdb.connect()
    _load_fake_dlt_tables(con)
    ep._export_parquets(con, RAW, tmp_path)
    for filename in ep.EXPORTS.values():
        assert (tmp_path / filename).is_file(), f"missing export {filename}"


def test_export_parquets_is_deterministic(tmp_path: Path) -> None:
    # Two identical loads -> byte-identical data.parquet (rows ordered by id).
    hashes = []
    for sub in ("a", "b"):
        con = duckdb.connect()
        _load_fake_dlt_tables(con)
        out = tmp_path / sub
        ep._export_parquets(con, RAW, out)
        hashes.append(compute_sha256(out / ep.PRIMARY))
    assert hashes[0] == hashes[1]


# --- derived metadata ----------------------------------------------------------


def test_periods_covered() -> None:
    con = duckdb.connect()
    _load_fake_dlt_tables(con)
    assert ep._periods_covered(con, RAW) == ["1990", "2024"]


def test_row_count(tmp_path: Path) -> None:
    con = duckdb.connect()
    _load_fake_dlt_tables(con)
    ep._export_parquets(con, RAW, tmp_path)
    assert ep._row_count(tmp_path / ep.PRIMARY) == 2


# --- idempotency short-circuit -------------------------------------------------


def test_run_skips_when_release_already_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = "2025-11-12"
    manifest_path = tmp_path / "manifest.yml"
    save_manifest(
        manifest_path,
        Manifest(
            source=ep.SOURCE,
            dataset=ep.DATASET,
            snapshots=[
                Snapshot(
                    release=release,
                    ingested_at="2025-11-13T00:00:00Z",
                    storage_url="file:///tmp/data.parquet",
                    sha256="a" * 64,
                    row_count=1,
                    periods_covered=["1990", "2024"],
                )
            ],
        ),
    )
    monkeypatch.setattr(ep, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(
        ep,
        "fetch_properties",
        lambda table: {"Modified": f"{release}T02:00:00+01:00", "Title": "NAMEA (test)"},
    )

    class _NoPipeline:
        def __getattr__(self, name: str) -> object:
            raise AssertionError("dlt must not be touched for an already-pinned release")

    monkeypatch.setattr(ep, "dlt", _NoPipeline())

    assert ep.run(offline=True) == 0
