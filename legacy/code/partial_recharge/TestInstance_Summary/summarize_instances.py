import os
import sys
import csv
from typing import Dict, List, Tuple

# Ensure project root is on sys.path before importing local modules
_ROOT = os.path.dirname(os.path.abspath(os.path.join(__file__, os.pardir)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import arcClass
import CSVreader
import network
import isFeasible


def project_root() -> str:
    return os.path.dirname(os.path.abspath(os.path.join(__file__, os.pardir)))


def ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def read_test_instance_basic(path: str) -> Tuple[str, List[Dict[str, str]]]:
    """Return (depot_name, nodes) where nodes include 'location' and 'serviceTime'."""
    depot: str = None
    nodes: List[Dict[str, str]] = []
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        section = None
        is_first_vehicle_row = True
        for row in reader:
            if not row:
                continue
            head = row[0].strip()
            if head.startswith("VehicleId"):
                section = "vehicles"
                continue
            if head.startswith("NodeId"):
                section = "nodes"
                continue
            if section == "vehicles" and is_first_vehicle_row:
                _, vehicle_location, _ = row[:3]
                depot = vehicle_location.strip()
                is_first_vehicle_row = False
                continue
            if section == "nodes" and len(row) >= 9:
                # NodeId,Location,LocationId,TimeWindowStart,TimeWindowEnd,Weight,Volume,Revenue,ServiceTime
                node = {
                    "location": row[1].strip(),
                    "serviceTime": float(row[8]),
                }
                nodes.append(node)
    if depot is None:
        raise ValueError(f"Could not find depot in {path}")
    return depot, nodes


def summarize_instance(i: int, cities_arcs) -> Dict[str, object]:
    filename = os.path.join(project_root(), f"testInstance{i}.txt")
    if not os.path.exists(filename):
        return {
            "instance": i,
            "present": False,
        }
    depot, nodes = read_test_instance_basic(filename)

    # Build network with baseline params (used only to construct CS and virtual graph)
    consumption = 1.12
    cs_interval_km = 40
    battery_cap = 350
    cp_kw = 350
    network.setGlobalParams(consumption, cs_interval_km, battery_cap, cp_kw)
    isFeasible.setGlobalParams(battery_cap)

    net = network.Network(filename, cities_arcs)

    # Counts
    num_customers = len(nodes)
    service_times = [float(n.get("serviceTime", 0.0) or 0.0) for n in nodes]
    svc_min = min(service_times) if service_times else 0.0
    svc_max = max(service_times) if service_times else 0.0

    node_types = [d.get("nodeType") for d in net.nodes.values()]
    num_city = sum(1 for t in node_types if t == "City")
    num_cs = sum(1 for t in node_types if t == "CS")
    num_virtual = sum(1 for t in node_types if t == "Intermediate")

    # Links (virtual graph only)
    virtual_links = len(net.paraArcs)

    return {
        "instance": i,
        "present": True,
        "depot": depot,
        "num_customers": num_customers,
        "service_time_min": svc_min,
        "service_time_max": svc_max,
        "num_cs": num_cs,
        "num_virtual_nodes": num_virtual,
        "real_nodes": num_city,
        "virtual_nodes_total": num_city + num_cs + num_virtual,
        "virtual_links_total": virtual_links,
        "cs_interval_km": cs_interval_km,
        "battery_kWh": battery_cap,
        "consumption_kWh_per_km": consumption,
        "cp_kW": cp_kw,
    }


def as_service_range(min_h: float, max_h: float) -> str:
    return f"{min_h:.1f}--{max_h:.1f}"


def write_csv(rows: List[Dict[str, object]], out_csv: str) -> None:
    headers = [
        "instance",
        "depot",
        "num_customers",
        "service_time_min",
        "service_time_max",
        "num_cs",
        "num_virtual_nodes",
        "real_nodes",
        "virtual_nodes_total",
        "virtual_links_total",
        "cs_interval_km",
        "battery_kWh",
        "consumption_kWh_per_km",
        "cp_kW",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            if r.get("present"):
                w.writerow({k: r.get(k) for k in headers})


def write_latex(rows: List[Dict[str, object]], out_tex: str) -> None:
    lines: List[str] = []
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\caption{Summary of test instances.}")
    lines.append("\\label{tab:test-instance-summary}")
    lines.append("\\begin{tabular}{lcccccc}")
    lines.append("\\toprule")
    lines.append(r"Instance & Depot & \# Customers & Service time range [h] & \# CS & Real nodes & Virtual nodes \\ ")
    lines.append("\\midrule")
    for r in rows:
        if not r.get("present"):
            continue
        inst = r["instance"]
        depot = r["depot"]
        ncust = r["num_customers"]
        svc_rng = as_service_range(r["service_time_min"], r["service_time_max"]) 
        ncs = r["num_cs"]
        real_nodes = r["real_nodes"]
        virt_nodes = r["virtual_nodes_total"]
        lines.append(f"{inst} & {depot} & {ncust} & {svc_rng} & {ncs} & {real_nodes} & {virt_nodes} \\ ")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")

    with open(out_tex, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    # Ensure working directory is project root
    os.chdir(project_root())

    # Build city arcs from matrices
    distance_matrix = 'DistanceMatrix.csv'
    time_matrix = 'TimeMatrix.csv'
    distance_data = CSVreader.CSVreader(distance_matrix)
    time_data = CSVreader.CSVreader(time_matrix)
    cities_arcs = arcClass.cityArcs.createArcs(distance_data, time_data)

    rows: List[Dict[str, object]] = []
    for i in range(1, 13):
        rows.append(summarize_instance(i, cities_arcs))

    out_dir = os.path.join('Results', 'TestInstance_Summary')
    ensure_dir(out_dir)
    write_csv(rows, os.path.join(out_dir, 'summary.csv'))
    write_latex(rows, os.path.join(out_dir, 'summary.tex'))
    print(f"Wrote summary for {sum(1 for r in rows if r.get('present'))} instances to {out_dir}")


if __name__ == "__main__":
    main()


