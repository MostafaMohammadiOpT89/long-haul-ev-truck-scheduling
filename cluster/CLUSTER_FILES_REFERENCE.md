# Cluster Task Distribution – File Reference

This document lists **each cluster-related file**, its **functionality**, and its **full code** so you can reimplement the same workflow in another project (e.g. via Cursor).

---

## Overview

| File | Role |
|------|------|
| **create_jobs.py** | Generates one JSON job file per scenario (e.g. instance × algorithm × parameters). |
| **run_all.sh** | Reserves compute nodes (lockdirs), distributes job files over SSH to nodes, runs `run_job.py` on each. |
| **run_job.py** | Runs one or more job JSONs on a single node; appends results to shared JSONL/CSV with file locking. |
| **merge_results.py** | Reads raw JSONL output and produces combined + per-algorithm JSON/CSV bundles. |
| **run_pipeline.py** | Single entrypoint: `create_jobs` → `run_all.sh` → `merge_results`. |

**Assumptions:**

- Linux cluster with SSH access to compute nodes (e.g. Solstorm: `compute-ROW-N.local`).
- Shared filesystem so all nodes see the same project root and `Results/Cluster/`.
- `gstat` (optional) for auto node selection by load; otherwise use `-r ROW -n node_list`.

---

## 1. `create_jobs.py`

**Functionality:**

- Imports experiment config from a “unified runner” module (here: `unified_experiment_runner`).
- Discovers instances (e.g. from `Partial/instances` and `Full/instances`), optionally filters by name.
- Builds a list of **jobs** (dataclass: algorithm, instance, parameters, optional tag like `diesel_lb`).
- Writes one JSON file per job under `cluster/jobs/<runid>/job_XXXXXX.json` and a `manifest.json`.

**Dependencies:** A module (e.g. `unified_experiment_runner`) that provides:

- `_discover_instances(instances_root)`, preset dicts (e.g. `BASE_CASE`, `FULL_GRID`), `SPECIFIC_INSTANCES_TO_RUN`, and optionally diesel/LB flags.

**Full code:**

```python
#!/usr/bin/env python3
"""
Create one JSON job per scenario (instance × algorithm × grid-parameter combination).

This mirrors the orchestration logic in `unified_experiment_runner.py`, but instead of running
the scenarios locally, it writes them out as independent job files for Solstorm distribution.

Output:
  cluster/jobs/<runid>/job_000001.json ...
  cluster/jobs/<runid>/manifest.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
PARTIAL_DIR = ROOT_DIR / "Partial Recharge" / "EVTDSPalgorithmmain"
FULL_DIR = ROOT_DIR / "Full Recharge" / "EVTDSPalgorithmmain"


# Import configuration from unified runner (single source of truth).
import sys
sys.path.insert(0, str(ROOT_DIR))
import unified_experiment_runner as U


@dataclass(frozen=True)
class Job:
    job_id: str
    algorithm: str  # partial_labeling | full_labeling | greedy
    tag: str  # "" or "diesel_lb"
    instance_name: str
    instance_path: str  # path relative to ROOT_DIR (portable on cluster)
    consumption: float
    distance_per_cs: float
    battery_cap: float
    charging_power: float
    safety_buffer_frac: Optional[float] = None


def _discover_instances(instances_root: Path) -> List[Tuple[str, Path]]:
    return U._discover_instances(instances_root)  # reuse the exact discovery logic


def _filter_instances(instances: List[Tuple[str, Path]], only: List[str]) -> List[Tuple[str, Path]]:
    if not only:
        return instances
    wanted = set(only)
    return [(n, p) for n, p in instances if n in wanted]


def _rel(p: Path) -> str:
    return str(p.resolve().relative_to(ROOT_DIR.resolve()))


def _build_jobs(
    preset: Dict,
    instance_pairs: List[Tuple[str, Path, Path]],
    include_diesel: bool,
) -> List[Job]:
    jobs: List[Job] = []

    cons_rates = preset["consumption_rates"]
    dcs_vals = preset["distances_per_cs"]
    battery_caps = preset["battery_caps"]
    cps = preset["charging_powers"]
    safety_fracs = preset["safety_buffer_fracs"]

    # Main grid
    for instance_name, partial_path, full_path in instance_pairs:
        for cp in cps:
            for bc in battery_caps:
                for cons in cons_rates:
                    for dcs in dcs_vals:
                        # partial labeling
                        jobs.append(
                            Job(
                                job_id="",
                                algorithm="partial_labeling",
                                tag="",
                                instance_name=instance_name,
                                instance_path=_rel(partial_path),
                                consumption=float(cons),
                                distance_per_cs=float(dcs),
                                battery_cap=float(bc),
                                charging_power=float(cp),
                            )
                        )
                        # full labeling
                        jobs.append(
                            Job(
                                job_id="",
                                algorithm="full_labeling",
                                tag="",
                                instance_name=instance_name,
                                instance_path=_rel(full_path),
                                consumption=float(cons),
                                distance_per_cs=float(dcs),
                                battery_cap=float(bc),
                                charging_power=float(cp),
                            )
                        )
                        # greedy (partial codebase)
                        for sb in safety_fracs:
                            jobs.append(
                                Job(
                                    job_id="",
                                    algorithm="greedy",
                                    tag="",
                                    instance_name=instance_name,
                                    instance_path=_rel(partial_path),
                                    consumption=float(cons),
                                    distance_per_cs=float(dcs),
                                    battery_cap=float(bc),
                                    charging_power=float(cp),
                                    safety_buffer_frac=float(sb),
                                )
                            )

        # Diesel/LB: base-case values but huge battery
        if include_diesel and U.RUN_DIESEL_LOWER_BOUND:
            cons0 = float(U.BASE_CASE["consumption_rates"][0])
            dcs0 = float(U.BASE_CASE["distances_per_cs"][0])
            cp0 = float(U.BASE_CASE["charging_powers"][0])
            jobs.append(
                Job(
                    job_id="",
                    algorithm="partial_labeling",
                    tag="diesel_lb",
                    instance_name=instance_name,
                    instance_path=_rel(partial_path),
                    consumption=cons0,
                    distance_per_cs=dcs0,
                    battery_cap=float(U.DIESEL_BATTERY_CAP),
                    charging_power=cp0,
                )
            )
            jobs.append(
                Job(
                    job_id="",
                    algorithm="greedy",
                    tag="diesel_lb",
                    instance_name=instance_name,
                    instance_path=_rel(partial_path),
                    consumption=cons0,
                    distance_per_cs=dcs0,
                    battery_cap=float(U.DIESEL_BATTERY_CAP),
                    charging_power=cp0,
                    safety_buffer_frac=float(U.DIESEL_SAFETY_BUFFER_FRAC),
                )
            )

    # Assign stable job ids after building list
    for i, job in enumerate(jobs, 1):
        jobs[i - 1] = Job(job_id=f"{i:06d}", **{k: v for k, v in asdict(job).items() if k != "job_id"})

    return jobs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset", choices=["base", "full"], default=U.DEFAULT_PRESET)
    parser.add_argument(
        "--runid",
        default="",
        help="Optional run id. If empty, a timestamp is used.",
    )
    parser.add_argument(
        "--instances",
        default="",
        help="Comma-separated instance names. Empty = use SPECIFIC_INSTANCES_TO_RUN from unified runner (or all if empty).",
    )
    parser.add_argument("--no_diesel", action="store_true")
    args = parser.parse_args()

    runid = args.runid.strip() or datetime.now().strftime("%Y%m%d_%H%M%S")

    # Determine instance filter
    only = [s.strip() for s in args.instances.split(",") if s.strip()] if args.instances.strip() else list(U.SPECIFIC_INSTANCES_TO_RUN)

    # Discover instances in both codebases, then intersect by name
    partial = _filter_instances(_discover_instances(PARTIAL_DIR / "instances"), only)
    full = _filter_instances(_discover_instances(FULL_DIR / "instances"), only)
    full_map = {n: p for n, p in full}

    instance_pairs: List[Tuple[str, Path, Path]] = []
    for name, p_path in partial:
        f_path = full_map.get(name)
        if f_path is None:
            continue
        instance_pairs.append((name, p_path, f_path))

    if not instance_pairs:
        print("No overlapping instances found between Partial and Full instances/ directories.")
        return 1

    preset = U.BASE_CASE if args.preset == "base" else U.FULL_GRID
    include_diesel = not args.no_diesel

    jobs = _build_jobs(preset, instance_pairs, include_diesel=include_diesel)

    jobs_dir = ROOT_DIR / "cluster" / "jobs" / runid
    jobs_dir.mkdir(parents=True, exist_ok=True)

    # Write each job
    for job in jobs:
        out = jobs_dir / f"job_{job.job_id}.json"
        out.write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")

    manifest = {
        "runid": runid,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "preset": args.preset,
        "include_diesel_lb": include_diesel and U.RUN_DIESEL_LOWER_BOUND,
        "instance_filter": only,
        "num_jobs": len(jobs),
        "jobs_dir": str(jobs_dir.relative_to(ROOT_DIR)),
        "project_root": str(ROOT_DIR),
    }
    (jobs_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Created {len(jobs)} jobs in: {jobs_dir}")
    print(f"Run id: {runid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## 2. `run_all.sh`

**Functionality:**

- Requires `-j <runid>` (folder under `cluster/jobs/`).
- Optional: `-r <row>` and `-n <nodes>` for manual node list (e.g. `-r 4 -n 1,2,3,4` or `-n 1:8`).
- If not provided, uses `gstat` to select up to `MAX_NODES` nodes with load below `LOAD_LIMIT` from given rows.
- Reserves nodes by creating lockdirs under `$LOCK_ROOT`; skips already reserved nodes; releases on exit (trap).
- Splits `job_*.json` across nodes (round-robin), then for each node: `ssh node "cd PROJECT_DIR; timeout ... python3 cluster/run_job.py --runid RUNID job1 job2 ..."`.
- Logs per-node stdout/stderr to `Results/Cluster/<runid>.<node>.out` and `.err`.

**Full code:**

```bash
#!/bin/bash
# Distribute all job JSONs to Solstorm compute nodes and run them via SSH (FOMO-style).
#
# Usage (manual nodes):
#   ./cluster/run_all.sh -r 4 -n 1,2,3,4
#
# Usage (auto nodes via gstat load filter):
#   ./cluster/run_all.sh
#
# Required:
# - Run from repository root on solstorm-login
# - Repo should be on shared storage, e.g. /storage/users/$USER/...
#
# Notes:
# - Reserves nodes using lockdirs under /storage/users/$USER/tdspevrp_node_locks
# - Writes outputs under Results/Cluster/

set -euo pipefail

TIMEOUT="24h"
PROJECT_DIR="$(pwd)"

NODE_ROWS="4"          # rows to pick from (auto mode)
MAX_NODES=5            # maximum number of nodes (auto mode)
LOAD_LIMIT=0.008       # don't use nodes with load higher than this (auto mode)

LOCK_ROOT="/storage/users/$USER/tdspevrp_node_locks"

RUNID=""
ROW=""
NODENUMS=""

while getopts ":r:n:j:t:" arg; do
  case ${arg} in
    r) ROW=${OPTARG} ;;
    n) NODENUMS=$(echo ${OPTARG} | awk -v RS='[,\n]' -F: 'NF == 1; NF == 2 { for (i = $1; i <= $2; ++i) print i }') ;;
    j) RUNID=${OPTARG} ;;
    t) TIMEOUT=${OPTARG} ;;
    :)
      echo "$0: Must supply an argument to -$OPTARG." >&2
      exit 1
      ;;
    ?)
      echo "Invalid option: -${OPTARG}."
      exit 2
      ;;
  esac
done

if [ -z "${RUNID}" ]; then
  echo "ERROR: missing -j <runid>. Create jobs first with: python3 cluster/create_jobs.py"
  echo "Then pass -j <runid> (same timestamp folder under cluster/jobs/)."
  exit 1
fi

JOBS_DIR="${PROJECT_DIR}/cluster/jobs/${RUNID}"
if [ ! -d "${JOBS_DIR}" ]; then
  echo "ERROR: jobs dir not found: ${JOBS_DIR}"
  exit 1
fi

mkdir -p "${LOCK_ROOT}"

# Build node list
NODES=()

if [ -n "${ROW}" ] && [ -n "${NODENUMS}" ]; then
  for i in ${NODENUMS}; do
    NODES+=("compute-${ROW}-${i}.local")
  done
else
  if ! command -v gstat >/dev/null 2>&1; then
    echo "ERROR: gstat not found; use manual mode: -r <row> -n <nodes>"
    exit 1
  fi
  mapfile -t CANDIDATES < <(gstat -i 10.1.1.1 -a1l \
    | grep "compute-[${NODE_ROWS}]" \
    | awk -v limit=${LOAD_LIMIT} '{ if(strtonum($7) < limit) printf("%s\n", $1); }' \
    | sort -r \
    | head -n ${MAX_NODES})

  for n in "${CANDIDATES[@]}"; do
    NODES+=("${n}")
  done
fi

if [ ${#NODES[@]} -eq 0 ]; then
  echo "ERROR: no nodes selected"
  exit 1
fi

# Reserve nodes (skip if already reserved)
RESERVED=()
for node in "${NODES[@]}"; do
  lockdir="${LOCK_ROOT}/${node}.lockdir"
  if mkdir "${lockdir}" 2>/dev/null; then
    echo "Reserved node: ${node}"
    RESERVED+=("${node}")
  else
    echo "Skipping node (already reserved): ${node}"
  fi
done

if [ ${#RESERVED[@]} -eq 0 ]; then
  echo "ERROR: all selected nodes are already reserved"
  exit 1
fi

cleanup() {
  for node in "${RESERVED[@]}"; do
    rm -rf "${LOCK_ROOT}/${node}.lockdir" || true
  done
}
trap cleanup EXIT

# Collect job files
mapfile -t JOBS < <(ls "${JOBS_DIR}"/job_*.json 2>/dev/null | sort)
num_nodes=${#RESERVED[@]}
num_jobs=${#JOBS[@]}

if [ ${num_jobs} -eq 0 ]; then
  echo "ERROR: no job_*.json files found in ${JOBS_DIR}"
  exit 1
fi

runs_per_node=$(python3 -c "import math; print(math.ceil(${num_jobs} / ${num_nodes}))")

echo "Runid: ${RUNID}"
echo "Jobs: ${num_jobs}"
echo "Nodes: ${num_nodes}"
echo "Jobs per node: ${runs_per_node}"
echo

node_counter=0
job_counter=0

# Clean previous node logs for this runid (local)
rm -f "Results/Cluster/${RUNID}".*.out "Results/Cluster/${RUNID}".*.err || true
mkdir -p "Results/Cluster"

while [ ${job_counter} -lt ${num_jobs} ]; do
  node="${RESERVED[$node_counter]}"
  node_counter=$((node_counter + 1))
  if [ ${node_counter} -ge ${num_nodes} ]; then
    node_counter=0
  fi

  echo "Sending to ${node}:"
  args=()
  for ((i=0; i<${runs_per_node}; i++)); do
    if [ ${job_counter} -ge ${num_jobs} ]; then
      break
    fi
    job="${JOBS[$job_counter]}"
    echo "  ${job}"
    args+=("${job}")
    job_counter=$((job_counter + 1))
  done

  # Run remotely
  ssh "${node}" "cd \"${PROJECT_DIR}\"; shopt -s huponexit; timeout \"${TIMEOUT}\" python3 cluster/run_job.py --runid \"${RUNID}\" ${args[*]}" \
    > "Results/Cluster/${RUNID}.${node}.out" \
    2> "Results/Cluster/${RUNID}.${node}.err" &

  echo
done

trap "kill 0" SIGINT
echo "Waiting for completion..."
wait

echo "All nodes finished."
echo "Raw outputs:"
echo "  Results/Cluster/output_${RUNID}.jsonl"
echo "  Results/Cluster/output_${RUNID}.csv"
```

---

## 3. `run_job.py`

**Functionality:**

- Invoked on each compute node (via SSH) with `--runid RUNID job1.json job2.json ...`.
- Loads each job JSON into a `Job` dataclass; maps `algorithm` to the correct runner script and working directory (e.g. partial vs full codebase).
- For each job: runs the child script (e.g. `single_scenario_runner.py`) with the right CLI args; expects JSON result on stdout.
- Appends each result (plus cluster metadata: runid, host, job_id, algorithm, tag) to:
  - `Results/Cluster/output_<runid>.jsonl` (one JSON object per line)
  - `Results/Cluster/output_<runid>.csv` (union of keys; first writer sets header).
- Uses a lock file (`output_<runid>.LOCK`) and `fcntl.flock` so multiple nodes can append safely. On Windows or without `fcntl`, locking is skipped (single-node or no concurrent writers).

**Dependencies:** Child runners (e.g. `single_scenario_runner.py`) that accept `--mode`, `--instance_name`, `--instance_path`, and parameter flags, and print a single JSON object to stdout.

**Full code:**

```python
#!/usr/bin/env python3
"""
Run one or more job JSON files on a compute node and append results safely.

This script is executed remotely by `cluster/run_all.sh` via SSH.
It is designed for Linux (Solstorm). It uses fcntl locks for safe appends.

Output (shared, appended by many nodes):
  Results/Cluster/output_<runid>.jsonl
  Results/Cluster/output_<runid>.csv
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


ROOT_DIR = Path(__file__).resolve().parents[1]
PARTIAL_DIR = ROOT_DIR / "Partial Recharge" / "EVTDSPalgorithmmain"
FULL_DIR = ROOT_DIR / "Full Recharge" / "EVTDSPalgorithmmain"

PARTIAL_SINGLE_SCENARIO = PARTIAL_DIR / "single_scenario_runner.py"
FULL_SINGLE_SCENARIO = FULL_DIR / "single_scenario_runner.py"


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


def _load_job(path: Path) -> Job:
    d = json.loads(path.read_text(encoding="utf-8"))
    return Job(**d)


def _run_child(script_path: Path, cwd: Path, args: List[str]) -> Dict[str, Any]:
    cmd = [sys.executable, str(script_path)] + args
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
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


def _append_csv_union(path: Path, row: Dict[str, Any]) -> None:
    """
    Append a row to a CSV while keeping a union-of-keys header.
    For cluster simplicity, we store a stable column set from the first row.
    Downstream merge_results.py rebuilds consistent CSVs from JSONL.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    fieldnames = list(row.keys())
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerow(row)


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
    else:
        raise ValueError(f"Unknown algorithm: {job.algorithm}")

    instance_abs = (ROOT_DIR / job.instance_path).resolve()
    args = [
        "--mode",
        mode,
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
    return child, cwd, args


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runid", required=True, help="Run id (folder name under cluster/jobs/).")
    parser.add_argument("job_files", nargs="+", help="One or more job JSON paths.")
    args = parser.parse_args()

    runid = args.runid
    out_dir = ROOT_DIR / "Results" / "Cluster"
    jsonl_path = out_dir / f"output_{runid}.jsonl"
    csv_path = out_dir / f"output_{runid}.csv"
    lock_path = out_dir / f"output_{runid}.LOCK"

    os.chdir(str(ROOT_DIR))

    hostname = os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "")

    for job_file in args.job_files:
        job_path = Path(job_file).resolve()
        job = _load_job(job_path)

        child, cwd, child_args = _job_to_child_args(job)
        result = _run_child(child, cwd=cwd, args=child_args)

        result["_cluster_runid"] = runid
        result["_cluster_host"] = hostname
        result["_cluster_job_file"] = str(job_path)
        result["_cluster_job_id"] = job.job_id
        result["_runner_algorithm"] = job.algorithm
        result["_runner_tag"] = job.tag or ""

        with _FileLock(lock_path):
            _append_jsonl(jsonl_path, result)
            _append_csv_union(csv_path, result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## 4. `merge_results.py`

**Functionality:**

- Reads `Results/Cluster/output_<runid>.jsonl` (one JSON object per line).
- Writes to `Results/Cluster/merged/<runid>/`:
  - `unified_results_<runid>.json` / `.csv`: all rows with a `metadata` wrapper in JSON.
  - One bundle per `_runner_algorithm`: `<algorithm>_results_<runid>.json` / `.csv`.
  - If any row has `_runner_tag == "diesel_lb"`: `diesel_lb_results_<runid>.json` / `.csv`.
- CSV is built with a union of all keys and sorted fieldnames for consistency.

**Full code:**

```python
#!/usr/bin/env python3
"""
Merge cluster raw outputs into unified-style bundles (combined + per-algorithm JSON/CSV).

Input:
  Results/Cluster/output_<runid>.jsonl

Output:
  Results/Cluster/merged/<runid>/
    unified_results_<runid>.json/.csv
    partial_labeling_results_<runid>.json/.csv
    full_labeling_results_<runid>.json/.csv
    greedy_results_<runid>.json/.csv
    diesel_lb_results_<runid>.json/.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _save_bundle(out_dir: Path, stem: str, meta: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    payload = {"metadata": meta, "results": rows}
    _write_json(out_dir / f"{stem}.json", payload)
    _write_csv(out_dir / f"{stem}.csv", rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runid", required=True)
    args = parser.parse_args()

    runid = args.runid
    raw_jsonl = ROOT_DIR / "Results" / "Cluster" / f"output_{runid}.jsonl"
    if not raw_jsonl.exists():
        print(f"ERROR: missing {raw_jsonl}")
        return 1

    rows = _read_jsonl(raw_jsonl)
    if not rows:
        print("ERROR: no rows found in jsonl")
        return 1

    out_dir = ROOT_DIR / "Results" / "Cluster" / "merged" / runid

    meta_base = {
        "runid": runid,
        "raw_input": str(raw_jsonl.relative_to(ROOT_DIR)),
        "total_rows": len(rows),
    }

    _save_bundle(out_dir, f"unified_results_{runid}", meta_base, rows)

    by_algo: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        algo = str(r.get("_runner_algorithm", "unknown"))
        by_algo.setdefault(algo, []).append(r)

    for algo, a_rows in by_algo.items():
        _save_bundle(out_dir, f"{algo}_results_{runid}", {**meta_base, "algorithm": algo, "total_rows": len(a_rows)}, a_rows)

    diesel_rows = [r for r in rows if str(r.get("_runner_tag", "")) == "diesel_lb"]
    if diesel_rows:
        _save_bundle(out_dir, f"diesel_lb_results_{runid}", {**meta_base, "tag": "diesel_lb", "total_rows": len(diesel_rows)}, diesel_rows)

    print(f"Merged outputs written to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## 5. `run_pipeline.py`

**Functionality:**

- Single entrypoint: (1) create jobs, (2) run `run_all.sh`, (3) merge results.
- Parses `--preset`, `--runid`, `--instances`, `--no_diesel`, and forwards `-r`, `-n`, `-t` to `run_all.sh`.
- Runs from project root; uses same `runid` for create_jobs, run_all, and merge_results.

**Full code:**

```python
#!/usr/bin/env python3
"""
One-command cluster pipeline:
  create_jobs -> run_all (SSH distribution) -> merge_results

This is the "single python code" entrypoint to run on Solstorm login node.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=str(cwd))
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="TDSPEVRP cluster pipeline (create_jobs -> run_all -> merge_results).")
    parser.add_argument("--preset", choices=["base", "full"], default="base")
    parser.add_argument("--runid", default="", help="Optional run id. If empty, timestamp is used.")
    parser.add_argument("--instances", default="", help="Comma-separated instance names (optional).")
    parser.add_argument("--no_diesel", action="store_true")

    parser.add_argument("-r", "--row", default="", help="Compute row for manual mode (e.g. 4).")
    parser.add_argument("-n", "--nodes", default="", help="Node numbers for manual mode (e.g. 1,2,3 or 1:8).")
    parser.add_argument("-t", "--timeout", default="", help="Timeout passed to run_all.sh (e.g. 24h, 12h).")
    args = parser.parse_args()

    runid = args.runid.strip() or datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1) Create jobs
    create_cmd = [sys.executable, "cluster/create_jobs.py", "--preset", args.preset, "--runid", runid]
    if args.instances.strip():
        create_cmd += ["--instances", args.instances.strip()]
    if args.no_diesel:
        create_cmd += ["--no_diesel"]
    _run(create_cmd, cwd=ROOT_DIR)

    # 2) Distribute + run via SSH
    run_all_cmd = ["bash", "cluster/run_all.sh", "-j", runid]
    if args.timeout.strip():
        run_all_cmd += ["-t", args.timeout.strip()]
    if args.row.strip() and args.nodes.strip():
        run_all_cmd += ["-r", args.row.strip(), "-n", args.nodes.strip()]
    _run(run_all_cmd, cwd=ROOT_DIR)

    # 3) Merge results
    merge_cmd = [sys.executable, "cluster/merge_results.py", "--runid", runid]
    _run(merge_cmd, cwd=ROOT_DIR)

    print(f"Pipeline finished. Runid: {runid}")
    print(f"Merged results: Results/Cluster/merged/{runid}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## Adapting to another project

1. **create_jobs.py**  
   Replace the import and use of `unified_experiment_runner` with your own config module that defines:
   - How to discover “instances” (e.g. `_discover_instances(instances_root)`).
   - Parameter grids (e.g. `BASE_CASE`, `FULL_GRID`) and any filters (e.g. `SPECIFIC_INSTANCES_TO_RUN`).  
   Keep the same `Job` structure (or extend it) and the same output layout: `cluster/jobs/<runid>/job_XXXXXX.json` + `manifest.json`.

2. **run_all.sh**  
   Adjust:
   - `LOCK_ROOT` to a path on your cluster’s shared storage.
   - Node hostname pattern: here `compute-${ROW}-${i}.local`; change to your cluster’s naming (e.g. `node${i}`, `cn${ROW}-${i}`).
   - If you don’t have `gstat`, require manual `-r` and `-n` or plug in your cluster’s job scheduler or node-list command.

3. **run_job.py**  
   Replace `_job_to_child_args` and the paths `PARTIAL_DIR`, `FULL_DIR`, and the single-scenario runner scripts with your project’s runners. Each runner must:
   - Accept CLI arguments that match what you put in the job JSON.
   - Print exactly one JSON object (the result) to stdout so `run_job.py` can parse and append it.

4. **merge_results.py**  
   Keep as-is for structure; optionally change how you split bundles (e.g. by a different tag or algorithm field) and add/remove optional bundles (e.g. `diesel_lb`).

5. **run_pipeline.py**  
   Keep the three-step flow; only change the arguments you pass to `create_jobs.py` and `run_all.sh` to match your presets and node selection.

Using this reference, you can hand the document (and optionally the actual files) to Cursor in another repo and ask it to implement the same cluster workflow there with your project’s config and runners.
