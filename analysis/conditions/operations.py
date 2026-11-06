"""Explain base-case penalties and reconstruct charging on minimum-time paths.

The saved charge activity duration is *additional* elapsed time. Physical
charging time is recovered from charged energy / power. For display only,
charging within rest is placed at the end of the rest (placement is not unique).
"""
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from analysis.conditions.data import ROOT, BASE, CLASSES, NAMES, sha
from analysis.conditions.plot_helpers import COLORS, INK

DETAILS = ROOT / "output/runs/details.jsonl"
TOL = 1e-6
CONTEXTS = ["break", "rest", "outside"]
CONTEXT_LABELS = ["During breaks", "During daily rests", "Outside breaks/rests"]
CONTEXT_COLORS = [COLORS[1], COLORS[2], COLORS[0]]
EXAMPLES = [
    ("short_cl2_cu4_Balanced", "rest_overlap", "Charging within daily rests"),
    ("short_cl1_cu4", "early_charge", "Charging outside breaks and rests"),
    ("med_cl3_cu13_Balanced", "extra_breaks", "Charging within additional breaks"),
]


def selected_records(base):
    wanted = set(base.model_run_id) | set(base.diesel_model_run_id)
    records = {}
    with DETAILS.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if record["model_run_id"] in wanted:
                assert not record["result_conflict"]
                records[record["model_run_id"]] = record
    assert set(records) == wanted and len(records) == 86
    return records


def selected_result(record):
    return next(o["result"] for o in record["observations"]
                if o["observation_id"] == record["selected_observation_id"])


def durations(result):
    totals = defaultdict(float)
    for event in result["activity_timeline"]:
        kind = "service" if event["type"].startswith("service@") else event["type"]
        assert kind in {"drive", "service", "charge", "break", "rest"}, kind
        totals[kind] += event["duration_minutes"]
    assert abs(sum(totals.values()) - result["total_route_time_hours"] * 60) < TOL
    return totals


def reconstruct_charges(result, instance_id):
    """Validate chronological energy balance and locate physical charging bars."""
    soc = float(BASE[0])
    charges = []
    interruptions = []
    for index, event in enumerate(result["activity_timeline"]):
        assert abs((event["end_time"] - event["start_time"]) * 60 - event["duration_minutes"]) < TOL
        if event["type"] == "drive":
            soc -= event["distance_km"] * BASE[3]
            assert soc >= -TOL
        if event["type"] in {"break", "rest"}:
            interruptions.append(event)
        if event["type"] != "charge":
            continue
        assert abs(soc - event["arrival_soc_min_kWh"]) < TOL
        energy = event["energy_charged_min_kWh"]
        physical_minutes = energy / event["power_kW"] * 60
        extra = event["extra_charge_time_min_minutes"]
        assert energy > TOL
        assert abs(extra - event["duration_minutes"]) < TOL
        assert abs(event["start_time"] - event["arrival_time_min_hours"]) < TOL
        context = event["sync_window_type"] or "outside"
        assert context in CONTEXTS
        if context == "outside":
            assert event["sync_type"] == "unsync"
            assert abs(physical_minutes - extra) < TOL
            start, end = event["start_time"], event["end_time"]
        else:
            # Current base records require no extra charging at synchronized stops.
            assert abs(extra) < TOL
            stop = interruptions[-1]
            assert stop["type"] == context
            assert abs(stop["end_time"] - event["start_time"]) < TOL
            assert physical_minutes <= stop["duration_minutes"] + TOL
            end = event["start_time"]
            start = end - physical_minutes / 60
            assert start >= stop["start_time"] - TOL
        soc += energy
        assert abs(soc - event["departure_soc_min_kWh"]) < TOL
        assert -TOL <= soc <= BASE[0] + TOL
        charges.append(dict(instance_id=instance_id, route_class=instance_id.split("_")[0],
                            event_index=index, context=context, station=event["cs_node"],
                            energy_kwh=energy, physical_minutes=physical_minutes,
                            outside_minutes=extra, display_start_hours=start, display_end_hours=end,
                            arrival_soc_kwh=event["arrival_soc_min_kWh"], departure_soc_kwh=soc,
                            arrival_to_break_minutes=event["arrival_time_to_break_minutes"],
                            arrival_to_rest_minutes=event["arrival_time_to_rest_minutes"]))
    return charges


def analyze(base):
    records = selected_records(base)
    rows, events, provenance = [], [], []
    for row in base.itertuples():
        er, dr = records[row.model_run_id], records[row.diesel_model_run_id]
        ev, diesel = selected_result(er), selected_result(dr)
        e, d = durations(ev), durations(diesel)
        delta = {k: e[k] - d[k] for k in {"drive", "service", "charge", "break", "rest"}}
        for kind in ["drive", "service", "rest"]:
            assert abs(delta[kind]) < TOL
        assert abs(delta["charge"] + delta["break"] - row.gap_minutes) < TOL
        assert delta["charge"] >= -TOL and delta["break"] >= -TOL
        extra_breaks = ev["number_of_breaks"] - diesel["number_of_breaks"]
        assert abs(45 * extra_breaks - delta["break"]) < TOL
        assert abs(delta["charge"] - ev["total_idle_charging_time_minutes"]) < TOL
        # Equivalent saved observations must not silently change the explanation.
        for o in er["observations"]:
            other = durations(o["result"])
            for kind in e:
                assert abs(other[kind] - e[kind]) < TOL
        category = ("no penalty" if row.gap_minutes < TOL else
                    "charging only" if delta["break"] < TOL else
                    "extra breaks only" if delta["charge"] < TOL else "both")
        rows.append(dict(instance_id=row.instance_id, route_class=row.route_class,
                         label=row.instance_id.split("_", 1)[1].replace("_Balanced", " B").replace("_Unbalanced", " U"),
                         penalty_minutes=row.gap_minutes, outside_minutes=delta["charge"],
                         extra_break_minutes=delta["break"], extra_breaks=extra_breaks,
                         ev_breaks=ev["number_of_breaks"], diesel_breaks=diesel["number_of_breaks"],
                         ev_rests=ev["number_of_rests"], diesel_rests=diesel["number_of_rests"],
                         category=category))
        events.extend(reconstruct_charges(ev, row.instance_id))
        provenance.append(dict(instance_id=row.instance_id, electric_run=row.model_run_id,
                               diesel_run=row.diesel_model_run_id,
                               electric_observation=er["selected_observation_id"],
                               diesel_observation=dr["selected_observation_id"]))
    return pd.DataFrame(rows), pd.DataFrame(events), records, provenance


def charging_summary(events):
    rows = []
    for route in [*CLASSES, "all"]:
        group = events if route == "all" else events[events.route_class.eq(route)]
        for context in CONTEXTS:
            part = group[group.context.eq(context)]
            rows.append(dict(route_class=route, context=context, instances=group.instance_id.nunique(),
                             stops=len(part), total_stops=len(group), energy_kwh=part.energy_kwh.sum(),
                             physical_minutes=part.physical_minutes.sum(),
                             stop_share_pct=100 * len(part) / len(group),
                             energy_share_pct=100 * part.energy_kwh.sum() / group.energy_kwh.sum()))
    return pd.DataFrame(rows)


def penalty_summary(data):
    """Equal-instance class means, including cases with zero time penalty."""
    rows = []
    for route in [*CLASSES, "all"]:
        group = data if route == "all" else data[data.route_class.eq(route)]
        rows.append(dict(route_class=route, n=len(group),
                         no_penalty=int(group.penalty_minutes.lt(TOL).sum()),
                         with_extra_breaks=int(group.extra_breaks.gt(0).sum()),
                         mean_outside_minutes=group.outside_minutes.mean(),
                         mean_extra_break_minutes=group.extra_break_minutes.mean(),
                         mean_penalty_minutes=group.penalty_minutes.mean()))
    return pd.DataFrame(rows)


def write_penalty_table(summary, folder):
    lines = [r"\begin{table}[tbp]", r"    \centering", r"    \begin{threeparttable}",
             r"    \caption{Base-case sources of additional route time relative to diesel, by route class.}",
             r"    \label{tab:penalty_summary}", r"    \small", r"    \setlength{\tabcolsep}{4pt}",
             r"    \begin{tabular}{@{}lrrrrrr@{}}", r"    \toprule",
             r"    Route class & $n$ & \multicolumn{2}{c}{Instances with} & \multicolumn{3}{c}{Mean additional time (min)} \\",
             r"    \cmidrule(lr){3-4}\cmidrule(l){5-7}",
             r"     & & No penalty & Extra breaks & Charging & Breaks & Total \\", r"    \midrule"]
    for row in summary.itertuples():
        cells = [NAMES[row.route_class], str(row.n), str(row.no_penalty), str(row.with_extra_breaks),
                 f"{row.mean_outside_minutes:.1f}", f"{row.mean_extra_break_minutes:.1f}",
                 f"{row.mean_penalty_minutes:.1f}"]
        if row.route_class == "all":
            lines.append(r"    \midrule")
            cells = [r"\textbf{" + c + "}" for c in cells]
        lines.append("    " + " & ".join(cells) + r" \\")
    lines += [r"    \bottomrule", r"    \end{tabular}",
              r"    \begin{tablenotes}[flushleft]\footnotesize",
              r"    \item Charging denotes time spent charging outside breaks and daily rests; Breaks denotes additional break time relative to diesel. Their sum equals the total penalty. Driving, customer-service, and daily-rest durations are identical within each electric--diesel pair.",
              r"    \item Means include every instance in the indicated class, including zero penalties. The overall row weights all 43 instances equally. Extra breaks counts instances with at least one additional break, including those that also incur uncovered charging time.",
              r"    \end{tablenotes}", r"    \end{threeparttable}", r"\end{table}", ""]
    (folder / "penalty_summary.tex").write_text("\n".join(lines), encoding="utf-8")


def save(fig, folder, name):
    fig.savefig(folder / f"{name}.pdf", facecolor="white")
    fig.savefig(folder / f"{name}.png", dpi=200, facecolor="white")
    plt.close(fig)


def plot_penalties(data, folder):
    fig, axes = plt.subplots(1, 3, figsize=(10.7, 5.8))
    for ax, route in zip(axes, CLASSES):
        group = data[data.route_class.eq(route)].sort_values(["penalty_minutes", "instance_id"])
        y = np.arange(len(group))
        ax.barh(y, group.outside_minutes, color=COLORS[0], height=.66)
        ax.barh(y, group.extra_break_minutes, left=group.outside_minutes, color=COLORS[1], height=.66)
        zero = group.penalty_minutes.lt(TOL)
        ax.scatter(np.zeros(zero.sum()), y[zero], facecolor="white", edgecolor=INK,
                   s=20, zorder=4, clip_on=False)
        ax.set_yticks(y, group.label, fontsize=8.5)
        ax.invert_yaxis()
        ax.set_ylim(14.8, -.8)
        ax.set_xlim(0, 192)
        ax.set_xticks([0, 45, 90, 135, 180])
        ax.set_xlabel(f"{NAMES[route]} (n = {len(group)})", labelpad=10)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0, pad=7)
        ax.grid(axis="x", color="#DEE4E7", linewidth=.6)
        ax.set_axisbelow(True)
    fig.legend(handles=[Patch(color=COLORS[0], label="Charging outside breaks/rests"),
                        Patch(color=COLORS[1], label="Additional breaks"),
                        Line2D([], [], marker="o", color="white", markeredgecolor=INK,
                               label="No penalty", markersize=5)],
               loc="upper center", ncol=3, frameon=False, fontsize=9.5, bbox_to_anchor=(.53, .995))
    fig.text(.52, .025, "Additional route time relative to diesel (minutes)", ha="center")
    fig.subplots_adjust(left=.09, right=.99, top=.90, bottom=.16, wspace=.52)
    save(fig, folder, "penalty_parts")


def plot_split(stats, folder):
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.65))
    routes = [*CLASSES, "all"]
    for ax, field, xlabel in zip(axes, ["energy_share_pct", "stop_share_pct"],
                                 ["Share of charged energy (%)", "Share of charging stops (%)"]):
        left = np.zeros(4)
        for context, color in zip(CONTEXTS, CONTEXT_COLORS):
            part = stats[stats.context.eq(context)].set_index("route_class").loc[routes]
            values = part[field].to_numpy()
            ax.barh(np.arange(4), values, left=left, color=color, height=.57)
            for y, (start, value) in enumerate(zip(left, values)):
                small = value < 9
                ax.text(101 if small else start + value / 2, y, f"{value:.1f}",
                        ha="left" if small else "center", va="center", fontsize=9,
                        color=INK if small else "white")
            left += values
        ax.set_yticks(range(4), [f"{'All' if r == 'all' else NAMES[r]} (n = {int(stats[stats.route_class.eq(r)].instances.iloc[0])})" for r in routes])
        ax.set_xlim(0, 114)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_ylim(3.6, -.6)
        ax.set_xlabel(xlabel)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    fig.legend(handles=[Patch(color=c, label=l) for c, l in zip(CONTEXT_COLORS, CONTEXT_LABELS)],
               loc="upper center", ncol=3, frameon=False, fontsize=9.5, bbox_to_anchor=(.54, .995))
    fig.subplots_adjust(left=.15, right=.98, top=.80, bottom=.18, wspace=.58)
    save(fig, folder, "charge_split")


ACTIVITY_COLORS = {"drive": "#DDE3E7", "service": "#77858D", "break": COLORS[1], "rest": COLORS[2]}
CHARGING_COLOR = "#006B5F"
CHARGING_HATCH = "////"


def timeline_legend(fig, loc="lower center", anchor=(.54, .01)):
    handles = [Patch(facecolor=ACTIVITY_COLORS[k], label=l) for k, l in
               [("drive", "Driving"), ("service", "Customer service"), ("break", "Break"), ("rest", "Daily rest")]]
    handles.append(Patch(facecolor=CHARGING_COLOR, edgecolor="white", hatch=CHARGING_HATCH,
                         label="Charging"))
    fig.legend(handles=handles, loc=loc, bbox_to_anchor=anchor, ncol=5, frameon=False, fontsize=9)


def draw_timeline(ax, name, base, data, events, records):
    pair = base[base.instance_id.eq(name)].iloc[0]
    for y, key in [(.58, pair.diesel_model_run_id), (0, pair.model_run_id)]:
        result = selected_result(records[key])
        for event in result["activity_timeline"]:
            kind = "service" if event["type"].startswith("service@") else event["type"]
            if kind == "charge":
                # Diesel proxy charge actions are bookkeeping, not diesel refueling.
                continue
            ax.broken_barh([(event["start_time"], event["duration_minutes"] / 60)],
                           (y - .20, .40), facecolors=ACTIVITY_COLORS[kind],
                           edgecolors="white", linewidth=.25, zorder=2)
        if y == 0:
            for event in events[events.instance_id.eq(name)].itertuples():
                ax.broken_barh([(event.display_start_hours, event.physical_minutes / 60)],
                               (y - .17, .34), facecolors=CHARGING_COLOR,
                               edgecolors="white", hatch=CHARGING_HATCH, linewidth=.25, zorder=3)
        ax.text(result["total_route_time_hours"] + .35, y, f"{result['total_route_time_hours']:.2f} h",
                va="center", fontsize=8.5)
    ax.set_yticks([.58, 0], ["Diesel", "Electric"], fontsize=10)
    ax.set_xlim(0, 61)
    ax.set_xticks(range(0, 61, 10))
    ax.set_ylim(-.30, .88)
    ax.set_xlabel("Elapsed route time (hours)")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#DEE4E7", linewidth=.6)
    ax.set_axisbelow(True)


def plot_timelines(base, data, events, records, folder, preview):
    for name, key, _ in EXAMPLES:
        fig, ax = plt.subplots(figsize=(9.6, 2.1))
        draw_timeline(ax, name, base, data, events, records)
        fig.subplots_adjust(left=.08, right=.995, bottom=.40, top=.96)
        timeline_legend(fig)
        save(fig, folder, key)
    fig, axes = plt.subplots(3, 1, figsize=(9.6, 5.9))
    for i, (ax, (name, _, description)) in enumerate(zip(axes, EXAMPLES)):
        draw_timeline(ax, name, base, data, events, records)
        ax.text(0, 1.18, f"({chr(97+i)}) {description}  |  {name}", transform=ax.transAxes, fontsize=10)
    fig.subplots_adjust(left=.08, right=.995, bottom=.15, top=.93, hspace=1.00)
    timeline_legend(fig, anchor=(.54, .015))
    fig.savefig(preview / "operations.png", dpi=180, facecolor="white")
    plt.close(fig)


def write_latex(folder, base_caption):
    for key, caption in [
        ("penalty_parts", "Decomposition of additional route time relative to diesel for all 43 instances. "
         "Bars separate charging outside breaks/rests from additional break time. Open circles mark zero penalty. "
         "Driving, service, and daily-rest durations are unchanged within each pair. "
         "Instance labels omit the route class; B and U denote Balanced and Unbalanced. " + base_caption),
        ("charge_split", "Charging during breaks, during daily rests, and outside either, by route class and overall. "
         "The left panel pools charged energy; the right pools charging-stop counts. "
         "Sample sizes refer to instances. Constant charging power means energy shares also equal physical charging-time shares. "
         "Shares describe the saved minimum-time paths and are not averages of instance-level percentages. " + base_caption),
    ]:
        (folder / f"{key}.tex").write_text("\n".join([
            r"\begin{figure}[tbp]", r"    \centering",
            f"    \\includegraphics[width=\\linewidth]{{figures/conditions/{key}.pdf}}",
            f"    \\caption{{{caption}}}", f"    \\label{{fig:{key}}}", r"\end{figure}", ""]), encoding="utf-8")
    lines = [r"\begin{figure}[tbp]", r"    \centering"]
    for name, key, label in EXAMPLES:
        lines += [r"    \begin{subfigure}{\linewidth}", r"        \centering",
                  f"        \\includegraphics[width=\\linewidth,trim=0 20bp 0 0,clip]{{figures/conditions/{key}.pdf}}",
                  "        \\caption{" + label + " (\\texttt{" + name.replace("_", r"\_") + "}).}",
                  f"        \\label{{fig:{key}}}", r"    \end{subfigure}", r"    \medskip"]
    # The 2.1-inch-high panel PDFs carry their legend in the bottom 20bp.
    # Hide that band in each panel and include it once outside the subfigures.
    lines += [r"    % One shared legend below all three schedule panels.",
              r"    \includegraphics[width=\linewidth,trim=0 8bp 0 131.2bp,clip]{figures/conditions/extra_breaks.pdf}\par",
              r"    \smallskip",
              "    \\caption{Three illustrative electric--diesel schedule pairs. " + base_caption +
              " Dark teal regions with diagonal hatching show physical charging time reconstructed from charged energy and power. "
              "These regions cover most of the activity-bar height while retaining the actual charging duration on the time axis. "
              "Charging during daily rest is placed at the end of that rest for display; its exact position within the rest is not unique. "
              "All panels use the same time scale. The plots follow the recorded minimum-time paths; interval maxima are not combined with them. "
              "Examples illustrate observed mechanisms and are not representative frequency estimates.}",
              r"    \label{fig:operations}", r"\end{figure}", ""]
    (folder / "operations.tex").write_text("\n".join(lines), encoding="utf-8")


def generate(base, out, base_caption):
    data, events, records, provenance = analyze(base)
    stats = charging_summary(events)
    summary = penalty_summary(data)
    data.to_csv(out / "tables/penalty_parts.csv", index=False)
    events.to_csv(out / "tables/charging_events.csv", index=False)
    stats.to_csv(out / "tables/charge_split.csv", index=False)
    summary.to_csv(out / "tables/penalty_summary.csv", index=False)
    write_penalty_table(summary, out / "tables")
    plot_penalties(data, out / "figures")
    plot_split(stats, out / "figures")
    plot_timelines(base, data, events, records, out / "figures", out / "previews")
    write_latex(out / "latex", base_caption)
    audit = dict(details_sha256=sha(DETAILS), code_sha256=sha(Path(__file__)), base_n=len(data),
                 charging_stops=len(events), physical_charging_minutes=events.physical_minutes.sum(),
                 penalty_minutes=data.penalty_minutes.sum(), outside_minutes=data.outside_minutes.sum(),
                 extra_break_minutes=data.extra_break_minutes.sum(),
                 categories=data.category.value_counts().to_dict(), provenance=provenance,
                 checks=["Paired duration decomposition reconciles for all 43 instances.",
                         "Chronological battery balance and stop energy reconcile on minimum-time paths.",
                         "Charging overlays lie within the stated break/rest or additional-time window.",
                         "Repeated saved electric observations agree on time components."],
                 conventions=["Pooled energy and stop shares, not equal-weight instance shares.",
                              "Rest charging right-aligned for display; within-rest timing is not uniquely observed.",
                              "Diesel proxy charge actions omitted from timeline.",
                              "No optimality or inevitability claim is inferred from the decomposition."])
    (out / "operations_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(stats[stats.route_class.eq("all")].round(3).to_string(index=False))
    print("Penalty minutes:", audit["penalty_minutes"], "from uncovered charging:", audit["outside_minutes"],
          "from additional breaks:", audit["extra_break_minutes"])
