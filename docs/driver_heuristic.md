# Driver-inspired sequential heuristic

A fifth algorithm variant next to the existing ones. It is kept in **separate files** so that every
run can be traced independently of the labeling algorithms and the greedy scheduler.

| Variant | What it is | Where it lives |
|---|---|---|
| Partial recharge (labeling) | Exact SPPRC labeling; charging amount is a decision | `policies/labeling/partial_recharge/` |
| Full recharge (labeling) | Exact SPPRC labeling; each charge restores battery to full | `policies/labeling/full_recharge/` |
| Greedy heuristic | Sequential baseline scheduler (myopic HoS + energy) | `policies/heuristics/greedy.py` |
| **Driver heuristic** | Sequential driver-inspired rules; two charging policies (`full`, `overlap`) | `policies/heuristics/driver.py` |
| Diesel proxy | Labeling / heuristics with a very large battery (`diesel_lb` tag) | same runners |

Runner modes: `partial_labeling`, `full_labeling`, `greedy`, `driver_heuristic` (+ `diesel_lb` tagged runs).

## Files

| File | Purpose |
|---|---|
| `policies/heuristics/driver.py` | Heuristic (rules 1-4, both policies), result class with the same sync metrics as the other variants (`docs/metrics.md`), an independent schedule validator, and a stand-alone batch `main()` |
| `policies/heuristics/driver_runner.py` | One-scenario child process printing one JSON (used by `experiments/run.py` and `experiments/cluster/run_job.py`) |
| `tests/test_driver_heuristic.py` | Unit tests for CS placement, each rule, both policies, validator, and all instances at the base configuration |
| `analysis/heuristic_comparison.py` | New figures/tables comparing the heuristic with Full, Partial, Greedy and the diesel proxy |
| `Post_Analysis/analysis_output_driverHeuristic/` | Output figures (`D01`..`D06`) and tables (`table_D00`..`table_D06`) |
| `output/analyses/imported/Post_Analysis_Report_DriverHeuristic.md` | Generated summary report |

The input structure is unchanged: the same `instances/<name>/<name>.txt` files, the same
`_DistanceMatrix.csv` / `_TimeMatrix.csv` (master matrices as fallback), the same CS placement as
`network.py` (one CS at the midpoint if the arc is at most one spacing long, otherwise every
`distance_per_cs` km), the same HoS constants, and the same service-time treatment as the labeling
model (service counts as elapsed time, not as driving time).

## The rules (as implemented)

1. **Drive as far as possible.** At a CS the vehicle passes by when its SOC reaches the next CS (or the
   destination), unless rule 2 applies.
2. **Synchronise upcoming interruptions.** At a CS, if the time until a break / daily rest becomes
   mandatory is below `t_sync`, the interruption is taken here, combined with charging. Daily rest
   is preferred. Default `t_sync = distance_per_cs / 60 km/h` (1 h at the base case): the
   interruption is taken here whenever the next CS cannot be reached before it binds.
3. **Necessary charging is combined with an interruption.** If the SOC does not reach the next CS, the
   vehicle charges here, with a daily rest if one is due within `t_sync`, otherwise with a break.
4. **Unavoidable interruptions on the road.** If a limit binds between stops the break / rest is taken
   there (no charging).

Charging policies: `full` charges to capacity at every charging stop; `overlap` charges only during
the concurrent break / rest and extends charging only when needed to reach the next CS.

Two feasibility guards are documented in the module docstring (a break that would leave no daily
elapsed window becomes a daily rest; a break-synchronised charge whose extra charging time would
exceed the daily elapsed window is upgraded to a daily rest). Both are counted in
`num_guard_break_to_rest`.

## Tracing a run

Every result row carries a `decision_log` (JSON) and the batch run also writes
`Results/Driver_Heuristic_Results/driver_heuristic_trace_<timestamp>.txt` with one line per decision:

```
  at CS_Origin_Cust1_3: need_next=89.4kWh must_charge=False time_to_break=0.50h time_to_rest=5.00h | t=4.000h soc=392.4kWh ...
    rule2_sync: break at CS, target SOC 750.0 kWh (full)
    -> break 0.75h + charge 357.6kWh in 1.02h (extra beyond break: 0.27h) | t=5.022h ...
```

Every schedule is replayed by `validate_schedule()`; the result columns `schedule_valid` /
`validation_errors` report whether the HoS and battery limits hold.

## Running

Use the common experiment interface from the repository root:

```sh
python -m experiments.run --preset paper_base --algorithms driver_heuristic
python -m experiments.run --preset driver_sync_sweep --algorithms driver_heuristic --no_diesel
python -m tests.test_driver_heuristic
python -m analysis.heuristic_comparison
```

Configurations live in `experiments/configs/`. Each run stores complete decision logs in
`output/runs/<run_id>/results.jsonl`. Analysis reads explicitly selected files in
`analysis/configs/paper_inputs.json` and writes under `output/analyses/`.

Result columns (CSV/JSON): `policy`, `t_sync_hours`, `total_time`, `num_charges`, `num_breaks`,
`num_rests`, `num_synchronized_events`, `num_unsynchronized_*`, `total_idle_charging_time_minutes`,
`percentage_of_charging_events_synchronized`, `total_charging_time_minutes`,
`total_energy_charged_kWh`, `final_soc_kWh`, rule counters (`num_rule2_sync_stops`,
`num_rule3_forced_charges`, `num_rule4_road_interruptions`, `num_customer_interruptions`,
`num_cs_passed`, `num_guard_break_to_rest`), `feasible`, `schedule_valid`, `computation_time`,
`activity_timeline` (charge events overlap their break / rest in time, so the overlap-based sync
metrics of `docs/metrics.md` apply directly).
