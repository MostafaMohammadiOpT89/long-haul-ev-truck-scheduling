"""
Predetermined customer-sequence route visualizations for test instances.

Single horizontal line (left → right): origin, corridor charging stations, customers
in visit order, and destination. Segment lengths are proportional to leg distance
(km) from each instance distance matrix; leg colour encodes within- / between-cluster
travel.

Writes one figure (PNG + PDF) per instance under figures_route_corridor/, plus a
2×3 overview for the six cl3_cu4 balanced/unbalanced short/med/long cases.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

from common.paths import BENCHMARK
from analysis.inputs import ANALYSIS_OUTPUT
ROOT = BENCHMARK
OUT_DIR = ANALYSIS_OUTPUT / "instance_visualization"

CS_INTERVAL_KM = 60.0


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


@dataclass
class LegStyle:
    label: str
    color: str
    linestyle: str = "-"
    linewidth: float = 1.4


LEG_STYLES = {
    "origin_departure": LegStyle("Origin → first customer", "#D55E00", "-", 1.6),
    "intra_cluster": LegStyle("Within cluster", "#0072B2", "-", 1.4),
    "inter_cluster": LegStyle("Between clusters", "#CC79A7", "-", 1.5),
    "return": LegStyle("Last customer → destination", "#009E73", "-", 1.6),
}

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


def classify_leg(sequence: list[SeqNode], leg_idx: int) -> str:
    if leg_idx >= len(sequence) - 1:
        return "inter_cluster"
    nxt = sequence[leg_idx + 1]
    cur = sequence[leg_idx]

    if cur.kind == NodeKind.ORIGIN:
        return "origin_departure"
    if nxt.kind == NodeKind.DESTINATION:
        return "return"

    if cur.kind == NodeKind.CUSTOMER and nxt.kind == NodeKind.CUSTOMER:
        if cur.cluster_idx == nxt.cluster_idx:
            return "intra_cluster"
        return "inter_cluster"

    prev_cust = None
    for j in range(leg_idx, -1, -1):
        if sequence[j].kind == NodeKind.CUSTOMER:
            prev_cust = sequence[j]
            break
    next_cust = None
    for j in range(leg_idx + 1, len(sequence)):
        if sequence[j].kind == NodeKind.CUSTOMER:
            next_cust = sequence[j]
            break

    if prev_cust and next_cust and prev_cust.cluster_idx == next_cust.cluster_idx:
        return "intra_cluster"
    if prev_cust and next_cust:
        return "inter_cluster"
    if prev_cust and nxt.kind == NodeKind.DESTINATION:
        return "return"
    if cur.kind == NodeKind.ORIGIN or prev_cust is None:
        return "origin_departure"
    return "inter_cluster"


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


def draw_route_segment(
    ax: plt.Axes,
    x0: float,
    x1: float,
    style_key: str,
    *,
    arrow: bool = False,
) -> None:
    style = LEG_STYLES[style_key]
    p0 = (x0, ROUTE_Y)
    p1 = (x1, ROUTE_Y)
    if arrow:
        arr = FancyArrowPatch(
            p0,
            p1,
            arrowstyle="-|>",
            mutation_scale=10,
            color=style.color,
            linewidth=style.linewidth,
            linestyle=style.linestyle,
            shrinkA=6,
            shrinkB=6,
            zorder=2,
        )
        ax.add_patch(arr)
    else:
        ax.plot(
            [x0, x1],
            [ROUTE_Y, ROUTE_Y],
            color=style.color,
            linewidth=style.linewidth,
            linestyle=style.linestyle,
            solid_capstyle="round",
            zorder=2,
        )


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
    diag = ROOT / instance_folder / f"{instance_folder}_Diagnostics.csv"
    dist_path = ROOT / instance_folder / f"{instance_folder}_DistanceMatrix.csv"
    if not diag.exists():
        raise FileNotFoundError(diag)
    if not dist_path.exists():
        raise FileNotFoundError(dist_path)

    rows = read_diagnostics(diag)
    _, dist = read_distance_matrix(dist_path)
    sequence, leg_lengths = build_sequence(rows, dist)
    xs = linear_x_positions(leg_lengths)
    total_km = xs[-1] if xs else 0.0

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
    for i in range(len(sequence) - 1):
        style_key = classify_leg(sequence, i)
        draw_route_segment(ax, xs[i], xs[i + 1], style_key, arrow=(i == len(sequence) - 2))

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
    ax.axhline(ROUTE_Y, color="0.82", linewidth=2.4, zorder=0, solid_capstyle="butt")
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
        from matplotlib.lines import Line2D

        seen: set[str] = set()
        leg_handles = []
        for i in range(len(sequence) - 1):
            key = classify_leg(sequence, i)
            if key in seen:
                continue
            seen.add(key)
            st = LEG_STYLES[key]
            leg_handles.append(Line2D([0], [0], color=st.color, linewidth=st.linewidth, label=st.label))
        leg_handles.extend(
            [
                Line2D(
                    [0],
                    [0],
                    marker="s",
                    linestyle="None",
                    markerfacecolor=ORIGIN_DEST_FACE,
                    markeredgecolor=ORIGIN_DEST_EDGE,
                    markersize=7,
                    label="Origin / destination",
                ),
                Line2D(
                    [0],
                    [0],
                    marker="o",
                    linestyle="None",
                    markerfacecolor=CUSTOMER_FACE,
                    markeredgecolor=CUSTOMER_EDGE,
                    markersize=7,
                    label="Customer (cluster colour)",
                ),
                Line2D(
                    [0],
                    [0],
                    marker="s",
                    linestyle="None",
                    markerfacecolor=STATION_FACE,
                    markeredgecolor=STATION_EDGE,
                    markersize=5,
                    label="Charging station",
                ),
            ]
        )
        ncols = 3 if len(leg_handles) > 4 else 2
        ax.legend(
            handles=leg_handles,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.14),
            ncol=ncols,
            framealpha=0.95,
            edgecolor="0.8",
            columnspacing=1.0,
            handletextpad=0.4,
            borderpad=0.35,
            labelspacing=0.3,
        )


def save_standalone_legend() -> None:
    """Save the shared legend once for inclusion as a manuscript subfigure."""
    from matplotlib.lines import Line2D

    handles = [
        Line2D([0], [0], color=style.color, linewidth=2.4, label=style.label)
        for style in LEG_STYLES.values()
    ]
    handles.extend(
        [
            Line2D(
                [0], [0], marker="s", linestyle="None",
                markerfacecolor=ORIGIN_DEST_FACE, markeredgecolor=ORIGIN_DEST_EDGE,
                markersize=11, label=r"Origin / destination ($o$, $d$)",
            ),
            Line2D(
                [0], [0], marker="o", linestyle="None",
                markerfacecolor=CUSTOMER_FACE, markeredgecolor=CUSTOMER_EDGE,
                markersize=11, label="Customer (cluster colour)",
            ),
            Line2D(
                [0], [0], marker="s", linestyle="None",
                markerfacecolor=STATION_FACE, markeredgecolor=STATION_EDGE,
                markersize=8, label="Charging station",
            ),
        ]
    )
    fig = plt.figure(figsize=(11.0, 1.15))
    fig.legend(
        handles=handles, loc="center", ncol=4, frameon=False,
        columnspacing=1.5, handletextpad=0.6,
    )
    save_figure(fig, OUT_DIR / "route_corridor_legend.pdf")
    plt.close(fig)


def main() -> None:
    setup_pub_style()
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
