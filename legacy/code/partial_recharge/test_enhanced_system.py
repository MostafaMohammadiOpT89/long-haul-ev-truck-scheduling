import arcClass, network, isFeasible, CSVreader
from instanceResultClass import EnhancedInstanceResult
import pstats, cProfile
import logging
import os
import json
import csv
from datetime import datetime

# Configure logging
logging.basicConfig(
    filename='test_enhanced.log',
    level=logging.INFO,
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Set the working directory
script_dir = r"C:\Users\mostafm\OneDrive - NTNU\Desktop\MyFiles\TDSPEVRP\EVTDSPalgorithmmainEV03\EVTDSPalgorithmmain"
os.chdir(script_dir)

def run_algorithm_with_profiling(network):
    """Run the algorithm with profiling and return results"""
    import label, isFeasible, dominate, heapq, time
    import network as _netmod
    
    # Initialise the parameterfree arcs
    networkArcs = network.paraArcs
    
    # Initialise lists unprocessed U (as a heap) and processed P
    U = []
    P = []

    # Initialise counters
    dominatedCounter = 0
    labelCounter = 0
    maxRuntime = 30*60 # 30 minutes in seconds
    startTime = time.time()

    # Initialise the first label with the depot
    startLabel = label.Label(network._getDepot(), batteryCapacity=network.batteryCap)
    heapq.heappush(U, (startLabel.time_min, startLabel))
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
                
                # Check feasibility
                if isFeasible.isFeasible(newL):
                    # Add newL to unprocessed labels U
                    heapq.heappush(U, (newL.time_min, newL))
                    # Update label counter
                    labelCounter += 1
        
        # Mark L as done and add to processed labels P
        L.done = True
        P.append(L)

        # Dominance step
        if U:
            labels_only = [label for _, label in U]  # Extract Label instances from the heap
            dominated_indices = dominate.dominate(labels_only, cp=_netmod.CP)
            # Update dominated counter
            dominatedCounter += len(dominated_indices)
            # Remove dominated labels from U and add them to P
            U = [(time, label) for i, (time, label) in enumerate(U) if i not in dominated_indices]
            for i in dominated_indices:
                P.append(labels_only[i])
            heapq.heapify(U)

    logging.info(f"Algorithm finished. Labels generated: {labelCounter}, Labels dominated: {dominatedCounter}")
    return P, labelCounter, dominatedCounter

def test_enhanced_system():
    """Test the enhanced system with a small subset of parameters"""
    
    # Load data
    distanceMatrix = 'DistanceMatrix.csv'
    timeMatrix = 'TimeMatrix.csv'
    distanceData = CSVreader.CSVreader(distanceMatrix)
    timeData = CSVreader.CSVreader(timeMatrix)
    citiesArcs = arcClass.cityArcs.createArcs(distanceData, timeData)
    
    # Test with a small subset of parameters
    test_instances = [1]  # Only test instances 1 and 2
    test_CPs = [350]  # Only test one charging power
    test_batteryCaps = [350]  # Test two battery capacities
    test_consumptionRates = [1.12]  # Only test one consumption rate
    test_distancesPerCS = [50]  # Test two CS intervals
    
    all_results_list = []
    
    print("Testing enhanced system with small parameter subset...")
    
    for i in test_instances:
        print(f"Testing Instance {i}...")
        
        for CP in test_CPs:
            for batteryCap in test_batteryCaps:
                for consumption in test_consumptionRates:
                    for distancePerCS in test_distancesPerCS:
                        
                        print(f"  Testing: Instance {i}, CP: {CP}, Battery: {batteryCap}, Consumption: {consumption}, CS Distance: {distancePerCS}")
                        
                        # Set the global parameters
                        network.setGlobalParams(consumption, distancePerCS, batteryCap, CP)
                        isFeasible.setGlobalParams(batteryCap)
                        
                        # Build and parse the network
                        testingInstanceFilename = f'testInstance{i}.txt'
                        testNetwork = network.Network(testingInstanceFilename, citiesArcs)
                        testNetwork.parse()
                        
                        nCityNodes = testNetwork._getCityNodesCount()
                        cityNodesList = testNetwork._getCityNodes()

                        # Initialize variables for tracking best label and time
                        bestLabel = None
                        bestTime = float('inf')

                        with cProfile.Profile() as profile:
                            labelingAlgo, labelsGenerated, labelsDominated = run_algorithm_with_profiling(testNetwork)

                            for l in labelingAlgo:
                                if all(city in l.path for city in cityNodesList):
                                    if l.time_min < bestTime:
                                        bestLabel = l
                                        bestTime = l.time_min

                            if bestLabel is None:
                                print(f"    No valid label found")
                                bestTime = float('inf')
                                bestLabel = 'No valid path'
                            else:
                                print(f"    Best label found with time: {bestTime:.1f} minutes")

                            results = pstats.Stats(profile)
                            total_calls = results.total_calls
                            total_time = results.total_tt

                        # Create enhanced result object
                        result = EnhancedInstanceResult(
                            instanceName=testingInstanceFilename,
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
                            cityNodesCount=nCityNodes,
                            synchronization_enabled=False
                        )
                        
                        all_results_list.append(result)
                        
                        # Test the result object
                        print(f"    Feasible: {result.feasible}")
                        print(f"    CS stops: {result.number_of_cs_stops}")
                        print(f"    Rest breaks: {result.number_of_rest_breaks}")
                        print(f"    Sync efficiency: {result.synchronization_efficiency_score:.1f}%")
                        print(f"    Activity timeline entries: {len(result.activity_timeline)}")
    
    # Save test results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create Results directory if it doesn't exist
    results_dir = 'Results'
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
        print(f"Created Results directory: {results_dir}")
    
    # Save to JSON
    json_filename = os.path.join(results_dir, f'test_enhanced_results_{timestamp}.json')
    with open(json_filename, 'w') as json_file:
        json_data = {
            'metadata': {
                'timestamp': timestamp,
                'total_scenarios': len(all_results_list),
                'test_parameters': {
                    'instances': test_instances,
                    'charging_powers': test_CPs,
                    'battery_capacities': test_batteryCaps,
                    'consumption_rates': test_consumptionRates,
                    'cs_intervals': test_distancesPerCS
                }
            },
            'results': [result.to_dict() for result in all_results_list]
        }
        json.dump(json_data, json_file, indent=2)
    
    # Save to CSV
    csv_filename = os.path.join(results_dir, f'test_enhanced_results_{timestamp}.csv')
    with open(csv_filename, 'w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(EnhancedInstanceResult.get_csv_headers())
        for result in all_results_list:
            writer.writerow(result.to_csv_row())
    
    print(f"\nTest completed!")
    print(f"Total scenarios tested: {len(all_results_list)}")
    feasible_scenarios = sum(1 for r in all_results_list if r.feasible)
    print(f"Feasible scenarios: {feasible_scenarios}")
    print(f"Results saved to {json_filename} and {csv_filename}")
    
    # Test post-analysis utilities
    print("\nTesting post-analysis utilities...")
    try:
        from post_analysis_utils import PostAnalysisUtils
        analyzer = PostAnalysisUtils(json_filename)
        
        # Test basic analysis
        analyzer.get_feasibility_summary()
        analyzer.analyze_synchronization_metrics()
        
        print("Post-analysis utilities working correctly!")
        
    except ImportError as e:
        print(f"Post-analysis utilities not available: {e}")
    
    return all_results_list

if __name__ == "__main__":
    test_enhanced_system() 