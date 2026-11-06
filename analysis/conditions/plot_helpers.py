"""Shared rendering helpers for the current base and sensitivity figures."""
import numpy as np
import pandas as pd
from analysis.conditions.data import CLASSES, NAMES, summarize
COLORS = ["#247E8B", "#BF783C", "#7967A3"]
INK = "#24333A"

def swarm(values, y_separation):
    """Deterministic offsets keep coincident/nearby observations visible."""
    offsets = np.zeros(len(values))
    candidates = [0.] + [sign * step * .045 for step in range(1, 8) for sign in (1, -1)]
    placed = []
    for index in np.argsort(values, kind="stable"):
        for candidate in candidates:
            if all(abs(values[index] - values[j]) >= y_separation or
                   abs(candidate - offsets[j]) >= .044 for j in placed):
                offsets[index] = candidate
                break
        placed.append(index)
    return offsets


def clean(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#DEE4E7", linewidth=.65)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, color="#86939A")


def draw_base(ax, base, field):
    ymax = 6.2 if field == "gap_pct" else 197
    for i, (route, color) in enumerate(zip(CLASSES, COLORS), 1):
        values = base[base.route_class.eq(route)].sort_values("instance_id")[field].to_numpy()
        ax.boxplot(values, positions=[i], widths=.45, showfliers=False, patch_artist=True,
                   boxprops=dict(facecolor=color, edgecolor=color, alpha=.18),
                   medianprops=dict(color=color, linewidth=1.6),
                   whiskerprops=dict(color=color), capprops=dict(color=color))
        ax.scatter(i + swarm(values, ymax * .029), values, color=color, s=25,
                   edgecolor="white", linewidth=.5, zorder=4)
        ax.scatter(i, values.mean(), marker="D", s=43, facecolor="white", edgecolor=INK, zorder=5)
    ax.set_xticks([1, 2, 3], [f"{NAMES[c]}\n(n = {base.route_class.eq(c).sum()})" for c in CLASSES])
    ax.set_xlim(.5, 3.5)
    ax.set_ylim(-ymax * .035, ymax)
    ax.set_ylabel("Electric minus diesel (%)" if field == "gap_pct" else "Electric minus diesel (minutes)")
    ax.set_yticks(range(7) if field == "gap_pct" else np.arange(0, 181, 30))
    peak = base[field].max()
    ax.annotate(f"{peak:.2f}%" if field == "gap_pct" else f"{peak:.0f} min",
                xy=(2, peak), xytext=(2.20, peak), va="center", fontsize=9, color=COLORS[1])
    clean(ax)


def class_statistics(frames):
    rows = []
    for parameter, frame in frames.items():
        for (route, level), group in frame.groupby(["route_class", parameter]):
            rows.append(dict(parameter=parameter, route_class=route, level=level,
                             **summarize(group), q25=group.gap_pct.quantile(.25),
                             q75=group.gap_pct.quantile(.75)))
    return pd.DataFrame(rows)
