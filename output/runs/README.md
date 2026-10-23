# Consolidated experiment results

- `summary.csv`: one row per instance, policy and parameter setting. Filter
  `record_status` before analyzing outcomes; missing records are not infeasible.
- `details.jsonl`: linked by `model_run_id`, with original observations and
  available route schedules. Placeholder rows have empty observation lists.
- `catalog.json`: source hashes, counts and export provenance.

All 45 stored instances remain included pending benchmark confirmation.

The old run folders are in `legacy/results/raw_runs/`. New experiment batches
go to `output/executions/`. Rebuild these files with
`python -m experiments.consolidate`; this does not execute optimization.

Analysis source selections are in `analysis/configs/paper_inputs.json`. They
read source cohorts from `details.jsonl`, not the archived input files, so
historical comparisons retain their original settings and observations.

See `docs/result_files.md` for the schema and `docs/benchmark_membership.md`
for the unresolved instance selection.
