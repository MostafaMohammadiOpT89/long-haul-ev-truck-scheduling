# Results for analysis

Start with `output/runs/summary.csv`. Each row describes one instance,
vehicle/scenario parameterization, and policy parameterization. The readable
`model_run_id` joins to one line in `output/runs/details.jsonl`.

All 45 stored instances are included for every observed joint parameter/policy
setting, plus five electric policy variants at the confirmed paper base. Those
five placeholders use partial labeling, full labeling, greedy (0.1 safety
buffer), and driver full/overlap (1-hour synchronization horizon); heuristic
settings are provisional defaults. This is not a cross-product of arbitrary
individual parameter values. `record_status=no_record_available` means that
outcomes are blank and the details have no observations, not that a run failed
or the instance is infeasible. Planned base rows have a separate input-version
label and do not assert that historical inputs match today's files.

No instances have been excluded pending colleague confirmation. Membership
flags describe the appendix and saved base case independently. See
[benchmark_membership.md](benchmark_membership.md) for the unresolved problem.

The summary contains battery capacity, charging power, station spacing, energy
consumption, policy name, charging policy, synchronization horizon and safety
buffer in separate columns. It includes makespan, reported feasibility, runtime,
stop counts, synchronization metrics, and the availability of a route schedule.
Blank values mean unavailable or inapplicable, never zero.

The confirmed paper base is **500 kWh, 350 kW, 50 km, 1.49 kWh/km**.
`matches_confirmed_paper_base` identifies matching electric configurations.
Older 750 kWh / 60 km results are retained with their actual values.

## Route plans and repeated executions

Each details record contains `configuration`, `selected_observation_id`, and
`observations`. Every observation retains the original result object under
`result`, including `activity_timeline`, driver `decision_log` when supplied,
all other fields, and its source identifier and source-row number.

An instance/configuration can have several executions. They occupy one summary
row, with every execution preserved in the details. The displayed summary uses
the latest recorded source timestamp, with a documented deterministic tie-break.
This is a display choice, not scientific validation. `observation_count`,
`result_conflict`, and the minimum/maximum observed makespan expose disagreement;
do not use a conflicting configuration without choosing the appropriate source.
Different schedules with the same makespan are retained, not treated as proof
of inconsistent optimal values. Historical inputs and code versions are not
verified; identical recorded parameters do not establish identical input files.

`termination_status=unknown` does not mean optimal. A failed search does not by
itself prove infeasibility. The interval-valued partial-charging timelines are
preserved as recorded; they have not been converted to a unique realized schedule.
Nonfinite numbers, if any, are losslessly represented by tagged objects in JSON.

Example:

```python
import json
import pandas as pd
summary = pd.read_csv('output/runs/summary.csv')
subset = summary.query("policy == 'partial_labeling' and vehicle_type == 'electric'")
with open('output/runs/details.jsonl', encoding='utf-8') as stream:
    record = next(r for line in stream if (r := json.loads(line))['observations'])
selected = next(o for o in record['observations']
                if o['observation_id'] == record['selected_observation_id'])
timeline = selected['result'].get('activity_timeline', [])
```

## Sources and rebuilding

`catalog.json` records source paths, hashes, row counts, selection rules and
output hashes. `experiments/configs/result_sources.json` selects the principal
base, sensitivity, driver and station-spacing archives. Their CSV mirrors and
individual-policy copies are not imported a second time. Older experimental
snapshots and diagnostic summaries are archived under `legacy/results/raw_runs/imported/`;
they are not silently mixed into the active research catalog.

Rebuild with `python -m experiments.consolidate`. This reads results only and
does not run scheduling algorithms. Rebuild explicitly after modifying the
source list or completing an experiment batch. Local and cluster runners write
new batches under `output/executions/`; the importer discovers their
`results.jsonl` files. Migration validation runs are archived under
`legacy/results/raw_runs/` and excluded from the research catalog.

Current Section 5.1 outputs are in `analysis/conditions/figures/` and
`analysis/conditions/tables/`. Charging-strategy and scheduling-rule outputs
likewise live beside their code. Historical plots and earlier reproduction
outputs are archived under `legacy/results/analyses/`. Original artifacts are retained for recovery and
provenance. The two consolidated files are the main entry point for inspecting
coverage. Active figure and table scripts now read `details.jsonl`, selecting
their original source cohorts through `analysis/configs/paper_inputs.json`.
Each selection explicitly names a source and, where needed, an algorithm.
This preserves historical comparisons without including missing placeholders
or accidentally mixing repeated executions. Analysis manifests record both
the consolidated file hash and the cohort selection. The legacy utilities in
`analysis/historical/` are retained as historical code, not active entry points.
