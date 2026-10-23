#!/usr/bin/env python3
"""
Unified single-thread experiment runner for TDSPEVRP (Partial + Full + Greedy + Driver heuristic + Diesel/LB).

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


from common.paths import ROOT as ROOT_DIR, BENCHMARK
PARTIAL_DIR = ROOT_DIR / "policies" / "labeling" / "partial_recharge"
FULL_DIR = ROOT_DIR / "policies" / "labeling" / "full_recharge"

PARTIAL_SINGLE_SCENARIO = PARTIAL_DIR / "single_scenario_runner.py"
FULL_SINGLE_SCENARIO = FULL_DIR / "single_scenario_runner.py"
DRIVER_HEURISTIC_RUNNER = ROOT_DIR / "policies" / "heuristics" / "driver_runner.py"


# Configurations are explicit, versioned inputs. Historical aliases remain available.
CONFIG_DIR = ROOT_DIR / "experiments" / "configs"
PRESETS = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in CONFIG_DIR.glob("*.json")}
PRESETS["base"] = PRESETS["legacy_base"]
PRESETS["full"] = PRESETS["parameter_sweep"]
DEFAULT_PRESET = "paper_base"

# Algorithms orchestrated by this runner (CLI --algorithms selects a subset).
ALL_ALGORITHMS = ("partial_labeling", "full_labeling", "greedy", "driver_heuristic")

# Driver-inspired sequential heuristic (Partial Recharge/EVTDSPalgorithmmain/driver_heuristic.py).
# One scenario per policy. t_sync_hours=None -> driver_heuristic.T_SYNC_HOURS default.
DRIVER_HEURISTIC = {
    "policies": ["full", "overlap"],
    "t_sync_hours": None,
}
# Diesel-tagged driver run: huge battery, overlap-only policy, t_sync = 0 (no early synchronisation).
DIESEL_DRIVER_POLICY = "overlap"
DIESEL_DRIVER_T_SYNC = 0.0

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


def diesel_anchor_params(preset: Optional[Dict[str, Any]] = None) -> Tuple[float, float, float]:
    """
    (consumption, distance_per_cs, charging_power) for diesel/LB runs: first tuple from the preset
    enumeration (BASE_CASE when no preset is given), with battery replaced by DIESEL_BATTERY_CAP in
    the scenario builder.
    """
    preset = BASE_CASE if preset is None else preset
    first = next(iter(iter_preset_parameter_combinations(preset)), None)
    if first is None:
        raise ValueError("Preset produces no parameter combinations (check battery_caps / charging_powers).")
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
    algorithm: str  # "partial_labeling" | "full_labeling" | "greedy" | "driver_heuristic"
    instance_name: str
    instance_path: Path
    consumption: float
    distance_per_cs: float
    battery_cap: float
    charging_power: float
    safety_buffer_frac: Optional[float] = None  # greedy only
    tag: Optional[str] = None  # e.g. "diesel_lb"
    policy: Optional[str] = None  # driver_heuristic only: "full" | "overlap"
    t_sync_hours: Optional[float] = None  # driver_heuristic only (None -> default)


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
    cmd = [sys.executable, "-m", ".".join(script_path.relative_to(ROOT_DIR).with_suffix("").parts)] + args
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT_DIR),
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


def driver_options(preset):
    config = preset.get("driver_heuristic", {"policies": ["full", "overlap"], "t_sync_hours": None})
    horizons = config["t_sync_hours"]
    if not isinstance(horizons, list):
        horizons = [horizons]
    return [(policy, horizon) for policy in config["policies"] for horizon in horizons]


def _build_scenarios(
    partial_instances: List[Tuple[str, Path]],
    full_instances: List[Tuple[str, Path]],
    preset: Dict[str, Any],
    algorithms: Tuple[str, ...] = ALL_ALGORITHMS,
) -> List[Scenario]:
    full_map = {name: path for name, path in full_instances}
    safety_fracs = [float(x) for x in preset["safety_buffer_fracs"]]
    cons0, dcs0, cp0 = diesel_anchor_params(preset)
    algos = set(algorithms)

    scenarios: List[Scenario] = []
    for instance_name, partial_path in partial_instances:
        full_path = full_map.get(instance_name)
        if full_path is None:
            # Skip instances not present in both versions (keeps comparisons aligned)
            continue

        for cons, dcs, bc, cp in iter_preset_parameter_combinations(preset):
            if "partial_labeling" in algos:
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
            if "full_labeling" in algos:
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
            if "greedy" in algos:
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
            if "driver_heuristic" in algos:
                for pol, sync in driver_options(preset):
                    scenarios.append(
                        Scenario(
                            algorithm="driver_heuristic",
                            instance_name=instance_name,
                            instance_path=partial_path,
                            consumption=cons,
                            distance_per_cs=dcs,
                            battery_cap=bc,
                            charging_power=cp,
                            policy=pol,
                            t_sync_hours=sync,
                        )
                    )

        if RUN_DIESEL_LOWER_BOUND:
            if "partial_labeling" in algos:
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
            if "greedy" in algos:
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
            if "driver_heuristic" in algos:
                scenarios.append(
                    Scenario(
                        algorithm="driver_heuristic",
                        instance_name=instance_name,
                        instance_path=partial_path,
                        consumption=cons0,
                        distance_per_cs=dcs0,
                        battery_cap=DIESEL_BATTERY_CAP,
                        charging_power=cp0,
                        tag="diesel_lb",
                        policy=DIESEL_DRIVER_POLICY,
                        t_sync_hours=DIESEL_DRIVER_T_SYNC,
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

    parser = argparse.ArgumentParser(
        description="Unified single-thread experiment runner (partial/full/greedy/driver heuristic + diesel LB)."
    )
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS.keys()),
        required=True,
        help=(
            "Parameter preset: 'base' = BASE_CASE, 'full' = FULL_GRID, "
            "'paper_base' = 750 kWh / 60 km / 350 kW / 1.49 kWh/km (base-scenario post-analysis)."
        ),
    )
    parser.add_argument(
        "--algorithms",
        default="",
        help=(
            "Comma-separated subset of: " + ", ".join(ALL_ALGORITHMS) + ". Default: all. "
            "Example: --algorithms driver_heuristic"
        ),
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

    global SPECIFIC_INSTANCES_TO_RUN, RUN_DIESEL_LOWER_BOUND, DRIVER_HEURISTIC
    if cli_args.instances.strip():
        SPECIFIC_INSTANCES_TO_RUN = [s.strip() for s in cli_args.instances.split(",") if s.strip()]
    if cli_args.no_diesel:
        RUN_DIESEL_LOWER_BOUND = False

    preset = PRESETS[cli_args.preset]
    DRIVER_HEURISTIC = preset.get("driver_heuristic", {"policies": ["full", "overlap"], "t_sync_hours": None})

    if cli_args.algorithms.strip():
        algorithms = tuple(a.strip() for a in cli_args.algorithms.split(",") if a.strip())
        unknown = set(algorithms) - set(ALL_ALGORITHMS)
        if unknown:
            raise SystemExit(f"Unknown algorithm(s): {sorted(unknown)}. Allowed: {', '.join(ALL_ALGORITHMS)}")
    else:
        algorithms = ALL_ALGORITHMS

    # Sanity checks
    if not PARTIAL_SINGLE_SCENARIO.exists():
        raise FileNotFoundError(f"Missing: {PARTIAL_SINGLE_SCENARIO}")
    if not FULL_SINGLE_SCENARIO.exists():
        raise FileNotFoundError(f"Missing: {FULL_SINGLE_SCENARIO}")
    if "driver_heuristic" in algorithms and not DRIVER_HEURISTIC_RUNNER.exists():
        raise FileNotFoundError(f"Missing: {DRIVER_HEURISTIC_RUNNER}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    # Discover instances (use each directory’s local instances folder)
    partial_instances = _filter_instances(_discover_instances(BENCHMARK))
    full_instances = _filter_instances(_discover_instances(BENCHMARK))
    if not partial_instances:
        print(f"No instances found under: {BENCHMARK}")
        return 1
    if not full_instances:
        print(f"No instances found under: {BENCHMARK}")
        return 1

    scenarios = _build_scenarios(partial_instances, full_instances, preset, algorithms)
    if not scenarios:
        print("No scenarios to run (maybe instance intersection is empty).")
        return 1
    if cli_args.max_scenarios and cli_args.max_scenarios > 0:
        scenarios = scenarios[: cli_args.max_scenarios]

    results_dir = ROOT_DIR / "output" / "executions" / (cli_args.preset + "_" + timestamp)
    _ensure_dir(results_dir)

    from experiments.provenance import create_manifest, save_manifest
    manifest = create_manifest(cli_args.preset, preset, scenarios)
    save_manifest(results_dir, manifest)
    all_rows: List[Dict[str, Any]] = []

    print(f"Unified runner starting. Scenarios: {len(scenarios)}. Timestamp: {timestamp}")
    print(f"Results dir: {results_dir}")
    print(f"Instances (partial discovered): {len(partial_instances)}")
    print(f"Preset: {cli_args.preset}")
    print(f"Algorithms: {', '.join(algorithms)}")

    for idx, sc in enumerate(scenarios, 1):
        mode: Optional[str]
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
        elif sc.algorithm == "driver_heuristic":
            child = DRIVER_HEURISTIC_RUNNER
            cwd = PARTIAL_DIR
            mode = None  # driver_heuristic_runner.py has no --mode
        else:
            raise ValueError(f"Unknown algorithm: {sc.algorithm}")

        child_args = (["--mode", mode] if mode else []) + [
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
        if sc.algorithm == "driver_heuristic":
            child_args += ["--policy", sc.policy or "full"]
            if sc.t_sync_hours is not None:
                child_args += ["--t_sync", str(sc.t_sync_hours)]

        extra = ""
        if mode == "greedy":
            extra = f" sb={sc.safety_buffer_frac}"
        elif sc.algorithm == "driver_heuristic":
            extra = f" policy={sc.policy} t_sync={sc.t_sync_hours if sc.t_sync_hours is not None else 'default'}"
        print(
            f"[{idx}/{len(scenarios)}] {sc.algorithm}"
            f"{'('+sc.tag+')' if sc.tag else ''}"
            f" | {sc.instance_name} | cons={sc.consumption} dcs={sc.distance_per_cs} bc={sc.battery_cap} cp={sc.charging_power}"
            f"{extra}"
        )

        try:
            row = _run_child(child, cwd=cwd, args=child_args)
        except Exception as exc:
            manifest.update(status="failed", completed_scenarios=len(all_rows), error=str(exc))
            save_manifest(results_dir, manifest)
            raise
        # Add unified metadata columns
        row["_runner_timestamp"] = timestamp
        row["_runner_algorithm"] = sc.algorithm
        row["_runner_tag"] = sc.tag or ""
        row["_runner_source_dir"] = str(cwd)
        all_rows.append(row)
        with (results_dir / "results.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        manifest["completed_scenarios"] = len(all_rows)
        save_manifest(results_dir, manifest)

    from experiments.export import export_results
    export_results(results_dir)
    manifest.update(status="completed", completed_scenarios=len(all_rows))
    save_manifest(results_dir, manifest)
    print(f"Saved canonical results: {results_dir / 'results.jsonl'}")
    print(f"Saved CSV summary: {results_dir / 'exports' / 'results.csv'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

