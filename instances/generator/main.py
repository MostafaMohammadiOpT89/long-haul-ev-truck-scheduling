import argparse
import csv
import math
import os
import random
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional


# -----------------------------
# Configuration and data models
# -----------------------------

SPEED_KMPH = 60.0  # keep consistent with network model


@dataclass
class RouteSpec:
    route_class: str  # one of: short, med, long
    clusters: int  # K in {1,2,3}
    total_customers: int  # N
    variant_idx: int  # v in {1,2}
    customer_range: str = "Few"  # Few (1-3), Medium (4-5), Many (6-15)
    round_trip: bool = True  # ensure Origin -> ... -> Origin
    add_baatsfjord_column: bool = True  # see CSV reader quirk
    allocation_strategy: str = "balanced"  # "balanced" | "unbalanced"
    variant_label: str = "Balanced"  # Human-readable variant name used in filenames and summaries


def class_distance_range_km(route_class: str) -> Tuple[float, float]:
    rc = route_class.lower()
    if rc in ("short", "s", "sh"):
        return 800.0, 1200.0
    if rc in ("med", "medium", "m"):
        return 1500.0, 2500.0
    if rc in ("long", "l"):
        return 3000.0, 4000.0
    raise ValueError(f"Unknown route class: {route_class}")


def slack_minutes_by_class(route_class: str) -> Tuple[int, int]:
    rc = route_class.lower()
    if rc in ("short", "s", "sh"):
        return 0, 90
    if rc in ("med", "medium", "m"):
        return 0, 120
    if rc in ("long", "l"):
        return 0, 180
    raise ValueError(f"Unknown route class: {route_class}")


def service_time_minutes_by_customer_count(n_customers: int) -> Tuple[int, int]:
    # Few (1–3): 20–30 min; Medium (4–5): 10–20; Many (6–15): 5–10
    if n_customers <= 3:
        return 20, 30
    if n_customers <= 5:
        return 10, 20
    return 5, 10


def time_window_width_hours_by_customer_count(n_customers: int) -> Tuple[float, float]:
    # Width W for Latest = Earliest + W
    if n_customers <= 5:
        return 2.0, 4.0  # 120–240 minutes
    return 1.5, 3.0  # 90–180 minutes


# -----------------------------
# Core helpers
# -----------------------------


def sample_total_distance_km(route_class: str, rng: random.Random) -> float:
    lo, hi = class_distance_range_km(route_class)
    return rng.uniform(lo, hi)


def base_cluster_center_positions_km(k: int, d_total: float, rng: random.Random) -> List[float]:
    # Follow recommended spreads with small jitter ±2–3% of D_total
    if k == 1:
        bases = [rng.uniform(0.50, 0.60) * d_total]
    elif k == 2:
        a = rng.uniform(0.35, 0.45) * d_total
        b = rng.uniform(0.55, 0.65) * d_total
        bases = sorted([a, b])
    elif k == 3:
        a = rng.uniform(0.25, 0.30) * d_total
        b = rng.uniform(0.50, 0.55) * d_total
        c = rng.uniform(0.70, 0.75) * d_total
        bases = sorted([a, b, c])
    else:
        raise ValueError("clusters (K) must be in {1,2,3}")

    jitter = 0.02 * d_total
    centers = []
    for pos in bases:
        centers.append(max(0.0, min(d_total, pos + rng.uniform(-jitter, jitter))))
    centers.sort()
    return centers


def allocate_customers_to_clusters(k: int, n: int, rng: random.Random) -> List[int]:
    # Handle case where customers < clusters (some clusters will be empty)
    if n < k:
        alloc = [0] * k
        for _ in range(n):
            alloc[rng.randrange(0, k)] += 1
        return alloc
    
    # Normal case: at least one customer per cluster
    alloc = [1] * k
    remaining = n - k
    # Random mild imbalance by distributing remaining one by one
    for _ in range(remaining):
        alloc[rng.randrange(0, k)] += 1
    return alloc


def allocate_customers_with_range_constraints(
    k: int, 
    n_total: int, 
    customer_range: str, 
    rng: random.Random
) -> List[int]:
    """
    Allocate n_total customers across k clusters while respecting customer_range constraints.
    
    Args:
        k: number of clusters
        n_total: total customers to distribute
        customer_range: "Few" (1-3), "Medium" (4-5), or "Many" (6-15)
        rng: random number generator
    
    Returns:
        List of customer counts per cluster
    """
    # Define range constraints
    if customer_range.lower() == "few":
        min_per_cluster, max_per_cluster = 1, 3
    elif customer_range.lower() == "medium":
        min_per_cluster, max_per_cluster = 4, 5
    elif customer_range.lower() == "many":
        min_per_cluster, max_per_cluster = 6, 15
    else:
        raise ValueError(f"Unknown customer range: {customer_range}")
    
    # Check if allocation is possible
    min_total = k * min_per_cluster
    max_total = k * max_per_cluster
    
    if n_total < min_total:
        # Not enough customers for minimum constraint - distribute as evenly as possible
        alloc = [0] * k
        for i in range(n_total):
            alloc[i % k] += 1
        return alloc
    
    if n_total > max_total:
        # Too many customers for maximum constraint - cap at maximum
        alloc = [max_per_cluster] * k
        remaining = n_total - max_total
        # Distribute remaining customers randomly (may exceed max_per_cluster)
        for _ in range(remaining):
            alloc[rng.randrange(0, k)] += 1
        return alloc
    
    # Normal case: n_total is within constraints
    # Start with minimum allocation
    alloc = [min_per_cluster] * k
    remaining = n_total - min_total
    
    # Distribute remaining customers while respecting max constraint
    for _ in range(remaining):
        # Find clusters that can still accept more customers
        available_clusters = [i for i in range(k) if alloc[i] < max_per_cluster]
        if not available_clusters:
            # All clusters at max - distribute randomly
            alloc[rng.randrange(0, k)] += 1
        else:
            # Choose randomly from available clusters
            chosen = rng.choice(available_clusters)
            alloc[chosen] += 1
    
    return alloc


def allocate_customers_unbalanced(
    k: int,
    n_total: int,
    customer_range: str,
    rng: random.Random
) -> List[int]:
    """
    Allocate customers in a highly uneven (heterogeneous) way:
    - Guarantees at least one customer per cluster
    - Choose one dominant cluster to hold most customers
    - Assign small extra counts to other clusters (0–2 each), then dump the rest into dominant
    - Softly respects feasibility; does not strictly enforce per-cluster min/max
    """
    if k <= 0:
        return []
    # Impossible to have >=1 per cluster
    if n_total < k:
        raise ValueError("n_total must be >= number of clusters to ensure at least one per cluster")

    # Start with 1 per cluster so no zeros
    alloc = [1] * k
    remaining = n_total - k

    dominant = rng.randrange(0, k)
    # Give small random extras to non-dominant clusters
    for i in range(k):
        if i == dominant:
            continue
        if remaining <= 0:
            break
        give = min(remaining, rng.randrange(0, 3))  # 0,1,2
        alloc[i] += give
        remaining -= give

    # Everything else goes to dominant cluster
    if remaining > 0:
        alloc[dominant] += remaining

    return alloc


def place_customers_within_clusters(
    centers: List[float],
    alloc: List[int],
    d_total: float,
    rng: random.Random,
) -> Tuple[List[float], List[int]]:
    # Returns ordered positions and their cluster membership index
    positions: List[float] = []
    membership: List[int] = []
    for c_idx, center in enumerate(centers):
        for _ in range(alloc[c_idx]):
            # Sample within a wider ±150 km band around the center so 30–150 km gaps are feasible
            x = center + rng.uniform(-150.0, 150.0)
            x = max(0.0, min(d_total, x))
            positions.append(x)
            membership.append(c_idx)

    # Order globally by position (backbone order)
    order = sorted(range(len(positions)), key=lambda i: positions[i])
    positions = [positions[i] for i in order]
    membership = [membership[i] for i in order]
    return positions, membership


def enforce_intra_cluster_spacing(
    positions: List[float],
    membership: List[int],
    centers: List[float],
    d_total: float,
    rng: random.Random,
    min_gap_km: float = 30.0,
    max_gap_km: float = 150.0,
    max_attempts: int = 100,
) -> Tuple[List[float], List[int]]:
    # Adjust positions within each cluster so consecutive in cluster obey [min,max] gap
    # Without breaking global order; if impossible, resample within cluster bounds
    idxs_by_cluster: Dict[int, List[int]] = {}
    for idx, cl in enumerate(membership):
        idxs_by_cluster.setdefault(cl, []).append(idx)

    pos = positions[:]
    for cl, idxs in idxs_by_cluster.items():
        if len(idxs) <= 1:
            continue
        idxs.sort()
        attempts = 0
        # Base bounds around cluster center (initial ±25km)
        base_min = max(0.0, centers[cl] - 25.0)
        base_max = min(d_total, centers[cl] + 25.0)
        # Ensure bounds can accommodate at least the minimum required span for this cluster size
        required_span = min_gap_km * (len(idxs) - 1)
        current_span = max(0.0, base_max - base_min)
        if required_span > current_span:
            half_span = required_span / 2.0
            expanded_min = max(0.0, centers[cl] - half_span)
            expanded_max = min(d_total, centers[cl] + half_span)
            # If still too small due to route edges, use whatever is possible
            cluster_min = expanded_min
            cluster_max = expanded_max
        else:
            cluster_min = base_min
            cluster_max = base_max
        while attempts < max_attempts:
            ok = True
            for a, b in zip(idxs, idxs[1:]):
                gap = pos[b] - pos[a]
                if gap < min_gap_km or gap > max_gap_km:
                    ok = False
                    break
            if ok:
                break

            # Re-layout customers with randomized gaps within [min_gap_km, max_gap_km]
            count = len(idxs)
            min_required = min_gap_km * (count - 1)
            max_allowed = max_gap_km * (count - 1)
            available = max(0.0, cluster_max - cluster_min)
            total_span_max = min(available, max_allowed)
            if total_span_max < min_required:
                # fallback: use whatever available evenly
                span = max(available, 0.0)
                start = cluster_min
                for i, local in enumerate(idxs):
                    step = 0.0 if count == 1 else span / (count - 1)
                    pos[local] = start + i * step
                attempts += 1
                continue

            # Choose a target span S uniformly within feasible range
            target_span = min_required if total_span_max == min_required else (cluster_min + 1.0) * 0.0  # placeholder
            if total_span_max == min_required:
                target_span = min_required
            else:
                target_span = rng.uniform(min_required, total_span_max)

            # Try a few times to sample gaps respecting per-gap <= max_gap_km
            sampled_ok = False
            for _ in range(10):
                # sample positive weights and normalize
                weights = [rng.random() + 1e-6 for _ in range(count - 1)]
                wsum = sum(weights)
                # compute extra span beyond min_required
                extra = target_span - min_required
                gaps = [min_gap_km + (extra * (w / wsum)) for w in weights]
                if all(g <= max_gap_km + 1e-9 for g in gaps):
                    sampled_ok = True
                    break
            if not sampled_ok:
                # fallback to equal gaps within bounds
                equal_gap = max(min_gap_km, min(max_gap_km, target_span / max(1, count - 1)))
                gaps = [equal_gap] * (count - 1)

            # Place customers starting near center, clamped to bounds
            span = sum(gaps)
            start = max(cluster_min, min(cluster_max - span, centers[cl] - span / 2.0))
            cur = start
            for i, local in enumerate(idxs):
                if i == 0:
                    pos[local] = cur
                else:
                    cur += gaps[i - 1]
                    pos[local] = cur

            attempts += 1

        if attempts >= max_attempts:
            # Fallback: full resample within the bounds, then sort
            new_vals = [rng.uniform(cluster_min, cluster_max) for _ in idxs]
            new_vals.sort()
            for local, val in zip(idxs, new_vals):
                pos[local] = val

    # Restore global order and align membership accordingly
    order = sorted(range(len(pos)), key=lambda i: pos[i])
    pos_sorted = [pos[i] for i in order]
    membership_sorted = [membership[i] for i in order]
    return pos_sorted, membership_sorted


def build_chain_segments(
    customer_positions: List[float],
    d_total: float,
    round_trip: bool,
) -> Tuple[List[str], List[float]]:
    # Node names in order; chain distances between consecutive nodes (always positive)
    node_names = ["Origin"] + [f"Cust{i+1}" for i in range(len(customer_positions))]
    node_names.append("Destination")

    # Ensure all customer positions are within [0, d_total] and sorted
    customer_positions_sorted = sorted([max(0.0, min(d_total, pos)) for pos in customer_positions])
    
    # Build coordinates: Origin at 0, customers at their positions
    coords = [0.0] + customer_positions_sorted[:]
    
    # Destination is positioned at d_total to ensure total route distance matches sampled value
    # This enforces that Origin → Cust1 → ... → CustN → Destination = d_total (within specified range)
    coords.append(d_total)

    # Compute segment distances (always positive, along the route)
    seg_dists = []
    for i in range(len(coords) - 1):
        # All segments are forward segments along the route
        seg_dists.append(abs(coords[i + 1] - coords[i]))
    
    return node_names, seg_dists


def build_dense_pairwise_matrix_from_segments(node_names: List[str], seg_dists: List[float]) -> List[List[float]]:
    # Convert chain segments to cumulative pairwise distances along the chain
    n = len(node_names)
    # prefix sums of segments: prefix[0] = 0, prefix[i] = sum(seg[0..i-1]) gives distance from node 0 to node i
    prefix = [0.0]
    for d in seg_dists:
        prefix.append(prefix[-1] + d)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i][j] = 0.0
            else:
                a, b = sorted((i, j))
                matrix[i][j] = prefix[b] - prefix[a]
    return matrix


def write_csv_matrix(
    path: str,
    node_names: List[str],
    matrix: List[List[float]],
    include_baatsfjord: bool,
) -> None:
    header = [""] + node_names[:]
    rows: List[List[Optional[float]]] = []
    for name, row_vals in zip(node_names, matrix):
        rows.append([name] + row_vals[:])

    if include_baatsfjord:
        header.append("Baatsfjord")
        for r in rows:
            r.append(0.0)
        # Also add a trailing Baatsfjord row of zeros
        rows.append(["Baatsfjord"] + [0.0] * (len(header) - 1))

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for r in rows:
            writer.writerow(r)


def _write_diagnostics_file(
    path: str,
    node_names: List[str],
    positions: List[float],
    membership: List[int],
    centers: List[float],
    clusters: int,
) -> None:
    """Write a per-instance diagnostics CSV containing cluster membership and spacing info.

    Columns:
      - Node: node name (Origin, Cust*, Destination)
      - PositionKm: cumulative km from Origin along backbone (Origin=0, Destination=0 or D_total)
      - ClusterIdx: cluster index for customers; -1 for Origin/Destination
      - ClusterCenterKm: center position of the assigned cluster (blank for non-customers)
      - IntraPrevGapKm: distance to previous customer within same cluster (NaN if first in cluster)
      - IntraNextGapKm: distance to next customer within same cluster (NaN if last in cluster)
    """
    # Build rows for Origin + customers + Destination
    rows: List[List[object]] = []
    # Origin
    rows.append(["Origin", 0.0, -1, "", "", ""])

    # Map cluster -> list of indices (in positions list)
    idxs_by_cluster: Dict[int, List[int]] = {}
    for idx, cl in enumerate(membership):
        idxs_by_cluster.setdefault(cl, []).append(idx)

    # Precompute gaps inside clusters
    intra_prev: Dict[int, Dict[int, float]] = {}
    intra_next: Dict[int, Dict[int, float]] = {}
    for cl, idxs in idxs_by_cluster.items():
        idxs.sort()
        intra_prev[cl] = {}
        intra_next[cl] = {}
        for i, idx in enumerate(idxs):
            if i == 0:
                intra_prev[cl][idx] = float("nan")
            else:
                intra_prev[cl][idx] = positions[idx] - positions[idxs[i - 1]]
            if i == len(idxs) - 1:
                intra_next[cl][idx] = float("nan")
            else:
                intra_next[cl][idx] = positions[idxs[i + 1]] - positions[idx]

    # Customers
    for i, (name) in enumerate(node_names[1:-1], start=0):  # iterate over Cust* only
        pos_km = positions[i]
        cl = membership[i]
        center_km = centers[cl] if 0 <= cl < len(centers) else ""
        prev_gap = intra_prev.get(cl, {}).get(i, float("nan"))
        next_gap = intra_next.get(cl, {}).get(i, float("nan"))
        rows.append([name, round(pos_km, 3), cl, round(center_km, 3) if center_km != "" else "", 
                     round(prev_gap, 3) if prev_gap == prev_gap else "",  # NaN check
                     round(next_gap, 3) if next_gap == next_gap else ""])  # NaN check

    # Destination: in round-trip it's 0; otherwise D_total, but not tracked here
    rows.append(["Destination", 0.0, -1, "", "", ""])

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Node", "PositionKm", "ClusterIdx", "ClusterCenterKm", "IntraPrevGapKm", "IntraNextGapKm"])
        writer.writerows(rows)


def _write_diagnostics_summary_file(
    path: str,
    instance_name: str,
    route_class: str,
    clusters: int,
    total_customers: int,
    variant_label: str,
    positions_only_customers: List[float],
    membership: List[int],
    centers: List[float],
    dist_matrix: List[List[float]],
    time_matrix: List[List[float]],
    windows_service: Dict[str, Tuple[float, float, float]],
) -> None:
    """Write a one-row summary CSV with aggregated features per instance."""
    # Basic
    test_name = instance_name
    route_cls = route_class
    cluster_count = clusters
    total_cust = total_customers
    # Use human-readable variant label
    spec_variant_label = variant_label

    # Main features
    total_route_distance = dist_matrix[0][-1] if dist_matrix else 0.0
    total_route_time = time_matrix[0][-1] if time_matrix else 0.0

    # Customers per cluster
    customers_per_cluster: List[int] = [0] * cluster_count
    for cl in membership:
        if 0 <= cl < cluster_count:
            customers_per_cluster[cl] += 1

    # Cluster centers (sorted by position)
    centers_sorted = sorted(centers[:cluster_count]) if centers else []

    # Distances between consecutive centers
    cluster_dists: List[float] = []
    for i in range(len(centers_sorted) - 1):
        cluster_dists.append(abs(centers_sorted[i + 1] - centers_sorted[i]))
    avg_cluster_dist = sum(cluster_dists) / len(cluster_dists) if cluster_dists else 0.0
    min_cluster_dist = min(cluster_dists) if cluster_dists else 0.0
    max_cluster_dist = max(cluster_dists) if cluster_dists else 0.0

    # Inter-cluster all-pair distances
    inter_cluster_dists: List[float] = []
    for i in range(len(centers_sorted)):
        for j in range(i + 1, len(centers_sorted)):
            inter_cluster_dists.append(abs(centers_sorted[j] - centers_sorted[i]))
    avg_inter_cluster = sum(inter_cluster_dists) / len(inter_cluster_dists) if inter_cluster_dists else 0.0
    min_inter_cluster = min(inter_cluster_dists) if inter_cluster_dists else 0.0
    max_inter_cluster = max(inter_cluster_dists) if inter_cluster_dists else 0.0

    # Intra-cluster consecutive customer gaps
    gaps_within: List[float] = []
    idxs_by_cluster: Dict[int, List[int]] = {}
    for idx, cl in enumerate(membership):
        idxs_by_cluster.setdefault(cl, []).append(idx)
    for cl, idxs in idxs_by_cluster.items():
        if len(idxs) <= 1:
            continue
        idxs.sort()
        for a, b in zip(idxs, idxs[1:]):
            gaps_within.append(abs(positions_only_customers[b] - positions_only_customers[a]))
    avg_intra = sum(gaps_within) / len(gaps_within) if gaps_within else 0.0
    min_intra = min(gaps_within) if gaps_within else 0.0
    max_intra = max(gaps_within) if gaps_within else 0.0

    # Service times
    service_vals = [svc for (_, _, svc) in windows_service.values()]
    avg_service = (sum(service_vals) / len(service_vals)) if service_vals else 0.0
    total_service = sum(service_vals)

    # Write one-row CSV
    header = [
        "Test_Name","Route_Class","Cluster_Count","Total_Customers","Variant",
        "Total_Route_Distance_km","Total_Route_Time_hours",
        "Customers_Per_Cluster","Cluster_Distances_km","Avg_Cluster_Distance_km","Min_Cluster_Distance_km","Max_Cluster_Distance_km",
        "Avg_Customer_Distance_Within_Cluster_km","Min_Customer_Distance_Within_Cluster_km","Max_Customer_Distance_Within_Cluster_km",
        "Inter_Cluster_Distances_km","Avg_Inter_Cluster_Distance_km","Min_Inter_Cluster_Distance_km","Max_Inter_Cluster_Distance_km",
        "Avg_Service_Time_hours","Total_Service_Time_hours",
    ]
    row = [
        test_name, route_cls, cluster_count, total_cust, spec_variant_label,
        round(total_route_distance, 3), round(total_route_time, 4),
        str(customers_per_cluster), str([round(x, 3) for x in cluster_dists]), round(avg_cluster_dist, 3), round(min_cluster_dist, 3), round(max_cluster_dist, 3),
        round(avg_intra, 3), round(min_intra, 3), round(max_intra, 3),
        str([round(x, 3) for x in inter_cluster_dists]), round(avg_inter_cluster, 3), round(min_inter_cluster, 3), round(max_inter_cluster, 3),
        round(avg_service, 4), round(total_service, 4),
    ]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerow(row)


def generate_master_node_list(max_customers: int = 15) -> List[str]:
    """Generate a comprehensive list of all possible nodes for master matrices."""
    nodes = ["Origin"]
    # Add all possible customer nodes (up to max_customers)
    for i in range(1, max_customers + 1):
        nodes.append(f"Cust{i}")
    nodes.append("Destination")
    nodes.append("Baatsfjord")
    return nodes


def build_master_distance_matrix(
    master_nodes: List[str],
    route_class: str,
    rng: random.Random,
    max_customers: int = 15
) -> List[List[float]]:
    """Build a master distance matrix covering all possible nodes."""
    n = len(master_nodes)
    matrix = [[0.0] * n for _ in range(n)]
    
    # Sample a total distance for the master matrix
    d_total = sample_total_distance_km(route_class, rng)
    
    # Generate customer positions for the maximum number of customers
    # Use 3 clusters for maximum complexity with "Many" range
    centers = base_cluster_center_positions_km(3, d_total, rng)
    alloc = allocate_customers_with_range_constraints(3, max_customers, "Many", rng)
    positions, membership = place_customers_within_clusters(centers, alloc, d_total, rng)
    positions, membership = enforce_intra_cluster_spacing(positions, membership, centers, d_total, rng)
    
    # Build chain segments for all customers
    node_names, seg_dists = build_chain_segments(positions, d_total, True)
    
    # Build the distance matrix for all nodes
    dist_matrix = build_dense_pairwise_matrix_from_segments(node_names, seg_dists)
    
    # Map the generated matrix to the master node structure
    for i, node_i in enumerate(master_nodes):
        for j, node_j in enumerate(master_nodes):
            if i == j:
                matrix[i][j] = 0.0
            elif node_i == "Baatsfjord" or node_j == "Baatsfjord":
                matrix[i][j] = 0.0
            else:
                # Find corresponding indices in the generated matrix
                try:
                    idx_i = node_names.index(node_i)
                    idx_j = node_names.index(node_j)
                    matrix[i][j] = dist_matrix[idx_i][idx_j]
                except ValueError:
                    # If node doesn't exist in generated matrix, use a reasonable default
                    if node_i == "Origin" and node_j == "Destination":
                        matrix[i][j] = d_total
                    elif node_j == "Origin" and node_i == "Destination":
                        matrix[i][j] = d_total
                    else:
                        # Use a large distance for non-existent connections
                        matrix[i][j] = 999999.0
    
    return matrix


def build_master_time_matrix(
    master_nodes: List[str],
    distance_matrix: List[List[float]]
) -> List[List[float]]:
    """Build a master time matrix from the distance matrix."""
    n = len(master_nodes)
    matrix = [[0.0] * n for _ in range(n)]
    
    for i in range(n):
        for j in range(n):
            matrix[i][j] = distance_matrix[i][j] / SPEED_KMPH
    
    return matrix


def generate_master_matrices(
    out_root: str,
    route_class: str = "long",
    max_customers: int = 15,
    rng: Optional[random.Random] = None
) -> Tuple[str, str]:
    """Generate master DistanceMatrix and TimeMatrix files."""
    if rng is None:
        rng = random.Random()
    
    # Generate master node list
    master_nodes = generate_master_node_list(max_customers)
    
    # Build master distance matrix
    master_dist_matrix = build_master_distance_matrix(master_nodes, route_class, rng, max_customers)
    
    # Build master time matrix
    master_time_matrix = build_master_time_matrix(master_nodes, master_dist_matrix)
    
    # Write master matrices
    master_dist_file = os.path.join(out_root, "Master_DistanceMatrix.csv")
    master_time_file = os.path.join(out_root, "Master_TimeMatrix.csv")
    
    write_csv_matrix(master_dist_file, master_nodes, master_dist_matrix, True)
    write_csv_matrix(master_time_file, master_nodes, master_time_matrix, True)
    
    return master_dist_file, master_time_file


def generate_time_windows_and_service(
    route_class: str,
    n_customers: int,
    seg_dists: List[float],
    node_names: List[str],
    rng: random.Random,
) -> Dict[str, Tuple[float, float, float]]:
    # Returns mapping from customer node name to (earliest_h, latest_h, service_h)
    # Compute travel-only arrival to each node as cumulative time
    travel_time_hours_prefix = [0.0]
    for d in seg_dists:
        travel_time_hours_prefix.append(travel_time_hours_prefix[-1] + (d / SPEED_KMPH))

    slack_lo, slack_hi = slack_minutes_by_class(route_class)
    st_lo_min, st_hi_min = service_time_minutes_by_customer_count(n_customers)
    w_lo_h, w_hi_h = time_window_width_hours_by_customer_count(n_customers)

    out: Dict[str, Tuple[float, float, float]] = {}
    # Customers are positions 1..N in node_names (Origin at 0). Destination gets wide window and zero service.
    for idx, name in enumerate(node_names):
        if name.startswith("Cust"):
            et_hours = travel_time_hours_prefix[idx]
            slack_min = rng.uniform(slack_lo, slack_hi)
            earliest_h = et_hours + (slack_min / 60.0)
            width_h = rng.uniform(w_lo_h, w_hi_h)
            latest_h = earliest_h + width_h
            service_min = rng.uniform(st_lo_min, st_hi_min)
            service_h = service_min / 60.0
            out[name] = (earliest_h, latest_h, service_h)
    return out


def write_instance_file(
    path: str,
    node_names: List[str],
    windows_service: Dict[str, Tuple[float, float, float]],
) -> None:
    # Format per spec
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["VehicleId", "Location", "LocationId"])
        writer.writerow([1, "Origin", 1])
        writer.writerow([])
        writer.writerow(["NodeId", "Location", "LocationId", "Start", "End", "_", "_", "_", "ServiceTime"])

        node_id = 2
        location_id = 2
        for name in node_names[1:]:  # skip Origin from nodes section
            if name.startswith("Cust"):
                # relaxed time windows for every node: Start=0, End=1e9; keep computed service
                _, _, service_h = windows_service[name]
                writer.writerow([
                    node_id,
                    name,
                    location_id,
                    0,
                    1000000000,
                    0,
                    0,
                    0,
                    round(service_h, 4),
                ])
                node_id += 1
                location_id += 1
            else:
                # Destination row with relaxed window and zero service
                writer.writerow([
                    node_id,
                    name,
                    location_id,
                    0,
                    1000000000,
                    0,
                    0,
                    0,
                    0.0,
                ])
                node_id += 1
                location_id += 1


def generate_instance(spec: RouteSpec, out_root: str, rng: random.Random) -> str:
    # 1) sample total distance
    d_total = sample_total_distance_km(spec.route_class, rng)

    # 2) cluster centers
    centers = base_cluster_center_positions_km(spec.clusters, d_total, rng)

    # 3) allocate customers (strategy: balanced vs unbalanced); for 1 cluster allocation mode is irrelevant
    if spec.clusters > 1 and getattr(spec, "allocation_strategy", "balanced") == "unbalanced":
        alloc = allocate_customers_unbalanced(spec.clusters, spec.total_customers, spec.customer_range, rng)
    else:
        alloc = allocate_customers_with_range_constraints(spec.clusters, spec.total_customers, spec.customer_range, rng)

    # 4) positions and enforce spacing
    positions, membership = place_customers_within_clusters(centers, alloc, d_total, rng)
    positions, membership = enforce_intra_cluster_spacing(positions, membership, centers, d_total, rng)

    # 5) chain nodes and segments (round trip supported)
    node_names, seg_dists = build_chain_segments(positions, d_total, spec.round_trip)

    # 6) matrices
    dist_matrix = build_dense_pairwise_matrix_from_segments(node_names, seg_dists)
    time_matrix = [[d / SPEED_KMPH for d in row] for row in dist_matrix]

    # 7) service times and time windows
    windows_service = generate_time_windows_and_service(
        spec.route_class, spec.total_customers, seg_dists, node_names, rng
    )

    # 8) write to per-instance folder
    if spec.clusters == 1:
        instance_name = f"{spec.route_class}_cl{spec.clusters}_cu{spec.total_customers}"
        effective_variant_label = ""
    else:
        instance_name = f"{spec.route_class}_cl{spec.clusters}_cu{spec.total_customers}_{spec.variant_label}"
        effective_variant_label = spec.variant_label
    instance_dir = os.path.join(out_root, instance_name)
    os.makedirs(instance_dir, exist_ok=True)

    instance_file = os.path.join(instance_dir, f"{instance_name}.txt")
    dist_file = os.path.join(instance_dir, f"{instance_name}_DistanceMatrix.csv")
    time_file = os.path.join(instance_dir, f"{instance_name}_TimeMatrix.csv")

    write_instance_file(instance_file, node_names, windows_service)
    write_csv_matrix(dist_file, node_names, dist_matrix, spec.add_baatsfjord_column)
    write_csv_matrix(time_file, node_names, time_matrix, spec.add_baatsfjord_column)

    # 9) diagnostics: cluster membership and spacing (for analysis only)
    diag_file = os.path.join(instance_dir, f"{instance_name}_Diagnostics.csv")
    _write_diagnostics_file(
        diag_file,
        node_names,
        positions,
        membership,
        centers,
        spec.clusters,
    )

    # 10) diagnostics summary (aggregated features)
    diag_summary_file = os.path.join(instance_dir, f"{instance_name}_DiagnosticsSummary.csv")
    _write_diagnostics_summary_file(
        diag_summary_file,
        instance_name,
        spec.route_class,
        spec.clusters,
        spec.total_customers,
        effective_variant_label,
        positions,
        membership,
        centers,
        dist_matrix,
        time_matrix,
        windows_service,
    )

    return instance_dir


# -----------------------------
# CLI
# -----------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Route instance generator with round-trip support")
    sub = p.add_subparsers(dest="cmd", required=False)

    # generate a single instance
    one = sub.add_parser("generate", help="Generate a single instance")
    one.add_argument("route_class", choices=["short", "med", "long"], help="Route class")
    one.add_argument("clusters", type=int, choices=[1, 2, 3], help="Number of clusters")
    one.add_argument("customers", type=int, help="Total number of customers")
    one.add_argument("variant", type=int, choices=[1, 2], help="Variant index")
    one.add_argument("--out", default="output/generated_instances", help="Output root directory")
    one.add_argument("--seed", type=int, default=None, help="Random seed")
    one.add_argument("--no-round-trip", action="store_true", help="Disable round-trip (end at far destination)")
    one.add_argument("--no-baatsfjord", action="store_true", help="Do not append Baatsfjord column/row")
    one.add_argument("--allocation", choices=["balanced", "unbalanced"], default="balanced", help="Customer allocation strategy")

    # generate a grid of instances (two variants per provided spec)
    grid = sub.add_parser("grid", help="Generate a small grid of instances")
    grid.add_argument("--out", default="output/generated_instances", help="Output root directory")
    grid.add_argument("--seed", type=int, default=None, help="Random seed")
    grid.add_argument("--no-baatsfjord", action="store_true", help="Do not append Baatsfjord column/row")
    grid.add_argument("--round-trip", action="store_true", help="Force round-trip")
    grid.add_argument("--add-unbalanced-variant", action="store_true", help="For each spec, add one extra unbalanced variant")

    # generate master matrices only
    master = sub.add_parser("master", help="Generate master DistanceMatrix and TimeMatrix only")
    master.add_argument("--out", default="output/generated_instances", help="Output root directory")
    master.add_argument("--seed", type=int, default=None, help="Random seed")
    master.add_argument("--route-class", choices=["short", "med", "long"], default="long", help="Route class for master matrix")
    master.add_argument("--max-customers", type=int, default=15, help="Maximum number of customers in master matrix")

    # default if no subcommand: run a short demo grid
    p.add_argument("--demo", action="store_true", help="If set without subcommand, generate a demo grid")
    p.add_argument("--out", default="output/generated_instances", help="Output root directory (demo mode)")
    p.add_argument("--seed", type=int, default=None, help="Random seed (demo mode)")
    p.add_argument("--no-baatsfjord", action="store_true", help="Do not append Baatsfjord in demo mode")
    p.add_argument("--round-trip", action="store_true", help="Force round-trip in demo mode")

    return p.parse_args()


def run_generate(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    # For single-cluster, ignore allocation and label
    is_single_cluster = args.clusters == 1
    spec = RouteSpec(
        route_class=args.route_class,
        clusters=args.clusters,
        total_customers=args.customers,
        variant_idx=args.variant,
        round_trip=(not args.no_round_trip),
        add_baatsfjord_column=(not args.no_baatsfjord),
        allocation_strategy=("balanced" if is_single_cluster else args.allocation),
        variant_label=("" if is_single_cluster else ("Unbalanced" if args.allocation == "unbalanced" else "Balanced")),
    )
    out_dir = generate_instance(spec, args.out, rng)
    print(f"Generated: {out_dir}")


def run_grid(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    # Test set matching your specification table
    # Format: (route_class, clusters, [customer_count_variant1, customer_count_variant2])
    grid_specs = [
        # Format: (route_class, clusters, customer_range, [total_customers_variant1, total_customers_variant2])
        # Short route class
        ("short", 1, "Few", [2, 3]),    # Short, 1 cluster, Few (1–3): 2, 3
        ("short", 1, "Medium", [4, 5]),    # Short, 1 cluster, Medium (4–5): 4, 5
        ("short", 2, "Few", [3, 2]),    # Short, 2 clusters, Few (1–3): 3, 2
        ("short", 2, "Medium", [5, 4]),    # Short, 2 clusters, Medium (4–5): 5, 4
        ("short", 3, "Few", [3, 4]),    # Short, 3 clusters, Few (1–3): 3, 2
        ("short", 3, "Medium", [5, 4]),    # Short, 3 clusters, Medium (4–5): 5, 4
        ("short", 3, "Many", [10, 12]),  # Short, 3 clusters, Many (6–15): 10, 12
        
        # Medium route class
        ("med", 1, "Few", [2, 3]),    # Medium, 1 cluster, Few (1–3): 2, 3
        ("med", 1, "Medium", [4, 5]),    # Medium, 1 cluster, Medium (4–5): 4, 5
        ("med", 2, "Few", [3, 2]),    # Medium, 2 clusters, Few (1–3): 3, 2
        ("med", 2, "Medium", [5, 4]),    # Medium, 2 clusters, Medium (4–5): 5, 4
        ("med", 3, "Few", [3, 4]),    # Medium, 3 clusters, Few (1–3): 3, 2
        ("med", 3, "Medium", [5, 4]),    # Medium, 3 clusters, Medium (4–5): 5, 4
        ("med", 3, "Many", [11, 13]),  # Medium, 3 clusters, Many (6–15): 11, 13
        
        # Long route class
        ("long", 1, "Few", [2, 3]),    # Long, 1 cluster, Few (1–3): 2, 3
        ("long", 1, "Medium", [4, 5]),    # Long, 1 cluster, Medium (4–5): 4, 5
        ("long", 2, "Few", [3, 2]),    # Long, 2 clusters, Few (1–3): 3, 2
        ("long", 2, "Medium", [5, 4]),    # Long, 2 clusters, Medium (4–5): 5, 4
        ("long", 3, "Few", [3, 4]),    # Long, 3 clusters, Few (1–3): 3, 2
        ("long", 3, "Medium", [5, 4]),    # Long, 3 clusters, Medium (4–5): 5, 4
        ("long", 3, "Many", [14, 12]),  # Long, 3 clusters, Many (6–15): 14, 12
    ]
    for route_class, k, customer_range, variants in grid_specs:
        if k == 1:
            # Only one instance for single cluster; use the first total and no variant label
            n_single = variants[0]
            spec = RouteSpec(
                route_class=route_class,
                clusters=k,
                total_customers=n_single,
                variant_idx=1,
                customer_range=customer_range,
                round_trip=(args.round_trip or True),
                add_baatsfjord_column=(not args.no_baatsfjord),
                allocation_strategy="balanced",
                variant_label="",
            )
            generate_instance(spec, args.out, rng)
            continue

        # k > 1: two balanced variants using provided totals
        for v_idx, n in enumerate(variants, start=1):
            spec = RouteSpec(
                route_class=route_class,
                clusters=k,
                total_customers=n,
                variant_idx=v_idx,
                customer_range=customer_range,
                round_trip=(args.round_trip or True),
                add_baatsfjord_column=(not args.no_baatsfjord),
                allocation_strategy="balanced",
                variant_label="Balanced",
            )
            generate_instance(spec, args.out, rng)

        # Optional extra unbalanced variant (use the second total by default)
        if getattr(args, "add_unbalanced_variant", False):
            n_unbalanced = variants[-1]
            spec = RouteSpec(
                route_class=route_class,
                clusters=k,
                total_customers=n_unbalanced,
                variant_idx=3,
                customer_range=customer_range,
                round_trip=(args.round_trip or True),
                add_baatsfjord_column=(not args.no_baatsfjord),
                allocation_strategy="unbalanced",
                variant_label="Unbalanced",
            )
            generate_instance(spec, args.out, rng)
    
    # Generate master matrices after all instances
    print("Generating master matrices...")
    master_dist_file, master_time_file = generate_master_matrices(args.out, "long", 15, rng)
    print(f"Master DistanceMatrix: {master_dist_file}")
    print(f"Master TimeMatrix: {master_time_file}")
    print(f"Grid generated under: {args.out}")


def run_master(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    print("Generating master matrices...")
    master_dist_file, master_time_file = generate_master_matrices(
        args.out, args.route_class, args.max_customers, rng
    )
    print(f"Master DistanceMatrix: {master_dist_file}")
    print(f"Master TimeMatrix: {master_time_file}")


def run_demo(args: argparse.Namespace) -> None:
    # rng = random.Random(args.seed)
    # grid_specs = [
    #     ("short", 1, [2, 3]),
    #     ("med", 2, [6, 8]),
    #     ("long", 3, [10, 12]),
    # ]
    # for route_class, k, variants in grid_specs:
    #     for v_idx, n in enumerate(variants, start=1):
    #         spec = RouteSpec(
    #             route_class=route_class,
    #             clusters=k,
    #             total_customers=n,
    #             variant_idx=v_idx,
    #             round_trip=(args.round_trip or True),
    #             add_baatsfjord_column=(not args.no_baatsfjord),
    #         )
    #         generate_instance(spec, args.out, rng)
    
    # # Generate master matrices after all instances
    # print("Generating master matrices...")
    # master_dist_file, master_time_file = generate_master_matrices(args.out, "long", 15, rng)
    # print(f"Master DistanceMatrix: {master_dist_file}")
    # print(f"Master TimeMatrix: {master_time_file}")
    # print(f"Demo grid generated under: {args.out}")
    # Default behavior: run the full grid instead of demo
    # Default behavior: mimic `python Test_Generator.py grid --add-unbalanced-variant --out instances --seed 42`
    # Respect user-provided overrides if they passed flags in demo mode
    if not hasattr(args, "add_unbalanced_variant"):
        setattr(args, "add_unbalanced_variant", True)
    else:
        args.add_unbalanced_variant = True
    if getattr(args, "seed", None) is None:
        args.seed = 42
    if not getattr(args, "out", None):
        args.out = "output/generated_instances"
    print("Running grid with unbalanced variant by default (grid --add-unbalanced-variant --out instances --seed 42)...")
    run_grid(args)


def main() -> None:
    args = parse_args()
    if args.cmd == "generate":
        run_generate(args)
        return
    if args.cmd == "grid":
        run_grid(args)
        return
    if args.cmd == "master":
        run_master(args)
        return
    if args.demo or args.cmd is None:
        run_demo(args)
        return


if __name__ == "__main__":
    main()


