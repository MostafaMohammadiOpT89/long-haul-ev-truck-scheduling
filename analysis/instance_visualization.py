"""Plot benchmark routes in visit order, using cumulative distance in kilometres.

Use --paper for the manuscript panels and the one-page overview of the paper cohort.
The default command exports individual benchmark plots and the six-route overview.
"""
from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.legend_handler import HandlerTuple
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator, StrMethodFormatter

from common.paths import BENCHMARK, ROOT as REPO_ROOT
from analysis.common.inputs import ANALYSIS_OUTPUT

ROOT = BENCHMARK
OUT_DIR = ANALYSIS_OUTPUT / "instance_visualization"
PAPER_FIGURES = REPO_ROOT / "manuscript/synch_paper_latex/figures"
PAPER_MEMBERS = REPO_ROOT / "instances/PAPER_INSTANCE_SET_43.txt"
REPRESENTATIVE = ("short_cl2_cu3_Balanced", "med_cl3_cu13_Balanced", "med_cl3_cu13_Unbalanced")
CS_INTERVAL_KM = 60.0
ROUTE_COLOR = "#59636B"


class NodeKind(Enum):
    ORIGIN = "origin"
    DESTINATION = "destination"
    CUSTOMER = "customer"
    STATION = "station"


@dataclass
class Row:
    node: str
    position_km: float | None
    cluster_idx: int | None
    cluster_center_km: float | None


@dataclass
class SeqNode:
    kind: NodeKind
    name: str
    cluster_idx: int | None = None
    cust_index: int | None = None



ROUTE_Y = 0.0
LABEL_Y_OFFSET_PT = 15
CLUSTER_LABEL_Y = 0.19
CAPTION_Y = -0.085


def _f(s: str) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    return float(s)


def _i(s: str) -> int | None:
    s = (s or "").strip()
    if not s:
        return None
    return int(float(s))


def read_diagnostics(path: Path) -> list[Row]:
    rows: list[Row] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for d in reader:
            node = (d.get("Node") or "").strip()
            rows.append(
                Row(
                    node=node,
                    position_km=_f(d.get("PositionKm", "")),
                    cluster_idx=_i(d.get("ClusterIdx", "")),
                    cluster_center_km=_f(d.get("ClusterCenterKm", "")),
                )
            )
    return rows


def read_distance_matrix(path: Path) -> tuple[list[str], dict[tuple[str, str], float]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        labels = [h.strip() for h in header[1:] if h.strip()]
        dist: dict[tuple[str, str], float] = {}
        for row in reader:
            if not row:
                continue
            src = row[0].strip()
            for j, val in enumerate(row[1 : 1 + len(labels)]):
                if val.strip():
                    dist[(src, labels[j])] = float(val)
    return labels, dist


def setup_pub_style() -> None:
    mpl.rcParams.update(
        {
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "font.family": "serif",
            "font.serif": ["Times New Roman", "DejaVu Serif", "Times", "Nimbus Roman"],
            "mathtext.fontset": "dejavuserif",
            "font.size": 14,
            "axes.labelsize": 15,
            "axes.titlesize": 15,
            "xtick.labelsize": 13,
            "ytick.labelsize": 13,
            "legend.fontsize": 13,
            "axes.linewidth": 0.8,
            "grid.linewidth": 0.4,
            "lines.linewidth": 1.2,
            "patch.linewidth": 0.8,
        }
    )


COLORS = [
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#E69F00",
    "#56B4E9",
    "#F0E442",
    "#000000",
]

ORIGIN_DEST_FACE = "#F4C89A"
ORIGIN_DEST_EDGE = "#C47A2C"
CUSTOMER_FACE = "#D4C4E8"
CUSTOMER_EDGE = "#6B4F8A"
STATION_FACE = "#B8E0B0"
STATION_EDGE = "#3D7A45"


def cluster_color(k: int) -> str:
    return COLORS[k % len(COLORS)]


def discover_instance_ids() -> list[str]:
    ids: list[str] = []
    for diag in sorted(ROOT.glob("*/*_Diagnostics.csv")):
        folder = diag.parent.name
        if folder == OUT_DIR.name:
            continue
        if diag.name != f"{folder}_Diagnostics.csv":
            continue
        ids.append(folder)
    return ids


def titles_for_instance(instance_id: str) -> tuple[str, str]:
    m = re.match(
        r"^(short|med|long)_cl(\d+)_cu(\d+)(?:_(Balanced|Unbalanced))?$",
        instance_id,
    )
    if m:
        h, n_cl, n_cu, bal = m.groups()
        horizon = {"short": "Short horizon", "med": "Medium horizon", "long": "Long horizon"}[h]
        line2 = f"{n_cl} clusters, {n_cu} customers"
        if bal:
            line2 += f" · {bal}"
        return horizon, line2
    line1 = instance_id.replace("_", " ")
    return line1, ""


def leg_distance(dist: dict[tuple[str, str], float], a: str, b: str) -> float:
    if (a, b) in dist:
        return dist[(a, b)]
    if (b, a) in dist:
        return dist[(b, a)]
    raise KeyError(f"No distance between {a!r} and {b!r}")


def build_sequence(rows: list[Row], dist: dict[tuple[str, str], float]) -> tuple[list[SeqNode], list[float]]:
    customers = [
        r
        for r in rows
        if r.node.startswith("Cust") and r.position_km is not None and r.cluster_idx is not None and r.cluster_idx >= 0
    ]
    if not customers:
        raise ValueError("No customer rows in diagnostics")

    sequence: list[SeqNode] = [SeqNode(NodeKind.ORIGIN, "Origin")]
    leg_lengths: list[float] = []
    station_counter = 1
    distance_travelled = 0.0
    next_station_km = CS_INTERVAL_KM

    major_nodes = ["Origin"] + [r.node for r in customers] + ["Destination"]
    for i in range(len(major_nodes) - 1):
        a_name = major_nodes[i]
        b_name = major_nodes[i + 1]
        leg_km = leg_distance(dist, a_name, b_name)

        leg_end_km = distance_travelled + leg_km
        # Charging stations follow one continuous corridor grid.  Do not restart
        # or redistribute the spacing at customer boundaries.
        offsets: list[float] = []
        while next_station_km < leg_end_km - 1e-9:
            if next_station_km > distance_travelled + 1e-9:
                offsets.append(next_station_km - distance_travelled)
            next_station_km += CS_INTERVAL_KM

        consumed = 0.0
        for off in offsets:
            leg_lengths.append(off - consumed)
            sequence.append(SeqNode(NodeKind.STATION, f"s{station_counter}"))
            station_counter += 1
            consumed = off
        leg_lengths.append(leg_km - consumed)
        distance_travelled = leg_end_km

        if b_name == "Destination":
            sequence.append(SeqNode(NodeKind.DESTINATION, "Destination"))
        else:
            cust_num = int(b_name.replace("Cust", ""))
            cust_row = customers[cust_num - 1]
            sequence.append(
                SeqNode(
                    NodeKind.CUSTOMER,
                    b_name,
                    cluster_idx=cust_row.cluster_idx,
                    cust_index=cust_num,
                )
            )

    return sequence, leg_lengths


def load_route(instance_id: str) -> tuple[list[SeqNode], list[float]]:
    folder = ROOT / instance_id
    rows = read_diagnostics(folder / f"{instance_id}_Diagnostics.csv")
    _, distances = read_distance_matrix(folder / f"{instance_id}_DistanceMatrix.csv")
    sequence, legs = build_sequence(rows, distances)
    return sequence, linear_x_positions(legs)


def linear_x_positions(leg_lengths: list[float]) -> list[float]:
    xs = [0.0]
    for leg in leg_lengths:
        xs.append(xs[-1] + leg)
    return xs


def figure_size(*, overview: bool = False) -> tuple[float, float]:
    if overview:
        return (12.0, 4.6)
    return (11.0, 1.9)


def save_figure(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix
    format_name = suffix.lstrip(".") or None
    temp_path = path.with_suffix(suffix + ".tmp")
    fig.savefig(temp_path, format=format_name, bbox_inches="tight", pad_inches=0.02)
    try:
        temp_path.replace(path)
    except PermissionError as exc:
        temp_path.unlink(missing_ok=True)
        raise PermissionError(
            f"Unable to write {path}. Close any open PDF/image viewer or editor that may be locking the file, then rerun."
        ) from exc


def cluster_spans(sequence: list[SeqNode], xs: list[float]) -> list[tuple[int, int, int, float, float]]:
    """Return one span per cluster, from its first to its last customer.

    Charging stations between customers belong visually inside the cluster band;
    they must not split one cluster into several small boxes.
    """
    indices_by_cluster: dict[int, list[int]] = {}
    for i, node in enumerate(sequence):
        if node.kind != NodeKind.CUSTOMER:
            continue
        cluster = node.cluster_idx if node.cluster_idx is not None else 0
        indices_by_cluster.setdefault(cluster, []).append(i)

    spans: list[tuple[int, int, int, float, float]] = []
    for cluster, indices in sorted(indices_by_cluster.items(), key=lambda item: item[1][0]):
        i_start, i_end = min(indices), max(indices)
        spans.append((cluster, i_start, i_end, xs[i_start], xs[i_end]))
    return spans


def customer_label_offsets(
    sequence: list[SeqNode],
    xs: list[float],
    total_km: float,
) -> dict[int, tuple[float, float]]:
    """Fan out labels in point space when customers are visually cramped on the path."""
    cust_idx = [i for i, n in enumerate(sequence) if n.kind == NodeKind.CUSTOMER]
    if not cust_idx:
        return {}

    close_gap = max(0.025 * total_km, 35.0)
    groups: list[list[int]] = []
    current = [cust_idx[0]]
    for idx in cust_idx[1:]:
        if xs[idx] - xs[current[-1]] < close_gap:
            current.append(idx)
        else:
            groups.append(current)
            current = [idx]
    groups.append(current)

    offsets: dict[int, tuple[float, float]] = {}
    for group in groups:
        if len(group) == 1:
            offsets[group[0]] = (0.0, LABEL_Y_OFFSET_PT)
            continue
        for j, i in enumerate(group):
            dx = (j - (len(group) - 1) / 2.0) * 30.0
            dy = LABEL_Y_OFFSET_PT + (5.0 if j % 2 else 0.0)
            offsets[i] = (dx, dy)
    return offsets




def node_label(node: SeqNode) -> str:
    if node.kind == NodeKind.ORIGIN:
        return r"$o$"
    if node.kind == NodeKind.DESTINATION:
        return r"$d$"
    if node.kind == NodeKind.CUSTOMER and node.cust_index is not None:
        return rf"$c_{{{node.cust_index}}}$"
    return node.name


def node_caption(node: SeqNode) -> str | None:
    if node.kind == NodeKind.ORIGIN:
        return "origin"
    if node.kind == NodeKind.DESTINATION:
        return "destination"
    return None


def plot_one_instance(
    ax: plt.Axes,
    instance_folder: str,
    title_line1: str,
    title_line2: str,
    *,
    annotate_customers: bool = True,
    show_legend: bool = True,
    marker_size: float | None = None,
) -> None:
    sequence, xs = load_route(instance_folder)
    total_km = xs[-1]

    customers = [n for n in sequence if n.kind == NodeKind.CUSTOMER]
    n_cust = len(customers)
    n_nodes = len(sequence)
    ms_cust = marker_size if marker_size is not None else max(100.0, min(220.0, 1200.0 / max(n_cust, 1)))
    ms_station = max(30.0, ms_cust * 0.30)

    for cluster, _i0, _i1, x_min, x_max in cluster_spans(sequence, xs):
        pad = max(0.01 * total_km, 8.0)
        ax.add_patch(
            Rectangle(
                (x_min - pad, -0.075),
                (x_max - x_min) + 2 * pad,
                0.15,
                facecolor=cluster_color(cluster),
                edgecolor="none",
                alpha=0.12,
                zorder=0,
            )
        )
    ax.plot([0, total_km], [ROUTE_Y, ROUTE_Y], color=ROUTE_COLOR, linewidth=1.3, zorder=2)

    for i, (node, x) in enumerate(zip(sequence, xs)):
        y = ROUTE_Y
        if node.kind in (NodeKind.ORIGIN, NodeKind.DESTINATION):
            # A text-sized box keeps the endpoint symbol fully inside.
            ax.text(
                x, y, node_label(node), ha="center", va="center", fontsize=12, zorder=6,
                bbox=dict(
                    boxstyle="square,pad=0.28",
                    facecolor=ORIGIN_DEST_FACE,
                    edgecolor=ORIGIN_DEST_EDGE,
                    linewidth=1.0,
                ),
            )
        elif node.kind == NodeKind.CUSTOMER:
            k = node.cluster_idx if node.cluster_idx is not None else 0
            ax.scatter(
                [x],
                [y],
                s=ms_cust,
                marker="o",
                facecolor=cluster_color(k),
                edgecolors=CUSTOMER_EDGE,
                linewidths=0.9,
                alpha=0.95,
                zorder=5,
            )
        else:
            ax.scatter(
                [x],
                [y],
                s=ms_station,
                marker="s",
                facecolor=STATION_FACE,
                edgecolors=STATION_EDGE,
                linewidths=0.7,
                zorder=4,
            )

    # Endpoint labels extend beyond their data coordinates; reserve enough room
    # to prevent clipping at both edges of the axes.
    pad_x = max(12.0, 0.012 * total_km)
    ax.set_xlim(-pad_x, total_km + pad_x)
    ax.set_ylim(-0.10, 0.17)
    ax.margins(x=0)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_yticks([])
    ax.grid(True, axis="x", linestyle=(0, (2, 4)), alpha=0.35)
    ax.set_axisbelow(True)
    # The manuscript caption identifies the instance; omit the in-figure title and frame.
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="x", length=0, pad=3)
    ax.text(
        1.005, -0.105, r"$\longrightarrow\ \mathrm{km}$",
        transform=ax.transAxes, ha="left", va="center", fontsize=13,
        clip_on=False,
    )

    if show_legend:
        marker_legend(ax, loc="upper center", bbox_to_anchor=(0.5, -0.14), fontsize=12)


def marker_legend(parent, *, fontsize, **placement):
    def symbol(shape, face, edge, size):
        return Line2D([], [], linestyle="none", marker=shape, markersize=size,
                      markerfacecolor=face, markeredgecolor=edge, markeredgewidth=0.6)

    handles = [
        symbol("s", ORIGIN_DEST_FACE, ORIGIN_DEST_EDGE, fontsize * 0.62),
        symbol("s", STATION_FACE, STATION_EDGE, fontsize * 0.46),
        tuple(symbol("o", cluster_color(k), CUSTOMER_EDGE, fontsize * 0.58) for k in range(3)),
    ]
    return parent.legend(handles, ["Origin / destination", "Charging station", "Customer (cluster colour)"],
                         handler_map={tuple: HandlerTuple(ndivide=None, pad=0.13)}, ncol=3,
                         frameon=False, handlelength=2.25, handletextpad=0.45,
                         columnspacing=1.5, fontsize=fontsize, **placement)


def save_standalone_legend(folder: Path = OUT_DIR) -> None:
    fig = plt.figure(figsize=(11, 0.34))
    marker_legend(fig, fontsize=14, loc="center")
    # Preserve the panel width so legend type scales with the manuscript panels.
    fig.add_axes([0, 0, 1, 1]).set_axis_off()
    save_figure(fig, folder / "route_corridor_legend.pdf")
    plt.close(fig)


def draw_overview_row(ax, y, sequence, xs, band_pad):
    total = xs[-1]
    ax.plot([0, total], [y, y], color=ROUTE_COLOR, linewidth=0.65, zorder=1)
    for cluster, _, _, left, right in cluster_spans(sequence, xs):
        ax.add_patch(Rectangle((left - band_pad, y - 0.31), right - left + 2 * band_pad,
                               0.62, color=cluster_color(cluster), alpha=0.10, linewidth=0))
    stations = [x for node, x in zip(sequence, xs) if node.kind == NodeKind.STATION]
    ax.scatter(stations, [y] * len(stations), marker="s", s=3.5, facecolors=STATION_FACE,
               edgecolors=STATION_EDGE, linewidths=0.28, zorder=2)
    customers = [(x, cluster_color(node.cluster_idx)) for node, x in zip(sequence, xs)
                 if node.kind == NodeKind.CUSTOMER]
    ax.scatter([x for x, _ in customers], [y] * len(customers), s=15,
               c=[color for _, color in customers], edgecolors=CUSTOMER_EDGE, linewidths=0.35, zorder=3)
    ax.scatter([0, total], [y, y], marker="s", s=14, facecolors=ORIGIN_DEST_FACE,
               edgecolors=ORIGIN_DEST_EDGE, linewidths=0.55, zorder=4, clip_on=False)


def save_paper_overview(folder: Path) -> None:
    members = PAPER_MEMBERS.read_text(encoding="utf-8").splitlines()
    if len(members) != len(set(members)) or len(members) != 43:
        raise ValueError(f"Expected 43 distinct paper instances in {PAPER_MEMBERS}")
    classes = {"short": "Short", "med": "Medium", "long": "Long"}
    groups = {key: [] for key in classes}
    for name in members:
        sequence, xs = load_route(name)
        groups[name.split("_")[0]].append((name, sequence, xs))

    fig = plt.figure(figsize=(6.4, 8.1))
    left, right = 0.262, 0.897
    grid = fig.add_gridspec(3, 1, left=left, right=right, top=0.92, bottom=0.018,
                            hspace=0.19, height_ratios=[len(group) for group in groups.values()])
    marker_legend(fig, loc="upper center", bbox_to_anchor=(0.5, 1.0), fontsize=8)
    for x, label, align in [(0.005, "Instance", "left"),
                            (left, "Distance from origin (km)", "left"),
                            (0.995, "Total (km)", "right")]:
        fig.text(x, 0.949, label, ha=align, va="bottom", fontsize=8.2, color="#414B52")

    for grid_cell, (key, routes) in zip(grid, groups.items()):
        routes.sort(key=lambda route: (route[2][-1], route[0]))
        longest = routes[-1][2][-1]
        ax = fig.add_subplot(grid_cell)
        ax.set(xlim=(0, longest), ylim=(len(routes) - 0.5, -0.5))
        ax.set_yticks([])
        ax.xaxis.tick_top()
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10], integer=True))
        ax.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax.tick_params(axis="x", length=0, pad=3, labelsize=7.5, colors="#505B62")
        ax.grid(axis="x", color="#D8DEE0", linewidth=0.4, linestyle=(0, (2, 3)))
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_visible(False)

        label_x = (0.005 - left) / (right - left)
        total_x = (0.995 - left) / (right - left)
        ax.annotate(f"{classes[key]} routes  ($n$ = {len(routes)})", xy=(label_x, 1),
                    xycoords="axes fraction", xytext=(0, 3), textcoords="offset points",
                    va="bottom", fontsize=9, fontweight="bold", annotation_clip=False)
        for row, (name, sequence, xs) in enumerate(routes):
            draw_overview_row(ax, row, sequence, xs, band_pad=longest * 0.004)
            ax.text(label_x, row, name, transform=ax.get_yaxis_transform(),
                    va="center", fontsize=7.6)
            ax.text(total_x, row, f"{xs[-1]:,.0f}", transform=ax.get_yaxis_transform(),
                    ha="right", va="center", fontsize=7.6)

    fig.savefig(folder / "benchmark_routes.pdf")
    fig.savefig(folder / "benchmark_routes.png", dpi=200)
    plt.close(fig)


def paper_figures() -> None:
    PAPER_FIGURES.mkdir(parents=True, exist_ok=True)
    mpl.rcParams["pdf.fonttype"] = 42
    for name in REPRESENTATIVE:
        fig, ax = plt.subplots(figsize=figure_size())
        plot_one_instance(ax, name, *titles_for_instance(name), show_legend=False)
        fig.subplots_adjust(left=0.055, right=0.995, bottom=0.34, top=0.96)
        save_figure(fig, PAPER_FIGURES / f"route_corridor_{name}.pdf")
        plt.close(fig)
    save_standalone_legend(PAPER_FIGURES)
    save_paper_overview(PAPER_FIGURES)

    preview, axes = plt.subplots(len(REPRESENTATIVE), 1, figsize=(9.4, 4.0))
    preview.subplots_adjust(left=0.025, right=0.92, top=0.99, bottom=0.23, hspace=1.20)
    for letter, name, ax in zip("abc", REPRESENTATIVE, axes):
        plot_one_instance(ax, name, *titles_for_instance(name), show_legend=False)
        ax.text(0.5, -0.52, f"({letter})  {name}", transform=ax.transAxes, ha="center",
                va="top", fontsize=11)
    marker_legend(preview, loc="lower center", fontsize=11)
    save_figure(preview, OUT_DIR / "representative_routes.png")
    plt.close(preview)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", action="store_true", help="regenerate the manuscript route figures")
    args = parser.parse_args()
    setup_pub_style()
    if args.paper:
        paper_figures()
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_ids = discover_instance_ids()
    if not all_ids:
        raise SystemExit(f"No *_Diagnostics.csv found under {ROOT}")

    save_standalone_legend()

    for folder in all_ids:
        l1, l2 = titles_for_instance(folder)
        diag = ROOT / folder / f"{folder}_Diagnostics.csv"
        rows = read_diagnostics(diag)
        n_cust = sum(
            1
            for r in rows
            if r.node.startswith("Cust")
            and r.position_km is not None
            and r.cluster_idx is not None
            and r.cluster_idx >= 0
        )
        annotate = n_cust <= 12
        w, h = figure_size()
        fig, ax = plt.subplots(figsize=(w, h))
        plot_one_instance(ax, folder, l1, l2, annotate_customers=annotate, show_legend=False)
        fig.subplots_adjust(left=0.055, right=0.995, bottom=0.34, top=0.96)
        stem = f"route_corridor_{folder}"
        save_figure(fig, OUT_DIR / f"{stem}.png")
        save_figure(fig, OUT_DIR / f"{stem}.pdf")
        plt.close(fig)

    scenarios: list[tuple[str, str, str]] = [
        ("short_cl3_cu4_Balanced", "Short horizon", "3 clusters, 4 customers · Balanced"),
        ("short_cl3_cu4_Unbalanced", "Short horizon", "3 clusters, 4 customers · Unbalanced"),
        ("med_cl3_cu4_Balanced", "Medium horizon", "3 clusters, 4 customers · Balanced"),
        ("med_cl3_cu4_Unbalanced", "Medium horizon", "3 clusters, 4 customers · Unbalanced"),
        ("long_cl3_cu4_Balanced", "Long horizon", "3 clusters, 4 customers · Balanced"),
        ("long_cl3_cu4_Unbalanced", "Long horizon", "3 clusters, 4 customers · Unbalanced"),
    ]

    fig, axes = plt.subplots(2, 3, figsize=figure_size(overview=True), layout="constrained")
    for ax, (folder, l1, l2) in zip(axes.ravel(), scenarios):
        plot_one_instance(ax, folder, l1, l2, annotate_customers=False, show_legend=False, marker_size=90.0)
    save_figure(fig, OUT_DIR / "route_corridor_overview_2x3.png")
    save_figure(fig, OUT_DIR / "route_corridor_overview_2x3.pdf")
    plt.close(fig)

    print(f"Wrote {len(all_ids)} instance figures (+ overview) under: {OUT_DIR}")


if __name__ == "__main__":
    main()
