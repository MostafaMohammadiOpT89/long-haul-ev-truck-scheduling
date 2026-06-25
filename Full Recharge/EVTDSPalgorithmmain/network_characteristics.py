import os
import csv
import logging
import time
from datetime import datetime
from collections import Counter

import arcClass
import network
import CSVreader


# Configure logging
logging.basicConfig(
    filename="network_characteristics.log",
    level=logging.INFO,
    filemode="w",
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Set the working directory to the script's location
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
print("Working directory set to:", os.getcwd())

# Default parameters for network construction (single set, not varied)
# These are only used to build the network structure - actual characteristics are independent
DEFAULT_CONSUMPTION = 1.49  # Average consumption
DEFAULT_DISTANCE_PER_CS = 60  # km
DEFAULT_BATTERY_CAP = 750  # kWh
DEFAULT_CP = 350  # kW

# Configuration: Specific instances to run (optional)
SPECIFIC_INSTANCES_TO_RUN = []  # Empty = run all, or specify names like: ['short_cl1_cu2']

# Legacy test instances (testInstance1.txt ... testInstance12.txt)
LEGACY_TEST_INSTANCE_RANGE = range(1, 13)

# Note: We now use instance-specific matrices from each test folder (not master matrices)
# This matches the behavior of enhanced_main.py after recent updates

# Legacy test instances may use different city names.
# If you have a separate matrix for legacy tests, set these.
# Leave as None to reuse the base matrices above.
legacyDistanceMatrix = os.path.join(
    "..",
    "..",
    "Partial Recharge",
    "EVTDSPalgorithmmain",
    "DistanceMatrix_original.csv",
)
legacyTimeMatrix = os.path.join(
    "..",
    "..",
    "Partial Recharge",
    "EVTDSPalgorithmmain",
    "TimeMatrix_Original.csv",
)


def discover_instance_tests(instances_root):
    """Discover instance test files under the given root directory."""
    discovered = []
    if not os.path.isdir(instances_root):
        logging.warning("Instances root does not exist: %s", instances_root)
        return discovered

    for entry in os.listdir(instances_root):
        entry_path = os.path.join(instances_root, entry)
        if os.path.isdir(entry_path):
            txt_candidates = [f for f in os.listdir(entry_path) if f.lower().endswith(".txt")]
            if not txt_candidates:
                logging.warning("No .txt file found in instance folder: %s", entry_path)
                continue
            preferred = None
            for f in txt_candidates:
                name_no_ext, _ = os.path.splitext(f)
                if name_no_ext.lower() == entry.lower():
                    preferred = f
                    break
            instance_txt = preferred if preferred is not None else txt_candidates[0]
            instance_file_path = os.path.join(entry_path, instance_txt)
            discovered.append((entry, instance_file_path))

    loose_txt = [f for f in os.listdir(instances_root) if f.lower().endswith(".txt")]
    for f in loose_txt:
        instance_name = os.path.splitext(f)[0]
        instance_file_path = os.path.join(instances_root, f)
        discovered.append((instance_name, instance_file_path))

    return discovered


def discover_legacy_test_instances(base_dir):
    """Discover legacy testInstance*.txt files in the base directory."""
    discovered = []
    for i in LEGACY_TEST_INSTANCE_RANGE:
        filename = f"testInstance{i}.txt"
        filepath = os.path.join(base_dir, filename)
        if os.path.isfile(filepath):
            discovered.append((filename.replace(".txt", ""), filepath))
    return discovered


def get_instance_locations(instance_path):
    """Extract location names from a test instance file."""
    locations = set()
    try:
        with open(instance_path, "r") as file:
            reader = csv.reader(file)
            section = None
            is_first_vehicle_row = True
            for row in reader:
                if not row:
                    continue
                if row[0].startswith("VehicleId"):
                    section = "vehicles"
                    continue
                if row[0].startswith("NodeId"):
                    section = "nodes"
                    continue
                if section == "vehicles" and is_first_vehicle_row:
                    # vehicle_id, location, location_id
                    if len(row) >= 2:
                        locations.add(row[1])
                    is_first_vehicle_row = False
                elif section == "nodes":
                    # node_id, location, ...
                    if len(row) >= 2:
                        locations.add(row[1])
    except Exception as exc:
        logging.warning("Failed to read instance locations from %s: %s", instance_path, exc)
    return locations


def get_route_order_and_customers(instance_path):
    """Extract route order (Origin -> Cust1 -> ... -> CustN -> Destination) and count customers."""
    route_order = []
    customers = []
    try:
        with open(instance_path, "r") as file:
            reader = csv.reader(file)
            section = None
            is_first_vehicle_row = True
            for row in reader:
                if not row:
                    continue
                if row[0].startswith("VehicleId"):
                    section = "vehicles"
                    continue
                if row[0].startswith("NodeId"):
                    section = "nodes"
                    continue
                if section == "vehicles" and is_first_vehicle_row:
                    # vehicle_id, location, location_id - this is Origin
                    if len(row) >= 2:
                        route_order.append(row[1])
                    is_first_vehicle_row = False
                elif section == "nodes":
                    # node_id, location, ...
                    if len(row) >= 2:
                        location = row[1]
                        route_order.append(location)
                        if location.startswith("Cust"):
                            customers.append(location)
    except Exception as exc:
        logging.warning("Failed to read route order from %s: %s", instance_path, exc)
    return route_order, customers


def load_instance_matrices(instance_path):
    """Load instance-specific distance and time matrices for an instance."""
    instance_dir = os.path.dirname(instance_path)
    instance_name = os.path.splitext(os.path.basename(instance_path))[0]
    
    distance_matrix_path = os.path.join(instance_dir, f"{instance_name}_DistanceMatrix.csv")
    time_matrix_path = os.path.join(instance_dir, f"{instance_name}_TimeMatrix.csv")
    
    # Fallback to master matrices if instance-specific ones don't exist
    if not os.path.isfile(distance_matrix_path) or not os.path.isfile(time_matrix_path):
        logging.warning(f"Instance-specific matrices not found for {instance_name}, using master matrices")
        distance_matrix_path = 'Master_DistanceMatrix.csv'
        time_matrix_path = 'Master_TimeMatrix.csv'
    
    distanceData = CSVreader.CSVreader(distance_matrix_path)
    timeData = CSVreader.CSVreader(time_matrix_path)
    citiesArcs = arcClass.cityArcs.createArcs(distanceData, timeData)
    
    return citiesArcs


def calculate_total_route_distance(route_order, cities_arcs):
    """Calculate total route distance from Origin to Destination using instance-specific matrices."""
    if len(route_order) < 2:
        return 0.0
    
    total_distance = 0.0
    driving_speed = 60.0  # km/h (from network.py)
    
    for i in range(len(route_order) - 1):
        from_location = route_order[i]
        to_location = route_order[i + 1]
        
        if from_location in cities_arcs:
            if to_location in cities_arcs[from_location].times:
                travel_time = float(cities_arcs[from_location].times[to_location])
                segment_distance = travel_time * driving_speed
                total_distance += segment_distance
            else:
                logging.warning("Time not found in cities_arcs for: %s -> %s", from_location, to_location)
        else:
            logging.warning("Location not found in cities_arcs: %s", from_location)
    
    return round(total_distance, 2)


def warn_missing_locations(instance_name, instance_path, cities_arcs):
    """Warn if instance locations are missing from the matrix."""
    instance_locations = get_instance_locations(instance_path)
    if not instance_locations:
        return
    missing = [loc for loc in instance_locations if loc not in cities_arcs]
    if missing:
        logging.warning(
            "Instance %s has %d locations missing from matrix: %s",
            instance_name,
            len(missing),
            missing,
        )
        print(
            f"WARNING: {instance_name} has {len(missing)} locations missing from matrix. "
            "Check that the correct Distance/Time matrices are used."
        )


def _count_nodes_by_type(nodes_dict):
    counts = Counter()
    for node_data in nodes_dict.values():
        node_type = node_data.get("nodeType", "Unknown")
        counts[node_type] += 1
    return counts


def _count_arcs_by_type(arcs_dict, nodes_dict):
    counts = Counter()
    for arc in arcs_dict.values():
        start_type = nodes_dict.get(arc.startNode, {}).get("nodeType", "Unknown")
        end_type = nodes_dict.get(arc.endNode, {}).get("nodeType", "Unknown")
        counts[f"{start_type}->{end_type}"] += 1
    return counts


def _count_para_arcs_by_transition(para_arcs):
    counts = Counter()
    for arc_key in para_arcs.keys():
        transition = arc_key[2] if len(arc_key) > 2 else "Unknown"
        counts[transition] += 1
    return counts


def collect_network_characteristics(instance_name, instance_path):
    """Build network and collect actual network characteristics (independent of parameters)."""
    # Load instance-specific matrices (same as enhanced_main.py)
    instance_cities_arcs = load_instance_matrices(instance_path)
    
    # Use default parameters to build network structure
    network.setGlobalParams(DEFAULT_CONSUMPTION, DEFAULT_DISTANCE_PER_CS, DEFAULT_BATTERY_CAP, DEFAULT_CP)

    start_time = time.time()
    test_network = network.Network(instance_path, instance_cities_arcs)
    build_time_seconds = time.time() - start_time

    # Get route order and customer count
    route_order, customers = get_route_order_and_customers(instance_path)
    num_customers = len(customers)
    num_origin_destination = 2  # Origin and Destination
    
    # Calculate total route distance using instance-specific matrices
    total_route_distance_km = calculate_total_route_distance(route_order, instance_cities_arcs)

    node_counts = _count_nodes_by_type(test_network.nodes)
    arc_counts = _count_arcs_by_type(test_network.arcs, test_network.nodes)
    para_counts = _count_para_arcs_by_transition(test_network.paraArcs)

    total_arcs = len(test_network.arcs) + len(test_network.paraArcs)

    return {
        "instance_name": instance_name,
        "instance_path": instance_path,
        "num_customers": num_customers,
        "num_origin_destination": num_origin_destination,
        "total_route_nodes": num_customers + num_origin_destination,  # Origin + Customers + Destination
        "total_route_distance_km": total_route_distance_km,
        "city_nodes": node_counts.get("City", 0),
        "cs_nodes": node_counts.get("CS", 0),
        "intermediate_nodes": node_counts.get("Intermediate", 0),
        "total_nodes": sum(node_counts.values()),
        "charging_station_pairs": len(test_network.chargingStations),
        "arcs_total": len(test_network.arcs),
        "para_arcs_total": len(test_network.paraArcs),
        "total_arcs": total_arcs,
        "arcs_city_to_cs": arc_counts.get("City->CS", 0),
        "arcs_cs_to_city": arc_counts.get("CS->City", 0),
        "arcs_cs_to_cs": arc_counts.get("CS->CS", 0),
        "arcs_city_to_city": arc_counts.get("City->City", 0),
        "arcs_other": sum(arc_counts.values()) - (
            arc_counts.get("City->CS", 0)
            + arc_counts.get("CS->City", 0)
            + arc_counts.get("CS->CS", 0)
            + arc_counts.get("City->City", 0)
        ),
        "para_arcs_start": para_counts.get("start", 0),
        "para_arcs_drive": para_counts.get("drive", 0),
        "para_arcs_break": para_counts.get("break", 0),
        "para_arcs_rest": para_counts.get("rest", 0),
        "para_arcs_visit": para_counts.get("visit", 0),
        "para_arcs_passingCS": para_counts.get("passingCS", 0),
        "para_arcs_other": sum(para_counts.values()) - (
            para_counts.get("start", 0)
            + para_counts.get("drive", 0)
            + para_counts.get("break", 0)
            + para_counts.get("rest", 0)
            + para_counts.get("visit", 0)
            + para_counts.get("passingCS", 0)
        ),
        "build_time_seconds": round(build_time_seconds, 6),
    }


def save_results(results, timestamp, filename_prefix):
    """Save results to a single CSV file."""
    results_dir = os.path.join("Results", "Network_Characteristics")
    os.makedirs(results_dir, exist_ok=True)

    csv_path = os.path.join(results_dir, f"{filename_prefix}_network_characteristics_{timestamp}.csv")
    if not results:
        print(f"No results to save for {filename_prefix}.")
        return

    headers = list(results[0].keys())
    with open(csv_path, "w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(results)

    print(f"Saved CSV: {csv_path}")


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.info("Starting network characteristics analysis at %s", timestamp)

    # Group 1: instances directory
    instances_root = os.path.join(script_dir, "instances")
    instances_tests = discover_instance_tests(instances_root)
    if SPECIFIC_INSTANCES_TO_RUN:
        instances_tests = [
            (name, path) for name, path in instances_tests if name in SPECIFIC_INSTANCES_TO_RUN
        ]

    results_instances = []
    for instance_name, instance_path in instances_tests:
        # Load master matrices for warning check (if needed)
        # But actual network building uses instance-specific matrices
        master_distance_data = CSVreader.CSVreader("Master_DistanceMatrix.csv")
        master_time_data = CSVreader.CSVreader("Master_TimeMatrix.csv")
        master_cities_arcs = arcClass.cityArcs.createArcs(master_distance_data, master_time_data)
        warn_missing_locations(instance_name, instance_path, master_cities_arcs)
        
        # One row per instance - no parameter loops
        # Uses instance-specific matrices internally
        row = collect_network_characteristics(
            instance_name,
            instance_path,
        )
        results_instances.append(row)

    save_results(results_instances, timestamp, "instances_folder")

    # Group 2: legacy testInstance1..12 in base directory
    legacy_tests = discover_legacy_test_instances(script_dir)
    if SPECIFIC_INSTANCES_TO_RUN:
        legacy_tests = [
            (name, path) for name, path in legacy_tests if name in SPECIFIC_INSTANCES_TO_RUN
        ]

    # For legacy instances, try to use legacy matrices if available, otherwise instance-specific
    if legacyDistanceMatrix and os.path.isfile(legacyDistanceMatrix) and os.path.isfile(legacyTimeMatrix):
        legacy_distance_data = CSVreader.CSVreader(legacyDistanceMatrix)
        legacy_time_data = CSVreader.CSVreader(legacyTimeMatrix)
        legacy_cities_arcs = arcClass.cityArcs.createArcs(legacy_distance_data, legacy_time_data)
    else:
        # Fallback: use master matrices for legacy instances
        master_distance_data = CSVreader.CSVreader("Master_DistanceMatrix.csv")
        master_time_data = CSVreader.CSVreader("Master_TimeMatrix.csv")
        legacy_cities_arcs = arcClass.cityArcs.createArcs(master_distance_data, master_time_data)

    results_legacy = []
    for instance_name, instance_path in legacy_tests:
        warn_missing_locations(instance_name, instance_path, legacy_cities_arcs)
        # For legacy instances, try instance-specific first, fallback to legacy/master
        # One row per instance - no parameter loops
        row = collect_network_characteristics(
            instance_name,
            instance_path,
        )
        results_legacy.append(row)

    save_results(results_legacy, timestamp, "legacy_testInstances")

    print("Network characteristics analysis completed.")


if __name__ == "__main__":
    main()