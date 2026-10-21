#!/usr/bin/env python3
"""
Driver-inspired sequential heuristic (TDSPEVRP, Partial Recharge codebase).

Stand-alone, self-contained module. It reads the SAME instance files and matrices as the
labeling algorithms and the greedy scheduler (instances/<name>/<name>.txt plus
<name>_DistanceMatrix.csv / <name>_TimeMatrix.csv, falling back to the master matrices),
places charging stations (CS) along each arc exactly like network.py does, and then builds
a feasible schedule sequentially along the prescribed route.

Rules (see thesis section "Driver-inspired sequential heuristic"):

  1. Drive as far as possible.
     At a CS the vehicle continues without charging if the SOC suffices to reach the next
     charging opportunity (next CS or the destination), unless rule 2 applies.
  2. Synchronize upcoming HoS interruptions.
     At a CS, if a break or a daily rest becomes mandatory within t_sync (time-to-limit
     strictly smaller than t_sync), the interruption is taken early at that CS and combined
     with charging. Daily rest is preferred. Default t_sync = distance_per_cs / speed, i.e.
     the interruption is taken here when the next CS cannot be reached before it binds.
  3. Combine necessary charging with an HoS interruption.
     If the SOC is insufficient to reach the next charging opportunity the vehicle charges
     here; the charging stop is always combined with a daily rest (if due within t_sync)
     or otherwise a break.
  4. Take unavoidable HoS interruptions when required.
     If an HoS limit becomes binding on the road (no CS reached in the preceding t_sync
     window) the required break / daily rest is taken at that point.

Charging policies:
  - "full":    charge to full capacity at every charging stop.
  - "overlap": charge only during the concurrent break / rest; if that is not enough to
               reach the next charging opportunity, extend charging only as required.

Two documented feasibility guards (not in the thesis text, but needed for a feasible schedule):
  - A break that would leave no remaining daily elapsed window (elapsed_R + break >= 13 h)
    is replaced by a daily rest (otherwise the rest would have to start right after the break).
  - A break-synchronized charging stop whose extra charging time would exceed the remaining
    daily elapsed window (13 h) is upgraded to a daily-rest-synchronized stop.

Everything the heuristic decides is written to `decision_log` so a schedule can be traced
step by step. `validate_schedule()` replays an activity timeline and verifies all HoS and
battery constraints independently of the construction code.

Stand-alone usage (same organisation as greedy_scheduler.py):
    python driver_heuristic.py            # runs all instances under ./instances with the
                                          # configuration block below, writes
                                          # Results/Driver_Heuristic_Results/...
    python driver_heuristic.py --trace    # additionally prints decision logs to stdout
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# HoS parameters (identical to network.py / greedy_scheduler.py)
# ---------------------------------------------------------------------------
driving_speed = 60.0   # km/h
maxElapsed_R = 13.0    # h elapsed since last daily rest
maxElapsed_B = 6.0     # h elapsed since last break
maxTimeDrive_B = 4.5   # h driving since last break
maxTimeDrive_R = 9.0   # h driving since last daily rest
minTimeBreak = 0.75    # h
minTimeRest = 11.0     # h

EPS = 1e-9

POLICIES = ("full", "overlap")

# ---------------------------------------------------------------------------
# Stand-alone configuration (base case of the paper; same as enhanced_main.py base scenario)
# ---------------------------------------------------------------------------
consumptionRates = [1.49]      # kWh/km
distancesPerCS = [60]          # km
batteryCaps = [750]            # kWh
CPs = [350]                    # kW
DRIVER_POLICIES = list(POLICIES)
# t_sync in hours. None -> distance_per_cs / driving_speed (one CS spacing of driving).
T_SYNC_HOURS: Optional[float] = None
SPECIFIC_INSTANCES_TO_RUN: List[str] = []   # [] = all discovered instances


# ===========================================================================
# Instance reading (mirrors greedy_scheduler.read_test_instance / create_simple_route)
# ===========================================================================
def read_test_instance(filename: str) -> Tuple[Optional[dict], List[dict]]:
    """Read an instance file (VehicleId / NodeId sections) -> (depot, nodes in route order)."""
    nodes: List[dict] = []
    depot: Optional[dict] = None
    with open(filename, "r") as f:
        reader = csv.reader(f)
        section = None
        first_vehicle_row = True
        for row in reader:
            if not row:
                continue
            if row[0].startswith("VehicleId"):
                section = "vehicles"
                continue
            if row[0].startswith("NodeId"):
                section = "nodes"
                continue
            if section == "vehicles" and first_vehicle_row:
                vehicle_id, location, location_id = row
                depot = {"id": vehicle_id, "location": location, "locationId": int(location_id)}
                first_vehicle_row = False
            elif section == "nodes":
                node_id, location, location_id, start, end, _, _, _, service = row
                nodes.append(
                    {
                        "id": node_id,
                        "location": location,
                        "locationId": int(location_id),
                        "timeWindowStart": int(start),
                        "timeWindowEnd": int(end),
                        "serviceTime": float(service),
                    }
                )
    return depot, nodes


def load_instance_matrices(instance_path: str):
    """Instance-specific matrices if present, else the master matrices in the CWD."""
    import arcClass
    import CSVreader

    instance_dir = os.path.dirname(instance_path)
    instance_name = os.path.splitext(os.path.basename(instance_path))[0]
    dpath = os.path.join(instance_dir, f"{instance_name}_DistanceMatrix.csv")
    tpath = os.path.join(instance_dir, f"{instance_name}_TimeMatrix.csv")
    if not (os.path.isfile(dpath) and os.path.isfile(tpath)):
        dpath, tpath = "Master_DistanceMatrix.csv", "Master_TimeMatrix.csv"
    return arcClass.cityArcs.createArcs(CSVreader.CSVreader(dpath), CSVreader.CSVreader(tpath))


def create_simple_route(depot: dict, nodes: List[dict], city_arcs) -> List[dict]:
    """Origin -> nodes in file order (last node is Destination). Distance = time * speed."""
    route: List[dict] = []
    current = depot
    for node in nodes:
        a, b = current["location"], node["location"]
        distance = 0.0
        if a in city_arcs and b in city_arcs[a].times:
            distance = float(city_arcs[a].times[b]) * driving_speed
        route.append(
            {
                "from": a,
                "to": b,
                "distance": distance,
                "service_time": float(node.get("serviceTime", 0.0) or 0.0),
            }
        )
        current = node
    return route


# ===========================================================================
# Stop sequence: CS placement identical to network._generateCS / greedy expand_route_with_cs
# ===========================================================================
def cs_positions_for_arc(distance_km: float, interval_km: float) -> List[float]:
    """CS positions (km from arc start). >interval: at k*interval (k=1..floor); else one at the midpoint."""
    d = float(distance_km or 0.0)
    if d > interval_km:
        n = int(math.floor(d / interval_km))
        return [k * interval_km for k in range(1, n + 1)]
    return [d / 2.0]


def build_stops(route: List[dict], distance_per_cs: float) -> List[dict]:
    """
    Expand the city route into an ordered list of stops.
    Each stop: kind in {depot, cs, customer, destination}, name, dist_from_prev (km), service (h).
    """
    if not route:
        return []
    stops: List[dict] = [{"kind": "depot", "name": route[0]["from"], "dist_from_prev": 0.0, "service": 0.0}]
    n_arcs = len(route)
    for i, seg in enumerate(route):
        d = float(seg.get("distance", 0.0) or 0.0)
        prev_pos = 0.0
        for k, pos in enumerate(cs_positions_for_arc(d, distance_per_cs)):
            stops.append(
                {
                    "kind": "cs",
                    "name": f"CS_{seg['from']}_{seg['to']}_{k}",
                    "dist_from_prev": max(0.0, pos - prev_pos),
                    "service": 0.0,
                }
            )
            prev_pos = pos
        stops.append(
            {
                "kind": "destination" if i == n_arcs - 1 else "customer",
                "name": seg["to"],
                "dist_from_prev": max(0.0, d - prev_pos),
                "service": float(seg.get("service_time", 0.0) or 0.0),
            }
        )
    return stops


def energy_to_next_opportunity(stops: List[dict], idx: int, consumption: float) -> float:
    """kWh needed from stop idx to the next CS (or the destination if no CS follows)."""
    dist = 0.0
    for j in range(idx + 1, len(stops)):
        dist += stops[j]["dist_from_prev"]
        if stops[j]["kind"] in ("cs", "destination"):
            break
    return dist * consumption


# ===========================================================================
# Core heuristic
# ===========================================================================
class _Schedule:
    """Mutable vehicle/driver state + event timeline + decision log."""

    def __init__(self, battery_capacity: float, charging_power: float, consumption: float):
        self.cap = float(battery_capacity)
        self.cp = float(charging_power)
        self.cons = float(consumption)
        self.t = 0.0
        self.soc = float(battery_capacity)
        self.drive_B = 0.0
        self.drive_R = 0.0
        self.elapsed_B = 0.0
        self.elapsed_R = 0.0
        self.timeline: List[dict] = []
        self.activity_list: List[str] = []
        self.log: List[str] = []
        self.counters = {
            "rule2_sync_stops": 0,
            "rule3_forced_charges": 0,
            "rule4_road_interruptions": 0,
            "customer_interruptions": 0,
            "cs_passed": 0,
            "guard_break_to_rest": 0,
        }

    # --- HoS helpers -------------------------------------------------------
    def time_to_break(self) -> float:
        return max(0.0, min(maxTimeDrive_B - self.drive_B, maxElapsed_B - self.elapsed_B))

    def time_to_rest(self) -> float:
        return max(0.0, min(maxTimeDrive_R - self.drive_R, maxElapsed_R - self.elapsed_R))

    def _fmt_state(self) -> str:
        return (
            f"t={self.t:.3f}h soc={self.soc:.1f}kWh dB={self.drive_B:.2f} eB={self.elapsed_B:.2f} "
            f"dR={self.drive_R:.2f} eR={self.elapsed_R:.2f}"
        )

    def _event(self, etype: str, start: float, duration: float, **extra) -> dict:
        ev = {
            "type": etype,
            "start_time": start,
            "end_time": start + duration,
            "duration_minutes": duration * 60.0,
        }
        ev.update(extra)
        self.timeline.append(ev)
        return ev

    # --- primitive actions -------------------------------------------------
    def drive(self, hours: float, location: str) -> None:
        if hours <= EPS:
            return
        self._event("drive", self.t, hours, distance_km=hours * driving_speed)
        self.activity_list.append(f"drive: {hours}")
        self.t += hours
        self.drive_B += hours
        self.drive_R += hours
        self.elapsed_B += hours
        self.elapsed_R += hours
        self.soc -= hours * driving_speed * self.cons

    def interruption(self, kind: str, location: str) -> float:
        """Take a break or a daily rest (no charging). Returns its duration (h)."""
        dur = minTimeRest if kind == "rest" else minTimeBreak
        self._event(kind, self.t, dur, location=location)
        self.activity_list.append(f"{kind}: {dur}")
        self.t += dur
        if kind == "rest":
            self.drive_R = self.drive_B = 0.0
            self.elapsed_R = self.elapsed_B = 0.0
        else:
            self.drive_B = 0.0
            self.elapsed_B = 0.0
            self.elapsed_R += dur
        return dur

    def charging_stop(self, kind: str, target_soc: float, location: str, reason: str) -> None:
        """
        Interruption `kind` (break / rest) at a CS, with charging running concurrently from
        the moment of arrival. Charging beyond the interruption counts as elapsed (not driving) time.
        """
        dur = minTimeRest if kind == "rest" else minTimeBreak
        energy = max(0.0, min(self.cap, target_soc) - self.soc)
        charge_time = energy / self.cp if self.cp > 0 else 0.0
        extra = max(0.0, charge_time - dur)

        # Guard: extra charging after a break must not exceed the remaining daily elapsed window.
        if kind == "break" and (self.elapsed_R + dur + extra) > maxElapsed_R + EPS:
            self.log.append(
                f"    guard: break + {extra:.2f}h extra charging would exceed the daily elapsed window "
                f"(eR={self.elapsed_R:.2f}) -> upgraded to daily rest"
            )
            self.counters["guard_break_to_rest"] += 1
            kind = "rest"
            dur = minTimeRest
            extra = max(0.0, charge_time - dur)

        t0 = self.t
        self._event(kind, t0, dur, location=location)
        self.activity_list.append(f"{kind}: {dur}")
        if energy > EPS:
            self._event(
                "charge",
                t0,
                charge_time,
                power_kW=self.cp,
                location=location,
                energy_kWh=energy,
                arrival_soc_kWh=self.soc,
                departure_soc_kWh=self.soc + energy,
                synchronized_with=kind,
                overlap_minutes=min(charge_time, dur) * 60.0,
                idle_minutes=extra * 60.0,
                reason=reason,
            )
            self.activity_list.append(f"charge[{kind}_sync]: {charge_time}")
        self.t = t0 + max(dur, charge_time)
        self.soc += energy
        if kind == "rest":
            self.drive_R = self.drive_B = 0.0
            self.elapsed_R = extra
            self.elapsed_B = extra
        else:
            self.drive_B = 0.0
            self.elapsed_B = extra
            self.elapsed_R += dur + extra
        self.log.append(
            f"    -> {kind} {dur:.2f}h + charge {energy:.1f}kWh in {charge_time:.2f}h "
            f"(extra beyond {kind}: {extra:.2f}h) | {self._fmt_state()}"
        )

    def service(self, hours: float, location: str) -> None:
        if hours <= EPS:
            return
        self._event("service", self.t, hours, location=location)
        self.activity_list.append(f"service@{location}: {hours}")
        self.t += hours
        self.elapsed_B += hours
        self.elapsed_R += hours


def _road_interruption_kind(s: _Schedule) -> str:
    """Rule 4 on the road: rest if the rest limit binds (or a break would leave no daily window)."""
    if s.time_to_rest() <= EPS:
        return "rest"
    if s.elapsed_R + minTimeBreak >= maxElapsed_R - EPS:
        s.counters["guard_break_to_rest"] += 1
        s.log.append("    guard: a break would leave no daily elapsed window -> daily rest instead")
        return "rest"
    return "break"


def driver_heuristic(
    route: List[dict],
    consumption_rate: float,
    battery_capacity: float,
    charging_power: float,
    distance_per_cs: float,
    policy: str = "full",
    t_sync: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build the schedule. Returns a dict with total_time (h), counts, activity_timeline, activity_list,
    decision_log, feasibility and computation_time (s). Distances in km, times in hours.
    """
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}, got {policy!r}")
    t_start = time.time()
    if t_sync is None:
        t_sync = float(distance_per_cs) / driving_speed
    t_sync = float(t_sync)

    stops = build_stops(route, distance_per_cs)
    s = _Schedule(battery_capacity, charging_power, consumption_rate)
    feasible = True
    reason_if_infeasible: Optional[str] = None
    s.log.append(
        f"policy={policy} t_sync={t_sync:.3f}h cap={battery_capacity} cp={charging_power} "
        f"cons={consumption_rate} dcs={distance_per_cs} stops={len(stops)}"
    )

    # Reachability of the first charging opportunity from the depot.
    if stops:
        need0 = energy_to_next_opportunity(stops, 0, consumption_rate)
        if need0 > s.cap + EPS:
            feasible = False
            reason_if_infeasible = (
                f"first charging opportunity needs {need0:.1f} kWh > battery {s.cap:.1f} kWh"
            )
            s.log.append(f"INFEASIBLE: {reason_if_infeasible}")

    for idx in range(1, len(stops)):
        if not feasible:
            break
        stop = stops[idx]
        leg_h = stop["dist_from_prev"] / driving_speed

        # ---- driving leg with rule 4 (on-road interruptions) ----------------------
        remaining = leg_h
        while remaining > EPS:
            delta = min(remaining, s.time_to_break(), s.time_to_rest())
            if delta > EPS:
                s.drive(delta, f"->{stop['name']}")
                remaining -= delta
            if remaining > EPS:
                kind = _road_interruption_kind(s)
                s.counters["rule4_road_interruptions"] += 1
                s.log.append(
                    f"  rule4 on road towards {stop['name']} ({remaining*driving_speed:.1f} km left): "
                    f"{kind} | {s._fmt_state()}"
                )
                s.interruption(kind, f"road->{stop['name']}")
        if s.soc < -1e-6:
            feasible = False
            reason_if_infeasible = f"battery depleted before {stop['name']} (soc={s.soc:.1f} kWh)"
            s.log.append(f"INFEASIBLE: {reason_if_infeasible}")
            break

        # ---- arrival ------------------------------------------------------------------
        if stop["kind"] == "cs":
            need = energy_to_next_opportunity(stops, idx, consumption_rate)
            must_charge = s.soc + EPS < need
            ttb, ttr = s.time_to_break(), s.time_to_rest()
            # "becomes mandatory within t_sync": time-to-limit strictly below t_sync. With
            # t_sync = CS spacing / speed this means: the next CS cannot be reached before the
            # limit binds (an interruption binding exactly at the next CS is taken there).
            rest_due = ttr < t_sync - EPS
            break_due = ttb < t_sync - EPS
            s.log.append(
                f"  at {stop['name']}: need_next={need:.1f}kWh must_charge={must_charge} "
                f"time_to_break={ttb:.2f}h time_to_rest={ttr:.2f}h | {s._fmt_state()}"
            )
            if must_charge and need > s.cap + EPS:
                feasible = False
                reason_if_infeasible = (
                    f"next charging opportunity after {stop['name']} needs {need:.1f} kWh > battery"
                )
                s.log.append(f"INFEASIBLE: {reason_if_infeasible}")
                break
            if must_charge:
                kind = "rest" if rest_due else "break"
                s.counters["rule3_forced_charges"] += 1
                reason = "rule3_forced_charge"
            elif rest_due or break_due:
                kind = "rest" if rest_due else "break"
                s.counters["rule2_sync_stops"] += 1
                reason = "rule2_sync"
            else:
                s.counters["cs_passed"] += 1
                s.log.append("    rule1: pass by (SOC sufficient, no interruption due)")
                continue
            dur = minTimeRest if kind == "rest" else minTimeBreak
            if policy == "full":
                target = s.cap
            else:  # overlap-only
                target = min(s.cap, s.soc + s.cp * dur)
                if target + EPS < need:
                    target = need  # extend only as required to restore reachability
            s.log.append(f"    {reason}: {kind} at CS, target SOC {min(target, s.cap):.1f} kWh ({policy})")
            s.charging_stop(kind, target, stop["name"], reason)
        else:
            svc = stop["service"]
            # Service counts as elapsed time: take the needed interruption before serving.
            guard = 0
            while svc > EPS and (
                s.elapsed_B + svc > maxElapsed_B + EPS or s.elapsed_R + svc > maxElapsed_R + EPS
            ):
                kind = "rest" if s.elapsed_R + svc > maxElapsed_R + EPS else "break"
                if kind == "break" and s.elapsed_R + minTimeBreak + svc > maxElapsed_R + EPS:
                    kind = "rest"
                s.counters["customer_interruptions"] += 1
                s.log.append(
                    f"  at {stop['name']}: {kind} before service ({svc:.2f}h would exceed elapsed limit) "
                    f"| {s._fmt_state()}"
                )
                s.interruption(kind, stop["name"])
                guard += 1
                if guard > 3:
                    feasible = False
                    reason_if_infeasible = f"service at {stop['name']} cannot be scheduled within HoS"
                    break
            if not feasible:
                s.log.append(f"INFEASIBLE: {reason_if_infeasible}")
                break
            s.service(svc, stop["name"])
            s.log.append(f"  at {stop['name']} ({stop['kind']}): service {svc:.3f}h | {s._fmt_state()}")

    comp = time.time() - t_start
    charges = [e for e in s.timeline if e["type"] == "charge"]
    breaks = [e for e in s.timeline if e["type"] == "break"]
    rests = [e for e in s.timeline if e["type"] == "rest"]
    s.log.append(
        f"DONE feasible={feasible} total_time={s.t:.3f}h charges={len(charges)} breaks={len(breaks)} "
        f"rests={len(rests)} final_soc={s.soc:.1f}kWh"
    )
    return {
        "total_time": s.t,
        "charges": len(charges),
        "breaks": len(breaks),
        "rests": len(rests),
        "feasible": feasible,
        "reason_if_infeasible": reason_if_infeasible,
        "computation_time": comp,
        "activity_timeline": s.timeline,
        "activity_list": s.activity_list,
        "decision_log": s.log,
        "counters": dict(s.counters),
        "final_soc_kWh": s.soc,
        "t_sync_hours": t_sync,
        "policy": policy,
        "n_stops": len(stops),
        "n_cs": sum(1 for st in stops if st["kind"] == "cs"),
    }


# ===========================================================================
# Independent validator (replays the timeline; used by tests and the result class)
# ===========================================================================
def validate_schedule(
    timeline: List[dict], battery_capacity: float, consumption: float, tol: float = 1e-6
) -> List[str]:
    """
    Replay a timeline and return a list of violations (empty = valid).
    Checks: driving / elapsed HoS limits, SOC within [0, cap], and interruption durations.
    Charging overlapping an interruption is accounted as elapsed time only beyond the interruption.
    """
    errs: List[str] = []
    events = sorted(timeline, key=lambda e: (float(e["start_time"]), 0 if e["type"] != "charge" else 1))
    dB = dR = eB = eR = 0.0
    soc = float(battery_capacity)
    cap = float(battery_capacity)
    t_cursor = 0.0
    i = 0
    while i < len(events):
        e = events[i]
        et = e["type"]
        dur = float(e["duration_minutes"]) / 60.0
        if float(e["start_time"]) < t_cursor - tol:
            errs.append(f"overlapping events at t={e['start_time']:.3f} ({et})")
        if et == "drive":
            dB += dur
            dR += dur
            eB += dur
            eR += dur
            soc -= dur * driving_speed * consumption
            if soc < -tol:
                errs.append(f"SOC negative ({soc:.2f} kWh) after drive ending t={e['end_time']:.3f}")
            t_cursor = float(e["end_time"])
        elif et in ("break", "rest"):
            need = minTimeRest if et == "rest" else minTimeBreak
            if dur + tol < need:
                errs.append(f"{et} shorter than minimum at t={e['start_time']:.3f}")
            extra = 0.0
            # concurrent charge event(s) starting at the same time
            j = i + 1
            while j < len(events) and abs(float(events[j]["start_time"]) - float(e["start_time"])) <= tol:
                c = events[j]
                if c["type"] == "charge":
                    cdur = float(c["duration_minutes"]) / 60.0
                    soc += cdur * float(c.get("power_kW", 0.0))
                    if soc > cap + 1e-3:
                        errs.append(f"SOC above capacity ({soc:.2f}) after charge at t={c['start_time']:.3f}")
                    extra = max(extra, cdur - dur)
                j += 1
            if et == "rest":
                dR = dB = 0.0
                eR = eB = extra
            else:
                dB = 0.0
                eB = extra
                eR += dur + extra
            t_cursor = float(e["start_time"]) + dur + extra
            i = j
            continue
        elif et == "charge":
            # charge without concurrent interruption (never produced by this heuristic)
            soc += dur * float(e.get("power_kW", 0.0))
            eB += dur
            eR += dur
            t_cursor = float(e["end_time"])
        elif et.startswith("service"):
            eB += dur
            eR += dur
            t_cursor = float(e["end_time"])
        if dB > maxTimeDrive_B + tol:
            errs.append(f"drive_B={dB:.3f} > {maxTimeDrive_B} after {et} ending t={t_cursor:.3f}")
        if dR > maxTimeDrive_R + tol:
            errs.append(f"drive_R={dR:.3f} > {maxTimeDrive_R} after {et} ending t={t_cursor:.3f}")
        if eB > maxElapsed_B + tol:
            errs.append(f"elapsed_B={eB:.3f} > {maxElapsed_B} after {et} ending t={t_cursor:.3f}")
        if eR > maxElapsed_R + tol:
            errs.append(f"elapsed_R={eR:.3f} > {maxElapsed_R} after {et} ending t={t_cursor:.3f}")
        i += 1
    return errs


# ===========================================================================
# Result container (same metric definitions as GreedySchedulerResult / METRICS_CALCULATION_RULES.md)
# ===========================================================================
class DriverHeuristicResult:
    def __init__(
        self,
        instance_id: str,
        distance_per_cs: float,
        battery_capacity: float,
        charging_power: float,
        consumption_rate: float,
        out: Dict[str, Any],
    ):
        self.instance_id = instance_id
        self.distance_per_cs = distance_per_cs
        self.battery_capacity = battery_capacity
        self.charging_power = charging_power
        self.consumption_rate = consumption_rate
        self.policy = out["policy"]
        self.t_sync_hours = out["t_sync_hours"]
        self.total_time = out["total_time"]
        self.num_charges = out["charges"]
        self.num_breaks = out["breaks"]
        self.num_rests = out["rests"]
        self.feasible = bool(out["feasible"])
        self.reason_if_infeasible = out.get("reason_if_infeasible")
        self.computation_time = out["computation_time"]
        self.activity_timeline = out["activity_timeline"]
        self.activity_list = out["activity_list"]
        self.decision_log = out["decision_log"]
        self.counters = out["counters"]
        self.final_soc_kWh = out["final_soc_kWh"]
        self.n_cs_on_route = out["n_cs"]
        self.validation_errors = validate_schedule(self.activity_timeline, battery_capacity, consumption_rate)
        self._sync_metrics()

    def _sync_metrics(self) -> None:
        tl = self.activity_timeline
        charges = [e for e in tl if e["type"] == "charge"]
        breaks = [e for e in tl if e["type"] == "break"]
        rests = [e for e in tl if e["type"] == "rest"]
        synced = 0
        overlap_total_h = 0.0
        used_b, used_r = set(), set()
        for c in charges:
            cs, ce = c["start_time"], c["end_time"]
            is_sync = False
            best = 0.0
            for k, r in enumerate(rests):
                o = min(ce, r["end_time"]) - max(cs, r["start_time"])
                if o > 0:
                    is_sync = True
                    best = max(best, o)
                    used_r.add(k)
            for k, b in enumerate(breaks):
                o = min(ce, b["end_time"]) - max(cs, b["start_time"])
                if o > 0:
                    is_sync = True
                    best = max(best, o)
                    used_b.add(k)
            if is_sync:
                synced += 1
                overlap_total_h += best
        self.num_synchronized_events = synced
        self.num_unsynchronized_charging_events = len(charges) - synced
        self.num_unsynchronized_breaks = len(breaks) - len(used_b)
        self.num_unsynchronized_rests = len(rests) - len(used_r)
        self.total_charging_time_minutes = sum(e["duration_minutes"] for e in charges)
        self.total_idle_charging_time_minutes = max(0.0, self.total_charging_time_minutes - overlap_total_h * 60.0)
        self.percentage_of_charging_events_synchronized = (synced / len(charges) * 100.0) if charges else 0.0
        self.total_energy_charged_kWh = sum(float(e.get("energy_kWh", 0.0)) for e in charges)
        self.num_charges_sync_with_rest = sum(1 for e in charges if e.get("synchronized_with") == "rest")
        self.num_charges_sync_with_break = sum(1 for e in charges if e.get("synchronized_with") == "break")
        self.total_driving_time_hours = sum(e["duration_minutes"] for e in tl if e["type"] == "drive") / 60.0
        self.total_service_time_hours = sum(e["duration_minutes"] for e in tl if e["type"] == "service") / 60.0
        self.total_break_time_hours = sum(e["duration_minutes"] for e in breaks) / 60.0
        self.total_rest_time_hours = sum(e["duration_minutes"] for e in rests) / 60.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "distance_per_cs": self.distance_per_cs,
            "battery_capacity": self.battery_capacity,
            "charging_power": self.charging_power,
            "consumption_rate": self.consumption_rate,
            "policy": self.policy,
            "t_sync_hours": self.t_sync_hours,
            "total_time": self.total_time,
            "num_charges": self.num_charges,
            "num_breaks": self.num_breaks,
            "num_rests": self.num_rests,
            "num_synchronized_events": self.num_synchronized_events,
            "num_unsynchronized_charging_events": self.num_unsynchronized_charging_events,
            "num_unsynchronized_breaks": self.num_unsynchronized_breaks,
            "num_unsynchronized_rests": self.num_unsynchronized_rests,
            "num_charges_sync_with_rest": self.num_charges_sync_with_rest,
            "num_charges_sync_with_break": self.num_charges_sync_with_break,
            "total_charging_time_minutes": self.total_charging_time_minutes,
            "total_idle_charging_time_minutes": self.total_idle_charging_time_minutes,
            "percentage_of_charging_events_synchronized": self.percentage_of_charging_events_synchronized,
            "total_energy_charged_kWh": self.total_energy_charged_kWh,
            "final_soc_kWh": self.final_soc_kWh,
            "total_driving_time_hours": self.total_driving_time_hours,
            "total_service_time_hours": self.total_service_time_hours,
            "total_break_time_hours": self.total_break_time_hours,
            "total_rest_time_hours": self.total_rest_time_hours,
            "num_rule2_sync_stops": self.counters["rule2_sync_stops"],
            "num_rule3_forced_charges": self.counters["rule3_forced_charges"],
            "num_rule4_road_interruptions": self.counters["rule4_road_interruptions"],
            "num_customer_interruptions": self.counters["customer_interruptions"],
            "num_cs_passed": self.counters["cs_passed"],
            "num_guard_break_to_rest": self.counters["guard_break_to_rest"],
            "num_cs_on_route": self.n_cs_on_route,
            "feasible": self.feasible,
            "reason_if_infeasible": self.reason_if_infeasible,
            "schedule_valid": len(self.validation_errors) == 0,
            "validation_errors": self.validation_errors,
            "computation_time": self.computation_time,
            "synchronization_enabled": True,
            "activity_timeline": self.activity_timeline,
            "decision_log": self.decision_log,
        }

    CSV_EXCLUDE = ("decision_log",)

    def to_csv_row(self) -> Dict[str, Any]:
        d = self.to_dict()
        return {k: v for k, v in d.items() if k not in self.CSV_EXCLUDE}


# ===========================================================================
# One scenario end-to-end (used by the runner script and by main())
# ===========================================================================
def run_one(
    instance_name: str,
    instance_path: str,
    consumption: float,
    distance_per_cs: float,
    battery_cap: float,
    charging_power: float,
    policy: str,
    t_sync: Optional[float] = None,
) -> Dict[str, Any]:
    city_arcs = load_instance_matrices(instance_path)
    depot, nodes = read_test_instance(instance_path)
    if not depot or not nodes:
        return {"instance_id": instance_name, "policy": policy, "feasible": False,
                "reason_if_infeasible": "Could not read test instance"}
    route = create_simple_route(depot, nodes, city_arcs)
    out = driver_heuristic(route, consumption, battery_cap, charging_power, distance_per_cs, policy, t_sync)
    return DriverHeuristicResult(instance_name, distance_per_cs, battery_cap, charging_power, consumption, out).to_dict()


def discover_instances(instances_dir: str = "instances") -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    if not os.path.isdir(instances_dir):
        return found
    for item in sorted(os.listdir(instances_dir), key=str.lower):
        p = os.path.join(instances_dir, item)
        if not os.path.isdir(p):
            continue
        preferred = os.path.join(p, f"{item}.txt")
        if os.path.exists(preferred):
            found.append((item, preferred))
        else:
            txts = [f for f in os.listdir(p) if f.endswith(".txt")]
            if txts:
                found.append((item, os.path.join(p, txts[0])))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Driver-inspired heuristic: stand-alone batch run.")
    parser.add_argument("--trace", action="store_true", help="Print decision logs to stdout.")
    parser.add_argument("--instances", default="", help="Comma-separated instance names (default: all).")
    parser.add_argument("--policies", default=",".join(DRIVER_POLICIES))
    parser.add_argument(
        "--t_sync",
        default="",
        help="t_sync in hours; comma-separated list runs a sweep (default: T_SYNC_HOURS, i.e. distance_per_cs / speed when None).",
    )
    parser.add_argument("--out_suffix", default="", help="Optional suffix for the output file names (e.g. tsync_sweep).")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    policies = [p.strip() for p in args.policies.split(",") if p.strip()]
    only = [s.strip() for s in args.instances.split(",") if s.strip()] or list(SPECIFIC_INSTANCES_TO_RUN)

    instances = discover_instances("instances")
    if only:
        instances = [(n, p) for n, p in instances if n in only]
    if not instances:
        print("No instances found.")
        return 1

    t_sync_values: List[Optional[float]] = (
        [float(x) for x in args.t_sync.split(",") if x.strip()] if args.t_sync.strip() else [T_SYNC_HOURS]
    )
    results: List[Dict[str, Any]] = []
    trace_lines: List[str] = []
    print(f"Driver heuristic: {len(instances)} instances x {len(policies)} policies x {len(t_sync_values)} t_sync values")
    for name, path in instances:
        for cp in CPs:
            for bc in batteryCaps:
                for cons in consumptionRates:
                    for dcs in distancesPerCS:
                        for t_sync in t_sync_values:
                            for pol in policies:
                                r = run_one(name, path, cons, dcs, bc, cp, pol, t_sync)
                                r["_runner_algorithm"] = "driver_heuristic"
                                r["_runner_tag"] = ""
                                results.append(r)
                                print(
                                    f"  {name:28s} {pol:8s} t_sync={r.get('t_sync_hours', float('nan')):.2f} "
                                    f"time={r.get('total_time', float('nan')):8.3f}h "
                                    f"charges={r.get('num_charges')} breaks={r.get('num_breaks')} rests={r.get('num_rests')} "
                                    f"feasible={r.get('feasible')} valid={r.get('schedule_valid')}"
                                )
                                trace_lines.append(
                                    f"=== {name} | policy={pol} | t_sync={r.get('t_sync_hours')} | cp={cp} bc={bc} cons={cons} dcs={dcs} ==="
                                )
                                trace_lines.extend(r.get("decision_log", []))
                                trace_lines.append("")
                                if args.trace:
                                    print("\n".join(r.get("decision_log", [])))

    out_dir = os.path.join("Results", "Driver_Heuristic_Results")
    os.makedirs(out_dir, exist_ok=True)
    suffix = f"_{args.out_suffix.strip()}" if args.out_suffix.strip() else ""
    stem = os.path.join(out_dir, f"driver_heuristic_results{suffix}_{timestamp}")
    with open(stem + ".json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": {
                    "timestamp": timestamp,
                    "algorithm": "driver_heuristic",
                    "total_scenarios": len(results),
                    "parameters": {
                        "consumption_rates": consumptionRates,
                        "distances_per_cs": distancesPerCS,
                        "battery_capacities": batteryCaps,
                        "charging_powers": CPs,
                        "policies": policies,
                        "t_sync_hours": t_sync_values,
                    },
                },
                "results": results,
            },
            f,
            indent=2,
        )
    rows = [{k: v for k, v in r.items() if k not in DriverHeuristicResult.CSV_EXCLUDE} for r in results]
    fieldnames = sorted({k for r in rows for k in r})
    with open(stem + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(os.path.join(out_dir, f"driver_heuristic_trace{suffix}_{timestamp}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(trace_lines))
    n_feas = sum(1 for r in results if r.get("feasible"))
    n_valid = sum(1 for r in results if r.get("schedule_valid"))
    print(f"Saved {stem}.json / .csv (+ trace). Feasible {n_feas}/{len(results)}, valid schedules {n_valid}/{len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
