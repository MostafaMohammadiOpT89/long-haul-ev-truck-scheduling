# Repository migration

The initial inventory covered 2,426 files, excluding Git internals, caches, local IDE settings and logs. `migration_manifest.json` records every inventoried original path, destination, original SHA-256, byte count, and action. 876 exact duplicate copies were consolidated. Non-code assets are preserved byte-for-byte at their recorded destinations; active Python sources were then updated for imports and paths.

## Decisions

- Root, full-recharge, partial-recharge and visualization copies of the 227 benchmark files are consolidated under `instances/benchmark_v1`.
- The generator dataset is represented by `instances/catalog.csv` plus its differing files. Shared content refers to the benchmark instead of being copied again. `python -m instances.materialize` reconstructs either complete dataset.
- Shared arc and CSV reader implementations now live under `common/`. Full and partial labeling retain separate network, label, feasibility and dominance implementations. Imports are fully qualified so both variants can coexist safely.
- Current local and cluster entry points use the same benchmark and experiment configurations. Subprocesses remain to isolate algorithm global state. The inherited computational runtime limits are preserved.
- New results have one canonical JSONL store; flat CSV is a derived export. Completed scenarios are saved incrementally, and failure metadata is retained.
- Analysis inputs are pinned explicitly. Imported result bytes, figures and tables remain historical snapshots. Paths embedded in their contents describe the original environment and are intentionally preserved; the migration manifest resolves original file locations.
- Older `main.py`, debugging/batch runners, old test drivers, mapping tools and differing greedy code are retained under `legacy/code/`. These may contain obsolete paths and are not supported runnable commands. The Git history and manifest preserve their origins. Archived text excerpts retain removed standalone orchestration without another full copy of each policy.
- Existing result JSON/CSV representations were preserved. Semantically overlapping historical bundles were not deleted merely because one might contain a subset of another.
- No commit, push, or remote repository update is part of this migration.

## Local state

The checkout initially had a deleted `Synchronization_TRSC (6).pdf` and an untracked `SupportingDocuments/main_manuscript.pdf`. The deleted file was not restored. The available manuscript was moved to `manuscript/main_manuscript.pdf`. Original IDE settings and ignored local artifacts are retained separately from supported research inputs.

## Validation scope

Tests cover catalog checksums and reconstruction, historical non-code asset preservation, simultaneous solver imports, local/cluster scenario parity, driver rules and all-instance schedule validation, and before/after five-policy comparison on `short_cl1_cu2`. Paper analysis commands and the cluster worker/merge path are checked locally. Actual Solstorm SSH dispatch requires access to that cluster and is not implied by local checks.

Remaining scientific choices are listed in `research_decisions.md`.

## Verification results

- Five methods on `short_cl1_cu2` match pre-migration schedules and scientific metrics exactly (full labeling, partial labeling, greedy, driver full, driver overlap). Only timing/profiling and runner metadata are excluded.
- All 15 existing driver test functions pass, including both policies on all 45 instances.
- Base-case, heuristic, sensitivity, paper-table, diagnostic-table and instance-visualization commands completed locally.
- Cluster jobs were generated, executed locally and merged successfully. SSH dispatch itself was not run.
