"""One job = one solver run. Shared by main_runner.py, experiments/run.py and the cluster scripts.

Everything that turns a job into a solver command lives here, so local and cluster runs
cannot drift apart. Each solver runs in its own subprocess and prints one JSON object.

A job never crashes the batch it is part of: a solver error or a job time-out becomes a
result row with job_status = "error" or "job_timeout", and the next job runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.paths import ROOT as ROOT_DIR

CHILD_MODULES = {
    "partial_labeling": "policies.labeling.partial_recharge.single_scenario_runner",
    "full_labeling": "policies.labeling.full_recharge.single_scenario_runner",
    "driver_heuristic": "policies.heuristics.driver_runner",
}
LABELING = ("partial_labeling", "full_labeling")

# Values used only by the older entry points (experiments/run.py, run_missing.py, old job files)
# that do not set these themselves. main_runner.py always sets every value explicitly.
LEGACY_DEFAULTS = {
    "rest_charge_sync": True,
    "cs_service_time_h": 0.0,
    "solver_time_limit_min": 3000.0,
}


@dataclass(frozen=True)
class Job:
    job_id: str
    algorithm: str  # partial_labeling | full_labeling | driver_heuristic
    tag: str  # "" or "diesel_lb"
    instance_name: str
    instance_path: str  # relative to the repo root (portable to the cluster) or absolute
    consumption: float
    distance_per_cs: float
    battery_cap: float
    charging_power: float
    safety_buffer_frac: Optional[float] = None  # unused by the solvers; kept for old job files
    policy: Optional[str] = None  # driver_heuristic: "full" | "overlap"
    t_sync_hours: Optional[float] = None  # driver_heuristic (None -> distance_per_cs / speed)
    rest_charge_sync: bool = LEGACY_DEFAULTS["rest_charge_sync"]
    cs_service_time_h: float = LEGACY_DEFAULTS["cs_service_time_h"]
    solver_time_limit_min: float = LEGACY_DEFAULTS["solver_time_limit_min"]
    job_timeout_min: Optional[float] = None  # hard kill of the solver process; None = no limit
    experiment: str = ""  # experiment block name in the main runner config


def job_from_dict(d: Dict[str, Any]) -> Job:
    known = {f.name for f in fields(Job)}
    return Job(**{k: v for k, v in d.items() if k in known})


def job_key(job: Job) -> tuple:
    """Identity of a job for skip-existing checks (ignores job_id and time limits)."""
    return (
        job.experiment, job.algorithm, job.tag, job.instance_name,
        round(float(job.consumption), 6), round(float(job.distance_per_cs), 6),
        round(float(job.battery_cap), 6), round(float(job.charging_power), 6),
        job.policy or "", "" if job.t_sync_hours is None else round(float(job.t_sync_hours), 6),
        bool(job.rest_charge_sync), round(float(job.cs_service_time_h), 6),
    )


def _bool_arg(value: bool) -> str:
    return "true" if value else "false"


def child_command(job: Job) -> List[str]:
    """Full command line for the solver subprocess of this job."""
    if job.algorithm not in CHILD_MODULES:
        raise ValueError(f"Unknown algorithm: {job.algorithm}")
    instance = Path(job.instance_path)
    if not instance.is_absolute():
        instance = ROOT_DIR / instance
    args = [
        "--instance_name", job.instance_name,
        "--instance_path", str(instance.resolve()),
        "--consumption", str(job.consumption),
        "--distance_per_cs", str(job.distance_per_cs),
        "--battery_cap", str(job.battery_cap),
        "--charging_power", str(job.charging_power),
        "--rest_charge_sync", _bool_arg(job.rest_charge_sync),
    ]
    if job.algorithm in LABELING:
        args = ["--mode", "labeling"] + args + [
            "--cs_service_time_h", str(job.cs_service_time_h),
            "--solver_time_limit_min", str(job.solver_time_limit_min),
        ]
    else:
        args += ["--policy", job.policy or "full"]
        if job.t_sync_hours is not None:
            args += ["--t_sync", str(job.t_sync_hours)]
    return [sys.executable, "-m", CHILD_MODULES[job.algorithm]] + args


def settings_mismatches(job: Job, row: Dict[str, Any]) -> List[str]:
    """Compare the settings the solver reports back with the settings of the job."""
    if job.algorithm in LABELING:
        expected = {
            "battery_capacity_kWh": job.battery_cap,
            "charging_station_interval_km": job.distance_per_cs,
            "charging_power_kW": job.charging_power,
            "energy_consumption_rate_kWh_per_km": job.consumption,
            "rest_charge_sync": job.rest_charge_sync,
            "cs_service_time_h": job.cs_service_time_h,
            "solver_time_limit_min": job.solver_time_limit_min,
        }
    else:
        expected = {
            "battery_capacity": job.battery_cap,
            "distance_per_cs": job.distance_per_cs,
            "charging_power": job.charging_power,
            "consumption_rate": job.consumption,
            "rest_charge_sync": job.rest_charge_sync,
            "policy": job.policy or "full",
        }
    problems = []
    for key, want in expected.items():
        got = row.get(key, "<missing>")
        if isinstance(want, bool) or isinstance(got, bool) or isinstance(want, str):
            same = got == want
        else:
            try:
                same = abs(float(got) - float(want)) < 1e-9
            except (TypeError, ValueError):
                same = False
        if not same:
            problems.append(f"{key}: expected {want!r}, solver reported {got!r}")
    return problems


def _job_columns(job: Job) -> Dict[str, Any]:
    return {f"job_{k}": v for k, v in asdict(job).items()}


def execute_job(job: Job, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run one job. Always returns a row; job_status tells whether it succeeded."""
    cmd = child_command(job)
    timeout_s = None if job.job_timeout_min is None else float(job.job_timeout_min) * 60.0
    started = time.time()
    status, error, row = "ok", "", {}
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True, timeout=timeout_s)
        if proc.returncode != 0:
            status, error = "error", f"rc={proc.returncode}\nstderr:\n{proc.stderr[-4000:]}"
        else:
            try:
                row = json.loads(proc.stdout.strip())
            except Exception as exc:  # noqa: BLE001
                status, error = "error", f"could not parse solver output: {exc}\nstdout:\n{proc.stdout[-2000:]}"
    except subprocess.TimeoutExpired:
        status, error = "job_timeout", f"killed after job_timeout_min={job.job_timeout_min}"

    if status == "ok":
        mismatches = settings_mismatches(job, row)
        if mismatches:
            status, error = "settings_mismatch", "; ".join(mismatches)

    row = dict(row)
    row.update(_job_columns(job))
    row["job_status"] = status
    row["job_error"] = error
    row["job_wall_seconds"] = time.time() - started
    row["_runner_algorithm"] = job.algorithm
    row["_runner_tag"] = job.tag or ""
    if extra:
        row.update(extra)
    return row
