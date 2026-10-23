import arcClass, network, isFeasible, CSVreader, instanceResultClass
from optAlgo import algorithm
import pstats, cProfile
import logging
import os

# Configure logging to write to a file
logging.basicConfig(
    filename='debug_detailed.log',
    level=logging.DEBUG,
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Set the working directory to the script's location
script_dir = r"C:\Users\mostafm\OneDrive - NTNU\Desktop\MyFiles\TDSPEVRP\EVTDSPalgorithmmainEV03\EVTDSPalgorithmmain"
os.chdir(script_dir)
print("Working directory set to:", os.getcwd())


# Parameters
consumptionBest = 1.12
consumptionAverage = 1.49
consumptionWorst = 2.08
battery350 = 350 # kWh
battery500 = 500 # kWh
battery750 = 750 # kWh
battery1000 = 1000 #kWh


consumptionRates = [consumptionBest, consumptionAverage, consumptionWorst]
distancesPerCS = [40, 50, 60, 70, 80, 90, 100]
batteryCaps = [battery350, battery500, battery750,battery1000]
CPs = [350, 1000]

# Input files
distanceMatrix = 'DistanceMatrix.csv'
timeMatrix = 'TimeMatrix.csv'

# Load data using the integrated CSVreader
distanceData = CSVreader.CSVreader(distanceMatrix)
timeData = CSVreader.CSVreader(timeMatrix)
citiesArcs = arcClass.cityArcs.createArcs(distanceData, timeData)

# Create an empty results list that will store everything before writing to the file
all_results_list = []

# Debug function to check why labels are being rejected
def debug_label_feasibility(label):
    """Debug function to check why a label is being rejected"""
    logging.debug(f"=== DEBUGGING LABEL FEASIBILITY ===")
    logging.debug(f"Label path: {label.path}")
    logging.debug(f"Label detailed path: {label.detailedPath}")
    logging.debug(f"Label activities: {label.activityList}")
    logging.debug(f"Time: {label.time}")
    logging.debug(f"Time to next: {label.timeToNext}")
    logging.debug(f"Drive_R: {label.drive_R} (max: {network.maxTimeDrive_R})")
    logging.debug(f"Drive_B: {label.drive_B} (max: {network.maxTimeDrive_B})")
    logging.debug(f"Elapsed_R: {label.elapsed_R} (max: {network.maxElapsed_R})")
    logging.debug(f"Elapsed_B: {label.elapsed_B} (max: {network.maxElapsed_B})")
    logging.debug(f"Required RT: {label.reqRT} (battery capacity: {network.batteryCapacity})")
    logging.debug(f"Done: {label.done}")
    
    # Check each feasibility condition
    conditions = [
        ("drive_R <= maxTimeDrive_R", label.drive_R <= network.maxTimeDrive_R),
        ("drive_R >= 0", label.drive_R >= 0),
        ("drive_B <= maxTimeDrive_B", label.drive_B <= network.maxTimeDrive_B),
        ("drive_B >= 0", label.drive_B >= 0),
        ("elapsed_R <= maxElapsed_R", label.elapsed_R <= network.maxElapsed_R),
        ("elapsed_R >= 0", label.elapsed_R >= 0),
        ("elapsed_B <= maxElapsed_B", label.elapsed_B <= network.maxElapsed_B),
        ("elapsed_B >= 0", label.elapsed_B >= 0),
        ("done == False", not label.done),
        ("reqRT <= batteryCapacity", label.reqRT <= network.batteryCapacity),
        ("reqRT >= 0", label.reqRT >= 0)
    ]
    
    for condition_name, condition_result in conditions:
        logging.debug(f"  {condition_name}: {condition_result}")
        if not condition_result:
            logging.debug(f"    *** FAILED: {condition_name} ***")
    
    return isFeasible.isFeasible(label)

# Modified algorithm with debugging
def debug_algorithm(network):
    import label, isFeasible, dominate, heapq, time
    
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

    # Initialise the first label with the depot using current battery capacity
    startLabel = label.Label(network._getDepot(), batteryCapacity=network.batteryCap)
    heapq.heappush(U, (startLabel.time, startLabel))
    labelCounter += 1
    
    logging.info(f"Starting algorithm with depot: {network._getDepot()}")
    logging.info(f"Total city nodes: {network._getCityNodesCount()}")
    logging.info(f"City nodes: {network._getCityNodes()}")

    while U and (time.time() - startTime) <= maxRuntime:
        # Pop the label with the lowest time from U
        _, L = heapq.heappop(U)
        currentNode = L.detailedPath[-1]
        currentNodeArcs = {arc: data for arc, data in networkArcs.items() if currentNode == arc[0] and currentNode != arc[1]}

        logging.debug(f"Processing label at node {currentNode}, path: {L.path}")
        
        for arc, arcData in currentNodeArcs.items():
            startNode, endNode, transitionType = arc
            if currentNode == startNode and currentNode != endNode:
                # Create a copy of L using the custom copy method
                newL = L.custom_copy()
                # Invoke the relevant REF and update the path of newL
                network.invoke_REF(newL, startNode, endNode, transitionType)
                
                logging.debug(f"  Created new label for transition {transitionType} to {endNode}")
                
                # Check feasibility with debugging
                if debug_label_feasibility(newL):
                    # Add newL to unprocessed labels U
                    heapq.heappush(U, (newL.time, newL))
                    # Update label 
                    labelCounter += 1
                    logging.debug(f"    *** LABEL ACCEPTED ***")
                else:
                    logging.debug(f"    *** LABEL REJECTED ***")
        
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
    return P, labelCounter, dominatedCounter

# Main execution
for i in [12]:  # Specify the instances directly
    print(f"Solving scenarios for Instance {i}...")
    for CP in CPs:  # Iterate over each charging power
        for batteryCap in batteryCaps:  # Iterate over each battery capacity
            for consumption in consumptionRates:  # Iterate over each alpha
                for distancePerCS in distancesPerCS:  # Iterate over each distance per CS
                    # Reset results_list for each combination of i, alpha, and distancePerCS
                    results_list = []
                    
                    logging.info(f"=== STARTING NEW SCENARIO ===")
                    logging.info(f"Instance: {i}, CP: {CP}, Battery: {batteryCap}, Consumption: {consumption}, CS Distance: {distancePerCS}")
                    
                    # Set the global parameters before building the network
                    network.setGlobalParams(consumption, distancePerCS, batteryCap, CP)
                    isFeasible.setGlobalParams(batteryCap)
                    
                    # Build and parse the network with the current parameters
                    testingInstanceFilename = f'testInstance{i}.txt'
                    testNetwork = network.Network(testingInstanceFilename, citiesArcs)
                    testNetwork.parse()
                    
                    logging.info(f"Network built with {testNetwork._getCityNodesCount()} city nodes")
                    logging.info(f"Number of charging stations: {testNetwork.numberCS()}")

                    nCityNodes = testNetwork._getCityNodesCount()
                    cityNodesList = testNetwork._getCityNodes()

                    # Initialize variables for tracking best label and time
                    bestLabel = None
                    bestTime = float('inf')

                    with cProfile.Profile() as profile:
                        labelingAlgo, labelsGenerated, labelsDominated = debug_algorithm(testNetwork)

                        for l in labelingAlgo:
                            if all(city in l.path for city in cityNodesList):
                                if l.time < bestTime:
                                    bestLabel = l
                                    bestTime = l.time

                        if bestLabel is None:
                            print(f"No valid label found for {testingInstanceFilename} with consumption: {consumption} and CS Interval: {distancePerCS} km")
                            logging.warning(f"No valid label found for {testingInstanceFilename}")
                            # Create a placeholder result with 'infinity' for bestTime and None for bestLabel
                            bestTime = float('inf')
                            bestLabel = 'No valid path'
                        else:
                            logging.info(f"Best label found with time: {bestTime}")
                            logging.info(f"Best path: {bestLabel.path}")

                        results = pstats.Stats(profile)
                        total_calls = results.total_calls
                        total_time = results.total_tt

                    # Prepare the result for this specific instance
                    result = instanceResultClass.InstanceResult(
                        instanceName=testingInstanceFilename,
                        distancePerCS=distancePerCS,
                        batteryCap=batteryCap,
                        chargingPower=CP,
                        maxRT= batteryCap / CP,
                        consumption=consumption,
                        bestLabel=bestLabel,
                        bestTime=bestTime,
                        labelsGenerated=labelsGenerated,
                        labelsDominated=labelsDominated,
                        profilingStats=f"Total Calls: {total_calls}, Total Time: {total_time:.6f} seconds",
                        totalTime=total_time
                    )
                    results_list.append(result)
                    
                    # Add to the global results list
                    all_results_list.extend(results_list)

print("Debug run completed. Check debug_detailed.log for detailed information.") 