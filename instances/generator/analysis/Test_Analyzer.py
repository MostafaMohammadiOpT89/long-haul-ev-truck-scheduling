#!/usr/bin/env python3
"""
Test Instance Feature Analyzer

This standalone script analyzes all generated test instances and extracts comprehensive
features including main characteristics, holistic metrics, and detailed cluster analysis.
"""

import csv
import os
import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import re


@dataclass
class InstanceFeatures:
    """Container for all extracted features of a test instance."""
    # Basic identification
    test_name: str
    route_class: str
    cluster_count: int
    total_customers: int
    variant: str
    
    # Main features
    total_route_distance: float
    total_route_time: float
    
    # Cluster analysis
    customers_per_cluster: List[int]
    cluster_distances: List[float]  # Distance between consecutive clusters
    avg_cluster_distance: float
    min_cluster_distance: float
    max_cluster_distance: float
    
    # Customer positioning within clusters
    avg_customer_distance_within_cluster: float
    min_customer_distance_within_cluster: float
    max_customer_distance_within_cluster: float
    
    # Inter-cluster distances (all pairs)
    inter_cluster_distances: List[float]
    avg_inter_cluster_distance: float
    min_inter_cluster_distance: float
    max_inter_cluster_distance: float
    
    # Holistic metrics
    cluster_density: float  # customers per km
    route_efficiency: float  # total_distance / total_customers
    cluster_balance: float  # std deviation of customers per cluster
    spatial_spread: float  # max_distance - min_distance
    
    # Service characteristics
    avg_service_time: float
    total_service_time: float


def parse_instance_name(filename: str) -> Tuple[str, str, int, str]:
    """Parse instance filename to extract components."""
    # Supported formats:
    # 1) {route_class}_cl{clusters}_cu{customers}_v{variant}
    # 2) {route_class}_cl{clusters}_cu{customers}_{Balanced|Unbalanced}
    # 3) {route_class}_cl{clusters}_cu{customers}  (single-cluster case, no variant)
    pattern_numeric = r'([a-z]+)_cl(\d+)_cu(\d+)_v(\d+)'
    pattern_label = r'([a-z]+)_cl(\d+)_cu(\d+)_(Balanced|Unbalanced)'
    pattern_single = r'([a-z]+)_cl(\d+)_cu(\d+)$'
    m = re.match(pattern_numeric, filename)
    if m:
        route_class, clusters, customers, variant_num = m.groups()
        return route_class, int(clusters), int(customers), f"v{variant_num}"
    m = re.match(pattern_label, filename)
    if m:
        route_class, clusters, customers, variant_label = m.groups()
        return route_class, int(clusters), int(customers), variant_label
    m = re.match(pattern_single, filename)
    if m:
        route_class, clusters, customers = m.groups()
        return route_class, int(clusters), int(customers), ""
    raise ValueError(f"Cannot parse filename: {filename}")


def read_distance_matrix(filepath: str) -> List[List[float]]:
    """Read distance matrix from CSV file."""
    matrix = []
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header
        
        for row in reader:
            # Skip first column (node names) and last column (Baatsfjord)
            values = []
            for i in range(1, len(row) - 1):  # Exclude first and last columns
                try:
                    values.append(float(row[i]))
                except ValueError:
                    break
            if values:
                matrix.append(values)
    
    return matrix


def read_instance_file(filepath: str) -> Dict[str, float]:
    """Read instance file and extract service times."""
    service_times = {}
    
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        
        # Skip to the nodes section
        for row in reader:
            if len(row) >= 9 and row[0] == "NodeId":
                break
        
        # Read customer nodes
        for row in reader:
            if len(row) >= 9 and row[1].startswith("Cust"):
                customer_name = row[1]
                service_time = float(row[8])
                service_times[customer_name] = service_time
    
    return service_times


def extract_cluster_positions(dist_matrix: List[List[float]], n_customers: int) -> List[float]:
    """Extract customer positions from distance matrix."""
    # Origin is at position 0, customers are at positions 1 to n_customers
    positions = [0.0]  # Origin position
    
    for i in range(1, n_customers + 1):
        if i < len(dist_matrix):
            positions.append(dist_matrix[0][i])  # Distance from origin
    
    return positions


def read_diagnostics(instance_dir: str, instance_name: str) -> Tuple[Optional[List[float]], Optional[List[int]], Optional[List[float]]]:
    """Read diagnostics file if present and return (positions, membership, centers)."""
    diag_path = os.path.join(instance_dir, f"{instance_name}_Diagnostics.csv")
    if not os.path.exists(diag_path):
        return None, None, None

    positions: List[float] = []
    membership: List[int] = []
    centers_by_cluster: Dict[int, float] = {}

    with open(diag_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            node = row.get('Node', '')
            if node.startswith('Cust'):
                # Positions and membership are aligned with customer order
                try:
                    positions.append(float(row.get('PositionKm', '0') or 0))
                except ValueError:
                    positions.append(0.0)
                try:
                    membership.append(int(row.get('ClusterIdx', '-1') or -1))
                except ValueError:
                    membership.append(-1)
                # capture center per cluster
                cl = membership[-1]
                try:
                    center_val_str = row.get('ClusterCenterKm', '')
                    if center_val_str != '':
                        centers_by_cluster.setdefault(cl, float(center_val_str))
                except ValueError:
                    pass

    if not positions or not membership:
        return None, None, None

    # Build centers array ordered by cluster index if available
    if centers_by_cluster:
        max_cl = max(centers_by_cluster.keys())
        centers: List[float] = []
        for i in range(max_cl + 1):
            centers.append(centers_by_cluster.get(i, 0.0))
    else:
        centers = None

    return positions, membership, centers

def analyze_clusters(positions: List[float], n_clusters: int) -> Tuple[List[int], List[float]]:
    """Fallback analysis when true membership is unavailable.

    Approximates customers per cluster by even split and uses first customer as center per cluster.
    positions is expected to include Origin at index 0 and then customers.
    """
    if n_clusters <= 1:
        customers_per_cluster = [max(0, len(positions) - 1)]
        return customers_per_cluster, []

    n_customers = max(0, len(positions) - 1)
    customers_per_cluster: List[int] = []
    base = n_customers // n_clusters
    rem = n_customers % n_clusters
    for i in range(n_clusters):
        customers_per_cluster.append(base + (1 if i < rem else 0))

    # Estimate centers from first customer in each chunk
    centers: List[float] = []
    idx = 1
    for count in customers_per_cluster:
        if count > 0 and idx < len(positions):
            centers.append(positions[idx])
            idx += count
        else:
            centers.append(positions[idx - 1] if idx - 1 < len(positions) else 0.0)

    centers.sort()
    cluster_dists: List[float] = []
    for i in range(len(centers) - 1):
        cluster_dists.append(abs(centers[i + 1] - centers[i]))
    return customers_per_cluster, cluster_dists
def analyze_clusters_from_membership(positions_only_customers: List[float], membership: List[int], n_clusters: int, centers: Optional[List[float]] = None) -> Tuple[List[int], List[float], List[float]]:
    """Analyze cluster distribution and distances using true membership.

    Returns: (customers_per_cluster, consecutive_cluster_center_dists, all_pair_center_dists)
    """
    customers_per_cluster = [0] * n_clusters
    for cl in membership:
        if 0 <= cl < n_clusters:
            customers_per_cluster[cl] += 1

    # Determine centers: prefer provided centers, otherwise approximate from first customer per cluster
    if centers is None or len(centers) < n_clusters:
        approx_centers: Dict[int, float] = {}
        for pos, cl in zip(positions_only_customers, membership):
            if cl not in approx_centers:
                approx_centers[cl] = pos
        centers_list: List[Tuple[int, float]] = sorted(((cl, c) for cl, c in approx_centers.items()), key=lambda x: x[1])
        centers_vals = [c for _, c in centers_list]
    else:
        # Use provided centers and sort by position
        centers_vals = sorted(centers)[:n_clusters]

    # Consecutive center distances
    consecutive_dists: List[float] = []
    for i in range(len(centers_vals) - 1):
        consecutive_dists.append(abs(centers_vals[i + 1] - centers_vals[i]))

    # All pairwise center distances
    all_pair_dists: List[float] = []
    for i in range(len(centers_vals)):
        for j in range(i + 1, len(centers_vals)):
            all_pair_dists.append(abs(centers_vals[j] - centers_vals[i]))

    return customers_per_cluster, consecutive_dists, all_pair_dists


def calculate_inter_cluster_distances(positions: List[float], n_clusters: int) -> List[float]:
    """Calculate all pairwise distances between clusters."""
    if n_clusters <= 1:
        return []
    
    # Simplified: estimate cluster centers
    n_customers = len(positions) - 1
    cluster_centers = []
    
    customer_idx = 1
    for i in range(n_clusters):
        if customer_idx <= n_customers:
            cluster_centers.append(positions[customer_idx])
            customer_idx += max(1, n_customers // n_clusters)
        else:
            cluster_centers.append(positions[-1] if positions else 0.0)
    
    # Calculate all pairwise distances
    distances = []
    for i in range(len(cluster_centers)):
        for j in range(i + 1, len(cluster_centers)):
            dist = abs(cluster_centers[j] - cluster_centers[i])
            distances.append(dist)
    
    return distances


def analyze_instance(instance_dir: str) -> InstanceFeatures:
    """Analyze a single test instance and extract all features."""
    instance_name = os.path.basename(instance_dir)
    
    # Parse instance name
    route_class, n_clusters, n_customers, variant = parse_instance_name(instance_name)
    
    # File paths
    dist_file = os.path.join(instance_dir, f"{instance_name}_DistanceMatrix.csv")
    time_file = os.path.join(instance_dir, f"{instance_name}_TimeMatrix.csv")
    instance_file = os.path.join(instance_dir, f"{instance_name}.txt")
    
    # Read data
    dist_matrix = read_distance_matrix(dist_file)
    time_matrix = read_distance_matrix(time_file)
    service_times = read_instance_file(instance_file)
    
    # Try diagnostics for true positions/membership
    diag_positions, diag_membership, diag_centers = read_diagnostics(instance_dir, instance_name)
    if diag_positions is not None and diag_membership is not None:
        positions = [0.0] + diag_positions[:] + [0.0]  # include origin/destination placeholders for spread calc
        positions_only_customers = diag_positions[:]
        membership = diag_membership[:]
        centers = diag_centers
    else:
        # Fallback to approximate extraction
        positions = extract_cluster_positions(dist_matrix, n_customers)
        # remove origin for consistent handling
        positions_only_customers = positions[1:]
        membership = []
        centers = None
    
    # Calculate main features
    total_route_distance = dist_matrix[0][-1] if dist_matrix else 0.0  # Origin to Destination
    total_route_time = time_matrix[0][-1] if time_matrix else 0.0
    
    # Analyze clusters (prefer true membership when available)
    if membership:
        customers_per_cluster, cluster_distances, inter_cluster_distances = analyze_clusters_from_membership(positions_only_customers, membership, n_clusters, centers)
    else:
        # Fallbacks when membership unknown
        customers_per_cluster, cluster_distances = analyze_clusters(positions, n_clusters)  # type: ignore[name-defined]
        inter_cluster_distances = calculate_inter_cluster_distances(positions, n_clusters)
    
    # Calculate cluster distance statistics
    avg_cluster_distance = sum(cluster_distances) / len(cluster_distances) if cluster_distances else 0.0
    min_cluster_distance = min(cluster_distances) if cluster_distances else 0.0
    max_cluster_distance = max(cluster_distances) if cluster_distances else 0.0
    
    # Intra-cluster consecutive customer gaps using true membership if available
    if membership:
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
        avg_customer_distance_within = sum(gaps_within) / len(gaps_within) if gaps_within else 0.0
        min_customer_distance_within = min(gaps_within) if gaps_within else 0.0
        max_customer_distance_within = max(gaps_within) if gaps_within else 0.0
    else:
        # Previous approximation across all customers (not ideal)
        customer_distances_within = []
        for i in range(1, len(positions) - 1):
            for j in range(i + 1, len(positions) - 1):
                dist = abs(positions[j] - positions[i])
                customer_distances_within.append(dist)
        avg_customer_distance_within = sum(customer_distances_within) / len(customer_distances_within) if customer_distances_within else 0.0
        min_customer_distance_within = min(customer_distances_within) if customer_distances_within else 0.0
        max_customer_distance_within = max(customer_distances_within) if customer_distances_within else 0.0
    avg_inter_cluster_distance = sum(inter_cluster_distances) / len(inter_cluster_distances) if inter_cluster_distances else 0.0
    min_inter_cluster_distance = min(inter_cluster_distances) if inter_cluster_distances else 0.0
    max_inter_cluster_distance = max(inter_cluster_distances) if inter_cluster_distances else 0.0
    
    
    # Calculate holistic metrics
    cluster_density = n_customers / total_route_distance if total_route_distance > 0 else 0.0
    route_efficiency = total_route_distance / n_customers if n_customers > 0 else 0.0
    
    # Cluster balance (standard deviation of customers per cluster)
    if customers_per_cluster:
        mean_customers = sum(customers_per_cluster) / len(customers_per_cluster)
        variance = sum((x - mean_customers) ** 2 for x in customers_per_cluster) / len(customers_per_cluster)
        cluster_balance = math.sqrt(variance)
    else:
        cluster_balance = 0.0
    
    # Spatial spread
    spatial_spread = max(positions) - min(positions) if positions else 0.0
    
    # Service time statistics
    service_time_values = list(service_times.values())
    avg_service_time = sum(service_time_values) / len(service_time_values) if service_time_values else 0.0
    total_service_time = sum(service_time_values)
    
    return InstanceFeatures(
        test_name=instance_name,
        route_class=route_class,
        cluster_count=n_clusters,
        total_customers=n_customers,
        variant=variant,
        total_route_distance=total_route_distance,
        total_route_time=total_route_time,
        customers_per_cluster=customers_per_cluster,
        cluster_distances=cluster_distances,
        avg_cluster_distance=avg_cluster_distance,
        min_cluster_distance=min_cluster_distance,
        max_cluster_distance=max_cluster_distance,
        avg_customer_distance_within_cluster=avg_customer_distance_within,
        min_customer_distance_within_cluster=min_customer_distance_within,
        max_customer_distance_within_cluster=max_customer_distance_within,
        inter_cluster_distances=inter_cluster_distances,
        avg_inter_cluster_distance=avg_inter_cluster_distance,
        min_inter_cluster_distance=min_inter_cluster_distance,
        max_inter_cluster_distance=max_inter_cluster_distance,
        cluster_density=cluster_density,
        route_efficiency=route_efficiency,
        cluster_balance=cluster_balance,
        spatial_spread=spatial_spread,
        avg_service_time=avg_service_time,
        total_service_time=total_service_time
    )


def analyze_all_instances(instances_dir: str) -> List[InstanceFeatures]:
    """Analyze all test instances in the directory."""
    features_list = []
    
    for item in os.listdir(instances_dir):
        item_path = os.path.join(instances_dir, item)
        
        # Skip files, only process directories
        if not os.path.isdir(item_path):
            continue
        
        # Skip master matrix files
        if item.startswith("Master_"):
            continue
        
        try:
            features = analyze_instance(item_path)
            features_list.append(features)
            print(f"Analyzed: {features.test_name}")
        except Exception as e:
            print(f"Error analyzing {item}: {e}")
    
    return features_list


def write_features_to_csv(features_list: List[InstanceFeatures], output_file: str):
    """Write all features to a CSV file."""
    
    # Define column headers
    headers = [
        # Basic identification
        "Test_Name", "Route_Class", "Cluster_Count", "Total_Customers", "Variant",
        
        # Main features
        "Total_Route_Distance_km", "Total_Route_Time_hours",
        
        # Cluster analysis
        "Customers_Per_Cluster", "Cluster_Distances_km", "Avg_Cluster_Distance_km",
        "Min_Cluster_Distance_km", "Max_Cluster_Distance_km",
        
        # Customer positioning within clusters
        "Avg_Customer_Distance_Within_Cluster_km", "Min_Customer_Distance_Within_Cluster_km",
        "Max_Customer_Distance_Within_Cluster_km",
        
        # Inter-cluster distances
        "Inter_Cluster_Distances_km", "Avg_Inter_Cluster_Distance_km",
        "Min_Inter_Cluster_Distance_km", "Max_Inter_Cluster_Distance_km",
        
        # Holistic metrics (temporarily excluded from CSV)
        # "Cluster_Density_customers_per_km", "Route_Efficiency_km_per_customer",
        # "Cluster_Balance_std_dev", "Spatial_Spread_km",
        
        # Service characteristics
        "Avg_Service_Time_hours", "Total_Service_Time_hours"
    ]
    
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            
            for features in features_list:
                row = [
                    # Basic identification
                    features.test_name,
                    features.route_class,
                    features.cluster_count,
                    features.total_customers,
                    features.variant,
                    
                    # Main features
                    round(features.total_route_distance, 2),
                    round(features.total_route_time, 4),
                    
                    # Cluster analysis
                    str(features.customers_per_cluster),
                    str([round(x, 2) for x in features.cluster_distances]),
                    round(features.avg_cluster_distance, 2),
                    round(features.min_cluster_distance, 2),
                    round(features.max_cluster_distance, 2),
                    
                    # Customer positioning within clusters
                    round(features.avg_customer_distance_within_cluster, 2),
                    round(features.min_customer_distance_within_cluster, 2),
                    round(features.max_customer_distance_within_cluster, 2),
                    
                    # Inter-cluster distances
                    str([round(x, 2) for x in features.inter_cluster_distances]),
                    round(features.avg_inter_cluster_distance, 2),
                    round(features.min_inter_cluster_distance, 2),
                    round(features.max_inter_cluster_distance, 2),
                    
                    # Holistic metrics (temporarily excluded from CSV)
                    # round(features.cluster_density, 4),
                    # round(features.route_efficiency, 2),
                    # round(features.cluster_balance, 2),
                    # round(features.spatial_spread, 2),
                    
                    # Service characteristics
                    round(features.avg_service_time, 4),
                    round(features.total_service_time, 4)
                ]
                writer.writerow(row)
    except PermissionError:
        alt_file = os.path.join(os.path.dirname(output_file), "test_instance_features_alt.csv")
        print(f"Permission denied writing '{output_file}'. Writing instead to '{alt_file}'. Close the file if it's open and rerun to overwrite the original.")
        with open(alt_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for features in features_list:
                row = [
                    features.test_name,
                    features.route_class,
                    features.cluster_count,
                    features.total_customers,
                    features.variant,
                    round(features.total_route_distance, 2),
                    round(features.total_route_time, 4),
                    str(features.customers_per_cluster),
                    str([round(x, 2) for x in features.cluster_distances]),
                    round(features.avg_cluster_distance, 2),
                    round(features.min_cluster_distance, 2),
                    round(features.max_cluster_distance, 2),
                    round(features.avg_customer_distance_within_cluster, 2),
                    round(features.min_customer_distance_within_cluster, 2),
                    round(features.max_customer_distance_within_cluster, 2),
                    str([round(x, 2) for x in features.inter_cluster_distances]),
                    round(features.avg_inter_cluster_distance, 2),
                    round(features.min_inter_cluster_distance, 2),
                    round(features.max_inter_cluster_distance, 2),
                    round(features.avg_service_time, 4),
                    round(features.total_service_time, 4)
                ]
                writer.writerow(row)


def write_features_to_latex(features_list: List[InstanceFeatures], output_txt_file: str) -> None:
    """Write features as a LaTeX tabular into a .txt file."""
    headers = [
        "Test_Name", "Route_Class", "Cluster_Count", "Total_Customers", "Variant",
        "Total_Route_Distance_km", "Total_Route_Time_hours",
        "Customers_Per_Cluster", "Cluster_Distances_km", "Avg_Cluster_Distance_km",
        "Min_Cluster_Distance_km", "Max_Cluster_Distance_km",
        "Avg_Customer_Distance_Within_Cluster_km", "Min_Customer_Distance_Within_Cluster_km",
        "Max_Customer_Distance_Within_Cluster_km",
        "Inter_Cluster_Distances_km", "Avg_Inter_Cluster_Distance_km",
        "Min_Inter_Cluster_Distance_km", "Max_Inter_Cluster_Distance_km",
        "Avg_Service_Time_hours", "Total_Service_Time_hours"
    ]

    def esc(s: str) -> str:
        # escape LaTeX special chars minimally (underscore common here)
        return s.replace("\\", "\\\\").replace("_", "\\_")

    # Column alignment: left for text, right for numbers
    align = "l l r r l r r l l r r r r r r l r r r r r"

    lines: List[str] = []
    lines.append("\\begin{tabular}{" + align + "}")
    lines.append("\\hline")
    lines.append(" & ".join(esc(h) for h in headers) + " \\\\")
    lines.append("\\hline")

    for f in features_list:
        row_vals = [
            f.test_name,
            f.route_class,
            str(f.cluster_count),
            str(f.total_customers),
            f.variant,
            f"{f.total_route_distance:.2f}",
            f"{f.total_route_time:.4f}",
            str(f.customers_per_cluster),
            str([round(x, 2) for x in f.cluster_distances]),
            f"{f.avg_cluster_distance:.2f}",
            f"{f.min_cluster_distance:.2f}",
            f"{f.max_cluster_distance:.2f}",
            f"{f.avg_customer_distance_within_cluster:.2f}",
            f"{f.min_customer_distance_within_cluster:.2f}",
            f"{f.max_customer_distance_within_cluster:.2f}",
            str([round(x, 2) for x in f.inter_cluster_distances]),
            f"{f.avg_inter_cluster_distance:.2f}",
            f"{f.min_inter_cluster_distance:.2f}",
            f"{f.max_inter_cluster_distance:.2f}",
            f"{f.avg_service_time:.4f}",
            f"{f.total_service_time:.4f}",
        ]
        lines.append(" & ".join(esc(v) for v in row_vals) + " \\\\")

    lines.append("\\hline")
    lines.append("\\end{tabular}")

    try:
        with open(output_txt_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
    except PermissionError:
        alt = os.path.join(os.path.dirname(output_txt_file), "test_instance_features_latex_alt.txt")
        print(f"Permission denied writing '{output_txt_file}'. Writing instead to '{alt}'.")
        with open(alt, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))


def write_features_to_latex_compact(features_list: List[InstanceFeatures], output_txt_file: str) -> None:
    """Write a compact LaTeX tabular with key metrics only."""
    # Use full words in the header row
    headers = [
        "Test Name", "Route Class", "Clusters", "Total Customers", "Variant",
        "Total Route Distance (km)", "Total Route Time (h)",
        "Customers Per Cluster", "Avg Cluster Distance (km)",
        "Avg Intra-Cluster Distance (km)", "Avg Inter-Cluster Distance (km)",
        "Avg Service Time (h)"
    ]

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("_", "\\_")

    align = "l l r r l r r X r r r r"

    lines: List[str] = []
    lines.append("% Requires \\usepackage{tabularx}")
    lines.append("\\begin{table}[htbp]")
    lines.append("\\centering")
    lines.append("\\small")
    lines.append("\\setlength{\\tabcolsep}{5pt}")
    lines.append("\\renewcommand{\\arraystretch}{1.1}")
    lines.append("\\begin{tabularx}{\\linewidth}{" + align + "}")
    lines.append("\\hline")
    lines.append(" & ".join(esc(h) for h in headers) + " \\\\")
    lines.append("\\hline")

    for f in features_list:
        cust_per_cl = '[' + ','.join(str(x) for x in f.customers_per_cluster) + ']'
        row_vals = [
            f.test_name,
            f.route_class,
            str(f.cluster_count),
            str(f.total_customers),
            (f.variant if f.variant else "-"),
            f"{f.total_route_distance:.2f}",
            f"{f.total_route_time:.4f}",
            cust_per_cl,
            f"{f.avg_cluster_distance:.2f}",
            f"{f.avg_customer_distance_within_cluster:.2f}",
            f"{f.avg_inter_cluster_distance:.2f}",
            f"{f.avg_service_time:.4f}",
        ]
        lines.append(" & ".join(esc(v) for v in row_vals) + " \\\\")

    lines.append("\\hline")
    lines.append("\\end{tabularx}")
    lines.append("\\vspace{0.5ex}")
    lines.append("\\footnotesize Key columns only. Distances in km; times in h.")
    lines.append("\\par\\footnotesize Abbreviations: Dist\\_km=Total Route Distance (km), Time\\_h=Total Route Time (h), Cust/Cl=Customers Per Cluster, AvgCl\\_km=Avg Cluster Distance (km), AvgIntra\\_km=Avg Intra-Cluster Distance (km), AvgInter\\_km=Avg Inter-Cluster Distance (km), AvgSvc\\_h=Avg Service Time (h).")
    lines.append("\\end{table}")

    try:
        with open(output_txt_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
    except PermissionError:
        alt = os.path.join(os.path.dirname(output_txt_file), "test_instance_features_latex_compact_alt.txt")
        print(f"Permission denied writing '{output_txt_file}'. Writing instead to '{alt}'.")
        with open(alt, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))


def main():
    """Main function to analyze all test instances."""
    # Get the parent directory (where instances folder is located)
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    from common.paths import BENCHMARK, OUTPUT
    instances_dir = str(BENCHMARK)
    output_dir = str(OUTPUT / "analyses" / "instance_features")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "test_instance_features.csv")
    latex_txt_file = os.path.join(output_dir, "test_instance_features_latex.txt")
    latex_txt_file_compact = os.path.join(output_dir, "test_instance_features_latex_compact.txt")
    
    print("Starting test instance analysis...")
    print(f"Looking for instances in: {instances_dir}")
    
    if not os.path.exists(instances_dir):
        print(f"Error: Directory '{instances_dir}' not found!")
        return
    
    # Analyze all instances
    features_list = analyze_all_instances(instances_dir)
    
    if not features_list:
        print("No test instances found to analyze!")
        return
    
    print(f"\nAnalyzed {len(features_list)} test instances")
    
    # Write results to CSV
    write_features_to_csv(features_list, output_file)
    write_features_to_latex(features_list, latex_txt_file)
    write_features_to_latex_compact(features_list, latex_txt_file_compact)
    
    print(f"\nAnalysis complete! Results saved to: {output_file}")
    print(f"LaTeX table saved to: {latex_txt_file}")
    print(f"Compact LaTeX table saved to: {latex_txt_file_compact}")
    print(f"Generated {len(features_list)} rows of feature data")


if __name__ == "__main__":
    main()
