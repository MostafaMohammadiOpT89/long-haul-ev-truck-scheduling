import arcClass, network, isFeasible, CSVreader
from instanceResultClass import EnhancedInstanceResult
from optAlgo import algorithm
import pstats, cProfile
import logging
import os
import json
import csv
from datetime import datetime

# Configure logging to write to a file with reduced verbosity
logging.basicConfig(
    filename='enhanced_results.log',
    level=logging.INFO,  # Changed from DEBUG to INFO to reduce log size
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Set the working directory to the script's location
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
print("Working directory set to:", os.getcwd())

# Parameters
consumptionBest = 1.12
consumptionAverage = 1.49
consumptionWorst = 2.08
battery750 = 750 # kWh
battery1000 = 1000 #kWh

# # Configuration: Energy consumption scenarios (kWh/km)
# consumptionRates = [consumptionBest, consumptionAverage, consumptionWorst]
# # Configuration: Inter-CS spacing (km)
# distancesPerCS = [40, 50, 60, 70, 80, 90, 100]
# # Configuration: Battery capacities (kWh) - baseline 750 kWh
# batteryCaps = [battery750, battery1000]
# # Configuration: Charging power (kW) - [350 (today), 500 (≈1 yr), 1000 (≈2 yrs)]
# CPs = [350, 500, 1000]


# Configuration: Energy consumption scenarios (kWh/km)
consumptionRates = [consumptionAverage]
# Configuration: Inter-CS spacing (km)
distancesPerCS = [60]
# Configuration: Battery capacities (kWh) - baseline 750 kWh
batteryCaps = [battery750]
# Configuration: Charging power (kW) - [350 (today), 500 (≈1 yr), 1000 (≈2 yrs)]
CPs = [350]

# Configuration: Specific instances to run (for debugging)
# Leave empty list [] to run all discovered instances
# Or specify instance names to run only those (e.g., ['long_cl1_cu2', 'med_cl2_cu3_Balanced'])
# Instance names should match the folder names in the instances directory
#SPECIFIC_INSTANCES_TO_RUN = ['short_cl3_cu12_Balanced', 'short_cl2_cu2_Balanced','long_cl3_cu12_Unbalanced','long_cl2_cu3_Unbalanced','med_cl3_cu4_Balanced']  # Empty = run all, or specify names like: ['long_cl1_cu2', 'short_cl1_cu2']
SPECIFIC_INSTANCES_TO_RUN = ["short_cl1_cu2","short_cl3_cu5_Balanced", "short_cl2_cu2_Unbalanced", "short_cl2_cu2_Balanced","long_cl3_cu4_Unbalanced"]

# Create an empty results list that will store everything before writing to the file
all_results_list = []

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

def discover_instance_tests(instances_root):
    """Discover instance test files under the given root directory.
    
    Returns a list of tuples: (instance_name, instance_file_path)
    where instance_name is typically the folder name and instance_file_path
    is the absolute path to the .txt file inside that folder.
    """
    discovered = []
    if not os.path.isdir(instances_root):
        logging.warning(f"Instances root does not exist or is not a directory: {instances_root}")
        return discovered
    
    for entry in os.listdir(instances_root):
        entry_path = os.path.join(instances_root, entry)
        if os.path.isdir(entry_path):
            txt_candidates = [f for f in os.listdir(entry_path) if f.lower().endswith('.txt')]
            if not txt_candidates:
                logging.warning(f"No .txt file found in instance folder: {entry_path}")
                continue
            # Prefer a .txt that matches the folder name, otherwise take the first one
            preferred = None
            for f in txt_candidates:
                name_no_ext, _ = os.path.splitext(f)
                if name_no_ext.lower() == entry.lower():
                    preferred = f
                    break
            instance_txt = preferred if preferred is not None else txt_candidates[0]
            instance_file_path = os.path.join(entry_path, instance_txt)
            discovered.append((entry, instance_file_path))
    # Also allow loose .txt files directly under instances root (optional)
    loose_txt = [f for f in os.listdir(instances_root) if f.lower().endswith('.txt')]
    for f in loose_txt:
        instance_name = os.path.splitext(f)[0]
        instance_file_path = os.path.join(instances_root, f)
        discovered.append((instance_name, instance_file_path))
    
    return discovered

def get_route_info(instance_path, cities_arcs):
    """Get route distance and customer count for an instance."""
    route_order = []
    customers = []
    try:
        with open(instance_path, 'r') as file:
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
                    if len(row) >= 2:
                        route_order.append(row[1])  # Origin
                    is_first_vehicle_row = False
                elif section == "nodes":
                    if len(row) >= 2:
                        location = row[1]
                        route_order.append(location)
                        if location.startswith("Cust"):
                            customers.append(location)
    except Exception:
        return 0.0, 0
    
    # Calculate total distance
    total_distance = 0.0
    driving_speed = 60.0  # km/h
    for i in range(len(route_order) - 1):
        from_location = route_order[i]
        to_location = route_order[i + 1]
        if from_location in cities_arcs and to_location in cities_arcs[from_location].times:
            travel_time = float(cities_arcs[from_location].times[to_location])
            total_distance += travel_time * driving_speed
    
    return round(total_distance, 2), len(customers)

def run_algorithm_with_profiling(network):
    """Run the algorithm with profiling and return results"""
    import label, isFeasible, dominate, heapq, time
    from collections import Counter
    
    # Initialise the parameterfree arcs
    networkArcs = network.paraArcs
    
    # Initialise lists unprocessed U (as a heap) and processed P
    U = []
    P = []

    # Initialise counters
    dominatedCounter = 0
    labelCounter = 0
    infeasibleReasons = Counter()
    maxRuntime = 3000*60 # 30 minutes in seconds
    startTime = time.time()

    # Initialise the first label with the depot using current battery capacity
    startLabel = label.Label(network._getDepot(), batteryCapacity=network.batteryCap)
    heapq.heappush(U, (startLabel.time, startLabel))
    labelCounter += 1
    
    logging.info(f"Starting algorithm with depot: {network._getDepot()}")
    logging.info(f"Total city nodes: {network._getCityNodesCount()}")

    while U and (time.time() - startTime) <= maxRuntime:
        # Pop the label with the lowest time from U
        _, L = heapq.heappop(U)
        currentNode = L.detailedPath[-1]
        currentNodeArcs = {arc: data for arc, data in networkArcs.items() if currentNode == arc[0] and currentNode != arc[1]}
        
        for arc, arcData in currentNodeArcs.items():
            startNode, endNode, transitionType = arc
            if currentNode == startNode and currentNode != endNode:
                # Create a copy of L using the custom copy method
                newL = L.custom_copy()
                # Invoke the relevant REF and update the path of newL
                network.invoke_REF(newL, startNode, endNode, transitionType)
                
                # Check feasibility with reasons
                feasible, reasons = isFeasible.check_feasibility(newL)
                if feasible:
                    # Add newL to unprocessed labels U
                    heapq.heappush(U, (newL.time, newL))
                    # Update label counter
                    labelCounter += 1
                else:
                    for reason in reasons:
                        infeasibleReasons[reason] += 1
        
        # Mark L as done and add to processed labels P
        L.done = True
        P.append(L)

        # Dominance step
        if U:
            labels_only = [label for _, label in U]  # Extract Label instances from the heap
            dominated_indices = dominate.dominate(labels_only)
            # Update dominated counter
            dominatedCounter += len(dominated_indices)
            # Remove dominated labels from U and add them to P
            U = [(time, label) for i, (time, label) in enumerate(U) if i not in dominated_indices]
            for i in dominated_indices:
                P.append(labels_only[i])
            heapq.heapify(U)

    logging.info(f"Algorithm finished. Labels generated: {labelCounter}, Labels dominated: {dominatedCounter}")
    if infeasibleReasons:
        logging.info(f"Infeasibility reasons: {dict(infeasibleReasons)}")
    return P, labelCounter, dominatedCounter, infeasibleReasons

def save_results_to_files(all_results, timestamp):
    """Save results to both JSON and CSV formats"""
    
    # Create Results directory if it doesn't exist
    results_dir = 'Results'
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
        print(f"Created Results directory: {results_dir}")
    
    # Save to JSON with full details
    json_filename = os.path.join(results_dir, f'enhanced_results_{timestamp}.json')
    with open(json_filename, 'w') as json_file:
        json_data = {
            'metadata': {
                'timestamp': timestamp,
                'total_scenarios': len(all_results),
                'parameters': {
                    'consumption_rates': consumptionRates,
                    'distances_per_cs': distancesPerCS,
                    'battery_capacities': batteryCaps,
                    'charging_powers': CPs
                }
            },
            'results': [result.to_dict() for result in all_results]
        }
        json.dump(json_data, json_file, indent=2)
    
    # Save to CSV for easy analysis
    csv_filename = os.path.join(results_dir, f'enhanced_results_{timestamp}.csv')
    with open(csv_filename, 'w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(EnhancedInstanceResult.get_csv_headers())
        for result in all_results:
            writer.writerow(result.to_csv_row())
    
    print(f"Results saved to {json_filename} and {csv_filename}")
    logging.info(f"Results saved to {json_filename} and {csv_filename}")

def main():
    """Main execution function"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.info(f"Starting enhanced analysis at {timestamp}")
    
    # Discover test instances under instances directory
    instances_root = os.path.join(script_dir, 'instances')
    discovered_tests = discover_instance_tests(instances_root)
    if not discovered_tests:
        print(f"No test instances found under: {instances_root}")
        logging.warning(f"No test instances found under: {instances_root}")
        return
    
    # Filter instances if specific instances are requested
    if SPECIFIC_INSTANCES_TO_RUN:
        # Filter to only run specified instances
        filtered_tests = [(name, path) for name, path in discovered_tests if name in SPECIFIC_INSTANCES_TO_RUN]
        if not filtered_tests:
            print(f"WARNING: None of the specified instances were found: {SPECIFIC_INSTANCES_TO_RUN}")
            print(f"Available instances: {[name for name, _ in discovered_tests]}")
            logging.warning(f"None of the specified instances found: {SPECIFIC_INSTANCES_TO_RUN}")
            return
        discovered_tests = filtered_tests
        print(f"Running specific instances: {[name for name, _ in discovered_tests]}")
        logging.info(f"Running specific instances: {[name for name, _ in discovered_tests]}")
    else:
        print(f"Running all discovered instances: {len(discovered_tests)} instances")
        logging.info(f"Running all discovered instances: {len(discovered_tests)} instances")
    
    for instance_name, instance_path in discovered_tests:
        # Load instance-specific matrices
        instance_citiesArcs = load_instance_matrices(instance_path)
        
        # Print route info using instance-specific matrices
        route_distance, num_customers = get_route_info(instance_path, instance_citiesArcs)
        print(f"Instance {instance_name}: Total distance = {route_distance} km, Customers = {num_customers}")
        print(f"Solving scenarios for Instance {instance_name}...")
        logging.info(f"Starting Instance {instance_name} at {instance_path} (Distance: {route_distance} km, Customers: {num_customers})")
        
        for CP in CPs:  # Iterate over each charging power
            for batteryCap in batteryCaps:  # Iterate over each battery capacity
                for consumption in consumptionRates:  # Iterate over each alpha
                    for distancePerCS in distancesPerCS:  # Iterate over each distance per CS
                        
                        logging.info(f"Processing: Instance {instance_name}, CP: {CP}, Battery: {batteryCap}, Consumption: {consumption}, CS Distance: {distancePerCS}")
                        
                        # Set the global parameters before building the network
                        network.setGlobalParams(consumption, distancePerCS, batteryCap, CP)
                        isFeasible.setGlobalParams(batteryCap)
                        
                        # Build and parse the network with the current parameters using instance-specific matrices
                        testingInstanceFilename = instance_path
                        testNetwork = network.Network(testingInstanceFilename, instance_citiesArcs)
                        testNetwork.parse()
                        
                        nCityNodes = testNetwork._getCityNodesCount()
                        cityNodesList = testNetwork._getCityNodes()

                        # Initialize variables for tracking best label and time
                        bestLabel = None
                        bestTime = float('inf')

                        with cProfile.Profile() as profile:
                            labelingAlgo, labelsGenerated, labelsDominated, infeasibleReasons = run_algorithm_with_profiling(testNetwork)

                            for l in labelingAlgo:
                                if all(city in l.path for city in cityNodesList):
                                    if l.time < bestTime:
                                        bestLabel = l
                                        bestTime = l.time

                            if bestLabel is None:
                                print(f"No valid label found for {testingInstanceFilename} with consumption: {consumption} and CS Interval: {distancePerCS} km")
                                logging.warning(f"No valid label found for {testingInstanceFilename}")
                                if infeasibleReasons:
                                    top_reasons = sorted(infeasibleReasons.items(), key=lambda x: x[1], reverse=True)[:5]
                                    print(f"Top infeasibility reasons: {top_reasons}")
                                    logging.warning(f"Top infeasibility reasons: {top_reasons}")
                                # Create a placeholder result with 'infinity' for bestTime and None for bestLabel
                                bestTime = float('inf')
                                bestLabel = 'No valid path'
                            else:
                                logging.info(f"Best label found with time: {bestTime}")

                            results = pstats.Stats(profile)
                            total_calls = results.total_calls
                            total_time = results.total_tt

                        # Create enhanced result object
                        result = EnhancedInstanceResult(
                            instanceName=instance_name,
                            distancePerCS=distancePerCS,
                            batteryCap=batteryCap,
                            chargingPower=CP,
                            maxRT=batteryCap / CP,
                            consumption=consumption,
                            bestLabel=bestLabel,
                            bestTime=bestTime,
                            labelsGenerated=labelsGenerated,
                            labelsDominated=labelsDominated,
                            profilingStats=f"Total Calls: {total_calls}, Total Time: {total_time:.6f} seconds",
                            totalTime=total_time,
                            cityNodesCount=nCityNodes
                        )
                        
                        all_results_list.append(result)
                        
                        # Print progress
                        print(f"  Completed: Instance {instance_name}, CP: {CP}, Battery: {batteryCap}, Consumption: {consumption}, CS Distance: {distancePerCS}")
    
    # Save all results
    save_results_to_files(all_results_list, timestamp)
    
    # Print summary
    total_scenarios = len(all_results_list)
    feasible_scenarios = sum(1 for r in all_results_list if r.feasible)
    print(f"\nAnalysis completed!")
    print(f"Total scenarios tested: {total_scenarios}")
    print(f"Feasible scenarios: {feasible_scenarios}")
    print(f"Infeasible scenarios: {total_scenarios - feasible_scenarios}")
    print(f"Results saved with timestamp: {timestamp}")

if __name__ == "__main__":
    main() 