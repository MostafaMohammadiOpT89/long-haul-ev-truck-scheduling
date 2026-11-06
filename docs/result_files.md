# Results for analysis

Start with `output/runs/summary.csv`. Each row describes one instance,
vehicle/scenario parameterization, and policy parameterization. The readable
`model_run_id` joins to one line in `output/runs/details.jsonl`.
The summary is restricted to the 43 paper instances, the base and nine
one-at-a-time electric sensitivities, and diesel references. Other policies at
these settings remain available. `summary_all.csv` preserves the complete
unfiltered catalog, and `details.jsonl` retains all source observations.
`one_at_a_time_coverage.csv` reports partial-charging coverage per setting;
`missing_partial_runs.csv` lists the exact missing runs.

The paper comparison uses 43 instances (`instances/PAPER_INSTANCE_SET_43.txt`).
The stored generator pool has 45 folders; `short_cl2_cu2_Balanced` and
`short_cl2_cu2_Unbalanced` are not in the paper. `record_status=no_record_available`
means outcomes are blank, not that a run failed or the instance is infeasible.

Paper methods: partial labeling, full labeling, driver heuristic (full / overlap).
See [benchmark_membership.md](benchmark_membership.md).

The summary contains battery capacity, charging power, station spacing, energy
consumption, policy name, charging policy, synchronization horizon and safety
buffer in separate columns. It includes makespan, reported feasibility, runtime,
stop counts, synchronization metrics, and the availability of a route schedule.
Blank values mean unavailable or inapplicable, never zero.

The confirmed paper base is **750 kWh, 350 kW, 60 km, 1.49 kWh/km**.
`matches_confirmed_paper_base` identifies matching electric configurations.
One-at-a-time levels are battery 350/500/1000 kWh, power 1000 kW, spacing
40/80/100 km, and consumption 1.12/2.08 kWh/km, with all other values fixed
at base. The 750 kWh / 60 km results now match the revised manuscript base.
Scope is defined in `experiments/paper_scope.py` and
is reapplied on every rebuild.

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
`analysis/conditions/tables/`. The single current generator reads the scoped
summary, validates diesel pairing and records source hashes and matched
cohorts in `analysis/conditions/audit.json`. All panels use descriptive
names; all four sensitivity bar charts use a shared vertical scale.
`analysis/conditions/conditions.zip` contains the Overleaf-ready exports.
The operational figures also read selected base-case schedules from the details
file. `operations_audit.json` records the paired observations, reconciled duration
components, and charging reconstruction conventions. Numeric exports are
`tables/penalty_parts.csv`, `tables/charging_events.csv`, and
`tables/charge_split.csv`. The saved charge activity duration is additional
elapsed time; physical charging time is reconstructed from charged energy and
power, placing rest-synchronized charging at the end of the rest for display.
This is one valid placement within the window, not an observed unique timestamp.
Superseded analysis code and derived outputs
were removed at the user's request; see `docs/analysis_cleanup.json` for the
checksums and recovery archive. Raw experimental records are preserved.
