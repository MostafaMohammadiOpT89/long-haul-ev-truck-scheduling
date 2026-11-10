import arcClass, network, isFeasible, CSVreader, instanceResultClass
from optAlgo import algorithm
import pstats, cProfile
import logging
import os


# import logging

# Configure logging to write to a file
logging.basicConfig(
    filename='debug.log',  # Log file name
    level=logging.INFO,    # Log level (INFO will capture messages from logging.info())
    filemode='w',          # Overwrite the log file each time (use 'a' to append)
    format='%(asctime)s - %(levelname)s - %(message)s'  # Add timestamps and levels to logs
)
# Set the working directory to the script's location
script_dir = r"C:\Users\mostafm\OneDrive - NTNU\Desktop\MyFiles\TDSPEVRP\EVTDSPalgorithmmainEV03\EVTDSPalgorithmmain"
os.chdir(script_dir)
print("Working directory set to:", os.getcwd())  # Debugging: Print current working directory


# Parameters
consumptionBest = 1.12
consumptionAverage = 1.49
consumptionWorst = 2.08
battery350 = 350 # kWh
battery500 = 500 # kWh
battery750 = 750 # kWh
battery1000 = 1000 #kWh


# consumptionRates = [consumptionBest, consumptionAverage, consumptionWorst]
# distancesPerCS = [40, 50, 60, 70, 80, 90, 100]
# batteryCaps = [battery350, battery500, battery750]
# CPs = [350, 1000]

consumptionRates = [1.12]
distancesPerCS = [40]
batteryCaps = [350]
CPs = [350]




# Input files
distanceMatrix = 'DistanceMatrix.csv'
timeMatrix = 'TimeMatrix.csv'
# testingInstanceFilename = f'testInstance{instanceNumber}.txt'

# Load data using the integrated CSVreader
distanceData = CSVreader.CSVreader(distanceMatrix)
timeData = CSVreader.CSVreader(timeMatrix)
citiesArcs = arcClass.cityArcs.createArcs(distanceData, timeData)


# Create an empty results list that will store everything before writing to the file
all_results_list = []



#for i in range(1,11):  # Iterate over test instances
for i in [11]:  # Specify the instances directly
    print(f"Solving scenarios for Instance {i}...")
    for CP in CPs:  # Iterate over each charging power
        for batteryCap in batteryCaps:  # Iterate over each battery capacity
            for consumption in consumptionRates:  # Iterate over each alpha
                for distancePerCS in distancesPerCS:  # Iterate over each distance per CS
                    # Reset results_list for each combination of i, alpha, and distancePerCS
                    results_list = []
                    
                    # Set the global parameters before building the network
                    network.setGlobalParams(consumption, distancePerCS, batteryCap, CP)
                    isFeasible.setGlobalParams(batteryCap)
                    
                    # Build and parse the network with the current parameters
                    testingInstanceFilename = f'testInstance{i}.txt'
                    testNetwork = network.Network(testingInstanceFilename, citiesArcs)
                    testNetwork.parse()
                    
                    #print(f"Solving {testingInstanceFilename} for CS Interval: {distancePerCS} km and Alpha: {alpha}...")

                    nCityNodes = testNetwork._getCityNodesCount()
                    cityNodesList = testNetwork._getCityNodes()

                    # Initialize variables for tracking best label and time
                    bestLabel = None
                    bestTime = float('inf')

                    with cProfile.Profile() as profile:
                        labelingAlgo, labelsGenerated, labelsDominated = algorithm(testNetwork)

                        for l in labelingAlgo:
                            if all(city in l.path for city in cityNodesList):
                                if l.time_min < bestTime:
                                    bestLabel = l
                                    bestTime = l.time_min

                        if bestLabel is None:
                            print(f"No valid label found for {testingInstanceFilename} with consumption: {consumption} and CS Interval: {distancePerCS} km")
                            # Create a placeholder result with 'infinity' for bestTime and None for bestLabel
                            bestTime = float('inf')
                            bestLabel = 'No valid path'

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


import csv

# Define the CSV output file name
output_csv_file = "results.csv"

# Prepare the results for CSV
csv_headers = [
    "Instance Information", "CSI (Distance per CS)", "BC (Battery Capacity)",
    "CP (Charging Capacity)", "CR (Consumption Rate)", "BT (Best Time)",
    "RT (Running Time)", "LG (Labels Generated)", "LD (Labels Dominated)"
]

# Collect rows for the CSV
csv_rows = []
for result in all_results_list:
    csv_rows.append([
        result.instanceName,
        result.distancePerCS,
        result.batteryCap,
        result.chargingPower,
        result.consumption,
        result.bestTime,
        result.totalTime,
        result.labelsGenerated,
        result.labelsDominated
    ])

# Write the rows to the CSV file
with open(output_csv_file, mode="w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(csv_headers)  # Write headers
    writer.writerows(csv_rows)   # Write data rows

print(f"Results saved to {output_csv_file}")
