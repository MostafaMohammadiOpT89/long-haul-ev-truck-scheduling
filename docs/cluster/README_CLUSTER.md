> Historical cluster reference. Current commands and output paths are documented in [the repository README](../../README.md#cluster-execution).

### Cluster workflow (Solstorm via SSH)

This folder provides a FOMO-style cluster distribution workflow for the **TDSPEVRP unified framework**.
It is **self-contained** and does **not** depend on `FOMOsim-main` (you can delete that folder later).

## Overview

- **`create_jobs.py`**: generates one JSON job per scenario (instance × algorithm × parameter-combination).
- **`run_all.sh`**: selects/reserves compute nodes and distributes jobs over SSH.
- **`run_job.py`**: runs jobs on each compute node and appends results safely to shared output files.
- **`merge_results.py`**: converts cluster outputs into combined + per-algorithm JSON/CSV bundles.

All scripts assume you run them from the repository root on Solstorm, e.g.:
`/storage/users/$USER/TDSPEVRP/Code_AllScenarios`

## 0) One-time setup on Solstorm (example)

- Load Python module in your `.bashrc` (example):
  - `module load Python/3.10.4-GCCcore-11.3.0`
- Install required packages for this project (same as your normal local requirements).

## 1) Create jobs

Create a job JSON file for each scenario:

```bash
python3 cluster/create_jobs.py --preset base
```

Or the full grid:

```bash
python3 cluster/create_jobs.py --preset full
```

Jobs are written to `cluster/jobs/<timestamp>/job_XXXXXX.json`.

## One-command pipeline (recommended)

Instead of running 3 separate commands, you can run the entire pipeline with **one python command**:

```bash
python3 cluster/run_pipeline.py --preset base -r 4 -n 1,2,3,4
```

Auto node selection:

```bash
python3 cluster/run_pipeline.py --preset full
```

After it finishes, merged outputs are in:
`Results/Cluster/merged/<runid>/`

## 2) Run distributed over nodes

Manual node selection (row + node numbers), like FOMO:

```bash
./cluster/run_all.sh -r 4 -n 1,2,3,4
```

Automatic node selection using `gstat` (load-based):

```bash
./cluster/run_all.sh
```

The dispatcher reserves nodes using lockdirs under:
`/storage/users/$USER/tdspevrp_node_locks/`

Results are appended to:
`Results/Cluster/output_<runid>.jsonl` and `Results/Cluster/output_<runid>.csv`

## 3) Merge results

After the run finishes:

```bash
python3 cluster/merge_results.py --runid <runid>
```

This creates:
- `Results/Cluster/merged/<runid>/unified_results_<runid>.json/.csv`
- per-algorithm bundles (partial/full/greedy) + diesel-only bundle

