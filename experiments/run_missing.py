#!/usr/bin/env python3
"""Queue or run only missing Full/Partial jobs for the paper 43-instance set.

Default preset fills holes in the saved 72-config grid (750/1000 kWh).
Use --preset sensitivity_plus_300_500 to also add 300 and 500 kWh batteries.

Already-saved rows in reviewer_results/ are skipped. Diesel and Driver are not run.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from collections import Counter
from typing import Dict, Iterable, List, Set, Tuple

import pandas as pd

from common.paths import ROOT as ROOT_DIR
import experiments.run as U
from experiments.cluster.create_jobs import Job, _rel
from experiments.provenance import create_manifest, save_manifest, validate_run_id

PAPER_LIST = ROOT_DIR / "instances" / "PAPER_INSTANCE_SET_43.txt"
EXISTING_CSVS = (
    ROOT_DIR / "reviewer_results" / "04_sensitivity_raw" / "unified_results_full_partial_grid_20260407_174118.csv",
    ROOT_DIR / "reviewer_results" / "02_base_scenario_raw" / "unified_results_full_partial_diesel_20260408_135323.csv",
)
ALGS = ("partial_labeling", "full_labeling")
PRESET_NAME = "fill_missing_sensitivity"
BASE_BATTERY = 750.0
BASE_SPACING = 60.0
BASE_CONS = 1.49
BASE_POWERS = (350.0, 500.0)
BASE_CFG = (750.0, 350.0, 60.0, 1.49)
BASE_500_CFG = (750.0, 500.0, 60.0, 1.49)
Key = Tuple[str, str, float, float, float, float]


def paper_instances() -> List[str]:
    names = []
    for line in PAPER_LIST.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            names.append(s)
    if len(names) != 43:
        raise SystemExit(f"Expected 43 paper instances in {PAPER_LIST}, found {len(names)}")
    return names


def _clean(s) -> str:
    return str(s).replace("TB_", "")


def _round_key(inst: str, alg: str, batt: float, pwr: float, spc: float, cons: float) -> Key:
    return (inst, alg, round(float(batt), 1), round(float(pwr), 1), round(float(spc), 1), round(float(cons), 2))


def _add_done_from_frame(done: Set[Key], df: pd.DataFrame) -> None:
    if "instance_id" not in df.columns or "_runner_algorithm" not in df.columns:
        return
    if "battery_capacity_kWh" in df.columns:
        df = df[pd.to_numeric(df["battery_capacity_kWh"], errors="coerce").fillna(0) < 1e6]
    for _, row in df.iterrows():
        alg = str(row["_runner_algorithm"])
        if alg not in ALGS:
            continue
        done.add(
            _round_key(
                _clean(row["instance_id"]),
                alg,
                row["battery_capacity_kWh"],
                row["charging_power_kW"],
                row["charging_station_interval_km"],
                row["energy_consumption_rate_kWh_per_km"],
            )
        )


def load_done_keys(paths: Iterable[Path] = EXISTING_CSVS) -> Set[Key]:
    done: Set[Key] = set()
    for path in paths:
        if not path.exists():
            print(f"Note: existing-results file not found, skipping: {path}")
            continue
        _add_done_from_frame(done, pd.read_csv(path, low_memory=False))
    exec_root = ROOT_DIR / "output" / "executions"
    if exec_root.exists():
        for path in sorted(exec_root.glob("*/results.jsonl")):
            rows = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
            if rows:
                _add_done_from_frame(done, pd.DataFrame(rows))
    return done


def iter_grid(preset: Dict) -> List[Tuple[float, float, float, float]]:
    return [(bc, cp, dcs, cons) for cons, dcs, bc, cp in U.iter_preset_parameter_combinations(preset)]


def missing_jobs(
    preset: Dict,
    paper: List[str],
    done: Set[Key],
    only_base: bool = False,
) -> List[Job]:
    instances = {n: p for n, p in U._discover_instances(ROOT_DIR / "instances" / "benchmark_v1")}
    missing: List[Job] = []
    for inst in paper:
        path = instances.get(inst)
        if path is None:
            raise SystemExit(f"Paper instance folder not found: {inst}")
        rel = _rel(path)
        configs = (
            [(BASE_BATTERY, pwr, BASE_SPACING, BASE_CONS) for pwr in BASE_POWERS]
            if only_base
            else iter_grid(preset)
        )
        for batt, pwr, spc, cons in configs:
            for alg in ALGS:
                if _round_key(inst, alg, batt, pwr, spc, cons) in done:
                    continue
                missing.append(
                    Job(
                        job_id="",
                        algorithm=alg,
                        tag="",
                        instance_name=inst,
                        instance_path=rel,
                        consumption=float(cons),
                        distance_per_cs=float(spc),
                        battery_cap=float(batt),
                        charging_power=float(pwr),
                    )
                )
    for i, job in enumerate(missing, 1):
        missing[i - 1] = Job(job_id=f"{i:06d}", **{k: v for k, v in asdict(job).items() if k != "job_id"})
    return missing


def summarize(jobs: List[Job], n_configs: int) -> None:
    n_partial = sum(1 for j in jobs if j.algorithm == "partial_labeling")
    n_full = sum(1 for j in jobs if j.algorithm == "full_labeling")
    by_batt = Counter(j.battery_cap for j in jobs)
    n_new_base = sum(
        1
        for j in jobs
        if (j.battery_cap, j.charging_power, j.distance_per_cs, j.consumption)
        == (500.0, 350.0, 60.0, 1.49)
    )
    print(f"Paper instances: 43")
    print(f"Grid configs: {n_configs} (consumption x spacing x battery x power)")
    print(f"Full factorial would be: 43 x {n_configs} x 2 = {43 * n_configs * 2}")
    print(f"Jobs to run (missing only): {len(jobs)}")
    print(f"  Partial: {n_partial}")
    print(f"  Full:    {n_full}")
    for batt in sorted(by_batt):
        print(f"  battery {batt:g} kWh: {by_batt[batt]} jobs")
    print(f"  of which new base 500 kWh / 60 km / 1.49 / 350 kW: {n_new_base}")


def write_jobs(jobs: List[Job], runid: str, preset: Dict, preset_name: str) -> Path:
    validate_run_id(runid)
    run_dir = ROOT_DIR / "output" / "executions" / runid
    if run_dir.exists():
        raise FileExistsError(f"Run already exists: {run_dir}")
    jobs_dir = run_dir / "jobs"
    jobs_dir.mkdir(parents=True)
    for job in jobs:
        (jobs_dir / f"job_{job.job_id}.json").write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")
    listing = run_dir / "missing_jobs.csv"
    with listing.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["job_id", "algorithm", "instance_name", "battery_cap", "charging_power", "distance_per_cs", "consumption"],
        )
        w.writeheader()
        for job in jobs:
            w.writerow(
                {
                    "job_id": job.job_id,
                    "algorithm": job.algorithm,
                    "instance_name": job.instance_name,
                    "battery_cap": job.battery_cap,
                    "charging_power": job.charging_power,
                    "distance_per_cs": job.distance_per_cs,
                    "consumption": job.consumption,
                }
            )
    manifest = create_manifest(preset_name, preset, jobs)
    manifest.update(status="prepared", executor="cluster", num_jobs=len(jobs), skip_existing=True)
    save_manifest(run_dir, manifest)
    print(f"Created {len(jobs)} jobs in: {jobs_dir}")
    print(f"Job list CSV: {listing}")
    print(f"Run id: {runid}")
    return run_dir


def run_local(jobs: List[Job], preset_name: str, max_scenarios: int = 0) -> int:
    if max_scenarios and max_scenarios > 0:
        jobs = jobs[:max_scenarios]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    results_dir = ROOT_DIR / "output" / "executions" / (preset_name + "_" + timestamp)
    results_dir.mkdir(parents=True)
    from experiments.export import export_results

    preset = U.PRESETS[preset_name]
    manifest = create_manifest(preset_name, preset, jobs)
    save_manifest(results_dir, manifest)
    print(f"Unified missing runner starting. Scenarios: {len(jobs)}. Results: {results_dir}")
    all_rows: List[Dict] = []
    for idx, job in enumerate(jobs, 1):
        if job.algorithm == "partial_labeling":
            child, cwd, mode = U.PARTIAL_SINGLE_SCENARIO, U.PARTIAL_DIR, "labeling"
        elif job.algorithm == "full_labeling":
            child, cwd, mode = U.FULL_SINGLE_SCENARIO, U.FULL_DIR, "labeling"
        else:
            raise ValueError(job.algorithm)
        print(
            f"[{idx}/{len(jobs)}] {job.algorithm} | {job.instance_name} | "
            f"cons={job.consumption} dcs={job.distance_per_cs} bc={job.battery_cap} cp={job.charging_power}"
        )
        # Same command builder as main_runner.py and the cluster worker (experiments/jobs.py).
        from experiments.jobs import execute_job
        row = execute_job(job)
        if row["job_status"] != "ok":
            raise RuntimeError(f"Job failed: {row['job_error']}")
        row["_runner_timestamp"] = timestamp
        row["_runner_algorithm"] = job.algorithm
        row["_runner_tag"] = ""
        all_rows.append(row)
        with (results_dir / "results.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        manifest["completed_scenarios"] = len(all_rows)
        save_manifest(results_dir, manifest)
    export_results(results_dir)
    manifest.update(status="completed", completed_scenarios=len(all_rows))
    save_manifest(results_dir, manifest)
    print(f"Saved: {results_dir / 'results.jsonl'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run only missing Full/Partial paper-grid jobs.")
    parser.add_argument("--count", action="store_true", help="Print how many missing jobs and exit.")
    parser.add_argument("--create-jobs", action="store_true", help="Write cluster job JSON files.")
    parser.add_argument("--run", action="store_true", help="Run locally (sequential; slow for the full missing set).")
    parser.add_argument("--runid", default="", help="Required with --create-jobs.")
    parser.add_argument("--max_scenarios", type=int, default=0, help="Optional cap for --run (smoke test).")
    parser.add_argument(
        "--only-base",
        action="store_true",
        help="Only 750 kWh / 60 km / 1.49 kWh/km at charging power 350 and 500 kW.",
    )
    parser.add_argument(
        "--preset",
        default=PRESET_NAME,
        help="Config in experiments/configs/. Use sensitivity_plus_300_500 to add 300 and 500 kWh.",
    )
    args = parser.parse_args()

    preset_name = args.preset
    if preset_name not in U.PRESETS:
        raise SystemExit(f"Preset {preset_name} not loaded. Check experiments/configs/{preset_name}.json")
    preset = U.PRESETS[preset_name]
    paper = paper_instances()
    done = load_done_keys()
    jobs = missing_jobs(preset, paper, done, only_base=args.only_base)
    if args.only_base:
        print("Mode: base case only (750 kWh / 60 km / 1.49, charging power 350 and 500 kW)")
    n_configs = len(iter_grid(preset))
    print(f"Preset: {preset_name}")
    summarize(jobs, n_configs)

    if args.count and not args.create_jobs and not args.run:
        return 0
    if args.create_jobs:
        if not args.runid.strip():
            raise SystemExit("--create-jobs needs --runid, e.g. fill_missing_grid")
        write_jobs(jobs, args.runid.strip(), preset, preset_name)
        print("Next, on the cluster:")
        print(f"  bash experiments/cluster/run_all.sh -j {args.runid.strip()} -r 4 -n 1,2,3,4 -t 24h")
        print(f"  python -m experiments.cluster.merge_results --runid {args.runid.strip()}")
        return 0
    if args.run:
        return run_local(jobs, preset_name, max_scenarios=args.max_scenarios)
    if not args.count:
        print("Nothing to do. Use --count, --create-jobs --runid ..., or --run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
