import argparse
import csv
import math
import os
import re
import statistics
from typing import Dict, List, Tuple, Optional


def list_instance_dirs(root: str) -> List[str]:
    if not os.path.isdir(root):
        return []
    out = []
    for name in os.listdir(root):
        p = os.path.join(root, name)
        if os.path.isdir(p):
            # require an instance txt file inside
            txts = [fn for fn in os.listdir(p) if fn.endswith('.txt')]
            if txts:
                out.append(p)
    out.sort()
    return out


def parse_instance_name(name: str) -> Tuple[str, int, int, int]:
    # pattern: {routeClass}_cl{K}_cu{N}_v{variant}
    m = re.match(r"^(short|med|long)_cl(\d+)_cu(\d+)_v(\d+)$", name)
    if not m:
        raise ValueError(f"Folder name not matching pattern: {name}")
    route_class = m.group(1)
    k = int(m.group(2))
    n = int(m.group(3))
    v = int(m.group(4))
    return route_class, k, n, v


def read_instance_txt(path: str) -> Tuple[List[str], Dict[str, Tuple[float, float, float]]]:
    # Returns ordered nodes [Origin, Cust..., Destination] and mapping for customers to (start, end, service)
    nodes: List[str] = ["Origin"]
    windows_service: Dict[str, Tuple[float, float, float]] = {}
    with open(path, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    # Find the nodes header row
    hdr_idx = None
    for i, r in enumerate(rows):
        if len(r) >= 3 and r[0] == "NodeId" and r[1] == "Location":
            hdr_idx = i
            break
    if hdr_idx is None:
        raise ValueError(f"Nodes header not found in {path}")
    for r in rows[hdr_idx + 1:]:
        if not r or all((c == "" for c in r)):
            continue
        # NodeId,Location,LocationId,Start,End,_,_,_,ServiceTime
        name = r[1]
        nodes.append(name)
        if name.startswith("Cust"):
            start = float(r[3])
            end = float(r[4])
            service = float(r[8])
            windows_service[name] = (start, end, service)
    return nodes, windows_service


def read_matrix(path: str) -> Tuple[List[str], List[List[float]]]:
    with open(path, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        raise ValueError(f"Empty matrix file: {path}")
    header = rows[0][1:]
    data_rows = rows[1:]
    matrix: List[List[float]] = []
    names: List[str] = []
    for r in data_rows:
        if not r:
            continue
        names.append(r[0])
        vals: List[float] = []
        for x in r[1:1 + len(header)]:
            try:
                vals.append(float(x))
            except Exception:
                vals.append(0.0)
        matrix.append(vals)
    return header, matrix


def build_index(names: List[str]) -> Dict[str, int]:
    return {n: i for i, n in enumerate(names)}


def reconstruct_prefix_from_origin(order_nodes: List[str], mat_names: List[str], mat: List[List[float]]) -> List[float]:
    name_to_idx = build_index(mat_names)
    if order_nodes[0] != "Origin":
        raise ValueError("Order must start with Origin")
    prefix: List[float] = []
    origin_idx = name_to_idx["Origin"]
    for nm in order_nodes:
        if nm not in name_to_idx:
            # ignore nodes absent in matrix (e.g., Baatsfjord)
            prefix.append(prefix[-1] if prefix else 0.0)
            continue
        j = name_to_idx[nm]
        d = mat[origin_idx][j]
        prefix.append(float(d))
    return prefix


def diffs(xs: List[float]) -> List[float]:
    return [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]


def kmeans_1d(values: List[float], k: int, max_iter: int = 50) -> Tuple[List[int], List[float]]:
    if k <= 0:
        return [0] * len(values), [statistics.mean(values) if values else 0.0]
    if k == 1:
        return [0] * len(values), [statistics.mean(values) if values else 0.0]
    xs = sorted((v, i) for i, v in enumerate(values))
    # initialize centroids by quantiles
    centroids = []
    for j in range(k):
        q_idx = int(round((j + 0.5) * (len(xs) / k) - 1))
        q_idx = max(0, min(len(xs) - 1, q_idx))
        centroids.append(xs[q_idx][0])
    assign = [0] * len(values)
    for _ in range(max_iter):
        changed = False
        # assign
        for v, i in xs:
            best = min(range(k), key=lambda c: abs(v - centroids[c]))
            if assign[i] != best:
                assign[i] = best
                changed = True
        # update
        new_centroids: List[float] = []
        for c in range(k):
            members = [values[i] for i, a in enumerate(assign) if a == c]
            if members:
                new_centroids.append(sum(members) / len(members))
            else:
                new_centroids.append(centroids[c])
        if not changed:
            break
        centroids = new_centroids
    return assign, centroids


def per_cluster_metrics(positions: List[float], assign: List[int], k: int) -> Tuple[List[int], List[float], List[float], List[float]]:
    sizes: List[int] = []
    spans: List[float] = []
    avg_gap: List[float] = []
    mean_abs_offset: List[float] = []
    for c in range(k):
        members = [p for p, a in zip(positions, assign) if a == c]
        if not members:
            sizes.append(0)
            spans.append(0.0)
            avg_gap.append(0.0)
            mean_abs_offset.append(0.0)
            continue
        members.sort()
        sizes.append(len(members))
        span = members[-1] - members[0] if len(members) > 1 else 0.0
        spans.append(span)
        avg_gap.append(span / (len(members) - 1) if len(members) > 1 else 0.0)
        center = sum(members) / len(members)
        mean_abs_offset.append(sum(abs(x - center) for x in members) / len(members))
    return sizes, spans, avg_gap, mean_abs_offset


def analyze_instance(instance_dir: str) -> Dict[str, object]:
    base = os.path.basename(instance_dir)
    route_class, k, n, v = parse_instance_name(base)
    instance_file = os.path.join(instance_dir, f"{base}.txt")
    dist_file = os.path.join(instance_dir, f"{base}_DistanceMatrix.csv")
    time_file = os.path.join(instance_dir, f"{base}_TimeMatrix.csv")
    if not (os.path.isfile(instance_file) and os.path.isfile(dist_file) and os.path.isfile(time_file)):
        raise FileNotFoundError(f"Missing files in {instance_dir}")

    order_nodes, windows_service = read_instance_txt(instance_file)
    mat_names, mat = read_matrix(dist_file)

    # Reconstruct prefix distances from Origin and segment lengths
    prefix = reconstruct_prefix_from_origin(order_nodes, mat_names, mat)
    seg_dists = diffs(prefix)
    total_distance = prefix[-1]

    # Positions of customers (skip Origin, Destination)
    cust_positions = [prefix[i] for i, nm in enumerate(order_nodes) if nm.startswith("Cust")]

    # Basic leg stats
    leg_stats = {
        "num_segments": len(seg_dists),
        "min_leg_km": min(seg_dists) if seg_dists else 0.0,
        "max_leg_km": max(seg_dists) if seg_dists else 0.0,
        "mean_leg_km": statistics.mean(seg_dists) if seg_dists else 0.0,
        "median_leg_km": statistics.median(seg_dists) if seg_dists else 0.0,
        "std_leg_km": statistics.pstdev(seg_dists) if len(seg_dists) > 1 else 0.0,
    }

    # Service/window stats
    service_vals = [ws[2] for nm, ws in windows_service.items()]
    window_widths = [ws[1] - ws[0] for nm, ws in windows_service.items()]

    # Arrival-only slack: earliest - travel_time
    # Need travel time at each customer: prefix distance / 70
    arrival_slacks = []
    for i, nm in enumerate(order_nodes):
        if nm.startswith("Cust") and nm in windows_service:
            et = prefix[i] / 70.0
            earliest = windows_service[nm][0]
            arrival_slacks.append(max(0.0, earliest - et))

    # Cluster customers via 1D k-means
    assign, centroids = kmeans_1d(cust_positions, k)
    sizes, spans, avg_gap, mean_abs_offset = per_cluster_metrics(cust_positions, assign, k)

    row: Dict[str, object] = {
        "instance": base,
        "route_class": route_class,
        "clusters": k,
        "customers": n,
        "variant": v,
        "total_distance_km": round(total_distance, 3),
        **{k_: round(v_, 3) for k_, v_ in leg_stats.items()},
        "service_total_h": round(sum(service_vals), 4) if service_vals else 0.0,
        "service_mean_h": round(statistics.mean(service_vals), 4) if service_vals else 0.0,
        "window_mean_width_h": round(statistics.mean(window_widths), 4) if window_widths else 0.0,
        "arrival_slack_mean_h": round(statistics.mean(arrival_slacks), 4) if arrival_slacks else 0.0,
        "max_customer_prefix_km": round(max(cust_positions) if cust_positions else 0.0, 3),
        "cluster_sizes": str(sizes),
        "cluster_spans_km": str([round(x, 3) for x in spans]),
        "cluster_avg_gap_km": str([round(x, 3) for x in avg_gap]),
        "cluster_mean_abs_offset_km": str([round(x, 3) for x in mean_abs_offset]),
    }
    return row


def write_csv(path: str, rows: List[Dict[str, object]]) -> None:
    if not rows:
        with open(path, "w", newline="") as f:
            f.write("")
        return
    # stable header order
    preferred = [
        "instance",
        "route_class",
        "clusters",
        "customers",
        "variant",
        "total_distance_km",
        "num_segments",
        "min_leg_km",
        "max_leg_km",
        "mean_leg_km",
        "median_leg_km",
        "std_leg_km",
        "service_total_h",
        "service_mean_h",
        "window_mean_width_h",
        "arrival_slack_mean_h",
        "max_customer_prefix_km",
        "cluster_sizes",
        "cluster_spans_km",
        "cluster_avg_gap_km",
        "cluster_mean_abs_offset_km",
    ]
    # include any others if present
    all_keys = list({k for row in rows for k in row.keys()})
    header = preferred + [k for k in all_keys if k not in preferred]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyze generated route instances into a CSV table")
    p.add_argument("--root", default="instances", help="Root directory containing instance subfolders")
    p.add_argument("--out", default="analysis.csv", help="Output CSV path")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    dirs = list_instance_dirs(args.root)
    rows: List[Dict[str, object]] = []
    for d in dirs:
        try:
            rows.append(analyze_instance(d))
        except Exception as e:
            # best-effort: record failure row
            rows.append({
                "instance": os.path.basename(d),
                "error": str(e),
            })
    write_csv(args.out, rows)
    print(f"Wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()


