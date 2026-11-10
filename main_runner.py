#!/usr/bin/env python3
"""Main experiment runner: one place to set the grid, the policies and every policy setting.

Edit CONFIG below, or keep a copy as a JSON file and pass it with --config (handy on the cluster).

    python main_runner.py --count                     # how many jobs, per experiment and policy
    python main_runner.py                             # run (local) or write job files (cluster)
    python main_runner.py --config my_config.json     # same, with settings from a JSON file
    python main_runner.py --max_jobs 2                # smoke test: only the first 2 jobs

Rules:
  * The solvers receive every setting from here. They have no defaults of their own for these
    settings and stop with an error if one is missing.
  * Each result row stores the settings it ran with, and this runner checks that the solver
    reported back the same values (job_status = "settings_mismatch" otherwise).
  * HoS rules (driving / rest / break limits, speed) live in common/hos.py for all policies.
  * Results go to output/executions/<run_id>/. Running the same run_id again skips jobs that
    already finished with job_status "ok", so an interrupted run is resumed, not restarted.
"""

from __future__ import annotations

import argparse
import itertools
import json
import shlex
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from common.paths import BENCHMARK, OUTPUT, ROOT

# =====================================================================================
# CONFIG - edit here
# =====================================================================================
CONFIG: Dict[str, Any] = {
    "run_id": "revision_base500_sens_20261110",
    # "paper43" = instances/PAPER_INSTANCE_SET_43.txt, "all" = every benchmark instance,
    # or an explicit list such as ["short_cl1_cu2", "long_cl3_cu5_Balanced"].
    "instances": "paper43",

    "run_settings": {
        "mode": "cluster",               # "local" runs the jobs now; "cluster" writes job files
        "solver_time_limit_min": 3000,   # labeling search limit (Full, Partial); timed_out=True if hit
        "job_timeout_min": 3100,         # hard kill of one solver process; keep above the solver limit
        "local_workers": 1,              # jobs in parallel on this computer
        "skip_existing": True,           # skip jobs already "ok" in output/executions/<run_id>
        "cluster": {
            "row": 4,                    # Solstorm compute row
            "nodes": [1, 2, 3, 4],       # compute-<row>-<node>
            "workers_per_node": 8,       # jobs in parallel on each node
            "node_timeout": "7d",        # wall-clock limit for one node's whole batch
        },
    },

    # Each experiment = one grid + the policies to run on it. Lists are swept.
    # The experiment name is stored in every result row (column job_experiment).
    "experiments": {
        # REFERENCE CASE: charging during the overnight rest is allowed (rest_charge_sync = True).
        # validate() refuses any other value here.
        "base": {
            "enabled": True,
            "grid": {
                "battery_kWh": [500],
                "charging_power_kW": [350],
                "cs_spacing_km": [60],
                "consumption_kWh_per_km": [1.49],
            },
            "policies": {
                "full_labeling": {
                    "enabled": True,
                    "rest_charge_sync": [True],
                    "cs_service_time_h": 0.0,            # fixed time per CS visit besides charging
                },
                "partial_labeling": {
                    "enabled": True,
                    "rest_charge_sync": [True],
                    "cs_service_time_h": 0.0,
                },
                "driver_heuristic": {
                    "enabled": True,
                    "variants": ["full", "overlap"],
                    "t_sync_h": [None],                  # None = cs_spacing / speed
                    "rest_charge_sync": [True],
                },
                # Lower bound without charging (battery 1e8 kWh), once per instance at the first
                # grid point. Charging settings do not matter here.
                "diesel_lb": {
                    "enabled": True,
                    "algorithms": ["partial_labeling"],
                },
            },
        },
        # SYNCHRONIZATION-RESTRICTION EXPERIMENT: same vehicle as the base case, but charging may
        # not overlap the 11 h daily rest (rest first, then the full charging time).
        # Compare against "base" to measure the value of rest synchronization.
        "base_rest_sync_off": {
            "enabled": True,
            "grid": {
                "battery_kWh": [500],
                "charging_power_kW": [350],
                "cs_spacing_km": [60],
                "consumption_kWh_per_km": [1.49],
            },
            "policies": {
                "full_labeling": {"enabled": True, "rest_charge_sync": [False], "cs_service_time_h": 0.0},
                "partial_labeling": {"enabled": True, "rest_charge_sync": [False], "cs_service_time_h": 0.0},
                "driver_heuristic": {
                    "enabled": True,
                    "variants": ["full", "overlap"],
                    "t_sync_h": [None],
                    "rest_charge_sync": [False],
                },
            },
        },
        # Parameter sensitivity around the reference case (rest_charge_sync = True).
        "sensitivity": {
            "enabled": True,
            "grid": {
                "battery_kWh": [300, 500, 750, 1000],
                "charging_power_kW": [350, 500, 1000],
                "cs_spacing_km": [40, 60, 80, 100],
                "consumption_kWh_per_km": [1.12, 1.49, 2.08],
            },
            "policies": {
                "full_labeling": {"enabled": True, "rest_charge_sync": [True], "cs_service_time_h": 0.0},
                "partial_labeling": {"enabled": True, "rest_charge_sync": [True], "cs_service_time_h": 0.0},
            },
        },
    },
}
# =====================================================================================

from experiments.jobs import Job, execute_job, job_key  # noqa: E402

DIESEL_BATTERY_CAP = 100_000_000.0
DIESEL_DRIVER_VARIANT = "overlap"
DIESEL_DRIVER_T_SYNC = 0.0
PAPER_LIST = ROOT / "instances" / "PAPER_INSTANCE_SET_43.txt"

GRID_KEYS = ("battery_kWh", "charging_power_kW", "cs_spacing_km", "consumption_kWh_per_km")
POLICY_KEYS = {
    "full_labeling": {"enabled", "rest_charge_sync", "cs_service_time_h",
                      "solver_time_limit_min", "job_timeout_min"},
    "partial_labeling": {"enabled", "rest_charge_sync", "cs_service_time_h",
                         "solver_time_limit_min", "job_timeout_min"},
    "driver_heuristic": {"enabled", "variants", "t_sync_h", "rest_charge_sync", "job_timeout_min"},
    "diesel_lb": {"enabled", "algorithms", "solver_time_limit_min", "job_timeout_min"},
}
RUN_KEYS = {"mode", "solver_time_limit_min", "job_timeout_min", "local_workers", "skip_existing", "cluster"}
CLUSTER_KEYS = {"row", "nodes", "workers_per_node", "node_timeout"}


# ------------------------------------------------------------------------- validation
def _fail(msg: str) -> None:
    raise SystemExit(f"Config error: {msg}")


def _unknown(keys, allowed, where):
    extra = set(keys) - set(allowed)
    if extra:
        _fail(f"unknown key(s) {sorted(extra)} in {where}. Allowed: {sorted(allowed)}")


def _as_list(value, where):
    if not isinstance(value, list) or not value:
        _fail(f"{where} must be a non-empty list")
    return value


def validate(cfg: Dict[str, Any]) -> None:
    """Stop on typos and wrong types instead of silently ignoring a setting."""
    _unknown(cfg, {"run_id", "instances", "run_settings", "experiments"}, "the top level")
    from experiments.provenance import validate_run_id
    validate_run_id(cfg["run_id"])
    rs = cfg["run_settings"]
    _unknown(rs, RUN_KEYS, "run_settings")
    if rs["mode"] not in ("local", "cluster"):
        _fail("run_settings.mode must be 'local' or 'cluster'")
    _unknown(rs.get("cluster", {}), CLUSTER_KEYS, "run_settings.cluster")
    if rs["job_timeout_min"] is not None and rs["job_timeout_min"] <= rs["solver_time_limit_min"]:
        _fail("job_timeout_min must be larger than solver_time_limit_min, or the solver never reports timed_out")
    if not any(e.get("enabled", True) for e in cfg["experiments"].values()):
        _fail("no experiment is enabled")
    # The base case is the reference: overnight rest and charging are synchronized.
    for exp_name in ("base", "sensitivity"):
        for pol, pc in cfg["experiments"].get(exp_name, {}).get("policies", {}).items():
            if pc.get("enabled", True) and any(v is not True for v in pc.get("rest_charge_sync", [True])):
                _fail(f"experiments.{exp_name}.policies.{pol}.rest_charge_sync must be [true]: the reference "
                      f"case synchronizes rest and charging. Put rest_charge_sync=false in base_rest_sync_off.")
    for name, exp in cfg["experiments"].items():
        _unknown(exp, {"enabled", "grid", "policies"}, f"experiments.{name}")
        _unknown(exp["grid"], GRID_KEYS, f"experiments.{name}.grid")
        for k in GRID_KEYS:
            if k not in exp["grid"]:
                _fail(f"experiments.{name}.grid is missing {k}")
            _as_list(exp["grid"][k], f"experiments.{name}.grid.{k}")
        for pol, pc in exp["policies"].items():
            where = f"experiments.{name}.policies.{pol}"
            if pol not in POLICY_KEYS:
                _fail(f"unknown policy {pol!r} in experiments.{name}. Allowed: {sorted(POLICY_KEYS)}")
            _unknown(pc, POLICY_KEYS[pol], where)
            if "rest_charge_sync" in pc:
                for v in _as_list(pc["rest_charge_sync"], f"{where}.rest_charge_sync"):
                    if not isinstance(v, bool):
                        _fail(f"{where}.rest_charge_sync values must be true/false, got {v!r}")
            if pol in ("full_labeling", "partial_labeling") and pc.get("enabled", True):
                if "rest_charge_sync" not in pc or "cs_service_time_h" not in pc:
                    _fail(f"{where} needs rest_charge_sync and cs_service_time_h")
                if float(pc["cs_service_time_h"]) < 0:
                    _fail(f"{where}.cs_service_time_h must be >= 0")
            if pol == "driver_heuristic" and pc.get("enabled", True):
                for k in ("variants", "t_sync_h", "rest_charge_sync"):
                    if k not in pc:
                        _fail(f"{where} needs {k}")
                for v in _as_list(pc["variants"], f"{where}.variants"):
                    if v not in ("full", "overlap"):
                        _fail(f"{where}.variants must be 'full' or 'overlap', got {v!r}")
                _as_list(pc["t_sync_h"], f"{where}.t_sync_h")
            if pol == "diesel_lb" and pc.get("enabled", True):
                for a in _as_list(pc.get("algorithms"), f"{where}.algorithms"):
                    if a not in ("partial_labeling", "full_labeling", "driver_heuristic"):
                        _fail(f"{where}.algorithms has unknown algorithm {a!r}")


# ------------------------------------------------------------------------- jobs
def resolve_instances(spec) -> List[tuple]:
    from experiments.run import _discover_instances
    found = dict(_discover_instances(BENCHMARK))
    if spec == "all":
        names = sorted(found)
    elif spec == "paper43":
        names = [s.strip() for s in PAPER_LIST.read_text(encoding="utf-8").splitlines()
                 if s.strip() and not s.strip().startswith("#")]
    elif isinstance(spec, list):
        names = spec
    else:
        _fail("instances must be 'paper43', 'all' or a list of instance names")
    missing = [n for n in names if n not in found]
    if missing:
        _fail(f"instances not found under {BENCHMARK}: {missing}")
    return [(n, found[n].resolve().relative_to(ROOT.resolve()).as_posix()) for n in names]


def build_jobs(cfg: Dict[str, Any]) -> List[Job]:
    rs = cfg["run_settings"]
    instances = resolve_instances(cfg["instances"])
    jobs: List[Job] = []

    def add(**kw):
        jobs.append(Job(job_id="", **kw))

    for exp_name, exp in cfg["experiments"].items():
        if not exp.get("enabled", True):
            continue
        g = exp["grid"]
        grid = [dict(zip(GRID_KEYS, combo)) for combo in itertools.product(*(g[k] for k in GRID_KEYS))]
        pols = {p: pc for p, pc in exp["policies"].items() if pc.get("enabled", True)}
        for inst, path in instances:
            for gp in grid:
                common = dict(experiment=exp_name, instance_name=inst, instance_path=path,
                              consumption=float(gp["consumption_kWh_per_km"]),
                              distance_per_cs=float(gp["cs_spacing_km"]),
                              battery_cap=float(gp["battery_kWh"]),
                              charging_power=float(gp["charging_power_kW"]))
                for alg in ("full_labeling", "partial_labeling"):
                    if alg not in pols:
                        continue
                    pc = pols[alg]
                    for sync in pc["rest_charge_sync"]:
                        add(algorithm=alg, tag="", rest_charge_sync=sync,
                            cs_service_time_h=float(pc["cs_service_time_h"]),
                            solver_time_limit_min=float(pc.get("solver_time_limit_min", rs["solver_time_limit_min"])),
                            job_timeout_min=pc.get("job_timeout_min", rs["job_timeout_min"]), **common)
                if "driver_heuristic" in pols:
                    pc = pols["driver_heuristic"]
                    for variant, ts, sync in itertools.product(pc["variants"], pc["t_sync_h"], pc["rest_charge_sync"]):
                        add(algorithm="driver_heuristic", tag="", policy=variant,
                            t_sync_hours=None if ts is None else float(ts), rest_charge_sync=sync,
                            solver_time_limit_min=float(rs["solver_time_limit_min"]),
                            job_timeout_min=pc.get("job_timeout_min", rs["job_timeout_min"]), **common)
            if "diesel_lb" in pols:
                pc = pols["diesel_lb"]
                gp = grid[0]
                for alg in pc["algorithms"]:
                    add(algorithm=alg, tag="diesel_lb", experiment=exp_name, instance_name=inst,
                        instance_path=path, consumption=float(gp["consumption_kWh_per_km"]),
                        distance_per_cs=float(gp["cs_spacing_km"]), battery_cap=DIESEL_BATTERY_CAP,
                        charging_power=float(gp["charging_power_kW"]),
                        policy=DIESEL_DRIVER_VARIANT if alg == "driver_heuristic" else None,
                        t_sync_hours=DIESEL_DRIVER_T_SYNC if alg == "driver_heuristic" else None,
                        rest_charge_sync=True, cs_service_time_h=0.0,
                        solver_time_limit_min=float(pc.get("solver_time_limit_min", rs["solver_time_limit_min"])),
                        job_timeout_min=pc.get("job_timeout_min", rs["job_timeout_min"]))
    seen = set()
    unique = []
    for j in jobs:
        if job_key(j) in seen:
            continue
        seen.add(job_key(j))
        unique.append(j)
    return [replace(j, job_id=f"{i:06d}") for i, j in enumerate(unique, 1)]


def finished_keys(run_dir: Path) -> set:
    done = set()
    path = run_dir / "results.jsonl"
    if not path.exists():
        return done
    from experiments.jobs import job_from_dict
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("job_status") != "ok":
            continue
        fields = {k[4:]: v for k, v in row.items() if k.startswith("job_") and k not in ("job_status", "job_error", "job_wall_seconds")}
        done.add(job_key(job_from_dict(fields)))
    return done


def print_counts(jobs: List[Job], todo: List[Job]) -> None:
    def label(j: Job) -> str:
        if j.tag == "diesel_lb":
            return f"diesel_lb/{j.algorithm}"
        return j.algorithm
    todo_ids = {j.job_id for j in todo}
    rows: Dict[tuple, List[int]] = {}
    for j in jobs:
        r = rows.setdefault((j.experiment, label(j)), [0, 0])
        r[0] += 1
        r[1] += j.job_id in todo_ids
    print(f"{'experiment':<22}{'policy':<34}{'jobs':>7}{'to run':>9}")
    for (exp, pol), (n, t) in sorted(rows.items()):
        print(f"{exp:<22}{pol:<34}{n:>7}{t:>9}")
    print(f"{'total':<56}{len(jobs):>7}{len(todo):>9}")


# ------------------------------------------------------------------------- run modes
def run_local(jobs: List[Job], run_dir: Path, workers: int) -> int:
    lock = threading.Lock()
    counter = {"n": 0, "bad": 0}

    def one(job: Job):
        row = execute_job(job, extra={"_run_id": run_dir.name})
        with lock:
            with (run_dir / "results.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            counter["n"] += 1
            counter["bad"] += row["job_status"] != "ok"
            extra = f" policy={job.policy}" if job.policy else ""
            print(f"[{counter['n']}/{len(jobs)}] {job.experiment} {job.algorithm}{'(' + job.tag + ')' if job.tag else ''}"
                  f"{extra} sync={job.rest_charge_sync} | {job.instance_name} | bc={job.battery_cap:g} "
                  f"cp={job.charging_power:g} dcs={job.distance_per_cs:g} cons={job.consumption:g}"
                  f" -> {row['job_status']}{' ' + row['job_error'][:200] if row['job_error'] else ''}", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(one, jobs))
    print(f"Finished: {counter['n']} jobs, {counter['bad']} not ok.")
    return 0 if counter["bad"] == 0 else 1


def write_cluster_jobs(jobs: List[Job], run_dir: Path, cluster: Dict[str, Any]) -> None:
    jobs_dir = run_dir / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    for old in jobs_dir.glob("job_*.json"):
        old.unlink()  # only the jobs still to run are sent to the nodes
    for j in jobs:
        (jobs_dir / f"job_{j.job_id}.json").write_text(json.dumps(asdict(j), indent=2), encoding="utf-8")
    nodes = ",".join(str(n) for n in cluster["nodes"])
    rid = shlex.quote(run_dir.name)
    print(f"Wrote {len(jobs)} job files to {jobs_dir}")
    print("Next, on solstorm-login from the repository root:")
    print(f"  bash experiments/cluster/run_all.sh -j {rid} -r {cluster['row']} -n {nodes} "
          f"-w {cluster['workers_per_node']} -t {cluster['node_timeout']}")
    print(f"  python3 -m experiments.cluster.merge_results --runid {rid}")
    print("If a node stops early, run main_runner.py again with the same run_id: it rewrites only the unfinished jobs.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Main experiment runner (grid, policies, settings in one place).")
    parser.add_argument("--config", type=Path, help="JSON file that replaces CONFIG in this file.")
    parser.add_argument("--count", action="store_true", help="Print job counts and exit.")
    parser.add_argument("--max_jobs", type=int, default=0, help="Only the first N jobs still to run (smoke test).")
    parser.add_argument("--write_config", type=Path, help="Write the CONFIG of this file to a JSON file and exit.")
    args = parser.parse_args()

    if args.write_config:
        args.write_config.write_text(json.dumps(CONFIG, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.write_config}")
        return 0
    cfg = json.loads(args.config.read_text(encoding="utf-8")) if args.config else json.loads(json.dumps(CONFIG))
    validate(cfg)
    rs = cfg["run_settings"]

    run_dir = OUTPUT / "executions" / cfg["run_id"]
    jobs = build_jobs(cfg)
    done = finished_keys(run_dir) if rs["skip_existing"] else set()
    todo = [j for j in jobs if job_key(j) not in done]
    print(f"Run id: {cfg['run_id']}   mode: {rs['mode']}   results: {run_dir}")
    print_counts(jobs, todo)
    if args.count:
        return 0

    from experiments.provenance import create_manifest, save_manifest
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if old.get("config") != cfg:
            _fail(f"{run_dir} was started with a different config. Use a new run_id, "
                  f"or restore the config saved in {manifest_path}.")
    if args.max_jobs and args.max_jobs > 0:
        todo = todo[: args.max_jobs]
    if not todo:
        print("Nothing to run: every job already finished ok.")
        return 0

    manifest = create_manifest(cfg["run_id"], cfg, jobs)
    manifest["runner"] = "main_runner.py"
    manifest["started_at_local"] = datetime.now().isoformat(timespec="seconds")
    save_manifest(run_dir, manifest)

    if rs["mode"] == "cluster":
        write_cluster_jobs(todo, run_dir, rs["cluster"])
        return 0

    rc = run_local(todo, run_dir, rs["local_workers"])
    from experiments.cluster.merge_results import final_rows
    rows = [json.loads(l) for l in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    best = final_rows(rows)
    with (run_dir / "results_final.jsonl").open("w", encoding="utf-8") as out:
        for key in sorted(best, key=str):
            out.write(json.dumps(best[key]) + "\n")
    from experiments.export import export_results
    print(f"CSV: {export_results(run_dir, source='results_final.jsonl')}")
    ok = sum(1 for r in best.values() if r.get("job_status") == "ok")
    manifest.update(status="completed" if ok == len(jobs) else "incomplete", completed_scenarios=ok)
    save_manifest(run_dir, manifest)
    return rc


if __name__ == "__main__":
    sys.exit(main())
