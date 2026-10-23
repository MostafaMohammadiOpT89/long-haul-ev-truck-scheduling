# Analysis code and outputs

Run commands from the repository root. Each research question keeps its code,
figures and tables together:

```text
analysis/
    conditions/                 # 5.1: electric versus diesel
        run.py
        figures/                # PDF exports and PNG previews
        tables/                 # CSV data and LaTeX summary
        audit.json
    charging_strategies/        # 5.2: partial versus full charging
        run.py
        paper_tables.py
        diagnostic_tables.py
        figures/
        tables/
        sensitivity/            # inherited broader sensitivity analysis
            run.py
            figures/
            tables/
    scheduling_rules/           # 5.3: heuristics versus optimization
        run.py
        figures/
        tables/
    common/                     # shared input selection and provenance
    configs/                    # explicit cohorts from consolidated results
```

```sh
python -m analysis.conditions.run
python -m analysis.charging_strategies.run
python -m analysis.charging_strategies.paper_tables
python -m analysis.charging_strategies.diagnostic_tables
python -m analysis.charging_strategies.sensitivity.run
python -m analysis.scheduling_rules.run
```

`conditions` is the current Section 5.1 draft. The broader inherited sensitivity
analysis remains available under `charging_strategies/sensitivity`; its
electric/diesel comparisons still require scientific review. Moving code has
not reconciled experimental settings or changed the selected cohorts.

Upload selected figure and table exports directly to Overleaf. Scripts no longer
write into the local manuscript directory. Existing manuscript assets are left
as a historical snapshot, and are not maintained by these commands.

The consolidated experiment data stay in `output/runs/`. Older analysis outputs
are archived in `legacy/results/analyses/`; they are not inputs to the active
analyses. `analysis/historical/` retains older code for reference.

`EV_TRUCK_ANALYSIS_OUTPUT` optionally redirects the output root (default:
`analysis/`), retaining the same question-based subfolders. Source code is never
overwritten by a regeneration. `EV_TRUCK_ANALYSIS_INPUTS` selects an alternative
input manifest. Instance-map generation remains available through
`python -m analysis.instance_visualization` and writes into
`analysis/instance_visualization/` by default.
