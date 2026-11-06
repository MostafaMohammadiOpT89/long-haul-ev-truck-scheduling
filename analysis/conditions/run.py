"""Current paper figures: base comparison and class-specific sensitivity bars.

Run: python -m analysis.conditions.run
Base, sensitivity and operational panels, tables and Overleaf snippets.
"""
import json
import math
import zipfile
from pathlib import Path
from shutil import copyfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from analysis.common.inputs import ANALYSIS_OUTPUT
from analysis.conditions.data import (
    ROOT, SOURCE, MEMBERS, BASE, PARAMETERS, CLASSES, NAMES, sha,
    load_pairs, matched_slices, summarize,
)
from analysis.conditions.plot_helpers import COLORS, INK, clean, draw_base, class_statistics
from analysis.conditions.operations import generate as generate_operations

OUT = ANALYSIS_OUTPUT / "conditions"
FIG = OUT / "figures"
TABLE = OUT / "tables"
LATEX = OUT / "latex"
PREVIEW = OUT / "previews"
KEYS = ["battery", "power", "spacing", "consumption"]
LABELS = ["Battery capacity (kWh)", "Charging power (kW)", "Station spacing (km)", "Energy consumption (kWh/km)"]
BASE_CAPTION = ("The base configuration is 750~kWh battery capacity, 350~kW charging power, "
                "60~km maximum charging-station spacing, and 1.49~kWh/km energy consumption.")


def shared_limit(stats):
    return max(1, math.ceil(1.08 * max(stats.q75.max(), stats.mean_gap_pct.max())))


def draw_sensitivity(ax, parameter, stats, cohort, index, ymax):
    selected = stats[stats.parameter.eq(parameter)]
    levels = sorted(selected.level.unique())
    present = [route for route in CLASSES if cohort["route_classes"][route] > 0]
    ticks = np.arange(len(levels))
    handles = []
    for route, color in zip(CLASSES, COLORS):
        n = cohort["route_classes"][route]
        if n == 0:
            handles.append(Line2D([], [], color="#ADB5BA", marker="x", ls="",
                                  label=f"{NAMES[route]}: no matched data", markersize=5))
            continue
        values = selected[selected.route_class.eq(route)].sort_values("level")
        assert list(values.level) == levels and values.n.eq(n).all()
        means, q25, q75 = values.mean_gap_pct.to_numpy(), values.q25.to_numpy(), values.q75.to_numpy()
        width = .70 / len(present)
        x = ticks + (present.index(route) - (len(present) - 1) / 2) * width
        ax.bar(x, means, width=width * .90, color=color, alpha=.86,
               edgecolor=color, linewidth=.6, zorder=3)
        # IQR endpoints, not confidence intervals or errors around the mean.
        ax.vlines(x, q25, q75, colors=INK, linewidth=1.05, zorder=4)
        for quantile in (q25, q75):
            ax.hlines(quantile, x - width * .16, x + width * .16, color=INK, linewidth=1.05, zorder=4)
        zero = np.isclose(means, 0, atol=1e-12)
        ax.scatter(x[zero], means[zero], marker="_", s=65, color=color,
                   linewidth=2.2, zorder=5, clip_on=False)
        handles.append(Patch(facecolor=color, alpha=.86, label=f"{NAMES[route]} (n = {n})"))
    ax.set_xticks(ticks, [f"{v:g}" + ("\n(base)" if v == BASE[index] else "") for v in levels])
    ax.set_xlim(-.6, len(levels) - .4)
    ax.set_xlabel(LABELS[index])
    ax.set_ylabel("Electric minus diesel (%)")
    ax.set_ylim(0, ymax)
    ax.set_yticks(np.arange(0, ymax + .1, max(1, math.ceil(ymax / 5))))
    clean(ax)
    ax.legend(handles=handles, loc="upper right" if index < 2 else "upper left",
              frameon=False, fontsize=9.5, handlelength=1.6, labelspacing=.35, borderaxespad=.5)


def save_panel(fig, name):
    fig.savefig(FIG / f"{name}.pdf", facecolor="white")
    fig.savefig(FIG / f"{name}.png", dpi=220, facecolor="white")
    plt.close(fig)


def write_latex(summary, cohorts):
    def panel(file, caption, label):
        return [r"    \begin{subfigure}[t]{0.49\linewidth}", r"        \centering",
                f"        \\includegraphics[width=\\linewidth]{{figures/conditions/{file}.pdf}}",
                f"        \\caption{{{caption}}}", f"        \\label{{{label}}}", r"    \end{subfigure}"]

    base = [r"\begin{figure}[tbp]", r"    \centering"]
    base += panel("time_penalty", "Relative time penalty", "fig:conditions_base_relative")
    base[-1] += r"\hfill"
    base += panel("extra_time", "Additional route time", "fig:conditions_base_additional")
    base += [r"    \caption{Route-time penalties of partial-charging electric schedules relative to diesel",
             "    for all 43 instances (13 short, 15 medium, and 15 long). " + BASE_CAPTION,
             "    Dots show individual instances and diamonds show means. Boxes span the interquartile",
             "    range, with the median shown inside. Whiskers extend to the most extreme observations",
             "    within 1.5 interquartile ranges; all observations are shown.}",
             r"    \label{fig:conditions_base}", r"\end{figure}", ""]
    (LATEX / "base_comparison.tex").write_text("\n".join(base), encoding="utf-8")

    sensitivity = [r"\begin{figure}[tbp]", r"    \centering"]
    for i, (key, label) in enumerate(zip(KEYS, LABELS)):
        sensitivity += panel(key, label.split(" (")[0], f"fig:conditions_{key}")
        if i % 2 == 0:
            sensitivity[-1] += r"\hfill"
        elif i == 1:
            sensitivity += ["", r"    \medskip", ""]
    sample_text = "; ".join(f"({chr(97+i)}) " + ", ".join(
        f"{cohorts[p]['route_classes'][c]} {NAMES[c].lower()}" for c in CLASSES)
        for i, p in enumerate(PARAMETERS))
    missing = cohorts["battery_kwh"]["unavailable_levels"]
    missing_text = (" Battery capacities of " + ", ".join(f"{x:g}" for x in missing) +
                    "~kWh are unavailable and omitted.") if missing else ""
    sensitivity += [r"    \caption{One-at-a-time sensitivity of the electric--diesel route-time penalty,",
                    "    separated by route class. " + BASE_CAPTION,
                    "    All parameters other than the one shown remain at base values. Bars show class means;",
                    "    whiskers span the 25th to 75th percentiles, describing variation across instances,",
                    "    not confidence intervals. A fixed matched set is used within each panel: " + sample_text + ".",
                    "    Sets can differ between panels. Unavailable classes are not plotted as zero." + missing_text,
                    "    All four panels use the same vertical scale.}", r"    \label{fig:conditions_sensitivity}",
                    r"\end{figure}", ""]
    (LATEX / "sensitivities.tex").write_text("\n".join(sensitivity), encoding="utf-8")

    table = [r"\begin{table}[tbp]", r"\centering", r"\begin{threeparttable}",
             r"\caption{Base-case route-time comparison of partial-charging electric schedules with the diesel reference. " + BASE_CAPTION + "}",
             r"\label{tab:conditions_base}", r"\small", r"\setlength{\tabcolsep}{4pt}",
             r"\begin{tabular}{@{}lrrrrrrr@{}}", r"\toprule",
             r"Route class & $n$ & \multicolumn{2}{c}{Mean route time (h)} & \multicolumn{2}{c}{Penalty (\%)} & \multicolumn{2}{c}{Extra time (min)} \\",
             r"\cmidrule(lr){3-4}\cmidrule(lr){5-6}\cmidrule(l){7-8}",
             r" & & Diesel & Electric & Mean & P90 & Mean & Max. \\", r"\midrule"]
    for row in summary.itertuples():
        cells = [NAMES[row.route_class], str(row.n), f"{row.diesel_hours:.2f}", f"{row.electric_hours:.2f}",
                 f"{row.mean_gap_pct:.2f}", f"{row.p90_gap_pct:.2f}", f"{row.mean_gap_minutes:.1f}", f"{row.max_gap_minutes:.1f}"]
        if row.route_class == "all":
            table.append(r"\midrule")
            cells = [r"\textbf{" + value + "}" for value in cells]
        table.append(" & ".join(cells) + r" \\")
    table += [r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}[flushleft]\footnotesize",
              r"\item Each instance receives equal weight. Percentage penalties are calculated as $100(T_i^{\mathrm{EV}}-T_i^{\mathrm{D}})/T_i^{\mathrm{D}}$ before averaging. Extra time is electric minus diesel duration.",
              r"\item P90 denotes the empirical 90th percentile of instance-level percentage penalties, using linear interpolation.",
              r"\end{tablenotes}", r"\end{threeparttable}", r"\end{table}", ""]
    (TABLE / "base_case.tex").write_text("\n".join(table), encoding="utf-8")
    (LATEX / "packages.tex").write_text("\n".join(r"\usepackage{" + p + "}" for p in
        ["graphicx", "subcaption", "booktabs", "threeparttable"]) + "\n", encoding="utf-8")
    (LATEX / "preview.tex").write_text("\n".join([
        r"\documentclass{article}", r"\usepackage[a4paper,margin=20mm]{geometry}", r"\input{packages}",
        r"\begin{document}", r"\input{operational_paragraph}", r"\end{document}", ""]), encoding="utf-8")


def main():
    for folder in (FIG, TABLE, LATEX, PREVIEW):
        folder.mkdir(parents=True, exist_ok=True)
    draft = Path(__file__).with_name("latex") / "operational_paragraph.tex"
    if not (LATEX / draft.name).exists():
        copyfile(draft, LATEX / draft.name)
    assert BASE == (750., 350., 60., 1.49), "Update caption base values"
    plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 10,
                         "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
                         "axes.edgecolor": "#86939A", "axes.linewidth": .65, "pdf.fonttype": 42})
    ev, base = load_pairs()
    frames, cohorts, _ = matched_slices(ev)
    stats = class_statistics(frames)
    ymax = shared_limit(stats)
    for field, key in [("gap_pct", "time_penalty"), ("gap_minutes", "extra_time")]:
        fig, ax = plt.subplots(figsize=(4.25, 3.5))
        draw_base(ax, base, field)
        fig.subplots_adjust(left=.18, right=.98, bottom=.22, top=.98)
        save_panel(fig, key)
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.7))
    for ax, field in zip(axes, ["gap_pct", "gap_minutes"]):
        draw_base(ax, base, field)
    fig.subplots_adjust(left=.08, right=.99, bottom=.25, top=.98, wspace=.34)
    for x, label in [(.29, "(a) Relative time penalty"), (.79, "(b) Additional route time")]:
        fig.text(x, .015, label, ha="center", fontsize=11)
    fig.savefig(PREVIEW / "base_comparison.png", dpi=190, facecolor="white")
    plt.close(fig)
    for i, (parameter, key) in enumerate(zip(PARAMETERS, KEYS)):
        fig, ax = plt.subplots(figsize=(4.25, 3.5))
        draw_sensitivity(ax, parameter, stats, cohorts[parameter], i, ymax)
        fig.subplots_adjust(left=.17, right=.98, bottom=.24, top=.98)
        save_panel(fig, key)
    fig, axes = plt.subplots(2, 2, figsize=(8.5, 7.5))
    for i, (ax, parameter) in enumerate(zip(axes.flat, PARAMETERS)):
        draw_sensitivity(ax, parameter, stats, cohorts[parameter], i, ymax)
        ax.text(.5, -.40, f"({chr(97+i)}) {LABELS[i].split(' (')[0]}", ha="center", va="top", transform=ax.transAxes, fontsize=11)
    fig.subplots_adjust(left=.08, right=.99, bottom=.19, top=.99, hspace=.70, wspace=.30)
    fig.savefig(PREVIEW / "sensitivities.png", dpi=190, facecolor="white")
    plt.close(fig)
    summary = pd.DataFrame([dict(route_class=c, **summarize(base if c == "all" else base[base.route_class.eq(c)]))
                            for c in [*CLASSES, "all"]])
    write_latex(summary, cohorts)
    summary.to_csv(TABLE / "base_case.csv", index=False)
    stats.to_csv(TABLE / "sensitivity.csv", index=False)
    base.to_csv(TABLE / "base_pairs.csv", index=False)
    pd.concat([f.assign(varied_parameter=p) for p, f in frames.items()]).to_csv(TABLE / "sensitivity_pairs.csv", index=False)
    pd.DataFrame([dict(parameter=p, instance_id=i) for p, c in cohorts.items() for i in c["instance_ids"]]).to_csv(TABLE / "matched_instances.csv", index=False)
    audit = dict(source=str(SOURCE.relative_to(ROOT)), source_sha256=sha(SOURCE), membership_sha256=sha(MEMBERS),
                 code_sha256={p.name: sha(p) for p in [Path(__file__), Path(__file__).with_name("data.py"), Path(__file__).with_name("plot_helpers.py")]},
                 base_n=43, base_settings=dict(zip(PARAMETERS, BASE)), cohorts=cohorts,
                 sensitivity_y_limits=[0, ymax], statistics="Equal-weight class means and empirical IQR; not confidence intervals.",
                 limitations=["No long instances currently have complete matched results.",
                              "Solver termination is not certified by the saved records.",
                              "Changing station spacing can change candidate station locations; sets need not be nested."])
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    generate_operations(base, OUT, BASE_CAPTION)
    with zipfile.ZipFile(OUT / "conditions.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(FIG.glob("*.pdf")):
            archive.write(path, "figures/conditions/" + path.name)
        for path in sorted(LATEX.glob("*.tex")):
            archive.write(path, path.name)
        for path in sorted(TABLE.glob("*.tex")):
            archive.write(path, "tables/conditions/" + path.name)
    print(f"Saved eleven panels; all sensitivity axes span 0--{ymax}%.")
    print("Overleaf bundle:", OUT / "conditions.zip")


if __name__ == "__main__":
    main()
