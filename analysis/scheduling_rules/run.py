"""
Driver-heuristic post-analysis (base scenario).

Compares the driver-inspired sequential heuristic (two charging policies) with the existing strategies:
Full recharge (labeling), Partial recharge (labeling), Greedy scheduler and the diesel proxy
(partial labeling with a very large battery).

Inputs pinned by analysis/configs/paper_inputs.json:
  - unified_results_*.csv (+ greedy_results_*.csv)            -> loaded through analyze.py (unchanged logic)
  - driver_heuristic_results_<timestamp>.csv                    -> latest headline run (default t_sync)
  - driver_heuristic_results_tsync_sweep_<timestamp>.csv        -> optional t_sync sensitivity sweep

Outputs:
  analysis/scheduling_rules/figures/*.png
  analysis/scheduling_rules/tables/*.csv
  analysis/scheduling_rules/report.md

Strategy keys used here: Full, Partial, Greedy, Driver_FC (full-charge policy), Driver_OO (overlap-only policy),
Partial_Diesel_LB. Driver rows are restricted to the EV base configuration (battery/CS spacing/power/consumption
equal to analyze.BASE_SCENARIO_*) and to HEADLINE_T_SYNC_HOURS when the file contains several t_sync values.

Run: python -m analysis.scheduling_rules.run (from the repository root)
"""

from __future__ import annotations

from analysis.common.inputs import input_source, ANALYSIS_OUTPUT, record_inputs
from common.results import read_frame
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import analysis.charging_strategies.run as A  # reuse loaders, masks, id map, formatting and figure style

import matplotlib.pyplot as plt

BASE_DIR = A.BASE_DIR
BASE_SCENARIO_DIR = A.BASE_SCENARIO_DIR
OUT_DIR = ANALYSIS_OUTPUT / "scheduling_rules"
record_inputs(OUT_DIR)
FIG_DIR = OUT_DIR / "figures"
TBL_DIR = OUT_DIR / "tables"
FIG_DIR.mkdir(parents=True, exist_ok=True)
TBL_DIR.mkdir(parents=True, exist_ok=True)

# Headline t_sync (hours). None -> the single value found in the file, else the value closest to
# distance_per_cs / 60 km/h (= 1.0 h at the base scenario).
HEADLINE_T_SYNC_HOURS: float | None = None

STRATEGIES = ["Full", "Partial", "Greedy", "Driver_FC", "Driver_OO", "Partial_Diesel_LB"]
LABELS = {
    "Full": "Full Recharge",
    "Partial": "Partial Recharge",
    "Greedy": "Greedy",
    "Driver_FC": "Driver heuristic (full charge)",
    "Driver_OO": "Driver heuristic (overlap-only)",
    "Partial_Diesel_LB": "Diesel proxy (high battery)",
}
COLORS = {
    "Full": "#5B8FA3",
    "Partial": "#E07B4D",
    "Greedy": "#4A7C59",
    "Driver_FC": "#6B3FA0",
    "Driver_OO": "#B98BD1",
    "Partial_Diesel_LB": "#C9A227",
}
POLICY_TO_STRATEGY = {"full": "Driver_FC", "overlap": "Driver_OO"}

# metric name candidates per strategy family (labeling / greedy / driver)
METRIC_CANDIDATES = {
    "n_charges": ("number_of_cs_stops", "num_charges"),
    "n_breaks": ("number_of_breaks", "num_breaks"),
    "n_rests": ("number_of_rests", "num_rests"),
    "n_sync_events": ("number_of_synchronized_events", "num_synchronized_events"),
    "n_unsync_charges": ("number_of_unsynchronized_charging_events", "num_unsynchronized_charging_events"),
    "pct_charge_sync": ("percentage_of_charging_events_synchronized",),
    "idle_charging_min": ("total_idle_charging_time_minutes",),
    "n_unsync_breaks": ("number_of_unsynchronized_breaks", "num_unsynchronized_breaks"),
    "n_unsync_rests": ("number_of_unsynchronized_rests", "num_unsynchronized_rests"),
}


# ----------------------------------------------------------------------------- loading


def find_driver_files() -> tuple[Path, Path]:
    return input_source("driver_headline"), input_source("driver_sync")


def _driver_ev_mask(df: pd.DataFrame) -> pd.Series:
    m = pd.Series(True, index=df.index)
    if "_runner_tag" in df.columns:
        m &= df["_runner_tag"].astype(str).str.lower() != "diesel_lb"
    for col, target, atol in (
        ("battery_capacity", A.BASE_SCENARIO_BATTERY_KWH, 0.51),
        ("distance_per_cs", A.BASE_SCENARIO_CS_INTERVAL_KM, 1e-4),
        ("charging_power", A.BASE_SCENARIO_CHARGING_POWER_KW, 1e-4),
        ("consumption_rate", A.BASE_SCENARIO_CONSUMPTION_KWH_PER_KM, 1e-6),
    ):
        if col in df.columns:
            v = pd.to_numeric(df[col], errors="coerce")
            m &= v.isna() | np.isclose(v, target, rtol=0.0, atol=atol)
    return m


def prepare_driver_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "_runner_algorithm" in df:
        df = df[df["_runner_algorithm"] == "driver_heuristic"].copy()
    df["instance_clean"] = df["instance_id"].astype(str).str.replace("TB_", "")
    df["route_time"] = pd.to_numeric(df["total_time"], errors="coerce")
    df["comp_time_sec"] = pd.to_numeric(df.get("computation_time"), errors="coerce")
    df["problem_size"] = df["instance_clean"].apply(A.get_problem_size)
    df["balance"] = df["instance_clean"].apply(A.get_balance)
    df["strategy"] = df["policy"].astype(str).str.lower().map(POLICY_TO_STRATEGY).fillna("Driver_other")
    if "t_sync_hours" in df.columns:
        df["t_sync_hours"] = pd.to_numeric(df["t_sync_hours"], errors="coerce")
    if "feasible" in df.columns:
        df["feasible"] = df["feasible"].astype(str).str.lower().isin(("true", "1"))
    return df


def load_driver_headline(path: Path) -> tuple[pd.DataFrame, float | None]:
    df = prepare_driver_df(read_frame(path))
    df = df.loc[_driver_ev_mask(df)]
    if A.EXCLUDED_INSTANCE_IDS:
        df = df[~df["instance_clean"].isin(set(A.EXCLUDED_INSTANCE_IDS))]
    t_used: float | None = None
    if "t_sync_hours" in df.columns and df["t_sync_hours"].notna().any():
        vals = sorted(df["t_sync_hours"].dropna().unique())
        if HEADLINE_T_SYNC_HOURS is not None:
            t_used = float(min(vals, key=lambda v: abs(v - HEADLINE_T_SYNC_HOURS)))
        elif len(vals) == 1:
            t_used = float(vals[0])
        else:
            default = A.BASE_SCENARIO_CS_INTERVAL_KM / 60.0
            t_used = float(min(vals, key=lambda v: abs(v - default)))
        df = df[np.isclose(df["t_sync_hours"], t_used)]
    return df, t_used


def build_strat_data(base: pd.DataFrame, driver: pd.DataFrame) -> dict[str, pd.DataFrame]:
    sd = A.build_strat_data(base)
    for key in ("Driver_FC", "Driver_OO"):
        sub = driver[driver["strategy"] == key]
        if "feasible" in sub.columns:
            n_inf = int((~sub["feasible"]).sum())
            if n_inf:
                print(f"Note: {n_inf} infeasible {key} row(s) dropped from comparisons.")
            sub = sub[sub["feasible"]]
        sd[key] = sub.drop_duplicates("instance_clean", keep="first")
    return sd


def instances_from(sd: dict) -> list[str]:
    """Instances in the comparison: those with a Partial (reference) result; union of all strategies otherwise."""
    ref = sd.get("Partial")
    if ref is not None and not ref.empty:
        insts = set(ref["instance_clean"].astype(str).unique())
    else:
        insts = set()
        for s in STRATEGIES:
            d = sd.get(s)
            if d is not None and not d.empty:
                insts.update(d["instance_clean"].astype(str).unique())
    return sorted(insts, key=A.instance_sort_key)


def route_time_matrix(sd: dict, instances: list[str]) -> pd.DataFrame:
    """index = instance, columns = strategy, values = route hours."""
    out = pd.DataFrame(index=instances, columns=STRATEGIES, dtype=float)
    for s in STRATEGIES:
        d = sd.get(s)
        if d is None or d.empty:
            continue
        ser = d.set_index("instance_clean")["route_time"]
        out[s] = ser.reindex(instances).astype(float)
    return out


def _metric(ser: pd.Series, key: str):
    for c in METRIC_CANDIDATES[key]:
        if c in ser.index and pd.notna(ser[c]):
            try:
                return float(ser[c])
            except (TypeError, ValueError):
                return np.nan
    return np.nan


# ----------------------------------------------------------------------------- comparisons
def pair_comparison(rt: pd.DataFrame, ref: str, cand: str) -> dict | None:
    """Advantage of `cand` over `ref`: (ref - cand)/ref*100 and (ref - cand) minutes, common instances."""
    m = rt[[ref, cand]].dropna()
    if m.empty:
        return None
    delta_h = m[ref] - m[cand]
    pct = delta_h / m[ref] * 100.0
    avg_s, min_s, max_s = A._partial_advantage_avg_min_max_display(pct, delta_h)
    return {
        "ref": ref,
        "cand": cand,
        "n": int(len(m)),
        "mean_ref_h": float(m[ref].mean()),
        "mean_cand_h": float(m[cand].mean()),
        "cand_better": int((m[cand] < m[ref] - 1e-9).sum()),
        "ref_better": int((m[ref] < m[cand] - 1e-9).sum()),
        "ties": int((np.abs(m[ref] - m[cand]) <= 1e-9).sum()),
        "avg_pct": float(pct.mean()),
        "avg_min": float(delta_h.mean() * 60.0),
        "median_pct": float(pct.median()),
        "display_avg": avg_s,
        "display_min": min_s,
        "display_max": max_s,
        "pct": pct,
        "delta_h": delta_h,
        "merged": m,
    }


COMPARISON_PAIRS = [
    # (reference, candidate, label)  -> "candidate advantage over reference"
    ("Driver_FC", "Partial", "Partial vs Driver (full charge)"),
    ("Driver_OO", "Partial", "Partial vs Driver (overlap-only)"),
    ("Driver_FC", "Full", "Full vs Driver (full charge)"),
    ("Driver_OO", "Full", "Full vs Driver (overlap-only)"),
    ("Greedy", "Driver_FC", "Driver (full charge) vs Greedy"),
    ("Greedy", "Driver_OO", "Driver (overlap-only) vs Greedy"),
    ("Driver_FC", "Driver_OO", "Driver overlap-only vs Driver full charge"),
    ("Driver_FC", "Partial_Diesel_LB", "Diesel proxy vs Driver (full charge)"),
    ("Driver_OO", "Partial_Diesel_LB", "Diesel proxy vs Driver (overlap-only)"),
    ("Greedy", "Partial", "Partial vs Greedy (reference)"),
    ("Partial", "Partial_Diesel_LB", "Diesel proxy vs Partial (reference)"),
]


def table_combined_comparisons(rt: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ref, cand, label in COMPARISON_PAIRS:
        c = pair_comparison(rt, ref, cand)
        if c is None:
            continue
        rows.append(
            {
                "Comparison": label,
                "reference": LABELS[ref],
                "candidate": LABELS[cand],
                "n": c["n"],
                "mean_reference_h": round(c["mean_ref_h"], 3),
                "mean_candidate_h": round(c["mean_cand_h"], 3),
                "candidate_better": c["cand_better"],
                "reference_better": c["ref_better"],
                "ties": c["ties"],
                "candidate_advantage_avg": c["display_avg"],
                "candidate_advantage_min": c["display_min"],
                "candidate_advantage_max": c["display_max"],
                "candidate_advantage_median_pct": round(c["median_pct"], 3),
            }
        )
    return pd.DataFrame(rows)


def table_per_instance(rt: pd.DataFrame, id_by: dict[str, str]) -> pd.DataFrame:
    df = rt.copy()
    df.insert(0, "instance", df.index)
    df.insert(0, "id", [id_by.get(i, "") for i in df.index])
    df.insert(2, "problem_size", [A.get_problem_size(i) for i in df.index])
    df.insert(3, "balance", [A.get_balance(i) for i in df.index])
    df = df.rename(columns={s: f"{s.lower()}_route_h" for s in STRATEGIES})
    p, f, g, d = (df["partial_route_h"], df["full_route_h"], df["greedy_route_h"], df["partial_diesel_lb_route_h"])
    for key in ("driver_fc", "driver_oo"):
        x = df[f"{key}_route_h"]
        df[f"{key}_minus_partial_min"] = (x - p) * 60.0
        df[f"{key}_pct_slower_than_partial"] = (x - p) / p * 100.0
        df[f"{key}_pct_slower_than_full"] = (x - f) / f * 100.0
        df[f"{key}_pct_faster_than_greedy"] = (g - x) / g * 100.0
        df[f"{key}_ev_gap_pct_vs_diesel"] = (x - d) / d * 100.0
    df["driver_oo_pct_faster_than_fc"] = (df["driver_fc_route_h"] - df["driver_oo_route_h"]) / df["driver_fc_route_h"] * 100.0
    num = df.select_dtypes(include=[float]).columns
    df[num] = df[num].round(4)
    return df.reset_index(drop=True)


def table_by_group(rt: pd.DataFrame, group_fn, group_col: str, order: list[str]) -> pd.DataFrame:
    rows = []
    groups = pd.Series([group_fn(i) for i in rt.index], index=rt.index)
    for g in order:
        sub = rt[groups == g]
        if sub.empty:
            continue
        row = {group_col: g, "n_instances": int(len(sub))}
        for s in STRATEGIES:
            row[f"mean_{s.lower()}_h"] = round(float(sub[s].mean()), 3) if sub[s].notna().any() else np.nan
        for key in ("Driver_FC", "Driver_OO"):
            m = sub[[key, "Partial"]].dropna()
            row[f"{key.lower()}_pct_slower_than_partial"] = (
                round(float(((m[key] - m["Partial"]) / m["Partial"] * 100).mean()), 3) if not m.empty else np.nan
            )
            m = sub[[key, "Greedy"]].dropna()
            row[f"{key.lower()}_pct_faster_than_greedy"] = (
                round(float(((m["Greedy"] - m[key]) / m["Greedy"] * 100).mean()), 3) if not m.empty else np.nan
            )
            m = sub[[key, "Partial_Diesel_LB"]].dropna()
            row[f"{key.lower()}_ev_gap_pct_vs_diesel"] = (
                round(float(((m[key] - m["Partial_Diesel_LB"]) / m["Partial_Diesel_LB"] * 100).mean()), 3)
                if not m.empty
                else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)


def table_activity_summary(sd: dict) -> pd.DataFrame:
    rows = []
    for s in STRATEGIES:
        d = sd.get(s)
        if d is None or d.empty:
            continue
        row = {"strategy": s, "label": LABELS[s], "n_instances": int(len(d))}
        vals = {k: [] for k in METRIC_CANDIDATES}
        for _, ser in d.iterrows():
            for k in METRIC_CANDIDATES:
                vals[k].append(_metric(ser, k))
        for k, v in vals.items():
            arr = np.array(v, dtype=float)
            row[f"mean_{k}"] = round(float(np.nanmean(arr)), 3) if np.isfinite(arr).any() else np.nan
        row["mean_route_h"] = round(float(d["route_time"].mean()), 3)
        ct = pd.to_numeric(d.get("comp_time_sec"), errors="coerce") if "comp_time_sec" in d.columns else None
        row["mean_computation_sec"] = round(float(ct.mean()), 6) if ct is not None and ct.notna().any() else np.nan
        for extra in ("total_charging_time_minutes", "total_energy_charged_kWh", "num_rule2_sync_stops",
                      "num_rule3_forced_charges", "num_rule4_road_interruptions", "num_customer_interruptions",
                      "num_cs_passed", "num_guard_break_to_rest"):
            if extra in d.columns:
                row[f"mean_{extra}"] = round(float(pd.to_numeric(d[extra], errors="coerce").mean()), 3)
        rows.append(row)
    return pd.DataFrame(rows)


def table_driver_rules(driver: pd.DataFrame, id_by: dict[str, str]) -> pd.DataFrame:
    cols = [
        "instance_clean", "policy", "t_sync_hours", "total_time", "num_charges", "num_breaks", "num_rests",
        "num_charges_sync_with_rest", "num_charges_sync_with_break", "num_rule2_sync_stops",
        "num_rule3_forced_charges", "num_rule4_road_interruptions", "num_customer_interruptions", "num_cs_passed",
        "num_guard_break_to_rest", "num_cs_on_route", "total_charging_time_minutes",
        "total_idle_charging_time_minutes", "total_energy_charged_kWh", "final_soc_kWh",
        "total_driving_time_hours", "total_service_time_hours", "total_break_time_hours", "total_rest_time_hours",
        "feasible", "schedule_valid", "computation_time",
    ]
    cols = [c for c in cols if c in driver.columns]
    df = driver[cols].copy()
    df.insert(0, "id", df["instance_clean"].map(lambda i: id_by.get(str(i), "")))
    df["_sk"] = df["instance_clean"].map(lambda i: A.instance_sort_key(str(i)))
    df = df.sort_values(["_sk", "policy"]).drop(columns="_sk")
    return df.reset_index(drop=True)


def table_tsync_sensitivity(sweep: pd.DataFrame, rt: pd.DataFrame) -> pd.DataFrame:
    """Mean route time per t_sync and policy over the instances common with Partial; gaps vs Partial / Greedy."""
    sweep = sweep[sweep["feasible"]] if "feasible" in sweep.columns else sweep
    rows = []
    partial = rt["Partial"].dropna()
    greedy = rt["Greedy"].dropna()
    for (t, pol), g in sweep.groupby(["t_sync_hours", "policy"]):
        s = g.set_index("instance_clean")["route_time"]
        common_p = s.index.intersection(partial.index)
        common_g = s.index.intersection(greedy.index)
        rows.append(
            {
                "t_sync_hours": float(t),
                "policy": POLICY_TO_STRATEGY.get(str(pol).lower(), pol),
                "n_instances": int(len(s)),
                "mean_route_h": round(float(s.mean()), 3),
                "mean_route_h_common_with_partial": round(float(s.loc[common_p].mean()), 3) if len(common_p) else np.nan,
                "mean_pct_slower_than_partial": (
                    round(float(((s.loc[common_p] - partial.loc[common_p]) / partial.loc[common_p] * 100).mean()), 3)
                    if len(common_p)
                    else np.nan
                ),
                "mean_pct_faster_than_greedy": (
                    round(float(((greedy.loc[common_g] - s.loc[common_g]) / greedy.loc[common_g] * 100).mean()), 3)
                    if len(common_g)
                    else np.nan
                ),
                "mean_charges": round(float(g["num_charges"].mean()), 3),
                "mean_breaks": round(float(g["num_breaks"].mean()), 3),
                "mean_rests": round(float(g["num_rests"].mean()), 3),
                "mean_idle_charging_min": round(float(g["total_idle_charging_time_minutes"].mean()), 3),
                "mean_rule2_sync_stops": round(float(g["num_rule2_sync_stops"].mean()), 3),
                "mean_rule4_road_interruptions": round(float(g["num_rule4_road_interruptions"].mean()), 3),
            }
        )
    return pd.DataFrame(rows).sort_values(["policy", "t_sync_hours"]).reset_index(drop=True)


# ----------------------------------------------------------------------------- figures
def _group_separators(instances: list[str]) -> tuple[list[int], list[float]]:
    sizes = [sum(1 for i in instances if A.get_problem_size(i) == g) for g in ("short", "medium", "large")]
    seps = [sizes[0] - 0.5, sizes[0] + sizes[1] - 0.5]
    return sizes, seps


def fig_route_time_per_instance(rt: pd.DataFrame, id_by: dict[str, str]) -> None:
    instances = list(rt.index)
    if not instances:
        return
    x = np.arange(len(instances))
    n_s = len(STRATEGIES)
    w = 0.8 / n_s
    fig, ax = plt.subplots(figsize=(max(14, len(instances) * 0.4), 5.2))
    for i, s in enumerate(STRATEGIES):
        ax.bar(x + (i - (n_s - 1) / 2) * w, rt[s].values, w, label=LABELS[s], color=COLORS[s], alpha=0.9)
    sizes, seps = _group_separators(instances)
    for xi in seps:
        ax.axvline(xi, color="black", linestyle="--", linewidth=1, alpha=0.7)
    y_max = np.nanmax(rt.values) * 1.18
    cum = 0
    for n, lbl in zip(sizes, ("Short", "Medium", "Long")):
        if n:
            ax.text(cum + (n - 1) / 2, y_max * 0.98, lbl, ha="center", va="top", fontsize=11, fontweight="bold")
        cum += n
    ax.set_xticks(x)
    ax.set_xticklabels([id_by.get(i, i) for i in instances], rotation=55, ha="right", fontsize=7)
    ax.set_ylabel("Total route time (hours)")
    ax.set_title("Base scenario: total route time per instance incl. driver-inspired heuristic")
    leg = ax.legend(loc="upper right", ncol=2, frameon=True, fancybox=False, edgecolor="black", framealpha=1, fontsize=8)
    leg.get_frame().set_linewidth(0.8)
    ax.set_ylim(0, y_max)
    ax.set_xlim(-0.6, len(instances) - 0.4)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "D01_route_time_per_instance.png", dpi=150, bbox_inches="tight")
    plt.close()


def fig_mean_route_time(rt: pd.DataFrame) -> None:
    common = rt.dropna()
    use = common if not common.empty else rt
    means = use.mean()
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    x = np.arange(len(STRATEGIES))
    bars = ax.bar(x, [means[s] for s in STRATEGIES], color=[COLORS[s] for s in STRATEGIES], alpha=0.9)
    for b, s in zip(bars, STRATEGIES):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + means.max() * 0.01, f"{means[s]:.1f}h",
                ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([LABELS[s].replace(" (", "\n(") for s in STRATEGIES], fontsize=8)
    ax.set_ylabel("Mean route time (hours)")
    ax.set_title(f"Mean route time by strategy (n = {len(use)} instances{' with all strategies' if not common.empty else ''})")
    ax.set_ylim(0, means.max() * 1.15)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "D02a_mean_route_time_by_strategy.png", dpi=150, bbox_inches="tight")
    plt.close()


def fig_per_instance_gaps(rt: pd.DataFrame, id_by: dict[str, str]) -> None:
    instances = list(rt.index)
    x = np.arange(len(instances))
    w = 0.38
    fig, axes = plt.subplots(3, 1, figsize=(max(10, len(instances) * 0.3), 12.5), gridspec_kw={"hspace": 0.45})

    panels = [
        ("Per-instance: driver heuristic time relative to Partial (positive = slower than Partial)",
         "% slower than Partial", lambda s: (rt[s] - rt["Partial"]) / rt["Partial"] * 100.0),
        ("Per-instance: driver heuristic improvement over Greedy (positive = faster than Greedy)",
         "Improvement % vs Greedy", lambda s: (rt["Greedy"] - rt[s]) / rt["Greedy"] * 100.0),
        ("Per-instance: EV time gap vs diesel proxy (positive = slower than diesel proxy)",
         "EV gap % vs diesel proxy", lambda s: (rt[s] - rt["Partial_Diesel_LB"]) / rt["Partial_Diesel_LB"] * 100.0),
    ]
    for ax, (title, ylabel, fn) in zip(axes, panels):
        for k, s in enumerate(("Driver_FC", "Driver_OO")):
            vals = fn(s)
            ax.bar(x + (k - 0.5) * w, vals.values, w, color=COLORS[s], alpha=0.9,
                   label=f"{LABELS[s]} (avg {np.nanmean(vals.values):.1f}%)")
            ax.axhline(np.nanmean(vals.values), color=COLORS[s], linestyle="--", linewidth=1.2)
        ax.axhline(0, color="black", linewidth=0.6)
        _, seps = _group_separators(instances)
        for xi in seps:
            ax.axvline(xi, color="black", linestyle=":", linewidth=0.8, alpha=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels([id_by.get(i, i) for i in instances], rotation=48, ha="right", fontsize=7.5)
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=10.5)
        ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "D02b_per_instance_gaps.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_boxplots(rt: pd.DataFrame) -> None:
    panels = [
        ("Driver FC\nvs Partial", (rt["Driver_FC"] - rt["Partial"]) / rt["Partial"] * 100, COLORS["Driver_FC"]),
        ("Driver OO\nvs Partial", (rt["Driver_OO"] - rt["Partial"]) / rt["Partial"] * 100, COLORS["Driver_OO"]),
        ("Greedy\nvs Partial", (rt["Greedy"] - rt["Partial"]) / rt["Partial"] * 100, COLORS["Greedy"]),
        ("Driver FC\nvs Greedy", (rt["Greedy"] - rt["Driver_FC"]) / rt["Greedy"] * 100, COLORS["Driver_FC"]),
        ("Driver OO\nvs Greedy", (rt["Greedy"] - rt["Driver_OO"]) / rt["Greedy"] * 100, COLORS["Driver_OO"]),
        ("Driver FC\nvs diesel", (rt["Driver_FC"] - rt["Partial_Diesel_LB"]) / rt["Partial_Diesel_LB"] * 100, COLORS["Driver_FC"]),
        ("Driver OO\nvs diesel", (rt["Driver_OO"] - rt["Partial_Diesel_LB"]) / rt["Partial_Diesel_LB"] * 100, COLORS["Driver_OO"]),
        ("Partial\nvs diesel", (rt["Partial"] - rt["Partial_Diesel_LB"]) / rt["Partial_Diesel_LB"] * 100, COLORS["Partial"]),
    ]
    groups = [
        ("% slower than Partial (positive = slower)", panels[0:3]),
        ("Improvement % over Greedy (positive = faster)", panels[3:5]),
        ("EV gap % vs diesel proxy (positive = slower)", panels[5:8]),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.8))
    for ax, (ylabel, items) in zip(axes, groups):
        data = [p[1].dropna().to_numpy(dtype=float) for p in items]
        bp = ax.boxplot(data, widths=0.5, patch_artist=True, showfliers=True,
                        medianprops={"color": "black", "linewidth": 1.2})
        for patch, p in zip(bp["boxes"], items):
            patch.set_facecolor(p[2])
            patch.set_alpha(0.85)
        for k, (lbl, ser, col) in enumerate(items, start=1):
            ax.scatter([k], [ser.mean()], marker="D", color="red", s=22, zorder=3,
                       label="mean" if k == 1 else None)
            ax.text(k, ax.get_ylim()[1] * 0.98 if False else ser.max() + 0.5, f"avg {ser.mean():.1f}%",
                    ha="center", va="bottom", fontsize=8)
        ax.axhline(0, color="black", linewidth=0.6)
        ax.set_xticks(range(1, len(items) + 1))
        ax.set_xticklabels([p[0] for p in items], fontsize=8.5)
        ax.set_ylabel(ylabel)
        ax.set_title(f"n = {len(data[0])}", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "D02c_boxplots_gaps.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_avg_route_time_by_group(rt: pd.DataFrame) -> None:
    groups = ["short", "medium", "large"]
    labels = ["Short", "Medium", "Long"]
    sizes = pd.Series([A.get_problem_size(i) for i in rt.index], index=rt.index)
    fig, ax = plt.subplots(figsize=(8, 4.4))
    n_s = len(STRATEGIES)
    w = 0.8 / n_s
    xg = np.arange(len(groups))
    all_vals = []
    for i, s in enumerate(STRATEGIES):
        vals = [rt.loc[sizes == g, s].mean() for g in groups]
        all_vals += [v for v in vals if pd.notna(v)]
        bars = ax.bar(xg + (i - (n_s - 1) / 2) * w, vals, w, label=LABELS[s], color=COLORS[s], alpha=0.9)
        for b, v in zip(bars, vals):
            if pd.notna(v):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.6, f"{v:.0f}", ha="center", va="bottom", fontsize=6.5)
    ax.set_xticks(xg)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Mean route time (hours)")
    ax.set_title("Mean route time by problem size")
    ax.legend(fontsize=7.5, ncol=2)
    if all_vals:
        ax.set_ylim(0, max(all_vals) * 1.25)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "D03_avg_route_time_by_group.png", dpi=150, bbox_inches="tight")
    plt.close()


def fig_activity(summary: pd.DataFrame) -> None:
    if summary.empty:
        return
    s = summary.set_index("strategy").reindex([x for x in STRATEGIES if x in summary["strategy"].values])
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.8))
    x = np.arange(len(s))
    cols = [COLORS[k] for k in s.index]
    short_lbl = {"Full": "Full", "Partial": "Partial", "Greedy": "Greedy", "Driver_FC": "Driver\n(full)",
                 "Driver_OO": "Driver\n(overlap)", "Partial_Diesel_LB": "Diesel\nproxy"}
    panels = [
        ("mean_n_charges", "Mean charging stops"),
        ("mean_n_breaks", "Mean breaks"),
        ("mean_n_rests", "Mean daily rests"),
        ("mean_idle_charging_min", "Mean idle charging time (min)"),
    ]
    for ax, (col, title) in zip(axes, panels):
        vals = s[col].values if col in s.columns else np.full(len(s), np.nan)
        bars = ax.bar(x, vals, color=cols, alpha=0.9)
        for b, v in zip(bars, vals):
            if pd.notna(v):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:.1f}", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels([short_lbl.get(k, k) for k in s.index], fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle("Activity and synchronisation metrics by strategy (means over instances)", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "D04_activity_by_strategy.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_rule_usage(driver: pd.DataFrame) -> None:
    cols = ["num_rule2_sync_stops", "num_rule3_forced_charges", "num_rule4_road_interruptions", "num_customer_interruptions"]
    if not all(c in driver.columns for c in cols):
        return
    names = ["Rule 2: early sync at CS", "Rule 3: forced charge (+interruption)", "Rule 4: interruption on the road",
             "Interruption before service"]
    groups = ["short", "medium", "large"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    palette = ["#6B3FA0", "#E07B4D", "#4A7C59", "#C9A227"]
    for ax, (pol, key) in zip(axes, (("full", "Driver_FC"), ("overlap", "Driver_OO"))):
        d = driver[driver["strategy"] == key]
        bottom = np.zeros(len(groups))
        for c, nm, col in zip(cols, names, palette):
            vals = np.array([pd.to_numeric(d.loc[d["problem_size"] == g, c], errors="coerce").mean() for g in groups])
            vals = np.nan_to_num(vals)
            ax.bar(groups, vals, bottom=bottom, label=nm, color=col, alpha=0.9)
            bottom += vals
        ax.set_title(LABELS[key], fontsize=10)
        ax.set_xticks(range(len(groups)))
        ax.set_xticklabels(["Short", "Medium", "Long"])
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("Mean number of events per route")
    axes[1].legend(fontsize=8)
    fig.suptitle("Which heuristic rule produced the stops (means per problem size)", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "D05_rule_usage_by_group.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_tsync_sensitivity(tsync: pd.DataFrame, rt: pd.DataFrame, t_used: float | None) -> None:
    if tsync.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for key in ("Driver_FC", "Driver_OO"):
        d = tsync[tsync["policy"] == key].sort_values("t_sync_hours")
        ax.plot(d["t_sync_hours"], d["mean_route_h_common_with_partial"], marker="o", color=COLORS[key], label=LABELS[key])
    common = rt[["Partial", "Greedy", "Full"]].dropna()
    for key, ls in (("Partial", "--"), ("Full", ":"), ("Greedy", "-.")):
        if key in rt.columns and rt[key].notna().any():
            ax.axhline(rt[key].mean(), color=COLORS[key], linestyle=ls, linewidth=1.3, label=f"{LABELS[key]} (mean)")
    if t_used is not None:
        ax.axvline(t_used, color="grey", linestyle=":", linewidth=1, label=f"headline t_sync = {t_used:g} h")
    ax.set_xlabel("t_sync (hours)")
    ax.set_ylabel("Mean route time (hours)")
    ax.set_title("Sensitivity of the driver heuristic to t_sync")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "D06_tsync_sensitivity.png", dpi=150, bbox_inches="tight")
    plt.close()


# ----------------------------------------------------------------------------- report
def write_report(comps: pd.DataFrame, by_size: pd.DataFrame, summary: pd.DataFrame, tsync: pd.DataFrame,
                 headline_file: Path, t_used: float | None, n_instances: int, n_driver_infeasible: int,
                 greedy_note: str) -> None:
    L: list[str] = []
    L.append("# Base-scenario post-analysis: driver-inspired sequential heuristic")
    L.append("")
    L.append(f"Driver heuristic results: `{headline_file.name}` (t_sync = {t_used if t_used is not None else 'default'} h; "
             f"policies: full charge = `Driver_FC`, overlap-only = `Driver_OO`).")
    L.append(f"EV configuration: {A.route_summary_config_caption()}")
    L.append(f"Instances compared: {n_instances}. Infeasible driver-heuristic rows dropped: {n_driver_infeasible}.")
    if greedy_note:
        L.append("")
        L.append(f"**Note on Greedy:** {greedy_note}")
    L.append("")
    L.append("## 1. Summary of comparisons (candidate advantage over reference = (ref - cand)/ref)")
    L.append("")
    if not comps.empty:
        slim = comps[["Comparison", "n", "mean_reference_h", "mean_candidate_h", "candidate_better", "reference_better",
                      "candidate_advantage_avg", "candidate_advantage_min", "candidate_advantage_max"]]
        try:
            L.append(slim.to_markdown(index=False))
        except (ImportError, ValueError):
            L.append(A._df_to_pipe_markdown(slim))
    L.append("")
    L.append("## 2. By problem size")
    L.append("")
    if not by_size.empty:
        cols = ["problem_size", "n_instances", "mean_full_h", "mean_partial_h", "mean_greedy_h", "mean_driver_fc_h",
                "mean_driver_oo_h", "mean_partial_diesel_lb_h", "driver_fc_pct_slower_than_partial",
                "driver_oo_pct_slower_than_partial", "driver_fc_pct_faster_than_greedy", "driver_oo_pct_faster_than_greedy"]
        slim = by_size[[c for c in cols if c in by_size.columns]]
        try:
            L.append(slim.to_markdown(index=False))
        except (ImportError, ValueError):
            L.append(A._df_to_pipe_markdown(slim))
    L.append("")
    L.append("## 3. Activity / synchronisation (means over instances)")
    L.append("")
    if not summary.empty:
        cols = ["label", "n_instances", "mean_route_h", "mean_n_charges", "mean_n_breaks", "mean_n_rests",
                "mean_pct_charge_sync", "mean_idle_charging_min", "mean_computation_sec"]
        slim = summary[[c for c in cols if c in summary.columns]]
        try:
            L.append(slim.to_markdown(index=False))
        except (ImportError, ValueError):
            L.append(A._df_to_pipe_markdown(slim))
    L.append("")
    if not tsync.empty:
        L.append("## 4. t_sync sensitivity (mean route time, instances common with Partial)")
        L.append("")
        piv = tsync.pivot(index="t_sync_hours", columns="policy", values="mean_route_h_common_with_partial").reset_index()
        try:
            L.append(piv.to_markdown(index=False))
        except (ImportError, ValueError):
            L.append(A._df_to_pipe_markdown(piv))
        L.append("")
    L.append("## Figures (`figures/`)")
    L.append("")
    for f, cap in [
        ("D01_route_time_per_instance.png", "Route time per instance, six strategies"),
        ("D02a_mean_route_time_by_strategy.png", "Mean route time by strategy"),
        ("D02b_per_instance_gaps.png", "Per-instance gaps: vs Partial, vs Greedy, vs diesel proxy"),
        ("D02c_boxplots_gaps.png", "Box plots of the per-instance gaps"),
        ("D03_avg_route_time_by_group.png", "Mean route time by problem size"),
        ("D04_activity_by_strategy.png", "Charging stops, breaks, rests, idle charging time"),
        ("D05_rule_usage_by_group.png", "Which heuristic rule produced the stops"),
        ("D06_tsync_sensitivity.png", "t_sync sensitivity"),
    ]:
        if (FIG_DIR / f).exists():
            L.append(f"- **{cap}:** ![{cap}](figures/{f})")
    L.append("")
    L.append("## Tables (`tables/`)")
    L.append("")
    for f, cap in [
        ("table_D00_instance_id_map.csv", "id <-> instance name"),
        ("table_D01_combined_comparisons.csv", "pairwise comparisons (means, counts, avg/min/max advantage)"),
        ("table_D02_per_instance_route_times.csv", "route hours of all strategies per instance + gap columns"),
        ("table_D03_by_problem_size.csv", "means by problem size"),
        ("table_D03b_by_balance.csv", "means by balance"),
        ("table_D04_activity_summary_by_strategy.csv", "activity / sync means per strategy"),
        ("table_D05_driver_rule_statistics.csv", "per instance and policy: rule counters, charging time, energy, SOC"),
        ("table_D06_tsync_sensitivity.csv", "t_sync sweep"),
    ]:
        if (TBL_DIR / f).exists():
            L.append(f"- `{f}`: {cap}")
    L.append("")
    A._safe_path_write_text(OUT_DIR / "report.md", "\n".join(L))
    print(f"Report: {OUT_DIR / 'report.md'}")


# ----------------------------------------------------------------------------- main
def main() -> int:
    headline_file, sweep_file = find_driver_files()
    if headline_file is None:
        print("Configure a driver-heuristic run in analysis/configs/paper_inputs.json.", file=sys.stderr)
        return 1
    print(f"Driver heuristic headline file: {headline_file}")
    if sweep_file is not None:
        print(f"Driver heuristic t_sync sweep file: {sweep_file}")

    print("Loading base scenario data (analyze.py)...")
    base = A.load_base_data()
    if base.empty:
        print("No base scenario data found.", file=sys.stderr)
        return 1

    driver_all, t_used = load_driver_headline(headline_file)
    print(f"Driver rows (EV base config, t_sync={t_used}): {len(driver_all)} | policies: "
          + ", ".join(f"{k}={int(v)}" for k, v in driver_all['strategy'].value_counts().items()))
    n_driver_infeasible = int((~driver_all["feasible"]).sum()) if "feasible" in driver_all.columns else 0

    sd = build_strat_data(base, driver_all)
    instances = instances_from(sd)
    print("Instances per strategy: " + ", ".join(f"{s}={len(sd[s])}" for s in STRATEGIES if s in sd))
    id_map = A.build_instance_id_map(base, sd)
    id_by = dict(zip(id_map["instance_clean"].astype(str), id_map["id"].astype(str)))
    rt = route_time_matrix(sd, instances)

    # Greedy configuration note (greedy rows may come from a different run / charging power)
    greedy_note = ""
    g = sd.get("Greedy")
    if g is not None and not g.empty:
        cp = pd.to_numeric(g.get("charging_power"), errors="coerce") if "charging_power" in g.columns else None
        if cp is not None and cp.notna().any() and not np.isclose(cp.dropna().unique(), A.BASE_SCENARIO_CHARGING_POWER_KW).all():
            greedy_note = (
                f"the Greedy rows in the base-scenario folder were run with charging power "
                f"{sorted(cp.dropna().unique().tolist())} kW, not {A.BASE_SCENARIO_CHARGING_POWER_KW:g} kW; "
                "Greedy comparisons are therefore not at identical charging power."
            )
            print("Note: " + greedy_note)

    # Tables
    A._safe_dataframe_to_csv(id_map, TBL_DIR / "table_D00_instance_id_map.csv")
    comps = table_combined_comparisons(rt)
    A._safe_dataframe_to_csv(comps, TBL_DIR / "table_D01_combined_comparisons.csv")
    per_inst = table_per_instance(rt, id_by)
    A._safe_dataframe_to_csv(per_inst, TBL_DIR / "table_D02_per_instance_route_times.csv")
    by_size = table_by_group(rt, A.get_problem_size, "problem_size", ["short", "medium", "large"])
    A._safe_dataframe_to_csv(by_size, TBL_DIR / "table_D03_by_problem_size.csv")
    by_bal = table_by_group(rt, A.get_balance, "balance", ["Balanced", "Unbalanced"])
    A._safe_dataframe_to_csv(by_bal, TBL_DIR / "table_D03b_by_balance.csv")
    summary = table_activity_summary(sd)
    A._safe_dataframe_to_csv(summary, TBL_DIR / "table_D04_activity_summary_by_strategy.csv")
    rules = table_driver_rules(driver_all, id_by)
    A._safe_dataframe_to_csv(rules, TBL_DIR / "table_D05_driver_rule_statistics.csv")
    tsync = pd.DataFrame()
    if sweep_file is not None:
        sweep = prepare_driver_df(read_frame(sweep_file))
        sweep = sweep.loc[_driver_ev_mask(sweep)]
        if A.EXCLUDED_INSTANCE_IDS:
            sweep = sweep[~sweep["instance_clean"].isin(set(A.EXCLUDED_INSTANCE_IDS))]
        tsync = table_tsync_sensitivity(sweep, rt)
        A._safe_dataframe_to_csv(tsync, TBL_DIR / "table_D06_tsync_sensitivity.csv")
    print(f"Tables: {TBL_DIR}")

    # Figures
    fig_route_time_per_instance(rt, id_by)
    fig_mean_route_time(rt)
    fig_per_instance_gaps(rt, id_by)
    fig_boxplots(rt)
    fig_avg_route_time_by_group(rt)
    fig_activity(summary)
    fig_rule_usage(driver_all)
    fig_tsync_sensitivity(tsync, rt, t_used)
    print(f"Figures: {FIG_DIR}")

    write_report(comps, by_size, summary, tsync, headline_file, t_used, len(instances), n_driver_infeasible, greedy_note)

    # Console summary
    if not comps.empty:
        print(comps[["Comparison", "n", "mean_reference_h", "mean_candidate_h", "candidate_better", "reference_better",
                     "candidate_advantage_avg"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
