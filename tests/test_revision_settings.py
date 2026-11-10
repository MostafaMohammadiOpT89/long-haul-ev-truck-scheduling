"""Tests for the November 2026 revision.

1. No fixed service time at charging stations in Full or Partial labeling (only charging time).
2. rest_charge_sync switch: with False, no charging overlaps a daily rest, in all three policies.
3. main_runner.py: config validation, job building, and settings reaching the solvers unchanged.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

import main_runner as mr
import policies.heuristics.driver as dh
from common.paths import BENCHMARK, ROOT
from experiments.jobs import Job, child_command, settings_mismatches

INSTANCE = "short_cl1_cu2"
INSTANCE_PATH = str(BENCHMARK / INSTANCE / f"{INSTANCE}.txt")
BASE500 = dict(consumption=1.49, distance_per_cs=60.0, battery_cap=500.0, charging_power=350.0)


def _labeling(alg):
    if alg == "full":
        import policies.labeling.full_recharge.single_scenario_runner as r
    else:
        import policies.labeling.partial_recharge.single_scenario_runner as r
    return r


def _run_labeling(alg, sync, service=0.0):
    return _labeling(alg).run_labeling_one(
        instance_name=INSTANCE, instance_path=INSTANCE_PATH, **BASE500,
        cs_service_time_h=service, rest_charge_sync=sync, solver_time_limit_min=10.0)


# ----------------------------------------------------------------- 1. CS service time
@pytest.mark.parametrize("alg", ["full", "partial"])
def test_charging_stations_have_no_service_time(alg):
    r = _labeling(alg)
    r.network.setGlobalParams(1.49, 60.0, 500.0, 350.0, 0.0, True)
    net = r.network.Network(INSTANCE_PATH, r.load_instance_matrices(INSTANCE_PATH))
    net.parse()
    cs = [n for n in net.nodes.values() if n.get("nodeType") == "CS"]
    assert cs, "instance has charging stations"
    assert all(n["serviceTime"] == 0.0 for n in cs)


@pytest.mark.parametrize("alg", ["full", "partial"])
def test_service_events_at_charging_stations_take_zero_time(alg):
    row = _run_labeling(alg, sync=True)
    assert row["feasible"]
    assert row["cs_service_time_h"] == 0.0
    timeline = row["activity_timeline"]
    for i, ev in enumerate(timeline):
        if ev.get("type") == "charge" and i > 0 and timeline[i - 1].get("type", "").startswith("service"):
            assert timeline[i - 1]["duration_minutes"] == 0.0


@pytest.mark.parametrize("alg", ["full", "partial"])
def test_solver_refuses_to_run_without_settings(alg):
    module = f"policies.labeling.{alg}_recharge.single_scenario_runner"
    cmd = [sys.executable, "-m", module, "--mode", "labeling", "--instance_name", INSTANCE,
           "--instance_path", INSTANCE_PATH, "--consumption", "1.49", "--distance_per_cs", "60",
           "--battery_cap", "500", "--charging_power", "350"]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode != 0
    assert "rest_charge_sync" in proc.stderr


# ----------------------------------------------------------------- 2. rest sync switch
@pytest.mark.parametrize("alg", ["full", "partial"])
def test_labeling_rest_sync_off_never_charges_during_rest(alg):
    on = _run_labeling(alg, sync=True)
    off = _run_labeling(alg, sync=False)
    assert on["rest_charge_sync"] is True and off["rest_charge_sync"] is False
    assert on["number_of_rest_synchronized_charging_events"] >= 1, "test instance should use rest sync"
    assert off["number_of_rest_synchronized_charging_events"] == 0
    assert off["total_route_time_hours"] >= on["total_route_time_hours"] - 1e-9


def _rest_at_cs_route():
    # 600 km with t_sync=1.5: a rest-synchronized charging stop is taken at a CS (see rule-2 test).
    return dh.driver_heuristic(_route_600(), consumption_rate=1.49, battery_capacity=750.0,
                               charging_power=350.0, distance_per_cs=60.0, policy="full", t_sync=1.5,
                               rest_charge_sync=False)


def _route_600():
    return [{"from": "O", "to": "D", "distance": 600.0, "service_time": 0.0}]


def test_driver_rest_sync_off_charges_after_the_rest():
    on = dh.driver_heuristic(_route_600(), consumption_rate=1.49, battery_capacity=750.0, charging_power=350.0,
                             distance_per_cs=60.0, policy="full", t_sync=1.5, rest_charge_sync=True)
    off = _rest_at_cs_route()
    assert on["feasible"] and off["feasible"]
    assert dh.validate_schedule(off["activity_timeline"], 750.0, 1.49) == []
    rests = [e for e in off["activity_timeline"] if e["type"] == "rest"]
    charges = [e for e in off["activity_timeline"] if e["type"] == "charge"]
    assert rests and charges
    for c in charges:
        for r in rests:
            overlap = min(c["end_time"], r["end_time"]) - max(c["start_time"], r["start_time"])
            assert overlap <= 1e-9, "charging must not overlap a daily rest"
    assert all(c["synchronized_with"] != "rest" for c in charges)
    assert off["total_time"] > on["total_time"]


def test_driver_overlap_variant_with_rest_sync_off_charges_only_what_is_needed():
    out = dh.driver_heuristic(_route_600(), consumption_rate=1.49, battery_capacity=750.0, charging_power=350.0,
                              distance_per_cs=60.0, policy="overlap", t_sync=1.5, rest_charge_sync=False)
    assert out["feasible"]
    assert dh.validate_schedule(out["activity_timeline"], 750.0, 1.49) == []


# ----------------------------------------------------------------- 3. main runner
def _cfg():
    return json.loads(json.dumps(mr.CONFIG))


def test_default_config_is_valid_and_builds_expected_jobs():
    cfg = _cfg()
    mr.validate(cfg)
    jobs = mr.build_jobs(cfg)
    by_exp = {}
    for j in jobs:
        by_exp.setdefault(j.experiment, []).append(j)
    # base (reference): Full + Partial + Driver 2 variants + diesel (Partial only)
    assert len(by_exp["base"]) == 43 * (1 + 1 + 2 + 1)
    assert all(j.rest_charge_sync for j in by_exp["base"])
    assert not any(j.tag == "diesel_lb" and j.algorithm == "driver_heuristic" for j in jobs)
    # synchronization-restriction experiment: Full + Partial + Driver 2 variants, all with sync off
    assert len(by_exp["base_rest_sync_off"]) == 43 * (1 + 1 + 2)
    assert not any(j.rest_charge_sync for j in by_exp["base_rest_sync_off"])
    # sensitivity: 4 batteries x 3 powers x 4 spacings x 3 consumptions x (Full + Partial), sync on
    assert len(by_exp["sensitivity"]) == 43 * 144 * 2
    assert all(j.rest_charge_sync for j in by_exp["sensitivity"])
    assert all(j.cs_service_time_h == 0.0 for j in jobs)
    assert len({j.job_id for j in jobs}) == len(jobs)


def test_reference_case_must_synchronize_rest_and_charging():
    cfg = _cfg()
    cfg["experiments"]["base"]["policies"]["full_labeling"]["rest_charge_sync"] = [True, False]
    with pytest.raises(SystemExit):
        mr.validate(cfg)


@pytest.mark.parametrize("path, value", [
    (("experiments", "base", "policies", "full_labeling", "rest_charge_synch"), [True]),   # typo
    (("experiments", "base", "grid", "battery"), [500]),                                    # typo
    (("run_settings", "mode"), "laptop"),
    (("experiments", "base", "policies", "partial_labeling", "rest_charge_sync"), ["no"]),
    (("run_settings", "job_timeout_min"), 10),                                               # below solver limit
])
def test_config_errors_stop_the_runner(path, value):
    cfg = _cfg()
    node = cfg
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(SystemExit):
        mr.validate(cfg)


def test_every_setting_reaches_the_solver_command():
    job = Job(job_id="1", algorithm="full_labeling", tag="", instance_name=INSTANCE, instance_path=INSTANCE_PATH,
              rest_charge_sync=False, cs_service_time_h=0.0, solver_time_limit_min=123.0, **BASE500)
    cmd = child_command(job)
    joined = " ".join(cmd)
    for part in ("--rest_charge_sync false", "--cs_service_time_h 0.0", "--solver_time_limit_min 123.0",
                 "--battery_cap 500.0", "--charging_power 350.0", "--distance_per_cs 60.0", "--consumption 1.49"):
        assert part in joined
    drv = Job(job_id="2", algorithm="driver_heuristic", tag="", instance_name=INSTANCE, instance_path=INSTANCE_PATH,
              policy="overlap", t_sync_hours=0.5, rest_charge_sync=True, **BASE500)
    joined = " ".join(child_command(drv))
    assert "--policy overlap" in joined and "--t_sync 0.5" in joined and "--rest_charge_sync true" in joined


def test_settings_check_catches_a_solver_that_ignored_a_setting():
    job = Job(job_id="1", algorithm="partial_labeling", tag="", instance_name=INSTANCE, instance_path=INSTANCE_PATH,
              rest_charge_sync=False, cs_service_time_h=0.0, solver_time_limit_min=10.0, **BASE500)
    row = _run_labeling("partial", sync=False)
    assert settings_mismatches(job, row) == []
    row["rest_charge_sync"] = True
    assert settings_mismatches(job, row)
