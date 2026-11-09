"""Regenerate the Section 5.3 paper figures: python -m analysis.simple_rules.run"""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

from analysis.conditions.data import BASE, CLASSES, MEMBERS, NAMES, SOURCE, at_base
from analysis.conditions.plot_helpers import INK


OUT = Path(__file__).resolve().parent
FIG = OUT / "figures"
BASE_HOURS = 1.0
POLICIES = ["full", "overlap"]
LABEL = {"full": "Full-charge heuristic", "overlap": "Overlap-only heuristic"}
COLOR = {"full": "#B06C32", "overlap": "#197F85"}
MARKER = {"full": "D", "overlap": "o"}
GRID = "#DFE5E7"


def matched_results():
    members = MEMBERS.read_text().splitlines()
    if len(set(members)) != len(members):
        raise ValueError("Duplicate instance in the paper membership list.")
    raw = at_base(pd.read_csv(SOURCE))
    raw = raw[raw.instance_id.isin(members) & raw.vehicle_type.eq("electric")
              & raw.synchronization_enabled.eq(True) & raw.record_status.eq("record_available")]
    reference = raw[raw.policy.eq("partial_labeling") & raw.charging_policy.eq("partial")]
    driver = raw[raw.policy.eq("driver_heuristic") & raw.charging_policy.isin(POLICIES)].copy()
    if driver.result_conflict.any() or reference.result_conflict.any():
        raise ValueError("Resolve conflicting model runs before comparing route times.")
    if driver.t_sync_hours.isna().any():
        raise ValueError("Missing synchronization horizon in a heuristic run.")
    if driver.duplicated(["instance_id", "t_sync_hours", "charging_policy"]).any():
        raise ValueError("Several heuristic configurations match the same route and horizon.")
    keys = ["instance_id", "input_version", "safety_buffer_fraction"]
    reference = reference[reference.feasible_reported.eq(True) & reference.makespan_hours.gt(0)
                          & ~reference.schedule_valid_reported.eq(False)]
    reference = reference[keys + ["makespan_hours"]].rename(columns={"makespan_hours": "reference_hours"})
    driver = driver.merge(reference, on=keys, how="left", validate="many_to_one")
    driver["valid"] = driver.feasible_reported.eq(True) & driver.schedule_valid_reported.eq(True)
    if (driver.valid & ~driver.makespan_hours.gt(0)).any():
        raise ValueError("A validated schedule has no positive route duration.")
    valid = driver.valid & driver.reference_hours.gt(0)
    driver["gap"] = (100 * (driver.makespan_hours / driver.reference_hours - 1)).where(valid)
    driver.loc[driver.gap.abs().lt(1e-8), "gap"] = 0
    hours = sorted(driver.t_sync_hours.unique())
    if BASE_HOURS not in hours:
        raise ValueError("The manuscript's one-hour base case is unavailable.")
    columns = pd.MultiIndex.from_product([hours, POLICIES], names=["t_sync_hours", "charging_policy"])
    wide = driver.pivot(index="instance_id", columns=["t_sync_hours", "charging_policy"], values="gap")
    wide = wide.reindex(index=members, columns=columns)
    base = driver.loc[driver.t_sync_hours.eq(BASE_HOURS) & valid]
    headline = base.pivot(index=keys, columns="charging_policy", values="gap")
    headline = headline.reindex(columns=POLICIES).dropna().droplevel(keys[1:])
    sweep = wide.dropna()
    if headline.empty or len(sweep) < 2:
        raise ValueError("The box plot needs matched policies and the SD bands need at least two matched routes.")
    return headline, sweep, driver, members


def export(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    for extension in ("pdf", "png"):
        fig.savefig(FIG / f"{name}.{extension}", dpi=210, bbox_inches="tight", pad_inches=.055)
    plt.close(fig)


def draw_premiums(headline):
    low = min(0, headline.min().min())
    high = max(0, headline.max().max())
    margin = .035 * (high - low or 1)
    for policy in POLICIES:
        values = headline[policy]
        color = COLOR[policy]
        groups = [("All routes", values)]
        for key in CLASSES:
            groups.append((NAMES[key], values[values.index.str.startswith(key + "_")]))

        fig, ax = plt.subplots(figsize=(6.1, 2.8))
        fig.subplots_adjust(left=.15, right=.85, bottom=.20, top=.92)
        positions = [3.35, 2, 1, 0]
        labels = []
        for y, (name, group) in zip(positions, groups):
            labels.append(f"{name}  ($n$ = {len(group)})")
            if group.empty:
                continue
            ax.boxplot(group, positions=[y], widths=.40, vert=False, patch_artist=True,
                       manage_ticks=False, whis=1.5,
                       boxprops=dict(facecolor=matplotlib.colors.to_rgba(color, .17), edgecolor=color),
                       whiskerprops=dict(color=color), capprops=dict(color=color),
                       medianprops=dict(color=INK, linewidth=1.1),
                       flierprops=dict(marker="o", markersize=3.6, markerfacecolor="white",
                                       markeredgecolor=color))
            mean = group.mean()
            ax.scatter(mean, y, s=30, marker="D", facecolor=color, edgecolor="white",
                       linewidth=.6, zorder=4)
            ax.text(1.025, y, f"{mean:.2f}%", transform=ax.get_yaxis_transform(),
                    ha="left", va="center", color=color,
                    fontweight="bold" if name == "All routes" else "normal")
        ax.text(1.025, 1.01, "Mean", transform=ax.transAxes, ha="left", color=INK)
        ax.axhline(2.67, color=GRID, linewidth=.7)
        ax.set_yticks(positions, labels)
        ax.get_yticklabels()[0].set_fontweight("bold")
        ax.set_ylim(-.60, 3.95)
        ax.set_xlim(low - margin, high + margin)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
        ax.grid(axis="x", color=GRID, linewidth=.6)
        ax.set_axisbelow(True)
        ax.spines[["left", "top", "right"]].set_visible(False)
        ax.tick_params(axis="y", length=0, pad=5)
        ax.set_xlabel(f"Route-time premium for the {LABEL[policy].lower()} (%)")
        export(fig, f"{policy}_premium")


def draw_horizons(sweep):
    fig, ax = plt.subplots(figsize=(6.1, 3.2))
    fig.subplots_adjust(left=.12, right=.985, bottom=.23, top=.84)
    hours = sweep.columns.get_level_values("t_sync_hours").unique().to_numpy()
    mins = hours * 60
    step = np.diff(mins).min() if len(mins) > 1 else 15
    for policy in POLICIES:
        gaps = sweep.xs(policy, axis=1, level="charging_policy").reindex(columns=hours)
        means = gaps.mean().to_numpy()
        sd = gaps.std(ddof=1).to_numpy()
        ax.fill_between(mins, means - sd, means + sd, color=COLOR[policy], alpha=.16,
                        linewidth=.6, zorder=1)
        ax.plot(mins, means, color=COLOR[policy], marker=MARKER[policy],
                linestyle="-" if policy == "full" else "--", linewidth=1.55,
                markersize=4.3, markeredgecolor="white", markeredgewidth=.45,
                label=LABEL[policy], zorder=3)
    ax.axhline(0, color="#89959B", linewidth=.7, zorder=2)
    ax.set_xticks(mins, [f"{m:g}" + ("\n(base)" if h == BASE_HOURS else "")
                          for m, h in zip(mins, hours)])
    ax.set_xlim(mins[0] - .32 * step, mins[-1] + 1.25 * step)
    tick = ax.get_xticklabels()[-1]
    ax.text(ax.get_xlim()[1], 0, "min", transform=tick.get_transform(), ha="right",
            va=tick.get_va(), fontproperties=tick.get_fontproperties(), color=tick.get_color())
    ax.grid(axis="y", color=GRID, linewidth=.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylabel("Gap to partial-charging labeling (%)")
    ax.set_xlabel("Synchronization horizon")
    fig.legend(loc="upper center", frameon=False, ncol=2)
    export(fig, "sync_horizon")


def package_figures(headline, sweep, driver, members):
    n = len(members)
    feasible = driver.groupby(["t_sync_hours", "charging_policy"]).valid.sum()
    coverage = (f"Both policies produced validated schedules for all {n} instances at every tested horizon."
                if len(sweep) == n and feasible.eq(n).all()
                else f"The plotted cohort contains {len(sweep)} of the {n} paper instances with "
                     "validated schedules for both policies and a reference duration at every tested horizon.")
    battery, power, spacing, consumption = BASE
    box_caption = (
        rf"Route-time premiums on {len(headline)} base-case routes at $t^{{\mathrm{{sync}}}}={BASE_HOURS:g}$~h. "
        r"Each premium is $100(T_{\mathrm{heuristic}}-T_{\mathrm{partial}})/T_{\mathrm{partial}}$, "
        r"where $T_{\mathrm{partial}}$ is the partial-charging labeling time for the same route. "
        "Diamonds and labels give the mean route-level premium. Boxes span the interquartile range, "
        "with a line at the median. Whiskers extend to the most extreme observation within "
        "1.5 interquartile ranges of the box. Open circles mark observations beyond the whiskers. "
        f"The base settings are {battery:g}~kWh, {power:g}~kW, {spacing:g}~km, and {consumption:g}~kWh/km.")
    horizon_caption = (
        f"Mean route-time premium across the same {len(sweep)} routes at each synchronization "
        "horizon, relative to partial-charging labeling for each route. Markers show tested horizons. "
        "Shaded bands extend one sample standard deviation above and below each policy mean. " + coverage)
    source = OUT / "simple_rules.tex"
    source.write_text(rf"""Figure~\ref{{fig:heuristic_premiums}} shows the route-time premium of each heuristic relative to partial-charging labeling, overall and by route class.

\begin{{figure}}[tbp]
    \centering
    \begin{{subfigure}}[b]{{0.49\linewidth}}
        \centering
        \includegraphics[width=\linewidth]{{figures/simple_rules/full_premium.pdf}}
        \caption{{Full-charge}}\label{{fig:full_premium}}
    \end{{subfigure}}\hfill
    \begin{{subfigure}}[b]{{0.49\linewidth}}
        \centering
        \includegraphics[width=\linewidth]{{figures/simple_rules/overlap_premium.pdf}}
        \caption{{Overlap-only}}\label{{fig:overlap_premium}}
    \end{{subfigure}}
    \caption{{{box_caption}}}
    \label{{fig:heuristic_premiums}}
\end{{figure}}

Figure~\ref{{fig:sync_horizon}} shows how the mean premium and its variation across routes change with the synchronization horizon.

\begin{{figure}}[tbp]
    \centering
    \includegraphics[width=\linewidth]{{figures/simple_rules/sync_horizon.pdf}}
    \caption{{{horizon_caption}}}
    \label{{fig:sync_horizon}}
\end{{figure}}
""", encoding="utf-8")
    archive = OUT / "simple_rules.zip"
    staging = archive.with_suffix(".zip.tmp")
    with ZipFile(staging, "w", ZIP_DEFLATED) as bundle:
        bundle.write(source, source.name)
        for key in ("full_premium", "overlap_premium", "sync_horizon"):
            bundle.write(FIG / f"{key}.pdf", f"figures/simple_rules/{key}.pdf")
    staging.replace(archive)


def main():
    headline, sweep, driver, members = matched_results()
    with plt.rc_context({"font.family": "serif", "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
                         "mathtext.fontset": "stix", "font.size": 9.5, "text.color": INK,
                         "axes.labelcolor": INK, "axes.edgecolor": "#8A979D", "axes.linewidth": .65,
                         "xtick.color": INK, "ytick.color": INK, "xtick.labelsize": 8.1,
                         "ytick.labelsize": 8.5, "pdf.fonttype": 42}):
        draw_premiums(headline)
        draw_horizons(sweep)
    package_figures(headline, sweep, driver, members)


if __name__ == "__main__":
    main()
