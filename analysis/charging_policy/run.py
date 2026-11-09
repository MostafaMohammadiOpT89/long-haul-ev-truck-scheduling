"""Refresh the base-case Section 5.2 figures: python -m analysis.charging_policy.run"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, StrMethodFormatter
import numpy as np
import pandas as pd

from analysis.conditions.data import BASE, CLASSES, MEMBERS, NAMES, SOURCE, at_base
from analysis.conditions.operations import DETAILS, selected_result
from analysis.conditions.plot_helpers import COLORS, INK, swarm


OUT = Path(__file__).resolve().parent / "figures"
TEAL = "#247E8B"
GRID = "#DCE2E4"
TOL = 1e-5
METHODS = ["full_labeling", "partial_labeling"]


def base_pairs():
    members = MEMBERS.read_text().splitlines()
    raw = at_base(pd.read_csv(SOURCE))
    runs = raw[raw.instance_id.isin(members) & raw.vehicle_type.eq("electric")
               & raw.policy.isin(METHODS) & raw.record_status.eq("record_available")]
    if runs.result_conflict.any():
        raise ValueError("Resolve conflicting base-case labeling results before plotting.")
    runs = runs[runs.synchronization_enabled.eq(True) & runs.feasible_reported.eq(True)
                & runs.makespan_hours.gt(0)]
    key = ["instance_id", "input_version", "t_sync_hours", "safety_buffer_fraction"]
    policy_runs = [runs[runs.policy.eq(method)] for method in METHODS]
    pairs = policy_runs[0].merge(policy_runs[1], on=key, validate="one_to_one",
                                 suffixes=("_full", "_partial"))
    if pairs.empty or pairs.instance_id.duplicated().any():
        raise ValueError("Expected one matched base-case comparison per included instance.")
    pairs["minutes"] = 60 * (pairs.makespan_hours_full - pairs.makespan_hours_partial)
    pairs["percent"] = 100 * pairs.minutes / (60 * pairs.makespan_hours_full)
    pairs["route_class"] = pairs.instance_id.str.split("_").str[0]
    return pairs


def load_schedules(pairs):
    wanted = set(pairs.model_run_id_full) | set(pairs.model_run_id_partial)
    schedules = {}
    with DETAILS.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if record["model_run_id"] in wanted:
                result = selected_result(record)
                if result.get("activity_timeline"):
                    schedules[record["model_run_id"]] = result
    return schedules


def schedule_parts(result):
    # The full-policy log calls both customer and station visits "service".
    # Match those events to actual charging locations by cumulative distance.
    events = []
    km = 0.0
    for event in result["activity_timeline"]:
        if event["type"] == "drive":
            km += event["distance_km"]
        events.append((round(km, 6), event))
    stations = {km for km, event in events if event["type"] == "charge"}
    totals = dict.fromkeys(["drive", "customer", "station", "break", "rest", "charge"], 0.0)
    for km, event in events:
        kind = event["type"]
        if kind == "service":
            kind = "station" if km in stations else "customer"
        elif kind.startswith("service@"):
            kind = "station" if kind.startswith("service@CS_") else "customer"
        totals[kind] += event["duration_minutes"]
    if not np.isclose(sum(totals.values()), result["total_route_time_hours"] * 60, atol=TOL, rtol=0):
        raise ValueError("Timeline components do not sum to the saved route duration.")
    return totals


def checked_details(pairs, schedules):
    rows = []
    for row in pairs.itertuples():
        if row.model_run_id_full not in schedules or row.model_run_id_partial not in schedules:
            continue
        values = {}
        for method in ("full", "partial"):
            result = schedules[getattr(row, "model_run_id_" + method)]
            if abs(result["total_route_time_hours"] - getattr(row, "makespan_hours_" + method)) > TOL:
                raise ValueError(f"Selected schedule differs from summary for {row.instance_id}")
            values[method] = schedule_parts(result)
        delta = {k: values["full"][k] - values["partial"][k] for k in values["full"]}
        if abs(sum(delta.values()) - row.minutes) > TOL:
            raise ValueError(f"Unexplained duration difference for {row.instance_id}")
        rows.append(dict(instance_id=row.instance_id, **delta, minutes=row.minutes))
    if not rows:
        raise ValueError("No matched pairs with both schedules for the example figure.")
    return pd.DataFrame(rows).set_index("instance_id")


def save(fig, stem):
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / f"{stem}.pdf", bbox_inches="tight", pad_inches=0.055)
    fig.savefig(OUT / f"{stem}.png", dpi=200, bbox_inches="tight", pad_inches=0.055)
    plt.close(fig)


def paired_figure(pairs):
    fig, axes = plt.subplots(1, 2, sharey=True, figsize=(7.2, 2.55))
    fig.subplots_adjust(left=.105, right=.99, bottom=.19, top=.82, wspace=.14)
    labels = []
    for category in CLASSES:
        n = pairs.route_class.eq(category).sum()
        labels.append(f"{NAMES[category]}\n$n$ = {n}")
    for ax, field, xlabel in zip(axes, ["minutes", "percent"],
                                 ["Full minus partial (min)", "Full minus partial (% of full route time)"]):
        low = min(0, pairs[field].min())
        high = max(0, pairs[field].max())
        span = high - low or 1
        ax.set_xlim(low - .035 * span, high + .065 * span)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.set_xlabel(xlabel)
        ax.set_ylim(-.62, 2.53)
        ax.set_yticks([2, 1, 0], labels)
        ax.grid(axis="x", color=GRID, linewidth=.6)
        ax.set_axisbelow(True)
        ax.spines[["top", "left", "right"]].set_visible(False)
        ax.tick_params(axis="y", length=0, pad=4)
        for i, category in enumerate(CLASSES):
            x = pairs.loc[pairs.route_class.eq(category), field].sort_index().to_numpy()
            if not len(x):
                continue
            y = 2 - i
            ax.scatter(x, y + 1.75 * swarm(x, .03 * span), s=19, facecolor=COLORS[i],
                       edgecolor="white", linewidth=.4, zorder=3)
            mean = x.mean()
            mean_y = y - .37
            ax.scatter(mean, mean_y, s=26, marker="D", facecolor="white",
                       edgecolor=INK, linewidth=.9, zorder=4)
            label = f"{mean:.1f} min" if field == "minutes" else f"{mean:.2f}%"
            near_right = mean > high - .20 * span
            ax.annotate(label, (mean, mean_y), xytext=(-6 if near_right else 6, 0),
                        textcoords="offset points", ha="right" if near_right else "left",
                        va="center", fontsize=8, color=INK, zorder=5)
    handles = [Line2D([], [], linestyle="none", marker="o", color="#68777D", markersize=5),
               Line2D([], [], linestyle="none", marker="D", markerfacecolor="white",
                      markeredgecolor=INK, markersize=5)]
    fig.legend(handles, [f"Matched instance ($n$ = {len(pairs)})", "Route-class mean"],
               loc="upper center", ncol=2, frameon=False)
    save(fig, "paired_route_time")


def draw_energy(ax, result, policy):
    capacity, _, _, consumption = BASE
    km, soc = 0.0, capacity
    driving, charging = [], []
    for event in result["activity_timeline"]:
        if event["type"] == "drive":
            distance = event["distance_km"]
            after = soc - distance * consumption
            driving.append([(km, soc), (km + distance, after)])
            km, soc = km + distance, after
        elif event["type"] == "charge":
            if policy == "Partial":
                if abs(soc - event["arrival_soc_min_kWh"]) > TOL:
                    raise ValueError("Partial-policy arrival state of charge differs from energy balance.")
                after = soc + event["energy_charged_min_kWh"]
            else:
                after = capacity
            charging.append([(km, soc), (km, after)])
            soc = after
        if not -TOL <= soc <= capacity + TOL:
            raise ValueError("Reconstructed battery energy is out of bounds.")
    if abs(soc - result["final_battery_energy_min_kWh"]) > TOL:
        raise ValueError("Reconstructed terminal battery energy differs from the saved schedule.")
    ax.add_collection(LineCollection(driving, colors="#798891", linewidths=.9))
    ax.add_collection(LineCollection(charging, colors=TEAL, linewidths=1.5))
    ax.set(xlim=(-.015 * km, 1.018 * km), ylim=(-.035 * capacity, 1.05 * capacity),
           yticks=[0, capacity / 2, capacity])
    ax.grid(axis="y", color=GRID, linewidth=.55)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"{policy} charging", loc="left", fontsize=10, pad=4)
    return km


def battery_figure(row, schedules):
    fig, (full, partial) = plt.subplots(2, 1, sharex=True, figsize=(5.0, 3.05))
    fig.subplots_adjust(left=.13, right=.99, bottom=.16, top=.90, hspace=.42)
    full_km = draw_energy(full, schedules[row.model_run_id_full], "Full")
    partial_km = draw_energy(partial, schedules[row.model_run_id_partial], "Partial")
    if abs(full_km - partial_km) > TOL:
        raise ValueError(f"Routes differ in length for {row.name}")
    fig.legend(handles=[Line2D([], [], color="#798891", linewidth=1.1, label="Driving"),
                        Line2D([], [], marker="|", markersize=9, markeredgewidth=1.6,
                               linestyle="none", color=TEAL, label="Charging")],
               loc="upper right", bbox_to_anchor=(1, 1.025), ncol=2,
               frameon=False, fontsize=8.5, handlelength=1.1, columnspacing=1.3)
    partial.set_xlabel("Distance from origin (km)")
    partial.xaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 5, 10], integer=True))
    partial.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    fig.text(.008, .53, "Battery energy (kWh)", va="center", rotation=90)
    save(fig, "battery_profiles")


def breakdown_figure(components):
    fig, ax = plt.subplots(figsize=(4.8, 2.25))
    fig.subplots_adjust(left=.29, right=.99, bottom=.22, top=.99)
    parts = [("Station service", "station"), ("Charging outside\nbreaks and rests", "charge"),
             ("Breaks", "break")]
    for label, key in [("Daily rests", "rest"), ("Customer service", "customer"), ("Driving", "drive")]:
        if abs(components[key]) > TOL:
            parts.append((label, key))
    parts.append(("Total route time", "minutes"))
    values = [components[key] for _, key in parts]
    y = np.arange(len(parts))[::-1]
    ax.axvline(0, color="#7E898D", linewidth=.8, zorder=1)
    ax.barh(y, values, height=.46,
            color=["#A395B7" if k == "station" else TEAL if k == "charge" else
                   INK if k == "minutes" else "#B77E48" for _, k in parts], zorder=2)
    width = max(max(values), 0) - min(min(values), 0) or 1
    ax.set_xlim(min(min(values), 0) - .18 * width, max(max(values), 0) + .21 * width)
    for yy, x in zip(y, values):
        inside = x < -.24 * width
        offset = 3 if inside or x >= 0 else -3
        ax.annotate(f"{x:+.1f}", (x, yy), xytext=(offset, 0), color="white" if inside else INK,
                    textcoords="offset points", ha="left" if offset > 0 else "right", va="center", fontsize=8.4)
    ax.axhline(.5, color=GRID, linewidth=.7)
    ax.set_yticks(y, [label for label, _ in parts])
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.set_xlabel("Full minus partial (min)")
    ax.tick_params(axis="y", length=0)
    ax.spines[["top", "left", "right"]].set_visible(False)
    save(fig, "time_breakdown")


def main():
    pairs = base_pairs()
    schedules = load_schedules(pairs)
    details = checked_details(pairs, schedules)
    with plt.rc_context({"font.family": "serif", "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
                         "font.size": 9.5, "text.color": INK, "axes.labelcolor": INK,
                         "axes.edgecolor": "#87959C", "axes.linewidth": .65,
                         "xtick.color": INK, "ytick.color": INK, "xtick.labelsize": 8.6,
                         "ytick.labelsize": 8.6, "pdf.fonttype": 42, "mathtext.fontset": "stix"}):
        paired_figure(pairs)
        # Use the same largest-gap example for both standalone figures.
        name = details.sort_index().minutes.idxmax()
        battery_figure(pairs.set_index("instance_id").loc[name], schedules)
        breakdown_figure(details.loc[name])


if __name__ == "__main__":
    main()
