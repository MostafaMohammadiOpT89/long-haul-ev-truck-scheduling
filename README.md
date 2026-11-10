# Long-haul electric truck scheduling

Scheduling along prescribed routes, coordinating charging, driver breaks and daily rests. The repository contains full- and partial-recharge labeling algorithms, a driver-inspired heuristic, and the experiments and analyses used in the manuscript.

## Repository layout

| Directory | Contents |
|---|---|
| `manuscript/` | Manuscript PDF; editable manuscript sources were not present in the inherited checkout |
| `instances/benchmark_v1/` | Generated instance folders (45). Paper set is 43; see `instances/PAPER_INSTANCE_SET_43.txt` |
| `instances/generator/` | Main clustered-route generator |
| `legacy/instances/alternative_generator_output/` | Differing generator data; shared files are referenced through `instances/catalog.csv` |
| `policies/labeling/` | Separate full- and partial-recharge implementations |
| `policies/heuristics/` | Driver-inspired heuristic |
| `common/` | Shared input loading, paths, and analysis metrics |
| `experiments/` | Local execution, explicit JSON configurations, exports, provenance, and cluster execution |
| `analysis/` | Base-case, sensitivity, heuristic comparison, instance visualization, and paper tables |
| `output/runs/` | Consolidated summary CSV, detailed JSONL and provenance catalog |
| `output/executions/` | Raw records, metadata and jobs for new experiment batches |
| `legacy/results/raw_runs/` | Archived inherited results and validation batches |
| `analysis/<question>/figures/`, `tables/` | Generated outputs beside the corresponding analysis code |
| `tests/` | Dataset integrity, orchestration, policy tests, and pre-migration fixtures |
| `docs/` | Methods, migration record, and research decisions still to resolve |
| `legacy/` | Retained older scripts and historical artifacts; not supported entry points |

Run commands from the repository root, using Python 3.10 or newer. Install with:

```sh
python -m pip install -e .
```

This project is intended for an editable source checkout: inputs and output directories live alongside the Python packages.

## Paper computational archive

`reviewer_results/` is the locked paper comparison on 43 instances: Full recharge, Partial recharge, Driver heuristic (full-charge and overlap-only), and the diesel proxy. Use that folder for manuscript numbers.

## Main runner (recommended)

`main_runner.py` at the repository root controls the grid, the policies and every policy setting in one place. Edit `CONFIG` at the top of the file, or save it as JSON (`python main_runner.py --write_config my.json`) and pass `--config my.json`.

```sh
python main_runner.py --count         # jobs per experiment and policy, and how many are still to run
python main_runner.py --max_jobs 2    # smoke test
python main_runner.py                 # mode "local": runs now; mode "cluster": writes job files and prints the cluster commands
```

Settings per policy:

| Setting | Policies | Meaning |
|---|---|---|
| `rest_charge_sync` | Full, Partial, Driver | `true`: charging during the 11 h daily rest at a station is free. `false`: the rest comes first, then the full charging time, which counts toward the next day's working window. Break-synchronized charging is unchanged. A list sweeps both. |
| `cs_service_time_h` | Full, Partial | Fixed hours per charging-station visit besides charging. Paper setting: `0.0`. |
| `variants`, `t_sync_h` | Driver | `full` / `overlap` charging and the synchronization horizon (`null` = spacing / speed). |
| `solver_time_limit_min` | Full, Partial | Labeling search limit. Rows that hit it have `timed_out = true`. |
| `job_timeout_min` | all | Hard kill of one solver process. Must exceed the solver limit. |

The solvers have no defaults of their own for these settings: a missing setting stops the solver. Every result row stores its settings (`job_*` columns), and the runner checks that the solver reported back the same values. Failed, timed-out or mismatched jobs are written as rows with `job_status` other than `ok`, and the batch continues. Running the same `run_id` again skips jobs that are already `ok`; a changed config needs a new `run_id`. `results_final.jsonl` and `exports/results.csv` keep one final row per job. Hours-of-service rules for all policies are in `common/hos.py`.

On the cluster, set `"mode": "cluster"` and run `main_runner.py`, then the printed `run_all.sh` and `merge_results` commands. `run_all.sh -w N` runs N jobs in parallel per node; `-t` limits one node's whole batch. If a node stops early, run `main_runner.py` again with the same `run_id` and resend: only unfinished jobs are written.

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

`--preset` is required. `paper_base` preserves the existing code's 750 kWh / 60 km / 350 kW / 1.49 kWh/km settings. `legacy_base` preserves the old default experiment; `base` is its compatibility alias. `full` aliases `parameter_sweep`. These names do not resolve the manuscript's different base values: see [open research decisions](docs/research_decisions.md).

The diesel reference uses existing methods with the inherited large-battery configuration. Algorithm identity and the driver's `full`/`overlap` charging policy remain distinct result fields.

## Reproduce the inherited paper analyses

`analysis/configs/paper_inputs.json` pins exact saved inputs. It does not select the newest file. Each analysis writes figures and tables into its own folder under `analysis/`. Previous outputs are archived in `legacy/results/analyses/`. See [analysis layout](analysis/README.md).

```sh
python -m analysis.conditions.run
python -m analysis.charging_strategies.run
python -m analysis.charging_strategies.sensitivity.run
python -m analysis.scheduling_rules.run
python -m analysis.instance_visualization
python -m analysis.charging_strategies.paper_tables
python -m analysis.charging_strategies.diagnostic_tables
```

Set `EV_TRUCK_ANALYSIS_INPUTS` to another JSON input manifest and `EV_TRUCK_ANALYSIS_OUTPUT` to another output directory to analyze a different selection. Default entries specify `path`, `source_id`, and optionally `algorithm`, selecting observations from consolidated `details.jsonl`. Analysis manifests record these selections and the input hash. Plain paths to raw CSV/JSON/JSONL remain supported for custom inputs; a consolidated details file requires a source selection. The flat batch export omits timelines and should be used for summaries, not synchronization analysis. Existing analyses retain the inherited 750 kWh / 60 km filters; the confirmed 500 kWh / 50 km paper base still awaits results.

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
