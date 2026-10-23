#!/usr/bin/env python3
"""
Run one or more job JSON files on a compute node and append results safely.

This script is executed remotely by `cluster/run_all.sh` via SSH.
It is designed for Linux (Solstorm). It uses fcntl locks for safe appends.

Output (shared, appended by many nodes):
  output/executions/<runid>/results.jsonl
  output/executions/<runid>/exports/results.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import fcntl  # type: ignore
except Exception:
    fcntl = None


ROOT_DIR = Path(__file__).resolve().parents[2]
PARTIAL_DIR = ROOT_DIR / "policies" / "labeling" / "partial_recharge"
FULL_DIR = ROOT_DIR / "policies" / "labeling" / "full_recharge"

PARTIAL_SINGLE_SCENARIO = PARTIAL_DIR / "single_scenario_runner.py"
FULL_SINGLE_SCENARIO = FULL_DIR / "single_scenario_runner.py"
DRIVER_HEURISTIC_RUNNER = ROOT_DIR / "policies" / "heuristics" / "driver_runner.py"


@dataclass
class Job:
    job_id: str
    algorithm: str
    tag: str
    instance_name: str
    instance_path: str
    consumption: float
    distance_per_cs: float
    battery_cap: float
    charging_power: float
    safety_buffer_frac: Optional[float] = None
    policy: Optional[str] = None  # driver_heuristic
    t_sync_hours: Optional[float] = None  # driver_heuristic


def _load_job(path: Path) -> Job:
    d = json.loads(path.read_text(encoding="utf-8"))
    return Job(**d)


def _run_child(script_path: Path, cwd: Path, args: List[str]) -> Dict[str, Any]:
    cmd = [sys.executable, "-m", ".".join(script_path.relative_to(ROOT_DIR).with_suffix("").parts)] + args
    proc = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Child runner failed (rc={proc.returncode}).\n"
            f"cmd: {cmd}\n"
            f"cwd: {cwd}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n"
        )
    return json.loads(proc.stdout.strip())


class _FileLock:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.fd = None

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = open(self.lock_path, "w")
        if fcntl is not None:
            fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.fd and fcntl is not None:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            if self.fd:
                self.fd.close()


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row))
        f.write("\n")




def _job_to_child_args(job: Job) -> tuple[Path, Path, List[str]]:
    if job.algorithm == "partial_labeling":
        child = PARTIAL_SINGLE_SCENARIO
        cwd = PARTIAL_DIR
        mode = "labeling"
    elif job.algorithm == "full_labeling":
        child = FULL_SINGLE_SCENARIO
        cwd = FULL_DIR
        mode = "labeling"
    elif job.algorithm == "greedy":
        child = PARTIAL_SINGLE_SCENARIO
        cwd = PARTIAL_DIR
        mode = "greedy"
    elif job.algorithm == "driver_heuristic":
        child = DRIVER_HEURISTIC_RUNNER
        cwd = PARTIAL_DIR
        mode = None  # driver_heuristic_runner.py has no --mode
    else:
        raise ValueError(f"Unknown algorithm: {job.algorithm}")

    instance_abs = (ROOT_DIR / job.instance_path).resolve()
    args = (["--mode", mode] if mode else []) + [
        "--instance_name",
        job.instance_name,
        "--instance_path",
        str(instance_abs),
        "--consumption",
        str(job.consumption),
        "--distance_per_cs",
        str(job.distance_per_cs),
        "--battery_cap",
        str(job.battery_cap),
        "--charging_power",
        str(job.charging_power),
    ]
    if mode == "greedy":
        args += ["--safety_buffer_frac", str(job.safety_buffer_frac if job.safety_buffer_frac is not None else 0.10)]
    if job.algorithm == "driver_heuristic":
        args += ["--policy", job.policy or "full"]
        if job.t_sync_hours is not None:
            args += ["--t_sync", str(job.t_sync_hours)]
    return child, cwd, args


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runid", required=True, help="Run id (folder name under output/executions/).")
    parser.add_argument("job_files", nargs="+", help="One or more job JSON paths.")
    args = parser.parse_args()

    runid = args.runid
    from experiments.provenance import validate_run_id
    validate_run_id(runid)
    out_dir = ROOT_DIR / "output" / "executions" / runid
    jsonl_path = out_dir / "results.jsonl"
    lock_path = out_dir / "results.LOCK"

    # Ensure we run from project root (relative imports & paths consistent)
    os.chdir(str(ROOT_DIR))

    hostname = os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "")

    for job_file in args.job_files:
        job_path = Path(job_file).resolve()
        job = _load_job(job_path)

        child, cwd, child_args = _job_to_child_args(job)
        result = _run_child(child, cwd=cwd, args=child_args)

        # Attach metadata (like unified runner)
        result["_cluster_runid"] = runid
        result["_cluster_host"] = hostname
        result["_cluster_job_file"] = str(job_path)
        result["_cluster_job_id"] = job.job_id
        result["_runner_algorithm"] = job.algorithm
        result["_runner_tag"] = job.tag or ""

        # Locked append
        with _FileLock(lock_path):
            _append_jsonl(jsonl_path, result)
            # CSV export is generated after all workers finish.

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

