#!/usr/bin/env python3
"""
Run exactly ONE scenario for the Partial Recharge codebase and print ONE JSON object to stdout.

Modes:
  - labeling: runs the labeling algorithm (partial recharge variant)
  - greedy: runs the greedy scheduler (latest version in Partial Recharge)

Important: this script is intentionally self-contained and does not modify any algorithm logic.
It mirrors the inner loop of enhanced_main.py / greedy_scheduler.py but parameterizes inputs.
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



def run_algorithm_with_profiling(net: network.Network) -> Tuple[list, int, int, Counter]:
    """Partial-recharge labeling algorithm runner (mirrors enhanced_main.py)."""
    networkArcs = net.paraArcs
    U = []
    P = []

    dominatedCounter = 0
    labelCounter = 0
    infeasibleReasons: Counter = Counter()
    maxRuntime = 3000 * 60
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

    return P, labelCounter, dominatedCounter, infeasibleReasons


def run_labeling_one(
    instance_name: str,
    instance_path: str,
    consumption: float,
    distance_per_cs: float,
    battery_cap: float,
    charging_power: float,
) -> Dict[str, Any]:
    citiesArcs = load_instance_matrices(instance_path)

    network.setGlobalParams(consumption, distance_per_cs, battery_cap, charging_power)
    isFeasible.setGlobalParams(battery_cap)

    net = network.Network(instance_path, citiesArcs)
    net.parse()

    nCityNodes = net._getCityNodesCount()
    cityNodesList = net._getCityNodes()

    bestLabel = None
    bestTime = float("inf")

    with cProfile.Profile() as profile:
        labelingAlgo, labelsGenerated, labelsDominated, infeasibleReasons = run_algorithm_with_profiling(net)

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
    return result.to_dict()


def run_greedy_one(
    instance_name: str,
    instance_path: str,
    consumption: float,
    distance_per_cs: float,
    battery_cap: float,
    charging_power: float,
    safety_buffer_frac: float,
) -> Dict[str, Any]:
    # Import greedy pieces from the latest greedy in this folder
    import policies.heuristics.greedy as gs
    # Ensure child output remains pure JSON; suppress greedy_scheduler console logging
    import logging
    logging.disable(logging.CRITICAL)

    citiesArcs = load_instance_matrices(instance_path)
    depot, nodes = gs.read_test_instance(instance_path)
    if not depot or not nodes:
        return {
            "instance_id": instance_name,
            "feasible": False,
            "reason_if_infeasible": "Could not read test instance",
        }

    route = gs.create_simple_route(depot, nodes, citiesArcs)
    if not route:
        return {
            "instance_id": instance_name,
            "feasible": False,
            "reason_if_infeasible": "Could not create route",
        }

    service_time_map = {n["location"]: float(n.get("serviceTime", 0.0) or 0.0) for n in nodes}
    out = gs.greedy_scheduler(
        route,
        consumption,
        battery_cap,
        charging_power,
        distance_per_cs,
        cs_positions_map=None,
        service_time_map=service_time_map,
        include_service_times=True,
        safety_buffer_frac=safety_buffer_frac,
    )

    greedy_result = gs.GreedySchedulerResult(
        instance_id=instance_name,
        distance_per_cs=distance_per_cs,
        battery_capacity=battery_cap,
        charging_power=charging_power,
        consumption_rate=consumption,
        total_time=out["total_time"],
        num_charges=out["charges"],
        num_breaks=out["breaks"],
        num_rests=out["rests"],
        num_synchronized_events=out["synchronized_events"],
        feasible=out["feasible"],
        computation_time=out["computation_time"],
        activity_list=out.get("activity_list"),
        safety_buffer_frac=safety_buffer_frac,
    )
    return greedy_result.to_dict()


def main() -> int:
    # Capture invocation cwd so we can resolve relative instance paths robustly
    invocation_cwd = os.getcwd()
    # Ensure all relative files (matrices, etc.) resolve as expected
    script_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["labeling", "greedy"], required=True)
    parser.add_argument("--instance_name", required=True)
    parser.add_argument("--instance_path", required=True)
    parser.add_argument("--consumption", type=float, required=True)
    parser.add_argument("--distance_per_cs", type=float, required=True)
    parser.add_argument("--battery_cap", type=float, required=True)
    parser.add_argument("--charging_power", type=float, required=True)
    parser.add_argument("--safety_buffer_frac", type=float, default=0.10)
    args = parser.parse_args()

    instance_path = args.instance_path
    if not os.path.isabs(instance_path):
        instance_path = os.path.abspath(os.path.join(invocation_cwd, instance_path))

    # Switch to script directory after resolving instance path
    # Inputs are absolute paths; no process-wide directory change.

    if args.mode == "labeling":
        result = run_labeling_one(
            instance_name=args.instance_name,
            instance_path=instance_path,
            consumption=args.consumption,
            distance_per_cs=args.distance_per_cs,
            battery_cap=args.battery_cap,
            charging_power=args.charging_power,
        )
    else:
        result = run_greedy_one(
            instance_name=args.instance_name,
            instance_path=instance_path,
            consumption=args.consumption,
            distance_per_cs=args.distance_per_cs,
            battery_cap=args.battery_cap,
            charging_power=args.charging_power,
            safety_buffer_frac=args.safety_buffer_frac,
        )

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

