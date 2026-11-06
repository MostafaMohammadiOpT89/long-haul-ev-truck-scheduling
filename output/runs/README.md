# Consolidated experiment results

- `summary.csv`: the 43 paper instances at the base and one-at-a-time electric
  settings, plus diesel references. Other policies at these settings are retained.
  Filter `record_status` before analyzing outcomes; missing records are not infeasible.
- `summary_all.csv`: the complete unfiltered summary, including historical settings
  outside the paper scope and the two excluded instances.
- `one_at_a_time_coverage.csv`: available and missing partial-charging counts for
  each of the ten required electric configurations.
- `missing_partial_runs.csv`: the exact missing instance/configuration pairs.
- `details.jsonl`: the full observation archive, linked by `model_run_id` from
  either summary. Placeholder rows have empty observation lists.
- `catalog.json`: source hashes, counts and export provenance.

Paper instance set: 43 tests in `instances/PAPER_INSTANCE_SET_43.txt`. The stored generator pool has 45 folders.

Confirmed base: **750 kWh, 350 kW, 60 km, 1.49 kWh/km**. Vary only one parameter:
battery 350/500/1000 kWh; charging power 1000 kW; spacing 40/80/100 km; consumption
1.12/2.08 kWh/km. No factorial crossings are included in `summary.csv`.

The old run folders are in `legacy/results/raw_runs/`. New experiment batches
go to `output/executions/`. Rebuild these files with
`python -m experiments.consolidate`; this does not execute optimization.

Analysis source selections are in `analysis/configs/paper_inputs.json`. They
read source cohorts from `details.jsonl`, not the archived input files, so
historical comparisons retain their original settings and observations.

Rebuilding preserves this scope; it does not restore factorial combinations to
`summary.csv`. Complete source observations remain in `details.jsonl`, so pinned
historical analyses continue to work.

See `docs/result_files.md` for the schema and `docs/benchmark_membership.md`
for the confirmed 43-instance selection.
