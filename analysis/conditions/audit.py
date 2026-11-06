"""Audit the requested one-at-a-time settings against summary.csv; no solvers.

Run from the repository root: python -m analysis.conditions.audit
The updated manuscript Table 5 specifies the 750 kWh / 60 km base.
Factorial crossings and battery/power interactions are outside the scope.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from experiments.paper_scope import BASE, PARAMETERS, configurations

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "output/runs/summary.csv"
MEMBERS = ROOT / "instances/PAPER_INSTANCE_SET_43.txt"
COLS = list(PARAMETERS)


def main():
    ids = MEMBERS.read_text().splitlines()
    assert len(ids) == len(set(ids)) == 43
    data = pd.read_csv(SOURCE)
    data = data[data.instance_id.isin(ids)].copy()
    ev = data[data.policy.eq("partial_labeling") & data.vehicle_type.eq("electric")]
    assert not ev.duplicated(["instance_id"] + COLS).any()
    recorded = ev[ev.record_status.eq("record_available")]
    assert recorded.makespan_hours.notna().all()
    assert not recorded.result_conflict.any()
    entries = []
    for values in configurations():
        mask = np.logical_and.reduce([ev[c].eq(v) for c, v in zip(COLS, values)])
        rows = ev[mask]
        present = set(rows.loc[rows.record_status.eq("record_available"), "instance_id"])
        placeholders = set(rows.loc[rows.record_status.eq("no_record_available"), "instance_id"])
        missing = sorted(set(ids) - present)
        entries.append({
            **dict(zip(COLS, values)),
            "expected": 43, "recorded": len(present), "missing": len(missing),
            "available_instances": sorted(present), "missing_instances": missing,
            "placeholder_instances": sorted(placeholders),
            "instances_without_any_row": sorted(set(ids) - set(rows.instance_id)),
        })
    diesel = data[data.vehicle_type.eq("diesel_proxy") &
                  data.policy.eq("partial_labeling") &
                  data.record_status.eq("record_available")]
    refs = diesel[diesel.battery_kwh.eq(1e10)]
    assert refs.instance_id.nunique() == len(refs) == 43
    overlap = diesel[diesel.battery_kwh.eq(1e8)].merge(refs, on="instance_id")
    assert np.allclose(overlap.makespan_hours_x, overlap.makespan_hours_y,
                       rtol=0, atol=1e-7)
    assert len(entries) == 10
    result = {
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "membership_sha256": hashlib.sha256(MEMBERS.read_bytes()).hexdigest(),
        "paper_instances": ids, "base": dict(zip(COLS, BASE)),
        "interpretation": "Base plus nine one-at-a-time sensitivities only; "
                          "750 kWh, 350 kW, 60 km, 1.49 kWh/km base. All other "
                          "parameters held at base. No factorial crossings.",
        "required_configurations": len(entries),
        "expected_results": 43 * len(entries),
        "recorded_results": sum(e["recorded"] for e in entries),
        "missing_results": sum(e["missing"] for e in entries),
        "diesel_reference_instances": sorted(refs.instance_id),
        "diesel_reference_ids": sorted(refs.model_run_id),
        "diesel_missing_instances": sorted(set(ids) - set(refs.instance_id)),
        "diesel_note": "Existing references use battery 1e10 kWh, power 350 kW, "
                       "spacing 60 km and consumption 1.49 kWh/km, matching the "
                       "user-corrected base spacing. Reuse across new inputs is not "
                       "validated by this availability audit.",
        "limitations": ["Missing results are not classified as infeasible.",
                        "Recorded results have unknown termination status.",
                        "Recorded parameter equality does not verify input/code versions."],
        "configurations": entries,
    }
    target = Path(__file__).parent / "tables" / "coverage.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    compact = pd.DataFrame(entries).drop(columns=["available_instances", "missing_instances",
                                                "placeholder_instances", "instances_without_any_row"])
    print(compact[compact.recorded.gt(0)].to_string(index=False))
    print(json.dumps({k: v for k, v in result.items() if k.endswith("results") or
                      k.endswith("configurations") and not isinstance(v, list)}, indent=2))
    print("Saved", target)


if __name__ == "__main__":
    main()
