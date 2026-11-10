#!/usr/bin/env python3
"""
Run exactly ONE scenario for the Partial Recharge codebase and print ONE JSON object to stdout.

Mode:
  - labeling: runs the labeling algorithm (partial recharge variant)

Important: this script is intentionally self-contained and does not modify any algorithm logic.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import os
import pstats
import time
from collections import Counter
from typing import Any, Dict, Tuple

import common.arcs as arcClass
import common.csv_reader as CSVreader
import policies.labeling.partial_recharge.dominate as dominate
import policies.labeling.partial_recharge.isFeasible as isFeasible
import policies.labeling.partial_recharge.label as label
import policies.labeling.partial_recharge.network as network
from policies.labeling.partial_recharge.instanceResultClass import EnhancedInstanceResult


def load_instance_matrices(instance_path: str):
    from common.instance_io import load_city_arcs
    return load_city_arcs(instance_path)



def run_algorithm_with_profiling(net: network.Network, time_limit_seconds: float) -> Tuple[list, int, int, Counter, bool]:
    """Partial-recharge labeling algorithm runner (mirrors enhanced_main.py)."""
    networkArcs = net.paraArcs
    U = []
    P = []

    dominatedCounter = 0
    labelCounter = 0
    infeasibleReasons: Counter = Counter()
    maxRuntime = float(time_limit_seconds)
    startTime = time.time()

    startLabel = label.Label(net._getDepot(), batteryCapacity=net.batteryCap)
    import heapq

    heapq.heappush(U, (startLabel.time_min, startLabel))
    labelCounter += 1

    while U and (time.time() - startTime) <= maxRuntime:
        _, L = heapq.heappop(U)
        currentNode = L.detailedPath[-1]
        currentNodeArcs = {arc: data for arc, data in networkArcs.items() if currentNode == arc[0] and currentNode != arc[1]}

        for arc, arcData in currentNodeArcs.items():
            startNode, endNode, transitionType = arc
            if currentNode == startNode and currentNode != endNode:
                newL = L.custom_copy()
                net.invoke_REF(newL, startNode, endNode, transitionType)
                feasible, reasons = isFeasible.check_feasibility(newL)
                if feasible:
                    heapq.heappush(U, (newL.time_min, newL))
                    labelCounter += 1
                else:
                    for reason in reasons:
                        infeasibleReasons[reason] += 1

        L.done = True
        P.append(L)

        if U:
            labels_only = [lab for _, lab in U]
            dominated_indices = dominate.dominate(labels_only, cp=network.CP)
            dominatedCounter += len(dominated_indices)
            U = [(t, lab) for i, (t, lab) in enumerate(U) if i not in dominated_indices]
            for i in dominated_indices:
                P.append(labels_only[i])
            heapq.heapify(U)

    # Labels still open when the loop ends mean the time limit stopped the search early.
    timed_out = bool(U)
    return P, labelCounter, dominatedCounter, infeasibleReasons, timed_out


def run_labeling_one(
    instance_name: str,
    instance_path: str,
    consumption: float,
    distance_per_cs: float,
    battery_cap: float,
    charging_power: float,
    cs_service_time_h: float,
    rest_charge_sync: bool,
    solver_time_limit_min: float,
) -> Dict[str, Any]:
    citiesArcs = load_instance_matrices(instance_path)

    network.setGlobalParams(consumption, distance_per_cs, battery_cap, charging_power,
                            cs_service_time_h, rest_charge_sync)
    isFeasible.setGlobalParams(battery_cap)

    net = network.Network(instance_path, citiesArcs)
    net.parse()

    nCityNodes = net._getCityNodesCount()
    cityNodesList = net._getCityNodes()

    bestLabel = None
    bestTime = float("inf")

    with cProfile.Profile() as profile:
        wall_start = time.time()
        labelingAlgo, labelsGenerated, labelsDominated, infeasibleReasons, timed_out = run_algorithm_with_profiling(
            net, solver_time_limit_min * 60.0)
        solver_wall_seconds = time.time() - wall_start

        for l in labelingAlgo:
            if all(city in l.path for city in cityNodesList):
                if l.time_min < bestTime:
                    bestLabel = l
                    bestTime = l.time_min

        if bestLabel is None:
            bestTime = float("inf")
            bestLabel = "No valid path"

        stats = pstats.Stats(profile)
        total_calls = stats.total_calls
        total_time = stats.total_tt

    result = EnhancedInstanceResult(
        instanceName=instance_name,
        distancePerCS=distance_per_cs,
        batteryCap=battery_cap,
        chargingPower=charging_power,
        maxRT=battery_cap / charging_power if charging_power else 0.0,
        consumption=consumption,
        bestLabel=bestLabel,
        bestTime=bestTime,
        labelsGenerated=labelsGenerated,
        labelsDominated=labelsDominated,
        profilingStats=f"Total Calls: {total_calls}, Total Time: {total_time:.6f} seconds",
        totalTime=total_time,
        cityNodesCount=nCityNodes,
    )
    row = result.to_dict()
    # Settings echoed back so every result row records exactly what it ran with.
    row["cs_service_time_h"] = float(cs_service_time_h)
    row["rest_charge_sync"] = bool(rest_charge_sync)
    row["solver_time_limit_min"] = float(solver_time_limit_min)
    row["timed_out"] = timed_out
    row["solver_wall_seconds"] = solver_wall_seconds
    return row


def main() -> int:
    # Capture invocation cwd so we can resolve relative instance paths robustly
    invocation_cwd = os.getcwd()
    # Ensure all relative files (matrices, etc.) resolve as expected
    script_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["labeling"], required=True)
    parser.add_argument("--instance_name", required=True)
    parser.add_argument("--instance_path", required=True)
    parser.add_argument("--consumption", type=float, required=True)
    parser.add_argument("--distance_per_cs", type=float, required=True)
    parser.add_argument("--battery_cap", type=float, required=True)
    parser.add_argument("--charging_power", type=float, required=True)
    # No defaults: the main runner must pass these, so nothing falls back to an old value.
    parser.add_argument("--cs_service_time_h", type=float, required=True,
                        help="Fixed hours per charging-station visit on top of charging time (paper: 0).")
    parser.add_argument("--rest_charge_sync", choices=["true", "false"], required=True,
                        help="true: charging during the 11 h daily rest is free; false: charge after the rest.")
    parser.add_argument("--solver_time_limit_min", type=float, required=True,
                        help="Labeling search time limit in minutes; result gets timed_out=True if reached.")
    args = parser.parse_args()

    instance_path = args.instance_path
    if not os.path.isabs(instance_path):
        instance_path = os.path.abspath(os.path.join(invocation_cwd, instance_path))

    # Switch to script directory after resolving instance path
    # Inputs are absolute paths; no process-wide directory change.

    result = run_labeling_one(
        instance_name=args.instance_name,
        instance_path=instance_path,
        consumption=args.consumption,
        distance_per_cs=args.distance_per_cs,
        battery_cap=args.battery_cap,
        charging_power=args.charging_power,
        cs_service_time_h=args.cs_service_time_h,
        rest_charge_sync=args.rest_charge_sync == "true",
        solver_time_limit_min=args.solver_time_limit_min,
    )

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

