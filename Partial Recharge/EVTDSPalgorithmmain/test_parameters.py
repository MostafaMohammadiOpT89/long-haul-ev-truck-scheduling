import arcClass, network, isFeasible, CSVreader, instanceResultClass
from optAlgo import algorithm
import pstats, cProfile
import logging
import os

# Configure logging
logging.basicConfig(
    filename='parameter_test.log',
    level=logging.INFO,
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Set the working directory
script_dir = r"C:\Users\mostafm\OneDrive - NTNU\Desktop\MyFiles\TDSPEVRP\EVTDSPalgorithmmainEV03\EVTDSPalgorithmmain"
os.chdir(script_dir)

# Input files
distanceMatrix = 'DistanceMatrix.csv'
timeMatrix = 'TimeMatrix.csv'

# Load data
distanceData = CSVreader.CSVreader(distanceMatrix)
timeData = CSVreader.CSVreader(timeMatrix)
citiesArcs = arcClass.cityArcs.createArcs(distanceData, timeData)

# Test different parameter combinations
test_combinations = [
    # (consumption, distancePerCS, batteryCap, CP, instance_file)
    (1.12, 40, 350, 350, 'testInstance11_simple.txt'),  # Simple 10-city instance
    (1.12, 40, 500, 500, 'testInstance11_fixed.txt'),   # 15-city with larger battery
    (1.12, 30, 500, 500, 'testInstance11_fixed.txt'),   # 15-city with closer CS
    (1.12, 50, 750, 750, 'testInstance11_fixed.txt'),   # 15-city with much larger battery
    (0.8, 40, 500, 500, 'testInstance11_fixed.txt'),    # 15-city with lower consumption
]

def test_combination(consumption, distancePerCS, batteryCap, CP, instance_file):
    """Test a specific parameter combination"""
    logging.info(f"=== TESTING: {instance_file} ===")
    logging.info(f"Consumption: {consumption}, CS Distance: {distancePerCS}, Battery: {batteryCap}, CP: {CP}")
    
    # Set global parameters
    network.setGlobalParams(consumption, distancePerCS, batteryCap, CP)
    isFeasible.setGlobalParams(batteryCap)
    
    # Build network
    testNetwork = network.Network(instance_file, citiesArcs)
    testNetwork.parse()
    
    logging.info(f"Network built with {testNetwork._getCityNodesCount()} city nodes")
    logging.info(f"Number of charging stations: {testNetwork.numberCS()}")
    
    # Run algorithm
    labelingAlgo, labelsGenerated, labelsDominated = algorithm(testNetwork)
    
    # Check for valid solution
    nCityNodes = testNetwork._getCityNodesCount()
    cityNodesList = testNetwork._getCityNodes()
    
    bestLabel = None
    bestTime = float('inf')
    
    for l in labelingAlgo:
        if all(city in l.path for city in cityNodesList):
            if l.time_min < bestTime:
                bestLabel = l
                bestTime = l.time_min
    
    if bestLabel is None:
        logging.warning(f"NO VALID SOLUTION FOUND")
        logging.warning(f"Labels generated: {labelsGenerated}, Labels dominated: {labelsDominated}")
        
        # Check what cities were visited in the best labels
        best_labels = sorted(labelingAlgo, key=lambda x: len(x.path), reverse=True)[:5]
        for i, label in enumerate(best_labels):
            logging.info(f"Best label {i+1}: visited {len(label.path)} cities: {label.path}")
            logging.info(f"  Time: {label.time_min}, Activities: {label.activityList[-5:] if label.activityList else 'None'}")
    else:
        logging.info(f"SOLUTION FOUND!")
        logging.info(f"Best time: {bestTime}")
        logging.info(f"Best path: {bestLabel.path}")
        logging.info(f"Labels generated: {labelsGenerated}, Labels dominated: {labelsDominated}")
    
    return bestLabel is not None

# Run all tests
for consumption, distancePerCS, batteryCap, CP, instance_file in test_combinations:
    success = test_combination(consumption, distancePerCS, batteryCap, CP, instance_file)
    print(f"Test {instance_file}: {'SUCCESS' if success else 'FAILED'}")
    print()

print("All tests completed. Check parameter_test.log for details.") 