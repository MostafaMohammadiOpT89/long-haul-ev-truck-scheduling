#!/usr/bin/env python3
"""
Unified single-thread experiment runner for TDSPEVRP (Partial + Full + Greedy + Diesel/LB).

Goal: keep algorithm logic unchanged; this runner only orchestrates parameter grids and
collects results in one place, using subprocesses to avoid module-name collisions between
"Partial Recharge" and "Full Recharge" codebases.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union


ROOT_DIR = Path(__file__).resolve().parent
PARTIAL_DIR = ROOT_DIR / "Partial Recharge" / "EVTDSPalgorithmmain"
FULL_DIR = ROOT_DIR / "Full Recharge" / "EVTDSPalgorithmmain"

PARTIAL_SINGLE_SCENARIO = PARTIAL_DIR / "single_scenario_runner.py"
FULL_SINGLE_SCENARIO = FULL_DIR / "single_scenario_runner.py"


# =========================
# Central configuration (single source of truth)
# =========================
#
# The unified runner is where we define parameter grids, exactly like enhanced_main.py:
# - Full grid: used for sensitivity / param sweep
# - Base-case: the single scenario used for baseline comparisons
#
# The single-scenario runners DO NOT have their own grids; they only execute what we pass in.

# Full-grid configuration (as requested)
# charging_powers: either a single list (same kW options for every battery_cap) or a dict
#   mapping battery_cap -> list of charging powers (kW).
FULL_GRID = {
    "consumption_rates": [1.12, 1.49, 2.08],
    "distances_per_cs": [40, 60, 80, 100],
    "battery_caps": [750, 1000],
    "charging_powers": {
        750: [350, 500, 1000],
        1000: [350, 500, 1000],
    },
    "safety_buffer_fracs": [0.10, 0.20, 0.30],
}

# Base-case configuration: edit lists/dict to match the experiments you want.
# Optional "grid_by_battery": { battery_cap: { "consumption_rates": [...], "distances_per_cs": [...], "charging_powers": [...] } }
# lets you use different cons/dcs/cp lists for specific batteries (Cartesian product inside each block).
BASE_CASE = {
    "consumption_rates": [2.08],
    "distances_per_cs": [100],
    "battery_caps": [500.0, 10_000_000_000.0],
    "charging_powers": {
        500.0: [150.0, 75.0],
        10_000_000_000.0: [150.0],
    },
    "safety_buffer_fracs": [0.10],
    "grid_by_battery": {
        10_000_000_000.0: {
            "consumption_rates": [2.08],
            "distances_per_cs": [100],
            "charging_powers": [150.0],
        },
    },
}

# Default preset (can be overridden by CLI: --preset base|full)
DEFAULT_PRESET = "base"

# Instances filter: [] = run all discovered instances.
# Names must match instance folder names (e.g., 'short_cl1_cu2').
# SPECIFIC_INSTANCES_TO_RUN: List[str] = [
#     # Edit this list to run only these instances (folder names under each `instances/` directory)
#     "short_cl1_cu2",
#     "short_cl2_cu3_Balanced",
# ]
SPECIFIC_INSTANCES_TO_RUN: List[str] = []

# Diesel / lower-bound: use the BASE CASE scenario but with huge battery → no recharging needed.
RUN_DIESEL_LOWER_BOUND = True
DIESEL_BATTERY_CAP = 100_000_000  # as requested
# For diesel greedy, set buffer to 0 so buffer doesn't force any charging.
DIESEL_SAFETY_BUFFER_FRAC = 0.0


def _float_key_match(bc: float, key: Any) -> bool:
    try:
        return abs(float(key) - float(bc)) < 1e-9
    except (TypeError, ValueError):
        return False


def _subgrid_for_battery(bc_f: float, grid_by_battery: Dict[Any, Any]) -> Optional[Dict[str, Any]]:
    if not grid_by_battery:
        return None
    for k, v in grid_by_battery.items():
        if _float_key_match(bc_f, k):
            return v
    return None


def _charging_powers_for_battery(
    bc_f: float,
    preset: Dict[str, Any],
    sub: Optional[Dict[str, Any]],
) -> List[float]:
    """Resolve the list of charging powers (kW) for this battery capacity."""
    if sub is not None and "charging_powers" in sub:
        v = sub["charging_powers"]
        if isinstance(v, dict):
            raise ValueError(
                "grid_by_battery[...]['charging_powers'] must be a list of kW, not a nested dict."
            )
        return [float(x) for x in v]

    raw = preset["charging_powers"]
    if isinstance(raw, (list, tuple)):
        return [float(x) for x in raw]
    if isinstance(raw, dict):
        for k, v in raw.items():
            if _float_key_match(bc_f, k):
                return [float(x) for x in v]
        raise KeyError(
            f"preset['charging_powers'] has no entry for battery_cap={bc_f}. "
            f"Keys present: {list(raw.keys())}"
        )
    raise TypeError(f"charging_powers must be list or dict, got {type(raw)}")


def iter_preset_parameter_combinations(preset: Dict[str, Any]) -> Iterator[Tuple[float, float, float, float]]:
    """
    Yield (consumption, distance_per_cs, battery_cap, charging_power) for the Cartesian grid
    defined by the preset (including optional grid_by_battery overrides per battery).
    """
    grid_by_battery: Dict[Any, Any] = preset.get("grid_by_battery") or {}
    for bc in preset["battery_caps"]:
        bc_f = float(bc)
        sub = _subgrid_for_battery(bc_f, grid_by_battery)
        cons_rates = (
            list(sub["consumption_rates"])
            if (sub is not None and "consumption_rates" in sub)
            else list(preset["consumption_rates"])
        )
        dcs_vals = (
            list(sub["distances_per_cs"])
            if (sub is not None and "distances_per_cs" in sub)
            else list(preset["distances_per_cs"])
        )
        cp_list = _charging_powers_for_battery(bc_f, preset, sub)
        for cons in cons_rates:
            for dcs in dcs_vals:
                for cp in cp_list:
                    yield (float(cons), float(dcs), bc_f, float(cp))


def diesel_anchor_params() -> Tuple[float, float, float]:
    """
    (consumption, distance_per_cs, charging_power) for diesel/LB runs: first tuple from BASE_CASE
    enumeration, with battery replaced by DIESEL_BATTERY_CAP in the scenario builder.
    """
    first = next(iter(iter_preset_parameter_combinations(BASE_CASE)), None)
    if first is None:
        raise ValueError("BASE_CASE produces no parameter combinations (check battery_caps / charging_powers).")
    cons0, dcs0, _bc, cp0 = first
    return cons0, dcs0, cp0


def preset_snapshot_for_json(preset: Dict[str, Any]) -> Dict[str, Any]:
    """JSON-safe view of a preset (dict keys as strings where needed)."""
    cp = preset["charging_powers"]
    cp_out: Union[List[float], Dict[str, List[float]]]
    if isinstance(cp, dict):
        cp_out = {str(k): [float(x) for x in v] for k, v in cp.items()}
    else:
        cp_out = [float(x) for x in cp]

    gbb = preset.get("grid_by_battery")
    gbb_out: Optional[Dict[str, Any]] = None
    if gbb:
        gbb_out = {}
        for k, block in gbb.items():
            entry = dict(block)
            if "charging_powers" in entry and isinstance(entry["charging_powers"], (list, tuple)):
                entry["charging_powers"] = [float(x) for x in entry["charging_powers"]]
            gbb_out[str(k)] = entry

    snap = {
        "consumption_rates": [float(x) for x in preset["consumption_rates"]],
        "distances_per_cs": [float(x) for x in preset["distances_per_cs"]],
        "battery_caps": [float(x) for x in preset["battery_caps"]],
        "charging_powers": cp_out,
        "safety_buffer_fracs": [float(x) for x in preset["safety_buffer_fracs"]],
    }
    if gbb_out is not None:
        snap["grid_by_battery"] = gbb_out
    return snap


@dataclass(frozen=True)
class Scenario:
    algorithm: str  # "partial_labeling" | "full_labeling" | "greedy"
    instance_name: str
    instance_path: Path
    consumption: float
    distance_per_cs: float
    battery_cap: float
    charging_power: float
    safety_buffer_frac: Optional[float] = None  # greedy only
    tag: Optional[str] = None  # e.g. "diesel_lb"


def _discover_instances(instances_root: Path) -> List[Tuple[str, Path]]:
    """Discover instance folders under an 'instances' directory (same logic as enhanced_main.py)."""
    discovered: List[Tuple[str, Path]] = []
    if not instances_root.exists():
        return discovered

    for entry in sorted([p for p in instances_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        txt_candidates = [p for p in entry.iterdir() if p.is_file() and p.suffix.lower() == ".txt"]
        if not txt_candidates:
            continue
        preferred = entry / f"{entry.name}.txt"
        instance_txt = preferred if preferred.exists() else txt_candidates[0]
        discovered.append((entry.name, instance_txt))

    # Optional: allow loose .txt files directly under root
    for loose in sorted([p for p in instances_root.iterdir() if p.is_file() and p.suffix.lower() == ".txt"], key=lambda p: p.name.lower()):
        discovered.append((loose.stem, loose))

    # De-dup by instance name (keep first)
    seen = set()
    out: List[Tuple[str, Path]] = []
    for name, path in discovered:
        if name in seen:
            continue
        seen.add(name)
        out.append((name, path))
    return out


def _filter_instances(instances: List[Tuple[str, Path]]) -> List[Tuple[str, Path]]:
    if not SPECIFIC_INSTANCES_TO_RUN:
        return instances
    wanted = set(SPECIFIC_INSTANCES_TO_RUN)
    return [(n, p) for n, p in instances if n in wanted]


def _run_child(script_path: Path, cwd: Path, args: List[str]) -> Dict[str, Any]:
    """Run a child scenario runner and parse its single JSON output."""
    cmd = [sys.executable, str(script_path)] + args
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Child runner failed (rc={proc.returncode}).\n"
            f"cmd: {cmd}\n"
            f"cwd: {cwd}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n"
        )

    # Child prints ONLY one JSON object on stdout.
    try:
        return json.loads(proc.stdout.strip())
    except Exception as e:
        raise RuntimeError(
            f"Failed to parse child JSON output.\n"
            f"cmd: {cmd}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n"
            f"error: {e}"
        )


def _build_scenarios(
    partial_instances: List[Tuple[str, Path]],
    full_instances: List[Tuple[str, Path]],
    preset: Dict[str, Any],
) -> List[Scenario]:
    full_map = {name: path for name, path in full_instances}
    safety_fracs = [float(x) for x in preset["safety_buffer_fracs"]]
    cons0, dcs0, cp0 = diesel_anchor_params()

    scenarios: List[Scenario] = []
    for instance_name, partial_path in partial_instances:
        full_path = full_map.get(instance_name)
        if full_path is None:
            # Skip instances not present in both versions (keeps comparisons aligned)
            continue

        for cons, dcs, bc, cp in iter_preset_parameter_combinations(preset):
            scenarios.append(
                Scenario(
                    algorithm="partial_labeling",
                    instance_name=instance_name,
                    instance_path=partial_path,
                    consumption=cons,
                    distance_per_cs=dcs,
                    battery_cap=bc,
                    charging_power=cp,
                )
            )
            scenarios.append(
                Scenario(
                    algorithm="full_labeling",
                    instance_name=instance_name,
                    instance_path=full_path,
                    consumption=cons,
                    distance_per_cs=dcs,
                    battery_cap=bc,
                    charging_power=cp,
                )
            )
            for sb in safety_fracs:
                scenarios.append(
                    Scenario(
                        algorithm="greedy",
                        instance_name=instance_name,
                        instance_path=partial_path,
                        consumption=cons,
                        distance_per_cs=dcs,
                        battery_cap=bc,
                        charging_power=cp,
                        safety_buffer_frac=sb,
                    )
                )

        if RUN_DIESEL_LOWER_BOUND:
            scenarios.append(
                Scenario(
                    algorithm="partial_labeling",
                    instance_name=instance_name,
                    instance_path=partial_path,
                    consumption=cons0,
                    distance_per_cs=dcs0,
                    battery_cap=DIESEL_BATTERY_CAP,
                    charging_power=cp0,
                    tag="diesel_lb",
                )
            )
            scenarios.append(
                Scenario(
                    algorithm="greedy",
                    instance_name=instance_name,
                    instance_path=partial_path,
                    consumption=cons0,
                    distance_per_cs=dcs0,
                    battery_cap=DIESEL_BATTERY_CAP,
                    charging_power=cp0,
                    safety_buffer_frac=DIESEL_SAFETY_BUFFER_FRAC,
                    tag="diesel_lb",
                )
            )

    return scenarios


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def _save_bundle(results_dir: Path, stem: str, payload: Dict[str, Any], rows: List[Dict[str, Any]]) -> Tuple[Path, Path]:
    """Save JSON + CSV together, returning (json_path, csv_path)."""
    json_out = results_dir / f"{stem}.json"
    csv_out = results_dir / f"{stem}.csv"
    _write_json(json_out, payload)
    _write_csv(csv_out, rows)
    return json_out, csv_out


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Unified single-thread experiment runner (partial/full/greedy + diesel LB).")
    parser.add_argument(
        "--preset",
        choices=["base", "full"],
        default=DEFAULT_PRESET,
        help="Select parameter preset: 'base' runs the base-case only, 'full' runs the full parameter grid.",
    )
    parser.add_argument(
        "--instances",
        default="",
        help="Comma-separated instance names to run (overrides SPECIFIC_INSTANCES_TO_RUN in this file). Empty = all discovered.",
    )
    parser.add_argument(
        "--max_scenarios",
        type=int,
        default=0,
        help="Optional cap: run only the first N scenarios (0 = no cap).",
    )
    parser.add_argument(
        "--no_diesel",
        action="store_true",
        help="Disable diesel / lower-bound runs (huge battery case).",
    )
    cli_args = parser.parse_args()

    global SPECIFIC_INSTANCES_TO_RUN, RUN_DIESEL_LOWER_BOUND
    if cli_args.instances.strip():
        SPECIFIC_INSTANCES_TO_RUN = [s.strip() for s in cli_args.instances.split(",") if s.strip()]
    if cli_args.no_diesel:
        RUN_DIESEL_LOWER_BOUND = False

    preset = BASE_CASE if cli_args.preset == "base" else FULL_GRID

    # Sanity checks
    if not PARTIAL_SINGLE_SCENARIO.exists():
        raise FileNotFoundError(f"Missing: {PARTIAL_SINGLE_SCENARIO}")
    if not FULL_SINGLE_SCENARIO.exists():
        raise FileNotFoundError(f"Missing: {FULL_SINGLE_SCENARIO}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Discover instances (use each directory’s local instances folder)
    partial_instances = _filter_instances(_discover_instances(PARTIAL_DIR / "instances"))
    full_instances = _filter_instances(_discover_instances(FULL_DIR / "instances"))
    if not partial_instances:
        print(f"No instances found under: {PARTIAL_DIR / 'instances'}")
        return 1
    if not full_instances:
        print(f"No instances found under: {FULL_DIR / 'instances'}")
        return 1

    scenarios = _build_scenarios(partial_instances, full_instances, preset)
    if not scenarios:
        print("No scenarios to run (maybe instance intersection is empty).")
        return 1
    if cli_args.max_scenarios and cli_args.max_scenarios > 0:
        scenarios = scenarios[: cli_args.max_scenarios]

    results_dir = ROOT_DIR / "Results" / "Unified_Experiment_Runner"
    _ensure_dir(results_dir)

    all_rows: List[Dict[str, Any]] = []

    print(f"Unified runner starting. Scenarios: {len(scenarios)}. Timestamp: {timestamp}")
    print(f"Results dir: {results_dir}")
    print(f"Instances (partial discovered): {len(partial_instances)}")
    print(f"Preset: {cli_args.preset}")

    for idx, sc in enumerate(scenarios, 1):
        if sc.algorithm == "partial_labeling":
            child = PARTIAL_SINGLE_SCENARIO
            cwd = PARTIAL_DIR
            mode = "labeling"
        elif sc.algorithm == "full_labeling":
            child = FULL_SINGLE_SCENARIO
            cwd = FULL_DIR
            mode = "labeling"
        elif sc.algorithm == "greedy":
            child = PARTIAL_SINGLE_SCENARIO
            cwd = PARTIAL_DIR
            mode = "greedy"
        else:
            raise ValueError(f"Unknown algorithm: {sc.algorithm}")

        child_args = [
            "--mode",
            mode,
            "--instance_name",
            sc.instance_name,
            "--instance_path",
            str(sc.instance_path),
            "--consumption",
            str(sc.consumption),
            "--distance_per_cs",
            str(sc.distance_per_cs),
            "--battery_cap",
            str(sc.battery_cap),
            "--charging_power",
            str(sc.charging_power),
        ]
        if mode == "greedy":
            child_args += ["--safety_buffer_frac", str(sc.safety_buffer_frac if sc.safety_buffer_frac is not None else 0.10)]

        print(
            f"[{idx}/{len(scenarios)}] {sc.algorithm}"
            f"{'('+sc.tag+')' if sc.tag else ''}"
            f" | {sc.instance_name} | cons={sc.consumption} dcs={sc.distance_per_cs} bc={sc.battery_cap} cp={sc.charging_power}"
            f"{' sb='+str(sc.safety_buffer_frac) if mode == 'greedy' else ''}"
        )

        row = _run_child(child, cwd=cwd, args=child_args)
        # Add unified metadata columns
        row["_runner_timestamp"] = timestamp
        row["_runner_algorithm"] = sc.algorithm
        row["_runner_tag"] = sc.tag or ""
        row["_runner_source_dir"] = str(cwd)
        all_rows.append(row)

    # Save combined outputs
    payload = {
        "metadata": {
            "timestamp": timestamp,
            "total_scenarios": len(scenarios),
            "preset": cli_args.preset,
            "grid": preset_snapshot_for_json(preset),
            "diesel_lower_bound": {
                "enabled": RUN_DIESEL_LOWER_BOUND,
                "battery_cap": DIESEL_BATTERY_CAP,
                "greedy_safety_buffer_frac": DIESEL_SAFETY_BUFFER_FRAC,
            },
            "specific_instances_to_run": SPECIFIC_INSTANCES_TO_RUN,
        },
        "results": all_rows,
    }
    json_out, csv_out = _save_bundle(results_dir, f"unified_results_{timestamp}", payload, all_rows)
    print(f"Saved: {json_out}")
    print(f"Saved: {csv_out}")

    # Also save per-algorithm bundles (so you always have JSON + CSV for each)
    by_algo: Dict[str, List[Dict[str, Any]]] = {}
    for r in all_rows:
        algo = str(r.get("_runner_algorithm", "unknown"))
        by_algo.setdefault(algo, []).append(r)

    for algo, rows in by_algo.items():
        algo_payload = {
            "metadata": {**payload["metadata"], "algorithm": algo, "total_scenarios": len(rows)},
            "results": rows,
        }
        a_json, a_csv = _save_bundle(results_dir, f"{algo}_results_{timestamp}", algo_payload, rows)
        print(f"Saved: {a_json}")
        print(f"Saved: {a_csv}")

    # And diesel-only bundle (if enabled and present)
    diesel_rows = [r for r in all_rows if str(r.get("_runner_tag", "")) == "diesel_lb"]
    if diesel_rows:
        diesel_payload = {
            "metadata": {**payload["metadata"], "tag": "diesel_lb", "total_scenarios": len(diesel_rows)},
            "results": diesel_rows,
        }
        d_json, d_csv = _save_bundle(results_dir, f"diesel_lb_results_{timestamp}", diesel_payload, diesel_rows)
        print(f"Saved: {d_json}")
        print(f"Saved: {d_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

