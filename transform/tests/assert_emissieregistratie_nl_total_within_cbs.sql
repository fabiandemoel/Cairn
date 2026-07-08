-- Singular test: every reconciled year in mart_emissieregistratie_cbs_reconciliation
-- must stay within 10% relative deviation.
--
-- Tolerance: Emissieregistratie's CRF Summary1 is the literal UNFCCC national
-- inventory submission that Eurostat's env_air_gge itself derives from (see
-- stg_eurostat__gge.sql's methodology note and the emissieregistratie
-- ingestion pipeline's module docstring: "the natural cross-check target for
-- CBS's national total"). assert_gge_nl_total_within_cbs already reconciles
-- that same submission chain against CBS at a 10% tolerance (observed gap
-- ~7% for NL 2024: CBS 144.4 Mt vs GGE 154.2 Mt) -- this test adopts the
-- same tolerance and reasoning: CBS revises its estimate more often than the
-- annual UNFCCC submission cycle, so a multi-percent gap is expected and not
-- a data-quality problem.
--
-- As of this PR the committed CI fixture
-- (tests/fixtures/emissieregistratie/crf_summary1/2026-V1.0/) is a minimal
-- excerpt (see stg_emissieregistratie__crf_summary1's fixture) that does not
-- include the "Total National Emissions and Removals" row, so this test
-- compiles to zero rows against it -- a vacuous pass, not a hidden failure.
-- It starts exercising real values once a fuller snapshot is ingested.
--
-- Returns zero rows on success (no reconciled year violates the tolerance).

select
    year,
    emissieregistratie_total_mt_co2eq,
    cbs_total_mt_co2eq,
    relative_deviation
from {{ ref('mart_emissieregistratie_cbs_reconciliation') }}
where relative_deviation >= 0.10
