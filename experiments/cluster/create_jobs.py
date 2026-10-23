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
from typing import Dict, FrozenSet, List, Optional, Tuple

ALLOWED_ALGORITHMS: FrozenSet[str] = frozenset({"partial_labeling", "full_labeling", "greedy", "driver_heuristic"})


ROOT_DIR = Path(__file__).resolve().parents[2]
PARTIAL_DIR = ROOT_DIR / "policies" / "labeling" / "partial_recharge"
FULL_DIR = ROOT_DIR / "policies" / "labeling" / "full_recharge"


# Import configuration from unified runner (single source of truth).
import sys
sys.path.insert(0, str(ROOT_DIR))
import experiments.run as U


@dataclass(frozen=True)
class Job:
    job_id: str
    algorithm: str  # partial_labeling | full_labeling | greedy | driver_heuristic
    tag: str  # "" or "diesel_lb"
    instance_name: str
    instance_path: str  # path relative to ROOT_DIR (portable on cluster)
    consumption: float
    distance_per_cs: float
    battery_cap: float
    charging_power: float
    safety_buffer_frac: Optional[float] = None
    policy: Optional[str] = None  # driver_heuristic: "full" | "overlap"
    t_sync_hours: Optional[float] = None  # driver_heuristic (None -> default)


def _discover_instances(instances_root: Path) -> List[Tuple[str, Path]]:
    return U._discover_instances(instances_root)  # reuse the exact discovery logic


def _filter_instances(instances: List[Tuple[str, Path]], only: List[str]) -> List[Tuple[str, Path]]:
    if not only:
        return instances
    wanted = set(only)
    return [(n, p) for n, p in instances if n in wanted]


def _rel(p: Path) -> str:
    return str(p.resolve().relative_to(ROOT_DIR.resolve()))


def _parse_algorithms(arg: str) -> FrozenSet[str]:
    """Empty / whitespace-only string means all algorithms."""
    if not arg.strip():
        return ALLOWED_ALGORITHMS
    parts = [p.strip() for p in arg.split(",") if p.strip()]
    if not parts:
        return ALLOWED_ALGORITHMS
    unknown = set(parts) - ALLOWED_ALGORITHMS
    if unknown:
        raise SystemExit(
            f"Unknown algorithm(s): {sorted(unknown)}. "
            f"Allowed (comma-separated): {', '.join(sorted(ALLOWED_ALGORITHMS))}"
        )
    return frozenset(parts)


def _build_jobs(
    preset: Dict,
    instance_pairs: List[Tuple[str, Path, Path]],
    include_diesel: bool,
    algorithms: FrozenSet[str],
) -> List[Job]:
    jobs: List[Job] = []

    safety_fracs = preset["safety_buffer_fracs"]

    # Main grid (same enumeration as unified_experiment_runner.iter_preset_parameter_combinations)
    for instance_name, partial_path, full_path in instance_pairs:
        for cons, dcs, bc, cp in U.iter_preset_parameter_combinations(preset):
            if "partial_labeling" in algorithms:
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
            if "full_labeling" in algorithms:
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
            if "greedy" in algorithms:
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
            if "driver_heuristic" in algorithms:
                for pol, sync in U.driver_options(preset):
                    jobs.append(
                        Job(
                            job_id="",
                            algorithm="driver_heuristic",
                            tag="",
                            instance_name=instance_name,
                            instance_path=_rel(partial_path),
                            consumption=float(cons),
                            distance_per_cs=float(dcs),
                            battery_cap=float(bc),
                            charging_power=float(cp),
                            policy=pol,
                            t_sync_hours=sync,
                        )
                    )

        # Diesel/LB: anchor from the preset (works with list or dict charging_powers)
        if include_diesel and U.RUN_DIESEL_LOWER_BOUND:
            cons0, dcs0, cp0 = U.diesel_anchor_params(preset)
            if "partial_labeling" in algorithms:
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
            if "greedy" in algorithms:
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
            if "driver_heuristic" in algorithms:
                jobs.append(
                    Job(
                        job_id="",
                        algorithm="driver_heuristic",
                        tag="diesel_lb",
                        instance_name=instance_name,
                        instance_path=_rel(partial_path),
                        consumption=cons0,
                        distance_per_cs=dcs0,
                        battery_cap=float(U.DIESEL_BATTERY_CAP),
                        charging_power=cp0,
                        policy=U.DIESEL_DRIVER_POLICY,
                        t_sync_hours=U.DIESEL_DRIVER_T_SYNC,
                    )
                )

    # Assign stable job ids after building list
    for i, job in enumerate(jobs, 1):
        jobs[i - 1] = Job(job_id=f"{i:06d}", **{k: v for k, v in asdict(job).items() if k != "job_id"})

    return jobs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset", choices=sorted(U.PRESETS.keys()), required=True)
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
    parser.add_argument(
        "--algorithms",
        default="",
        help=(
            "Comma-separated subset of: partial_labeling, full_labeling, greedy, driver_heuristic. "
            "Default: all."
        ),
    )
    args = parser.parse_args()

    from experiments.provenance import create_manifest, save_manifest, validate_run_id
    runid = args.runid.strip() or datetime.now().strftime("%Y%m%d_%H%M%S")

    # Determine instance filter
    only = [s.strip() for s in args.instances.split(",") if s.strip()] if args.instances.strip() else list(U.SPECIFIC_INSTANCES_TO_RUN)

    # Discover instances in both codebases, then intersect by name
    partial = _filter_instances(_discover_instances(ROOT_DIR / "instances" / "benchmark_v1"), only)
    full = _filter_instances(_discover_instances(ROOT_DIR / "instances" / "benchmark_v1"), only)
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

    preset = U.PRESETS[args.preset]
    include_diesel = not args.no_diesel
    algorithms = _parse_algorithms(args.algorithms)

    jobs = _build_jobs(preset, instance_pairs, include_diesel=include_diesel, algorithms=algorithms)

    validate_run_id(runid)
    run_dir = ROOT_DIR / "output" / "runs" / runid
    if run_dir.exists():
        raise FileExistsError(f"Run already exists: {run_dir}")
    jobs_dir = run_dir / "jobs"
    jobs_dir.mkdir(parents=True)
    for job in jobs:
        (jobs_dir / f"job_{job.job_id}.json").write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")
    manifest = create_manifest(args.preset, preset, jobs)
    manifest.update(status="prepared", executor="cluster", num_jobs=len(jobs))
    save_manifest(run_dir, manifest)

    print(f"Created {len(jobs)} jobs in: {jobs_dir}")
    print(f"Run id: {runid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

