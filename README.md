# Long-haul electric truck scheduling

Scheduling along prescribed routes, coordinating charging, driver breaks and daily rests. The repository contains full- and partial-recharge labeling algorithms, a driver-inspired heuristic, and the experiments and analyses used in the manuscript.

## Repository layout

| Directory | Contents |
|---|---|
| `manuscript/` | Current manuscript PDF and local LaTeX sources |
| `instances/benchmark_v1/` | Generated instance folders (45). Paper set is 43; see `instances/PAPER_INSTANCE_SET_43.txt` |
| `instances/generator/` | Main clustered-route generator |
| `legacy/instances/alternative_generator_output/` | Differing generator data; shared files are referenced through `instances/catalog.csv` |
| `policies/labeling/` | Separate full- and partial-recharge implementations |
| `policies/heuristics/` | Driver-inspired heuristic |
| `common/` | Shared input loading, paths, and analysis metrics |
| `experiments/` | Local execution, explicit JSON configurations, exports, provenance, and cluster execution |
| `analysis/` | Current base-case and sensitivity figures/tables, plus instance visualization |
| `output/runs/` | Consolidated summary CSV, detailed JSONL and provenance catalog |
| `output/executions/` | Raw records, metadata and jobs for new experiment batches |
| `legacy/results/raw_runs/` | Archived inherited results and validation batches |
| `analysis/<question>/figures/`, `tables/` | Generated outputs beside the corresponding analysis code |
| `tests/` | Dataset integrity, orchestration, policy tests, and pre-migration fixtures |
| `docs/` | Methods, migration record, and research decisions still to resolve |
| `legacy/` | Archived raw results and alternate datasets; superseded plotting code/outputs removed |

Run commands from the repository root, using Python 3.10 or newer. Install with:

```sh
python -m pip install -e .
```

This project is intended for an editable source checkout: inputs and output directories live alongside the Python packages.

## Paper computational archive

`reviewer_results/` retains the raw paper comparison on 43 instances: Full recharge, Partial recharge, Driver heuristic (full-charge and overlap-only), and the diesel proxy. These results are included in `output/runs/`; current figures and tables are generated under `analysis/conditions/`.

## Run an experiment

Start with one short instance across the paper methods (Full, Partial, Driver_FC, Driver_OO):

```sh
python -m experiments.run --preset paper_base --instances short_cl1_cu2 --no_diesel
```

New batches go to `output/executions/paper_base_<timestamp>/`. Each contains `manifest.json`, raw `results.jsonl` with complete timelines/decisions, and `exports/results.csv`. After a batch completes, run `python -m experiments.consolidate` to refresh `output/runs/summary.csv`, `details.jsonl`, and `catalog.json`. Active analyses read explicit source cohorts from the consolidated details file; see [result files](docs/result_files.md). No Excel workbook is generated automatically.

```sh
python -m experiments.run --preset paper_base --algorithms driver_heuristic
python -m experiments.run --preset parameter_sweep --algorithms partial_labeling,full_labeling
python -m experiments.run --preset driver_sync_sweep --algorithms driver_heuristic --no_diesel
python -m experiments.run --preset station_spacing --algorithms full_labeling --no_diesel
```

`--preset` is required. `paper_base` uses the confirmed 750 kWh / 60 km / 350 kW / 1.49 kWh/km settings. `legacy_base` preserves the old default experiment; `base` is its compatibility alias. `full` aliases `parameter_sweep`.

The diesel reference uses existing methods with the inherited large-battery configuration. Algorithm identity and the driver's `full`/`overlap` charging policy remain distinct result fields.

## Generate the current paper figures

The current generator reads the scoped `output/runs/summary.csv` and selected schedules in `details.jsonl`. It writes descriptively named base, sensitivity, and operational PDF/PNG panels, supporting tables, and an Overleaf bundle. See [analysis layout](analysis/README.md).

```sh
python -m analysis.conditions.run
python -m analysis.conditions.audit
python -m analysis.instance_visualization
```

Set `EV_TRUCK_ANALYSIS_OUTPUT` to redirect generated outputs. The figures use the confirmed 750 kWh / 60 km base, 43 paper instances, and fixed matched cohorts for one-at-a-time sensitivities. The four sensitivity bar charts share a vertical scale. Common loaders still support explicitly selected observations through `analysis/configs/paper_inputs.json` for schedule-level investigation. Superseded scripts and generated outputs were removed; their checksums and recovery archive are recorded in `docs/analysis_cleanup.json`.

## Datasets and generation

`instances/catalog.csv` records dataset version, logical filename, stored path, and SHA-256. The generator variant differs in 147 files and must not be substituted for the benchmark silently. Reconstruct it when needed:

```sh
python -m instances.materialize legacy_generator_variant output/reconstructed_legacy_generator_variant
python -m instances.generator grid --seed 42 --add-unbalanced-variant --out output/generated_instances
```

The materializer requires a new destination directory and verifies all source hashes before copying. The main generator follows the mapped benchmark design and now uses seeded randomness throughout. New generated datasets are not exact historical reproductions. For the original mapped instances, use `benchmark_v1`. See [generator provenance](docs/generator_provenance.md) for the comparison and archived alternative.

## Cluster execution

```sh
python -m experiments.cluster.create_jobs --preset paper_base --algorithms driver_heuristic --runid my_run
bash experiments/cluster/run_all.sh -j my_run -r 4 -n 1,2,3,4
python -m experiments.cluster.merge_results --runid my_run
```

Or use `python -m experiments.cluster.run_pipeline --preset paper_base`. Cluster execution requires the existing Solstorm SSH/shared-filesystem setup. Jobs are stored under the same run directory as the results. Creating jobs refuses an existing run ID.

## Verification

```sh
python -m unittest tests.test_repository
python -m tests.test_driver_heuristic
python -m tests.verify_run output/executions/paper_base_<timestamp>
```

The last command checks a short-instance paper-base run against pre-migration results, excluding execution-time/profiling fields. The driver tests replay both policies on the stored instances.

Imported results and figures are preserved for traceability. New runs, generated analyses, and temporary reconstructions are ignored by Git by default; explicitly promote selected research artifacts when needed. Do not copy result files into the analysis source directory.

See [migration notes](docs/migration.md) and the machine-readable [original-file manifest](docs/migration_manifest.json) for provenance and retained historical files.
