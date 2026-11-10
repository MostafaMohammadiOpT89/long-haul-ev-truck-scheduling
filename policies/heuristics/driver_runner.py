#!/usr/bin/env python3
"""
Run exactly ONE driver-heuristic scenario and print ONE JSON object to stdout.

Child process used by unified_experiment_runner.py and cluster/run_job.py (same contract as
single_scenario_runner.py: pure JSON on stdout, nothing else).

Example:
  python driver_heuristic_runner.py --instance_name short_cl1_cu2 \
      --instance_path instances/short_cl1_cu2/short_cl1_cu2.txt \
      --consumption 1.49 --distance_per_cs 60 --battery_cap 750 --charging_power 350 \
      --policy full [--t_sync 1.0]
"""

from __future__ import annotations

import argparse
import json
import os

import policies.heuristics.driver as dh


def main() -> int:
    invocation_cwd = os.getcwd()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser()
    parser.add_argument("--instance_name", required=True)
    parser.add_argument("--instance_path", required=True)
    parser.add_argument("--consumption", type=float, required=True)
    parser.add_argument("--distance_per_cs", type=float, required=True)
    parser.add_argument("--battery_cap", type=float, required=True)
    parser.add_argument("--charging_power", type=float, required=True)
    parser.add_argument("--policy", choices=list(dh.POLICIES), default="full")
    parser.add_argument("--t_sync", type=float, default=None, help="Hours; default distance_per_cs / speed.")
    args = parser.parse_args()

    instance_path = args.instance_path
    if not os.path.isabs(instance_path):
        instance_path = os.path.abspath(os.path.join(invocation_cwd, instance_path))
    pass  # All input paths are resolved explicitly.

    result = dh.run_one(
        instance_name=args.instance_name,
        instance_path=instance_path,
        consumption=args.consumption,
        distance_per_cs=args.distance_per_cs,
        battery_cap=args.battery_cap,
        charging_power=args.charging_power,
        policy=args.policy,
        t_sync=args.t_sync,
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
