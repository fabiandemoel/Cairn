For a NEW data source, the research brief above (generated before this run
by an isolated web-research step) is your ONLY window on the live source -
you have no web access. Treat its verified facts as authoritative and
anything it marks UNVERIFIED as a hypothesis the committed fixture and
unit test must not silently depend on. If the brief is missing or lacks a
fact you genuinely cannot proceed without, hand `legwork` ONE narrowly
scoped fetch (an explicit curl via Bash, not open-ended exploration); if
that fails too, open a draft PR explaining the blocker - but WITHOUT
`sources/<source>/manifest.yml` in it: that file arms the per-source
register guards in tests/test_source_wiring.py, so a scaffold-only draft
that ships it can never go green. Revert the scaffolded files (`git rm` /
restore) so the draft carries only the blocker description, with CI
passing. Do NOT run the real `--offline` ingest as a check - it downloads
the full dataset and writes a machine-specific `file://` snapshot into the
manifest that you would then have to detect and reset. Rely on the unit test
against the committed fixture; the manifest ships `snapshots: []`.
