#!/usr/bin/env python3
"""
Run one or more job JSON files on a compute node and append results safely.

Jobs run through experiments/jobs.py (the same code path as local runs). A failed or
timed-out job is written as a row with job_status != "ok" and the next job continues.
Jobs whose job_id already has an "ok" row in results.jsonl are skipped, so a node batch
that was stopped can simply be sent again.

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
import threading
from concurrent.futures import ThreadPoolExecutor
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import fcntl  # type: ignore
except Exception:
    fcntl = None


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from experiments.jobs import Job, execute_job, job_from_dict  # noqa: E402


def _load_job(path: Path) -> Job:
    return job_from_dict(json.loads(path.read_text(encoding="utf-8")))


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


_THREAD_LOCK = threading.Lock()


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def finished_job_ids(jsonl_path: Path) -> set:
    done = set()
    if not jsonl_path.exists():
        return done
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001  (half-written line from a killed process)
                continue
            if row.get("job_status") == "ok":
                done.add(row.get("job_job_id"))
    return done


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runid", required=True, help="Run id (folder name under output/executions/).")
    parser.add_argument("--workers", type=int, default=1, help="Jobs run in parallel on this node.")
    parser.add_argument("job_files", nargs="+", help="One or more job JSON paths.")
    args = parser.parse_args()

    runid = args.runid
    from experiments.provenance import validate_run_id
    validate_run_id(runid)
    out_dir = ROOT_DIR / "output" / "executions" / runid
    jsonl_path = out_dir / "results.jsonl"
    lock_path = out_dir / "results.LOCK"
    os.chdir(str(ROOT_DIR))
    hostname = os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "")

    done = finished_job_ids(jsonl_path)
    todo = []
    for job_file in args.job_files:
        job_path = Path(job_file).resolve()
        job = _load_job(job_path)
        if job.job_id in done:
            print(f"skip {job.job_id} (already ok)", flush=True)
            continue
        todo.append((job_path, job))

    def run_one(item):
        job_path, job = item
        row = execute_job(job, extra={
            "_cluster_runid": runid,
            "_cluster_host": hostname,
            "_cluster_job_file": str(job_path),
            "_cluster_job_id": job.job_id,
        })
        with _THREAD_LOCK, _FileLock(lock_path):
            _append_jsonl(jsonl_path, row)
        print(f"{job.job_id} {job.algorithm} {job.instance_name} -> {row['job_status']}", flush=True)
        return row["job_status"]

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        statuses = list(pool.map(run_one, todo))
    bad = sum(1 for s in statuses if s != "ok")
    print(f"node done: {len(statuses)} run, {bad} not ok, {len(args.job_files) - len(todo)} skipped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
