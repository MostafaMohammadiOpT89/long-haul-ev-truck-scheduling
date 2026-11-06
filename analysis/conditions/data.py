"""Validated paired results and complete-cohort selection for the current paper."""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
from common.paths import ROOT
from experiments.paper_scope import BASE, PARAMETERS, SENSITIVITIES

SOURCE = ROOT / "output/runs/summary.csv"
MEMBERS = ROOT / "instances/PAPER_INSTANCE_SET_43.txt"
CLASSES = ["short", "med", "long"]
NAMES = {"short": "Short", "med": "Medium", "long": "Long", "all": "All instances"}
TOL = 1e-7  # Hours; floating-point noise only.

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def at_base(frame, except_parameter=None):
    mask = np.ones(len(frame), dtype=bool)
    for field, value in zip(PARAMETERS, BASE):
        if field != except_parameter:
            mask &= frame[field].eq(value).to_numpy()
    return frame.loc[mask].copy()


def load_pairs():
    ids = set(MEMBERS.read_text().splitlines())
    assert len(ids) == 43
    raw = pd.read_csv(SOURCE)
    raw = raw[raw.instance_id.isin(ids) & raw.policy.eq("partial_labeling")
              & raw.record_status.eq("record_available")].copy()
    assert not raw.result_conflict.any(), "Resolve conflicting observations before plotting"
    assert raw.feasible_reported.eq(True).all()
    assert raw.makespan_hours.notna().all()
    refs = raw[raw.vehicle_type.eq("diesel_proxy") & raw.battery_kwh.eq(1e10)].copy()
    assert len(refs) == refs.instance_id.nunique() == 43
    assert set(refs.instance_id) == ids
    refs = refs[["instance_id", "makespan_hours", "model_run_id"]].rename(
        columns={"makespan_hours": "diesel_hours", "model_run_id": "diesel_model_run_id"})
    older = raw[raw.vehicle_type.eq("diesel_proxy") & raw.battery_kwh.eq(1e8)].merge(refs, on="instance_id")
    assert np.allclose(older.makespan_hours, older.diesel_hours, atol=TOL, rtol=0)
    ev = raw[raw.vehicle_type.eq("electric")].merge(refs, on="instance_id", validate="many_to_one")
    assert not ev.duplicated(["instance_id", *PARAMETERS]).any()
    assert ev.diesel_hours.gt(0).all()
    ev["gap_hours"] = ev.makespan_hours - ev.diesel_hours
    assert ev.gap_hours.ge(-TOL).all(), "Electric result below diesel reference"
    ev.loc[ev.gap_hours.abs().le(TOL), "gap_hours"] = 0.
    ev["gap_pct"] = 100 * ev.gap_hours / ev.diesel_hours
    ev["gap_minutes"] = 60 * ev.gap_hours
    ev["route_class"] = ev.instance_id.str.split("_").str[0]
    base = at_base(ev)
    assert len(base) == 43 and set(base.instance_id) == ids
    assert base.route_class.value_counts().to_dict() == {"long": 15, "med": 15, "short": 13}
    return ev, base


def summarize(frame):
    return dict(n=len(frame), diesel_hours=frame.diesel_hours.mean(),
                electric_hours=frame.makespan_hours.mean(), mean_gap_pct=frame.gap_pct.mean(),
                median_gap_pct=frame.gap_pct.median(), p90_gap_pct=frame.gap_pct.quantile(.9),
                max_gap_pct=frame.gap_pct.max(), mean_gap_minutes=frame.gap_minutes.mean(),
                max_gap_minutes=frame.gap_minutes.max(),
                zero_gap=int(frame.gap_hours.eq(0).sum()),
                within_1pct=int(frame.gap_pct.le(1).sum()),
                within_5pct=int(frame.gap_pct.le(5).sum()))


def matched_slices(ev):
    frames, cohorts, rows = {}, {}, []
    for index, param in enumerate(PARAMETERS):
        subset = at_base(ev, except_parameter=param)
        intended = sorted({BASE[index], *SENSITIVITIES[index]})
        available = sorted(subset[param].unique())
        assert set(available) <= set(intended) and BASE[index] in available
        assert len(available) >= 2
        cohort = set.intersection(*[set(g.instance_id) for _, g in subset.groupby(param)])
        assert cohort
        selected = subset[subset.instance_id.isin(cohort)].copy()
        wide = selected.pivot(index="instance_id", columns=param, values="gap_pct")
        assert wide.notna().all().all() and len(wide) == len(cohort)
        frames[param] = selected
        cohorts[param] = dict(n=len(cohort), instance_ids=sorted(cohort),
                             route_classes={c: sum(i.startswith(c + "_") for i in cohort) for c in CLASSES},
                             plotted_levels=available, unavailable_levels=sorted(set(intended) - set(available)))
        for value, group in selected.groupby(param):
            rows.append(dict(parameter=param, level=value, **summarize(group),
                             q25_gap_pct=group.gap_pct.quantile(.25), q75_gap_pct=group.gap_pct.quantile(.75)))
    return frames, cohorts, pd.DataFrame(rows)
