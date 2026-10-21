#!/usr/bin/env python3
"""
Tests for driver_heuristic.py (run from this folder: python -m pytest test_driver_heuristic.py -q
or simply: python test_driver_heuristic.py).

Covers: CS placement parity with network.py, each of the four rules, both charging policies,
the independent schedule validator, infeasibility detection, and a replay of every instance
under ./instances at the base configuration (all schedules must be feasible and valid).
"""

from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import driver_heuristic as dh  # noqa: E402

BASE = dict(consumption_rate=1.49, battery_capacity=750.0, charging_power=350.0, distance_per_cs=60.0)


def _route(*legs):
    """legs: (from, to, distance_km, service_h)."""
    return [{"from": a, "to": b, "distance": float(d), "service_time": float(s)} for a, b, d, s in legs]


def _types(out):
    return [e["type"] for e in out["activity_timeline"]]


# --------------------------------------------------------------------------- CS placement
def test_cs_positions_match_network_rule():
    assert dh.cs_positions_for_arc(50, 60) == [25.0]           # <= interval: midpoint
    assert dh.cs_positions_for_arc(60, 60) == [30.0]           # == interval: midpoint (not >)
    assert dh.cs_positions_for_arc(150, 60) == [60.0, 120.0]   # floor(150/60)=2
    assert dh.cs_positions_for_arc(180, 60) == [60.0, 120.0, 180.0]  # last CS at the end city


def test_build_stops_and_energy_to_next_opportunity():
    stops = dh.build_stops(_route(("O", "C1", 150, 0.1), ("C1", "D", 50, 0.0)), 60)
    kinds = [s["kind"] for s in stops]
    assert kinds == ["depot", "cs", "cs", "customer", "cs", "destination"]
    assert math.isclose(sum(s["dist_from_prev"] for s in stops), 200.0)
    # from depot: next CS is 60 km away
    assert math.isclose(dh.energy_to_next_opportunity(stops, 0, 2.0), 120.0)
    # from the 2nd CS (120 km): customer at 150 then CS at 175 -> 55 km
    assert math.isclose(dh.energy_to_next_opportunity(stops, 2, 2.0), 110.0)
    # from last CS: destination 25 km
    assert math.isclose(dh.energy_to_next_opportunity(stops, 4, 2.0), 50.0)


# --------------------------------------------------------------------------- rule 1
def test_rule1_short_route_no_stops():
    out = dh.driver_heuristic(_route(("O", "D", 120, 0.0)), **BASE, policy="full")
    assert out["feasible"]
    assert out["charges"] == 0 and out["breaks"] == 0 and out["rests"] == 0
    assert math.isclose(out["total_time"], 2.0)
    assert out["counters"]["cs_passed"] == 2
    assert not dh.validate_schedule(out["activity_timeline"], 750.0, 1.49)


# --------------------------------------------------------------------------- rule 2
def test_rule2_break_synchronized_at_cs_full_policy():
    # 270 km = 4.5 h driving -> break binds exactly at CS k=4 (240 km) + 0.5 h => with t_sync=1h the
    # break is taken at the CS at 240 km (time_to_break = 0.5 < 1) and charging to full overlaps it.
    out = dh.driver_heuristic(_route(("O", "D", 300, 0.0)), **BASE, policy="full", t_sync=1.0)
    assert out["feasible"]
    assert out["breaks"] == 1 and out["charges"] == 1 and out["rests"] == 0
    assert out["counters"]["rule2_sync_stops"] == 1
    assert out["counters"]["rule4_road_interruptions"] == 0
    ch = [e for e in out["activity_timeline"] if e["type"] == "charge"][0]
    br = [e for e in out["activity_timeline"] if e["type"] == "break"][0]
    assert ch["start_time"] == br["start_time"]
    assert math.isclose(ch["departure_soc_kWh"], 750.0)
    # charging to full needs (750-392.4)/350 = 1.0217 h > 0.75 h break -> idle part exists
    assert ch["idle_minutes"] > 0
    assert math.isclose(out["total_time"], 5.0 + (750 - 392.4) / 350, rel_tol=1e-6)


def test_rule2_overlap_policy_charges_only_during_break():
    out = dh.driver_heuristic(_route(("O", "D", 300, 0.0)), **BASE, policy="overlap", t_sync=1.0)
    ch = [e for e in out["activity_timeline"] if e["type"] == "charge"][0]
    assert math.isclose(ch["duration_minutes"], 45.0)
    assert math.isclose(ch["energy_kWh"], 350 * 0.75)
    assert ch["idle_minutes"] == 0
    assert math.isclose(out["total_time"], 5.0 + 0.75, rel_tol=1e-9)


def test_rule2_prefers_rest_when_both_due():
    # 9 h of driving binds the rest at 540 km. At CS 480 km: time_to_rest = 1 h (not < 1), at CS 540 km
    # both break (after break at 240 km, drive_B = 5 -> binds at 510 km, so a rule-4 break happens first)
    # Use t_sync=1.5 so at CS 480 km (time_to_rest=1.0 < 1.5) a rest is chosen although a break is due too.
    out = dh.driver_heuristic(_route(("O", "D", 600, 0.0)), **BASE, policy="full", t_sync=1.5)
    assert out["feasible"]
    assert out["rests"] >= 1
    rest_logs = [l for l in out["decision_log"] if "rule2_sync: rest" in l]
    assert rest_logs, "expected a rest-synchronized charging stop"


# --------------------------------------------------------------------------- rule 3
def test_rule3_forced_charge_takes_break_even_if_not_due():
    # Small battery: 100 kWh = 67 km range at 1.49. CS every 60 km: must charge at every CS.
    out = dh.driver_heuristic(
        _route(("O", "D", 240, 0.0)), consumption_rate=1.49, battery_capacity=100.0, charging_power=350.0,
        distance_per_cs=60.0, policy="full", t_sync=0.0,
    )
    assert out["feasible"]
    assert out["counters"]["rule3_forced_charges"] >= 3
    assert out["charges"] == out["counters"]["rule3_forced_charges"]
    # every forced charge is combined with a break (or rest)
    assert out["breaks"] + out["rests"] >= out["charges"]
    assert not dh.validate_schedule(out["activity_timeline"], 100.0, 1.49)


def test_rule3_overlap_policy_extends_only_as_required():
    # 100 kWh battery, 10 kW charger: a 0.75 h break only gives 7.5 kWh; 60 km needs 89.4 kWh.
    out = dh.driver_heuristic(
        _route(("O", "D", 180, 0.0)), consumption_rate=1.49, battery_capacity=100.0, charging_power=10.0,
        distance_per_cs=60.0, policy="overlap", t_sync=0.0,
    )
    assert out["feasible"]
    charges = [e for e in out["activity_timeline"] if e["type"] == "charge"]
    assert charges
    for c in charges:
        # departs with exactly what is needed for the next 60 km (not full)
        assert c["departure_soc_kWh"] <= 60 * 1.49 + 1e-6
        assert c["departure_soc_kWh"] >= 60 * 1.49 - 1e-6


def test_infeasible_when_gap_exceeds_range():
    out = dh.driver_heuristic(
        _route(("O", "D", 500, 0.0)), consumption_rate=1.49, battery_capacity=50.0, charging_power=350.0,
        distance_per_cs=60.0, policy="full",
    )
    assert not out["feasible"]
    assert out["reason_if_infeasible"]


# --------------------------------------------------------------------------- rule 4
def test_rule4_on_road_interruption_without_cs():
    # No CS within reach of the binding point: distance 500 km -> CS at 60..480; use huge CS spacing
    # so that the only CS is at the midpoint (250 km = 4.17 h) and the break binds at 270 km on the road.
    out = dh.driver_heuristic(
        _route(("O", "D", 500, 0.0)), consumption_rate=0.1, battery_capacity=750.0, charging_power=350.0,
        distance_per_cs=1000.0, policy="full", t_sync=0.25,
    )
    assert out["feasible"]
    assert out["counters"]["rule4_road_interruptions"] >= 1
    assert out["breaks"] >= 1 and out["charges"] == 0
    types = _types(out)
    assert "break" in types
    assert not dh.validate_schedule(out["activity_timeline"], 750.0, 0.1)


def test_rule4_daily_rest_when_driving_limit_binds():
    # 1200 km with a very large battery (no charging): 20 h driving -> 2 rests + breaks required.
    out = dh.driver_heuristic(
        _route(("O", "D", 1200, 0.0)), consumption_rate=0.01, battery_capacity=1e8, charging_power=350.0,
        distance_per_cs=60.0, policy="overlap", t_sync=0.0,
    )
    assert out["feasible"]
    assert out["rests"] == 2
    assert out["charges"] == 0
    assert not dh.validate_schedule(out["activity_timeline"], 1e8, 0.01)
    assert math.isclose(out["total_time"], 20.0 + 2 * 11 + out["breaks"] * 0.75, rel_tol=1e-9)


# --------------------------------------------------------------------------- service handling
def test_service_counts_as_elapsed_and_triggers_interruption_before_service():
    # 5.9 h elapsed on arrival, 0.5 h service would exceed 6 h elapsed-since-break -> break before service.
    out = dh.driver_heuristic(
        _route(("O", "C1", 354, 0.5), ("C1", "D", 10, 0.0)), consumption_rate=0.01, battery_capacity=1e8,
        charging_power=350.0, distance_per_cs=1000.0, policy="overlap", t_sync=0.0,
    )
    assert out["feasible"]
    assert out["counters"]["customer_interruptions"] >= 1 or out["counters"]["rule4_road_interruptions"] >= 1
    assert not dh.validate_schedule(out["activity_timeline"], 1e8, 0.01)


# --------------------------------------------------------------------------- validator
def test_validator_detects_violations():
    bad = [
        {"type": "drive", "start_time": 0.0, "end_time": 5.0, "duration_minutes": 300.0},
    ]
    errs = dh.validate_schedule(bad, 750.0, 1.49)
    assert any("drive_B" in e for e in errs)
    bad2 = [{"type": "drive", "start_time": 0.0, "end_time": 4.0, "duration_minutes": 240.0}]
    errs2 = dh.validate_schedule(bad2, 100.0, 1.49)
    assert any("SOC negative" in e for e in errs2)


def test_result_metrics_consistency():
    out = dh.driver_heuristic(_route(("O", "C1", 500, 0.2), ("C1", "D", 400, 0.0)), **BASE, policy="full")
    res = dh.DriverHeuristicResult("t", 60.0, 750.0, 350.0, 1.49, out).to_dict()
    assert res["schedule_valid"], res["validation_errors"]
    assert res["num_synchronized_events"] + res["num_unsynchronized_charging_events"] == res["num_charges"]
    assert res["num_unsynchronized_charging_events"] == 0  # every charge overlaps an interruption
    assert res["total_idle_charging_time_minutes"] >= -1e-9
    assert res["total_idle_charging_time_minutes"] <= res["total_charging_time_minutes"] + 1e-9
    tl_end = max(e["end_time"] for e in res["activity_timeline"])
    assert math.isclose(tl_end, res["total_time"], rel_tol=1e-9)


# --------------------------------------------------------------------------- all instances
def test_all_instances_feasible_and_valid_at_base_configuration():
    instances = dh.discover_instances("instances")
    assert instances, "no instances found"
    for name, path in instances:
        for pol in dh.POLICIES:
            r = dh.run_one(name, path, 1.49, 60.0, 750.0, 350.0, pol)
            assert r["feasible"], (name, pol, r.get("reason_if_infeasible"))
            assert r["schedule_valid"], (name, pol, r["validation_errors"])
            assert r["num_unsynchronized_charging_events"] == 0


if __name__ == "__main__":
    import inspect

    failures = 0
    for fname, fn in sorted(globals().items()):
        if fname.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print(f"PASS {fname}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {fname}: {e}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"ERROR {fname}: {type(e).__name__}: {e}")
    print("ALL PASSED" if failures == 0 else f"{failures} FAILED")
    raise SystemExit(1 if failures else 0)
