# Long-haul electric truck scheduling

Scheduling along prescribed routes, coordinating charging, driver breaks and daily rests. The repository contains full- and partial-recharge labeling algorithms, a greedy baseline, a driver-inspired heuristic, and the experiments and analyses used in the manuscript.

## Repository layout

| Directory | Contents |
|---|---|
| `manuscript/` | Manuscript PDF; editable manuscript sources were not present in the inherited checkout |
| `instances/benchmark_v1/` | Authoritative inherited benchmark: 45 instances, 227 files |
| `instances/generator/` | Main clustered-route generator |
| `legacy/instances/alternative_generator_output/` | Differing generator data; shared files are referenced through `instances/catalog.csv` |
| `policies/labeling/` | Separate full- and partial-recharge implementations |
| `policies/heuristics/` | Greedy and driver-inspired policies |
| `common/` | Shared input loading, paths, and analysis metrics |
| `experiments/` | Local execution, explicit JSON configurations, exports, provenance, and cluster execution |
| `analysis/` | Base-case, sensitivity, heuristic comparison, instance visualization, and paper tables |
| `output/runs/` | Canonical results and metadata, one folder per run |
| `output/analyses/` | Derived figures, tables, and reports |
| `tests/` | Dataset integrity, orchestration, policy tests, and pre-migration fixtures |
| `docs/` | Methods, migration record, and research decisions still to resolve |
| `legacy/` | Retained older scripts and historical artifacts; not supported entry points |

Run commands from the repository root, using Python 3.10 or newer. Install with:

```sh
python -m pip install -e .
```

This project is intended for an editable source checkout: inputs and output directories live alongside the Python packages.

## Run an experiment

Start with one short instance across all methods (five EV schedules):

```sh
python -m experiments.run --preset paper_base --instances short_cl1_cu2 --no_diesel
```

Results go to `output/runs/paper_base_<timestamp>/`. Each run contains `manifest.json`, canonical `results.jsonl` with complete timelines/decisions, and a generated flat summary at `exports/results.csv`, which can be opened in Excel. No Excel workbook is generated automatically.

```sh
python -m experiments.run --preset paper_base --algorithms driver_heuristic
python -m experiments.run --preset parameter_sweep --algorithms partial_labeling,full_labeling
python -m experiments.run --preset driver_sync_sweep --algorithms driver_heuristic --no_diesel
python -m experiments.run --preset station_spacing --algorithms full_labeling --no_diesel
```

`--preset` is required. `paper_base` preserves the existing code's 750 kWh / 60 km / 350 kW / 1.49 kWh/km settings. `legacy_base` preserves the old default experiment; `base` is its compatibility alias. `full` aliases `parameter_sweep`. These names do not resolve the manuscript's different base values: see [open research decisions](docs/research_decisions.md).

The diesel reference uses existing methods with the inherited large-battery configuration. Algorithm identity and the driver's `full`/`overlap` charging policy remain distinct result fields.

## Reproduce the inherited paper analyses

`analysis/configs/paper_inputs.json` pins exact saved inputs. It does not select the newest file. By default, new figures and tables are written under `output/analyses/paper_reproduction/`; inherited assets remain under `output/analyses/imported/`.

```sh
python -m analysis.base_case
python -m analysis.sensitivity
python -m analysis.heuristic_comparison
python -m analysis.instance_visualization
python -m analysis.paper_tables
python -m analysis.diagnostic_tables
```

Set `EV_TRUCK_ANALYSIS_INPUTS` to another JSON input manifest and `EV_TRUCK_ANALYSIS_OUTPUT` to another output directory to analyze a different selection. Input paths are relative to the repository root (or absolute). The analysis readers accept both inherited CSV/JSON bundles and new canonical `results.jsonl` files. Point the relevant manifest entries directly to JSONL to analyze new runs without copying results. A combined JSONL may serve multiple roles: readers select the relevant algorithms. The flat `exports/results.csv` omits timelines and should be used for summaries, not synchronization analysis. For base-case analyses, provide a run at the documented `paper_base` settings; sensitivity readers apply the inherited study filters.

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
python -m tests.verify_run output/runs/paper_base_<timestamp>
```

The last command checks the five-scenario short-instance run above against pre-migration results, excluding execution-time/profiling fields. The driver tests replay both policies on all 45 instances.

Imported results and figures are preserved for traceability. New runs, generated analyses, and temporary reconstructions are ignored by Git by default; explicitly promote selected research artifacts when needed. Do not copy result files into the analysis source directory.

See [migration notes](docs/migration.md) and the machine-readable [original-file manifest](docs/migration_manifest.json) for provenance and retained historical files.
