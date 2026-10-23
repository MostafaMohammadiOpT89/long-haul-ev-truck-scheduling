"""Draft Section 5.1 figures from explicitly matched inherited results.

Run: python -m analysis.conditions.run
The archive does not establish solver termination status or overall feasibility.
Missing records are never treated as infeasible. No optimization is run here.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from common.paths import ROOT, BENCHMARK
from common.results import read_frame
from analysis.common.inputs import INPUTS, input_source, ANALYSIS_OUTPUT

OUT = ANALYSIS_OUTPUT / "conditions"
FIG = OUT / "figures"
TABLE = OUT / "tables"
PARAMS = {
    "battery_capacity_kWh": (750., "Battery capacity (kWh)"),
    "charging_power_kW": (350., "Charging power (kW)"),
    "charging_station_interval_km": (60., "Station spacing (km)"),
    "energy_consumption_rate_kWh_per_km": (1.49, "Energy consumption (kWh/km)"),
}
COLORS = ["#26758A", "#BF7332", "#766399"]
CLASSES = ["short", "med", "long"]
NAMES = {"short": "Short", "med": "Medium", "long": "Long", "all": "All routes"}
TOL_HOURS = 1e-7


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    frame = read_frame(path)
    frame = frame.loc[frame._runner_algorithm.eq("partial_labeling")].copy()
    frame["feasible"] = frame.feasible.astype(str).str.lower().map({"true": True, "false": False})
    if frame.feasible.isna().any():
        raise ValueError(f"Unknown feasibility encoding: {path}")
    if frame.loc[frame.feasible, "total_route_time_hours"].isna().any():
        raise ValueError(f"Feasible record without route duration: {path}")
    return frame


def pair(ev, refs):
    result = ev.merge(refs, on="instance_id", how="left", validate="many_to_one")
    if result.diesel_hours.isna().any():
        raise ValueError("Missing diesel reference")
    result["gap_hours"] = result.total_route_time_hours - result.diesel_hours
    if result.loc[result.feasible, "gap_hours"].lt(-TOL_HOURS).any():
        raise ValueError("EV result improves on its diesel lower bound; investigate before plotting")
    # Only remove floating-point noise, never substantive negative observations.
    result.loc[result.gap_hours.abs().le(TOL_HOURS), "gap_hours"] = 0.
    result["gap_minutes"] = 60 * result.gap_hours
    result["gap_pct"] = 100 * result.gap_hours / result.diesel_hours
    result["route_class"] = result.instance_id.str.split("_").str[0]
    return result


def summarize(frame):
    return {
        "n": int(len(frame)), "diesel_hours": frame.diesel_hours.mean(),
        "ev_hours": frame.total_route_time_hours.mean(),
        "mean_gap_pct": frame.gap_pct.mean(), "median_gap_pct": frame.gap_pct.median(),
        "p90_gap_pct": frame.gap_pct.quantile(.9), "max_gap_pct": frame.gap_pct.max(),
        "mean_gap_minutes": frame.gap_minutes.mean(), "max_gap_minutes": frame.gap_minutes.max(),
        "within_1pct": int(frame.gap_pct.le(1).sum()), "within_5pct": int(frame.gap_pct.le(5).sum()),
    }


def clean_axes(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#DDE1E4", linewidth=.6, zorder=0)
    ax.set_axisbelow(True)


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(FIG / f"{name}.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def base_figure(frame):
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.65))
    for ax, field, title, ylabel in zip(axes, ["gap_pct", "gap_minutes"],
            ["(a) Relative time penalty", "(b) Additional route time"],
            ["EV minus diesel (%)", "EV minus diesel (minutes)"]):
        for index, (route, color) in enumerate(zip(CLASSES, COLORS), 1):
            values = frame.loc[frame.route_class.eq(route)].sort_values("instance_id")[field].to_numpy()
            ax.boxplot(values, positions=[index], widths=.5, showfliers=False, patch_artist=True,
                       boxprops={"facecolor": color, "alpha": .18, "edgecolor": color},
                       medianprops={"color": color, "linewidth": 1.8},
                       whiskerprops={"color": color}, capprops={"color": color})
            # Deterministic spread shows each of the few benchmark observations.
            jitter = np.random.default_rng(42 + index).uniform(-.15, .15, len(values))
            ax.scatter(index + jitter, values, s=21, color=color, alpha=.85, linewidths=.4,
                       edgecolors="white", zorder=3)
            ax.scatter(index, values.mean(), marker="D", s=36, color="white", edgecolor="#222222", zorder=5)
        ax.set_xticks([1, 2, 3], [f"{NAMES[c]}\n(n={sum(frame.route_class.eq(c))})" for c in CLASSES])
        ax.set_title(title, loc="left", pad=9)
        ax.set_ylabel(ylabel)
        ax.set_ylim(bottom=-.03 * frame[field].max())
        clean_axes(ax)
    fig.legend(handles=[Line2D([], [], marker="o", color="#555555", linestyle="none", label="Individual route"),
                        Line2D([], [], marker="D", markerfacecolor="white", color="#222222", linestyle="none", label="Mean")],
               loc="upper center", ncol=2, bbox_to_anchor=(.5, 1.03), frameon=False)
    fig.tight_layout(rect=(0, 0, 1, .94), w_pad=2)
    save(fig, "base_case")


def sensitivity_figure(slices, cohort):
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 5.6), sharey=True)
    stats = []
    for ax, (param, (default, xlabel)), letter in zip(axes.flat, PARAMS.items(), "abcd"):
        frame = slices[param].loc[lambda x: x.instance_id.isin(cohort)]
        wide = frame.pivot(index="instance_id", columns=param, values="gap_pct").sort_index(axis=1)
        assert wide.notna().all().all() and len(wide) == len(cohort)
        levels = wide.columns.to_numpy()
        means, p90 = wide.mean().to_numpy(), wide.quantile(.9).to_numpy()
        q25, q75 = wide.quantile(.25).to_numpy(), wide.quantile(.75).to_numpy()
        ax.fill_between(levels, q25, q75, color="#26758A", alpha=.16, label="Interquartile range")
        ax.plot(levels, means, "o-", color="#26758A", linewidth=1.8, markersize=4, label="Mean")
        ax.plot(levels, p90, "s--", color="#BF7332", linewidth=1.3, markersize=4, label="90th percentile")
        ax.axvline(default, color="#777777", linestyle=":", linewidth=1, label="Base setting")
        ax.set_xticks(levels, [f"{x:g}" for x in levels])
        ax.set_xlabel(xlabel)
        ax.set_title(f"({letter}) {xlabel.split(' (')[0]}", loc="left")
        clean_axes(ax)
        for level in levels:
            stats.append({"parameter": param, "level": level, **summarize(frame[frame[param].eq(level)])})
    for ax in axes[:, 0]:
        ax.set_ylabel("EV minus diesel (%)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(.5, 1.01))
    fig.text(.5, .005, f"Exploratory subset: the same {len(cohort)} short routes at every setting; other parameters held at base values.",
             ha="center", fontsize=8.5, color="#555555")
    fig.tight_layout(rect=(0, .045, 1, .94), h_pad=1.7)
    save(fig, "sensitivities")
    return pd.DataFrame(stats)


def heatmap_figure(sweep, cohort):
    frame = sweep[sweep.charging_station_interval_km.eq(60) & sweep.instance_id.isin(cohort)]
    groupcols = ["energy_consumption_rate_kWh_per_km", "battery_capacity_kWh", "charging_power_kW"]
    rows = [{**dict(zip(groupcols, key)), **summarize(group)} for key, group in frame.groupby(groupcols)]
    stats = pd.DataFrame(rows)
    assert stats.n.eq(len(cohort)).all()
    fig, axes = plt.subplots(1, 3, figsize=(8.4, 2.75), sharey=True, layout="constrained")
    for ax, (consumption, group) in zip(axes, stats.groupby(groupcols[0])):
        matrix = group.pivot(index=groupcols[1], columns=groupcols[2], values="mean_gap_pct").sort_index(ascending=False)
        im = ax.imshow(matrix.values, cmap="YlGnBu", vmin=0, vmax=stats.mean_gap_pct.max(), aspect="auto")
        for (row, col), value in np.ndenumerate(matrix.values):
            ax.text(col, row, f"{value:.2f}", ha="center", va="center",
                    color="white" if value > .55 * stats.mean_gap_pct.max() else "#222222", fontsize=10)
        ax.set_xticks(range(len(matrix.columns)), [f"{x:g}" for x in matrix.columns])
        ax.set_yticks(range(len(matrix.index)), [f"{x:g}" for x in matrix.index])
        ax.set_xlabel("Charging power (kW)")
        ax.set_title(f"Consumption: {consumption:g} kWh/km", fontsize=10)
        ax.set_xticks(np.arange(-.5, len(matrix.columns), 1), minor=True)
        ax.set_yticks(np.arange(-.5, len(matrix.index), 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=2)
        ax.tick_params(which="minor", bottom=False, left=False)
        if np.isclose(consumption, 1.49):
            row = list(matrix.index).index(750.)
            col = list(matrix.columns).index(350.)
            ax.add_patch(Rectangle((col-.5, row-.5), 1, 1, fill=False, edgecolor="#222222", linewidth=2))
    axes[0].set_ylabel("Battery capacity (kWh)")
    bar = fig.colorbar(im, ax=axes, fraction=.035, pad=.02)
    bar.set_label("Mean EV minus diesel (%)")
    fig.suptitle(f"Exploratory interaction: {len(cohort)} matched short routes; station spacing 60 km", fontsize=10)
    save(fig, "battery_power")
    return stats


def main():
    for folder in (OUT, FIG, TABLE):
        folder.mkdir(parents=True, exist_ok=True)
    config = INPUTS
    source_names = ["base_unified", "sweep_unified", "sweep_diesel"]
    sources = {key: input_source(key) for key in source_names}
    base_raw, sweep_raw, old_diesel = (load(sources[k]) for k in source_names)
    expected = sorted(p.name for p in BENCHMARK.iterdir() if p.is_dir() and (p / f"{p.name}.txt").is_file())
    ev = base_raw[base_raw.battery_capacity_kWh.eq(750)].copy()
    refs = base_raw[base_raw.battery_capacity_kWh.gt(1e7)].copy()
    assert not ev.duplicated("instance_id").any() and not refs.duplicated("instance_id").any()
    assert not old_diesel.duplicated("instance_id").any()
    assert refs.feasible.all() and old_diesel.feasible.all()
    for param, (value, _) in PARAMS.items():
        assert ev[param].eq(value).all()
    overlap = refs.merge(old_diesel, on="instance_id", suffixes=("_base", "_older"))
    assert np.allclose(overlap.total_route_time_hours_base, overlap.total_route_time_hours_older, atol=TOL_HOURS, rtol=0)
    refs = refs[["instance_id", "total_route_time_hours"]].assign(diesel_source="base_unified")
    additions = old_diesel.loc[~old_diesel.instance_id.isin(refs.instance_id), ["instance_id", "total_route_time_hours"]]
    refs = pd.concat([refs, additions.assign(diesel_source="sweep_diesel")], ignore_index=True)
    refs = refs.rename(columns={"total_route_time_hours": "diesel_hours"})
    assert not sweep_raw.duplicated(["instance_id"] + list(PARAMS)).any()
    base = pair(ev, refs)
    sweep = pair(sweep_raw, refs)
    assert set(base.instance_id) <= set(expected) and set(sweep.instance_id) <= set(expected)
    overlap_ev = sweep.merge(base[["instance_id", "total_route_time_hours"]], on="instance_id", suffixes=("", "_base"))
    mask = np.logical_and.reduce([overlap_ev[p].eq(v).to_numpy() for p, (v, _) in PARAMS.items()])
    assert np.allclose(overlap_ev.loc[mask, "total_route_time_hours"], overlap_ev.loc[mask, "total_route_time_hours_base"], atol=TOL_HOURS, rtol=0)
    # A common complete observed-feasible cohort prevents changing composition.
    slices, sets = {}, []
    for param in PARAMS:
        subset = sweep.loc[sweep.feasible].copy()
        for other, (value, _) in PARAMS.items():
            if other != param:
                subset = subset[subset[other].eq(value)]
        slices[param] = subset
        for _, group in subset.groupby(param):
            sets.append(set(group.instance_id))
    common = set.intersection(*sets)
    interaction = sweep[sweep.feasible & sweep.charging_station_interval_km.eq(60)]
    heat_common = set.intersection(*[set(g.instance_id) for _, g in interaction.groupby(
        ["battery_capacity_kWh", "charging_power_kW", "energy_consumption_rate_kWh_per_km"])])
    assert common and heat_common
    assert all(x.startswith("short_") for x in common | heat_common), "Update figure cohort descriptions"
    plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 9,
                         "axes.titlesize": 10, "axes.labelsize": 9, "pdf.fonttype": 42,
                         "axes.linewidth": .6, "savefig.facecolor": "white"})
    base_figure(base.loc[base.feasible])
    sens = sensitivity_figure(slices, common)
    heat = heatmap_figure(sweep, heat_common)
    summary = []
    for cls in CLASSES + ["all"]:
        subset = base if cls == "all" else base[base.route_class.eq(cls)]
        intended = len(expected) if cls == "all" else sum(x.startswith(cls + "_") for x in expected)
        summary.append({"route_class": cls, "stored_routes": intended, **summarize(subset[subset.feasible])})
    summary = pd.DataFrame(summary)
    for name, frame in [("base_pairs", base), ("base_summary", summary), ("sensitivity_summary", sens),
                        ("interaction_summary", heat), ("diesel_references", refs)]:
        # Export only analysis fields, not a duplicate of raw serialized timelines.
        frame.drop(columns=["activity_timeline"], errors="ignore").to_csv(TABLE / f"{name}.csv", index=False)
    table = [r"\begin{table}[htbp]", r"\centering", r"\begin{threeparttable}",
             r"\caption{Draft base-case comparison of partial-charging electric schedules with the diesel reference.}",
             r"\label{tab:conditions_base}", r"\small\setlength{\tabcolsep}{4pt}",
             r"\begin{tabular}{lrrrrrrr}", r"\toprule",
             r"Route & Pairs & Diesel & Electric & Mean gap & P90 gap & Mean gap & Max. gap \\",
             r"class & & (h) & (h) & (\%) & (\%) & (min) & (min) \\", r"\midrule"]
    for _, row in summary.iterrows():
        if row.route_class == "all":
            table.append(r"\midrule")
        table.append(f"{NAMES[row.route_class]} & {int(row.n)} & {row.diesel_hours:.2f} & {row.ev_hours:.2f} & {row.mean_gap_pct:.2f} & {row.p90_gap_pct:.2f} & {row.mean_gap_minutes:.1f} & {row.max_gap_minutes:.1f}" + r" \\")
    table += [r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}[flushleft]\footnotesize",
              r"\item Pairs reports available historical paired records; final benchmark membership remains unresolved. All available pairs are reported feasible; missing records have unknown status. Durations and percentage gaps are averaged over routes, with each route weighted equally. P90 is the empirical 90th percentile of paired percentage gaps (linear interpolation).",
              r"\item Saved base settings: 750~kWh, 350~kW, 60~km station spacing, and 1.49~kWh/km. Historical input hashes and solver termination status are unavailable.",
              r"\end{tablenotes}", r"\end{threeparttable}", r"\end{table}"]
    (TABLE / "base_summary.tex").write_text("\n".join(table) + "\n", encoding="utf-8")
    levels = {p: sorted(float(x) for x in sweep[p].unique()) for p in PARAMS}
    expected_grid = list(itertools.product(expected, *(levels[p] for p in PARAMS)))
    present = set(sweep[["instance_id"] + list(PARAMS)].itertuples(index=False, name=None))
    absent = [row for row in expected_grid if row not in present]
    pd.DataFrame(absent, columns=["instance_id"] + list(PARAMS)).to_csv(TABLE / "absent_from_comparison_grid.csv", index=False)
    audit = {
        "status": "exploratory inherited data; not a verified complete experiment",
        "sources": {k: {"path": str(Path(p).relative_to(ROOT)), "sha256": sha(p), "selection": config[k]} for k, p in sources.items()},
        "analysis_sha256": sha(__file__), "base_settings": {p: v for p, (v, _) in PARAMS.items()},
        "stored_routes": len(expected), "base_pairs": len(base),
        "base_missing_routes": sorted(set(expected) - set(base.instance_id)),
        "base_summary": summary.to_dict("records"), "partial_sweep_rows": len(sweep),
        "partial_sweep_routes": int(sweep.instance_id.nunique()), "levels": levels,
        "comparison_grid_size": len(expected_grid), "absent_records_unknown_status": len(absent),
        "sensitivity_cohort": sorted(common), "interaction_cohort": sorted(heat_common),
        "older_diesel_reference_additions": sorted(additions.instance_id),
        "diesel_overlap_consistency_pairs": len(overlap), "base_sweep_consistency_pairs": int(mask.sum()),
        "max_base_reported_computation_seconds": float(ev.computation_time_seconds.max()),
        "limitations": ["Complete-case sensitivities cover short routes only and may be selected by solve difficulty.",
                        "Missing rows do not establish infeasibility or timeout.",
                        "No optimality/termination status is stored in the selected files.",
                        "Station-spacing changes regenerate candidate locations; configurations need not be nested.",
                        "Extended spacing archive contains full charging only and is excluded.",
                        "The manuscript parameter table must be reconciled with saved base settings."]}
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(summary.to_string(index=False))
    print("Sensitivity cohort:", len(common), "short routes; interaction cohort:", len(heat_common))
    print(sens[["parameter", "level", "n", "mean_gap_pct", "p90_gap_pct"]].to_string(index=False))
    print("Saved three figures (PDF/PNG), a LaTeX table, source hashes, paired data, and missing-grid diagnostics.")


if __name__ == "__main__":
    main()
