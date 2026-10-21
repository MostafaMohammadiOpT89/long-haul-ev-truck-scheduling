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
    parser.add_argument("--preset", choices=["base", "full", "paper_base"], default="base")
    parser.add_argument("--runid", default="", help="Optional run id. If empty, timestamp is used.")
    parser.add_argument("--instances", default="", help="Comma-separated instance names (optional).")
    parser.add_argument("--no_diesel", action="store_true")
    parser.add_argument(
        "--algorithms",
        default="",
        help=(
            "Comma-separated subset passed to create_jobs.py: partial_labeling, full_labeling, greedy, driver_heuristic. "
            "Default: all."
        ),
    )

    # run_all.sh args (manual node selection)
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
    if args.algorithms.strip():
        create_cmd += ["--algorithms", args.algorithms.strip()]
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

