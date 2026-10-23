import csv, math, re
from itertools import combinations

# Parameters
driving_speed = 60 # km/h
maxElapsed_R = 13
maxElapsed_B = 6
maxTimeDrive_B = 4.5
maxTimeDrive_R = 9
minTimeBreak = 0.75
minTimeRest = 11
timeDay = 24
velocity = 60 # km/h


CP = None
distance_per_cs = None
consumption = None
batteryCapacity = None
# Hours of fixed "visit" time at a CS before the charging REF (0 = only charging time counts).
cs_service_time = 0.0

def setGlobalParams(consumptionRate, distPerCS, batteryCap, chargingPower, cs_service_time_hours=0.0):
    global consumption
    global distance_per_cs
    global batteryCapacity
    global CP
    global cs_service_time
    consumption = consumptionRate
    distance_per_cs = distPerCS
    batteryCapacity = batteryCap
    CP = chargingPower
    cs_service_time = cs_service_time_hours


# Helper function to extract numbers and parts for sorting
def natural_sort_key(key):
	return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', key)]

class Arc:
	def __init__(self, startNode, endNode, travelTime):
		self.startNode = startNode
		self.endNode = endNode
		self.travelTime = travelTime


class Network:
	def __init__(self, filepath, cityArcs):
		self.filepath = filepath
		self.cityArcs = cityArcs
		self.nodes = {}  # To store node data, including the depot
		self.chargingStations = {}
		# Capture current global battery capacity for this network instance
		self.batteryCap = batteryCapacity
		
		self.parse()
		self._generateCS()
		self.arcs = self._generateArcs()
		self._generateIntermediateNodes()
		self.paraArcs = self._generateParaArcs()


	def parse(self):
		with open(self.filepath, 'r') as file:
			reader = csv.reader(file)
			section = None
			isFirstVehicleRow = True

			for row in reader:
				if not row:  # Skip empty lines
					continue

				if row[0].startswith('VehicleId'):
					section = 'vehicles'
					continue
				elif row[0].startswith('NodeId'):
					section = 'nodes'
					continue

				if section == 'vehicles' and isFirstVehicleRow:
					self._parseDepotRow(row)
					isFirstVehicleRow = False
				elif section == 'nodes':
					self._parseNodeRow(row)

	def _parseDepotRow(self, row):
		vehicle_id, location, location_id = row
		self.nodes[vehicle_id] = {
			'location': location,
			'locationId': int(location_id),
			'timeWindowStart': 0,
			'timeWindowEnd': float('inf'),
			'serviceTime': 0.0,
			'nodeType': 'City'
		}

	def _parseNodeRow(self, row):
		node_id, location, location_id, start, end, _, _, _, serviceTime = row
		self.nodes[node_id] = {
			'location': location,
			'locationId': int(location_id),
			'timeWindowStart': int(start),
			'timeWindowEnd': int(end),
			'serviceTime': float(serviceTime),
			'nodeType': 'City'
		}

	def _generateCS(self):
		self.chargingStations = {}
		# Sort the nodes by their keys to ensure proper consecutive pairing
		sorted_nodes = sorted(self.nodes.keys(), key=natural_sort_key)

		# Pair consecutive nodes using zip
		for startNode, endNode in zip(sorted_nodes, sorted_nodes[1:]):
			startNodeData = self.nodes[startNode]
			endNodeData = self.nodes[endNode]

			startCity = startNodeData['location']
			endCity = endNodeData['location']

			if startCity in self.cityArcs:
				startArc = self.cityArcs[startCity]
				if endCity in startArc.times:
					# Convert time to float
					time = float(startArc.times[endCity])

					total_dist = time * driving_speed
					cs_nodes = []

					if total_dist > distance_per_cs:
						num_cs = math.floor(total_dist / distance_per_cs)
					else:
						num_cs = 1 # Ensure at least one CS is created even if the distance is less than distance_per_cs
					
					for i in range(num_cs):

						cs_location_id = f"CS_{startNodeData['locationId']}_{endNodeData['locationId']}_{i}"
						cs_node_id = f"CS_{startNode}_{endNode}_{i}"
						self.nodes[cs_node_id] = {
							'location': f'Charging Station {i} between {startCity} and {endCity}',
							'locationId': cs_location_id,
							'timeWindowStart': 0,
							'timeWindowEnd': float('inf'),
							'serviceTime': cs_service_time,
							'nodeType': 'CS',
							'startNode': startNode,
							'endNode': endNode,
							'iterator': i
						}

						cs_nodes.append(cs_node_id)

					node_pair = (startNode, endNode)
					self.chargingStations[node_pair] = cs_nodes		

	def _generateArcs(self):
		arcs = {}
		processed_pairs = set()

		# Sort the nodes by their keys to ensure proper consecutive pairing
		sorted_nodes = sorted(self.nodes.keys(), key=natural_sort_key)

		# Pair consecutive nodes using zip
		for startNode, endNode in zip(sorted_nodes, sorted_nodes[1:]):
			startNodeData = self.nodes[startNode]
			endNodeData = self.nodes[endNode]

			startCity = startNodeData['location']
			endCity = endNodeData['location']

			if startCity in self.cityArcs:
				startArc = self.cityArcs[startCity]
				if endCity in startArc.times:
					# Convert time to float
					time = float(startArc.times[endCity])

					node_pair = tuple(sorted([startNode, endNode], key=lambda x: int(x)))
					if node_pair in processed_pairs:
						continue

					if node_pair in self.chargingStations:
						cs_nodes = self.chargingStations[node_pair]
						total_dist = time * driving_speed
						
						num_cs = len(cs_nodes)
						if num_cs == 1:
							# Special case: single charging station
							cs = cs_nodes[0]
							half_dist = total_dist / 2
							half_time = half_dist / driving_speed
							arcs[(startNode, cs)] = Arc(startNode, cs, half_time)
							arcs[(cs, endNode)] = Arc(cs, endNode, half_time)
						else:
							# Create arcs ONLY through charging stations
							for i, cs in enumerate(cs_nodes):
								# Arc from start city to first charging station
								if i == 0:
									segment_dist = distance_per_cs * (i + 1)
									cumulative_time = segment_dist / driving_speed
									arcs[(startNode, cs)] = Arc(startNode, cs, cumulative_time)

								# Arcs between consecutive charging stations
								if i > 0:
									prev_cs = cs_nodes[i - 1]
									segment_dist = distance_per_cs
									cumulative_time = segment_dist / driving_speed
									arcs[(prev_cs, cs)] = Arc(prev_cs, cs, cumulative_time)

								# Arc from last charging station to end city
								if i == num_cs - 1:
									remaining_dist = total_dist - (distance_per_cs * num_cs)
									cumulative_time = remaining_dist / driving_speed
									arcs[(cs, endNode)] = Arc(cs, endNode, cumulative_time)

					# Mark this pair as processed
					processed_pairs.add(node_pair)

		return arcs



	# def _generateArcs(self):
	# 	arcs = {}
	# 	processed_pairs = set()

	# 	# Sort the nodes by their keys to ensure proper consecutive pairing
	# 	sorted_nodes = sorted(self.nodes.keys(), key=natural_sort_key)
	# 	#print(sorted_nodes)

	# 	# Pair consecutive nodes using zip
	# 	for startNode, endNode in zip(sorted_nodes, sorted_nodes[1:]):
	# 		startNodeData = self.nodes[startNode]
	# 		endNodeData = self.nodes[endNode]

	# 		startCity = startNodeData['location']
	# 		endCity = endNodeData['location']

	# 		if startCity in self.cityArcs:
	# 			startArc = self.cityArcs[startCity]
	# 			if endCity in startArc.times:
	# 				# Convert time to float
	# 				time = float(startArc.times[endCity])

	# 				node_pair = tuple(sorted([startNode, endNode]))
	# 				if node_pair in processed_pairs:
	# 					continue

	# 				# Add a direct arc from start to end node
	# 				arcs[(startNode, endNode)] = Arc(startNode, endNode, time)

	# 				if node_pair in self.chargingStations:
	# 					cs_nodes = self.chargingStations[node_pair]
	# 					total_dist = time * driving_speed
	# 					num_cs = len(cs_nodes)

	# 					if num_cs == 1:
	# 						# Special case: single charging station
	# 						cs = cs_nodes[0]
	# 						half_dist = total_dist / 2
	# 						half_time = half_dist / driving_speed
	# 						arcs[(startNode, cs)] = Arc(startNode, cs, half_time)
	# 						arcs[(cs, endNode)] = Arc(cs, endNode, half_time)
	# 					else:
	# 						# Create arcs from start city to all CS nodes
	# 						for i, cs in enumerate(cs_nodes):
	# 							segment_dist = distance_per_cs * (i + 1)
	# 							cumulative_time = segment_dist / driving_speed
	# 							arcs[(startNode, cs)] = Arc(startNode, cs, cumulative_time)

	# 						# Create arcs between all CS nodes
	# 						for cs1, cs2 in combinations(cs_nodes, 2):
	# 							segment_dist = distance_per_cs * abs(cs_nodes.index(cs2) - cs_nodes.index(cs1))
	# 							cumulative_time = segment_dist / driving_speed
	# 							arcs[(cs1, cs2)] = Arc(cs1, cs2, cumulative_time)

	# 						# Create arcs from CS nodes to end city
	# 						for i, cs in enumerate(cs_nodes):
	# 							remaining_dist = total_dist - (distance_per_cs * (i + 1))
	# 							if remaining_dist >= 0:
	# 								arcs[(cs, endNode)] = Arc(cs, endNode, remaining_dist / driving_speed)
	# 							else:
	# 								# Handle case where remaining distance is less than distance_per_cs
	# 								cumulative_time = (total_dist - (distance_per_cs * i)) / driving_speed
	# 								arcs[(cs, endNode)] = Arc(cs, endNode, cumulative_time)

	# 					# Mark this pair as processed
	# 					processed_pairs.add(node_pair)

	# 	return arcs


	def _generateIntermediateNodes(self):
		# Generate intermediate nodes for each arc
		for (startNode, endNode) in self.arcs.keys():

			# Generate 'fit' and 'dull' intermediate nodes for each arc
			fit_node_id = f"fit_{startNode}_{endNode}"
			dull_node_id = f"dull_{startNode}_{endNode}"
				
			self.nodes[fit_node_id] = {
				'location': f"Fit node between {self.nodes[startNode]['location']} and {self.nodes[endNode]['location']}",
				'nodeType': 'Intermediate',
				'state': 'fit',
				'startNode': startNode,
				'endNode': endNode
			}

			self.nodes[dull_node_id] = {
				'location': f"Dull node between {self.nodes[startNode]['location']} and {self.nodes[endNode]['location']}",
				'nodeType': 'Intermediate',
				'state': 'dull',
				'startNode': startNode,
				'endNode': endNode
			}




	def _generateParaArcs(self):
		paraArcs = {}

		# Step 1: Create arcs from original nodes to their respective intermediate nodes
		for node_id, node_data in self.nodes.items():
			if node_data['nodeType'] == 'Intermediate':
				original_start, original_end = node_data['startNode'], node_data['endNode']
				state = node_data['state']

				# Determine REF based on node type
				start_node_data = self.nodes.get(original_start)
				# From CS
				if start_node_data and start_node_data['nodeType'] == 'CS':
					start_ref = self._fcharge_cs
				# From normal node
				else:
					start_ref = self._fstart_nm if start_node_data else None

				if start_ref:
					# Link start to its intermediate node
					paraArcs[(original_start, node_id, 'start')] = {'REF': start_ref}

					# Link fit and dull intermediate nodes
					if state == 'fit':
						opposite_node_id = f"dull_{original_start}_{original_end}"
						paraArcs[(node_id, opposite_node_id, 'drive')] = {'REF': self._fdrive_delta}  # Fit to Dull transition
					elif state == 'dull':
						opposite_node_id = f"fit_{original_start}_{original_end}"
						paraArcs[(node_id, opposite_node_id, 'break')] = {'REF': self._fbreak_delta}  # Dull to Fit, break transition
						paraArcs[(node_id, opposite_node_id, 'rest')] = {'REF': self._frest_delta}  # Dull to Fit, rest transition

					# Link intermediate to corresponding end node
					paraArcs[(node_id, original_end, 'visit')] = {'REF': self._fvisit_nm}

		# Step 2: Add skipping arcs for charging stations
		for node_id, node_data in self.nodes.items():
			if node_data['nodeType'] == 'Intermediate':
				original_end = node_data['endNode']

				# Check if the next node (original_end) is a CS
				if self.nodes[original_end]['nodeType'] == 'CS':
					# Iterate over all nodes to find fit and dull nodes after the charging station
					fit_after_cs = None
					dull_after_cs = None

					for potential_node_id, potential_node_data in self.nodes.items():
						if potential_node_data['nodeType'] == 'Intermediate':
							# Match nodes with original_end as their startNode
							if potential_node_data['startNode'] == original_end:
								if potential_node_data['state'] == 'fit':
									fit_after_cs = potential_node_id
								elif potential_node_data['state'] == 'dull':
									dull_after_cs = potential_node_id

					# Add arc from fit before CS to fit after CS
					if node_data['state'] == 'fit' and fit_after_cs:
						paraArcs[(node_id, fit_after_cs, 'passingCS')] = {'REF': self._fpassby_start}
						#paraArcs[(node_id, dull_after_cs, 'passingCS')] = {'REF': self._fpassby_start}
					# Add arc from dull before CS to dull after CS
					if node_data['state'] == 'dull' and dull_after_cs:
						paraArcs[(node_id, dull_after_cs, 'passingCS')] = {'REF': self._fpassby_start}
						paraArcs[(node_id, fit_after_cs, 'passingCS')] = {'REF': self._fpassby_start}


		return paraArcs




#2
	# def _generateParaArcs(self):
	# 	paraArcs = {}

	# 	# Create arcs from original nodes to their respective intermediate nodes
	# 	for node_id, node_data in self.nodes.items():
	# 		if node_data['nodeType'] == 'Intermediate':
	# 			original_start, original_end = node_data['startNode'], node_data['endNode']
	# 			state = node_data['state']

	# 			# Determine REF based on node type
	# 			start_node_data = self.nodes.get(original_start)
	# 			# From CS
	# 			if start_node_data and start_node_data['nodeType'] == 'CS':
	# 				start_ref = self._fcharge_cs
	# 			# From normal node
	# 			else:
	# 				start_ref = self._fstart_nm if start_node_data else None

	# 			if start_ref:
	# 				# Link start to its intermediate node
	# 				paraArcs[(original_start, node_id, 'start')] = {'REF': start_ref}

	# 				# Link fit and dull intermediate nodes
	# 				if state == 'fit':
	# 					opposite_node_id = f"dull_{original_start}_{original_end}"
	# 					paraArcs[(node_id, opposite_node_id, 'drive')] = {'REF': self._fdrive_delta}  # Fit to Dull transition
	# 				elif state == 'dull':
	# 					opposite_node_id = f"fit_{original_start}_{original_end}"
	# 					paraArcs[(node_id, opposite_node_id, 'break')] = {'REF': self._fbreak_delta}  # Dull to Fit, break transition
	# 					paraArcs[(node_id, opposite_node_id, 'rest')] = {'REF': self._frest_delta}  # Dull to Fit, rest transition

	# 				# Link intermediate to corresponding end node
	# 				paraArcs[(node_id, original_end, 'visit')] = {'REF': self._fvisit_nm}

	# 				# Additional logic: Add arcs for skipping charging stations
	# 				if self.nodes[original_end]['nodeType'] == 'CS':
	# 					# Identify the fit and dull nodes after the charging station
	# 					fit_after_cs = f"fit_{original_end}_{node_data['endNode']}"
	# 					dull_after_cs = f"dull_{original_end}_{node_data['endNode']}"

	# 					# Add arc from fit before CS to fit after CS
	# 					if state == 'fit':
	# 						paraArcs[(node_id, fit_after_cs, 'drive')] = {'REF': self._fdrive_delta}
	# 					# Add arc from dull before CS to dull after CS
	# 					elif state == 'dull':
	# 						paraArcs[(node_id, dull_after_cs, 'drive')] = {'REF': self._fdrive_delta}

	# 	return paraArcs








#1
	# def _generateParaArcs(self):
	# 	paraArcs = {}

	# 	# Create arcs from original nodes to their respective intermediate nodes
	# 	for node_id, node_data in self.nodes.items():
	# 		if node_data['nodeType'] == 'Intermediate':
	# 			original_start, original_end = node_data['startNode'], node_data['endNode']
	# 			state = node_data['state']

	# 			# Determine REF based on node type
	# 			start_node_data = self.nodes.get(original_start)
	# 			# From CS
	# 			if start_node_data and start_node_data['nodeType'] == 'CS':
	# 				start_ref = self._fcharge_cs
	# 			# From normal node
	# 			else:
	# 				start_ref = self._fstart_nm if start_node_data else None

	# 			if start_ref:
	# 				# Link start to its intermediate node
	# 				paraArcs[(original_start, node_id, 'start')] = {'REF': start_ref}

	# 				# Link fit and dull intermediate nodes
	# 				if state == 'fit':
	# 					opposite_node_id = f"dull_{original_start}_{original_end}"
	# 					paraArcs[(node_id, opposite_node_id, 'drive')] = {'REF': self._fdrive_delta}  # Fit to Dull transition
	# 				elif state == 'dull':
	# 					opposite_node_id = f"fit_{original_start}_{original_end}"
	# 					paraArcs[(node_id, opposite_node_id, 'break')] = {'REF': self._fbreak_delta}  # Dull to Fit, break transition
	# 					paraArcs[(node_id, opposite_node_id, 'rest')] = {'REF': self._frest_delta}  # Dull to Fit, rest transition

	# 				# Link intermediate to corresponding end node
	# 				paraArcs[(node_id, original_end, 'visit')] = {'REF': self._fvisit_nm}



	# 	return paraArcs

	def _getDepot(self):
		return (next(iter(self.nodes.keys())))
	
	def _getNodes(self):
		return self.nodes.keys()
	
	def _getCityNodesCount(self):
		return sum(1 for node_data in self.nodes.values() if node_data.get('nodeType') == 'City')
	
	def _getCityNodes(self):
		return [node_id for node_id, node_data in self.nodes.items() if node_data.get('nodeType') == 'City']

	def delta_l(self, label, maxTimeDrive_R, maxTimeDrive_B, timeDay, minTimeRest):
		# Ensure all attributes and parameters are numeric
		numeric_attributes = [label.timeToNext, label.drive_R, label.elapsed_R, maxTimeDrive_R, maxTimeDrive_B, timeDay, minTimeRest]
		
		if all(isinstance(attr, (int, float)) for attr in numeric_attributes):
			# Proceed with calculations
			return min(
				label.timeToNext, 
				maxTimeDrive_R - label.drive_R, 
				maxTimeDrive_B - label.drive_B, 
				timeDay - (label.elapsed_R + minTimeRest),
				maxElapsed_B - label.elapsed_B
			)
		else:
			raise ValueError("All attributes and parameters must be numeric.")

	# Define REF methods here
	def _fstart_nm(self, label, startNode, endNode): 
		endNodeData = self.nodes.get(endNode)
		realEndNode = endNodeData['endNode']
		time_nm = self.arcs[(startNode, realEndNode)].travelTime		
	
		label.timeToNext = time_nm
		# Ensure H (full-charge time) is set once charging power is known
		# H = batteryCapacity / CP (in hours); CP is global in this module
		if getattr(label, 'H', 0.0) == 0.0 and CP:
			label.H = label.batteryCapacity / CP
		
		# Check if this is depot start or customer-to-customer
		#startNodeData = self.nodes.get(startNode)
		is_depot_start = startNode == self._getDepot()
		# if is_depot_start:
		# 	# Initialize line segments for depot start
		# 	label.time_min = label.time_min
		# 	label.time_max = label.time_max
		# 	label.remainingBattery_min = label.batteryCapacity
		# 	label.remainingBattery_max = label.batteryCapacity
		# 	label.reqRT_min = 0.0
		# 	label.reqRT_max = 0.0
		# else:
		# 	# Customer-to-customer: preserve existing line segments
		# 	# Only update time bounds if needed
		# 	label.time_min = label.time_min
		# 	label.time_max = label.time_max	
	
	def _fpassby_start(self,label, startNode, endNode):
		endNodeData=self.nodes.get(endNode)
		realEndNode = endNodeData['endNode']
		startNodeData=self.nodes.get(startNode)
		realStartNode_afterpassing = startNodeData['endNode']
		time_CSM=self.arcs[(realStartNode_afterpassing, realEndNode)].travelTime

		label.timeToNext=time_CSM




	def _fdrive_delta(self, label, delta_l):
		label.time_min += delta_l
		label.time_max += delta_l
		label.timeToNext -= delta_l
		label.drive_B += delta_l
		label.drive_R += delta_l
		label.elapsed_R += delta_l
		label.elapsed_B += delta_l
		label.latest_B = min(label.latest_B, label.latest_R + maxElapsed_R - label.elapsed_B - delta_l)
		label.reqRT_min += delta_l * consumption * velocity # alpha
		label.reqRT_max += delta_l * consumption * velocity # alpha
		label.remainingBattery_min -= delta_l * consumption * velocity # Decrease battery level
		label.remainingBattery_max -= delta_l * consumption * velocity # Decrease battery level
		
		label.activityList.append(f'drive: {delta_l}')

	def _fbreak_delta(self, label, startNode, endNode):
		label.time_min += minTimeBreak
		label.time_max += minTimeBreak
		label.drive_B = 0
		label.elapsed_R += minTimeBreak
		label.elapsed_B = 0
		label.latest_B = float('inf')

		label.activityList.append(f'break: {minTimeBreak}')

	def _frest_delta(self, label, startNode, endNode):
		label.time_min += minTimeRest
		label.time_max += minTimeRest
		label.drive_R = 0
		label.drive_B = 0
		label.elapsed_R = 0
		label.elapsed_B = 0
		label.latest_R = float('inf')
		label.latest_B = float('inf')

		label.activityList.append(f'rest: {minTimeRest}')

	def _fvisit_nm(self, label, endNode):
		t_min_m, t_max_m, serviceTime_m = self.nodes[endNode]['timeWindowStart'], self.nodes[endNode]['timeWindowEnd'], self.nodes[endNode]['serviceTime']
		# Compute waiting before updating times
		arrival_before_min = label.time_min
		arrival_before_max = label.time_max
		wait_min = max(0.0, t_min_m - arrival_before_min)
		wait_max = max(0.0, t_min_m - arrival_before_max)
		label.time_min = max(label.time_min, t_min_m) + serviceTime_m
		label.time_max = max(label.time_max, t_min_m) + serviceTime_m
		#label.time += serviceTime_m
		label.elapsed_R = max(label.elapsed_R, t_min_m - label.latest_R) + serviceTime_m
		#label.elapsed_R += serviceTime_m
		label.elapsed_B = max(label.elapsed_B, t_min_m - label.latest_B) + serviceTime_m
		#label.elapsed_B += serviceTime_m
		label.latest_R = min(label.latest_R, t_max_m + serviceTime_m - label.elapsed_R)
		label.latest_B = min(label.latest_B, t_max_m + serviceTime_m - label.elapsed_B)
		label.path.append(endNode)
		label.timeToNext = 0
		
		# Log wait and service separately for analysis
		if wait_min > 0:
			label.activityList.append(f'wait@{endNode}: {wait_min}')
		label.activityList.append(f'service@{endNode}: {serviceTime_m}')
	# def _fvisit_nm(self, label, endNode):
	# 	# Time window and nominal service time
	# 	t_min_m = self.nodes[endNode]['timeWindowStart']
	# 	t_max_m = self.nodes[endNode]['timeWindowEnd']
	# 	serviceTime_m = self.nodes[endNode]['serviceTime']

	# 	# For CS nodes, do not add fixed service time (charging is handled in _fcharge_cs)
	# 	node_type = self.nodes[endNode].get('nodeType')
	# 	serviceTime_effective = serviceTime_m if node_type != 'CS' else 0.0

	# 	# Compute waiting before updating times
	# 	arrival_before_min = label.time_min
	# 	arrival_before_max = label.time_max
	# 	wait_min = max(0.0, t_min_m - arrival_before_min)
	# 	wait_max = max(0.0, t_min_m - arrival_before_max)

	# 	label.time_min = max(label.time_min, t_min_m) + serviceTime_effective
	# 	label.time_max = max(label.time_max, t_min_m) + serviceTime_effective

	# 	label.elapsed_R = max(label.elapsed_R, t_min_m - label.latest_R) + serviceTime_effective
	# 	label.elapsed_B = max(label.elapsed_B, t_min_m - label.latest_B) + serviceTime_effective
	# 	label.latest_R = min(label.latest_R, t_max_m + serviceTime_effective - label.elapsed_R)
	# 	label.latest_B = min(label.latest_B, t_max_m + serviceTime_effective - label.elapsed_B)

	# 	label.path.append(endNode)
	# 	label.timeToNext = 0

	# 	# Log wait and service separately for analysis
	# 	if wait_min > 0:
	# 		label.activityList.append(f'wait@{endNode}: {wait_min}')
	# 		if hasattr(label, "soc_timeline"):
	# 			label.soc_timeline.append({
	# 				"remainingBattery_min": label.remainingBattery_min,
	# 				"remainingBattery_max": label.remainingBattery_max,
	# 			})

	# 	# Only log service if it actually consumes time (i.e., non-CS nodes)
	# 	if serviceTime_effective > 0:
	# 		label.activityList.append(f'service@{endNode}: {serviceTime_effective}')
	# 		if hasattr(label, "soc_timeline"):
	# 			label.soc_timeline.append({
	# 				"remainingBattery_min": label.remainingBattery_min,
	# 				"remainingBattery_max": label.remainingBattery_max,
	# 			})
				
	def _fcharge_cs(self, label, startNode, endNode):
		endNodeData = self.nodes.get(endNode)
		realEndNode = endNodeData['endNode']
		time_nm = self.arcs[(startNode, realEndNode)].travelTime
		tempTime_min = label.time_min
		tempTime_max = label.time_max

		# Helper: compute charging needed to reach certain targets
		def time_to_full_from(energy_level):
			return max(0.0, (label.batteryCapacity - energy_level) / CP) if CP else 0.0

		def time_to_zero_from(energy_level):
			return max(0.0, -energy_level / CP) if CP else 0.0

		def time_to_break_hours(drive_b, elapsed_b):
			return max(0.0, min(maxTimeDrive_B - drive_b, maxElapsed_B - elapsed_b))

		def time_to_rest_hours(drive_r, elapsed_r):
			return max(0.0, min(maxTimeDrive_R - drive_r, timeDay - (elapsed_r + minTimeRest)))

		# Snapshot arrival state for post-analysis
		arrival_time_min = label.time_min
		arrival_time_max = label.time_max
		arrival_rb_min = label.remainingBattery_min
		arrival_rb_max = label.remainingBattery_max
		arrival_reqRT_min = label.reqRT_min
		arrival_reqRT_max = label.reqRT_max
		arrival_time_to_break_minutes = time_to_break_hours(label.drive_B, label.elapsed_B) * 60.0
		arrival_time_to_rest_minutes = time_to_rest_hours(label.drive_R, label.elapsed_R) * 60.0
		full_time_needed_min = time_to_full_from(arrival_rb_min)
		full_time_needed_max = time_to_full_from(arrival_rb_max)

		# Case 1: Synchronized with rest (elapsed_R == 0 after rest, or CS service-only tick if cs_service_time > 0)
		def _rest_sync_elapsed_r(er):
			if er == 0:
				return True
			return cs_service_time > 0 and abs(er - cs_service_time) < 1e-9

		if _rest_sync_elapsed_r(label.elapsed_R):
			sync_tag = "rest_sync"
			# Fully recharge within synchronization window; no extra time accounted here
			label.remainingBattery_min = label.batteryCapacity
			label.remainingBattery_max = label.batteryCapacity
			label.reqRT_min = 0.0
			label.reqRT_max = 0.0
			# times unchanged (+= 0)
			added_time_min = 0.0
			added_time_max = 0.0
			sync_window_type = "rest"
			sync_window_hours = float(minTimeRest)
		# Case 2: At a break start (drive_B == 0)
		elif label.drive_B == 0:
			full_time_min = time_to_full_from(label.remainingBattery_min)
			full_time_max = time_to_full_from(label.remainingBattery_max)
#			if full_time_min >= minTimeBreak or full_time_max >= minTimeBreak:
			if full_time_min >= minTimeBreak:
				# Charging uses the whole break window (synchronized part),
				# but still needs extra time beyond the break (unsynchronized part).
				# Mark this as a partially break-synchronized charging event.
				if full_time_min > 0:
					sync_fraction_break = min(1.0, minTimeBreak / full_time_min)
				else:
					sync_fraction_break = 1.0
				# We encode both the type and the synchronized fraction in the tag;
				# post-processing will parse "break_partial_sync|<fraction>".
				sync_tag = f"break_partial_sync|{sync_fraction_break:.6f}"
				# Can at least use the break duration to charge
				energy_gained = CP * minTimeBreak 
				label.remainingBattery_min += energy_gained
				# If still negative, add time to reach zero SOC for min branch
				added_time_to_zero_min = 0.0
				if label.remainingBattery_min < 0:
					added_time_to_zero_min = time_to_zero_from(label.remainingBattery_min)
					label.remainingBattery_min = 0.0
					print(f"Reached critical point - Battery min: {label.remainingBattery_min}, Added time to zero: {added_time_to_zero_min}")
					raise RuntimeError("Reached critical point - stopping after print")
				# Max branch: aim for full recharge.
				# In Model A (physically realized interval), time_max must include only
				# the extra charging beyond the already-accounted break window.
				added_time_min = max(0.0, added_time_to_zero_min - minTimeBreak) if added_time_to_zero_min > minTimeBreak else 0.0
				added_time_max = max(0.0, full_time_max - minTimeBreak)
				label.remainingBattery_max = label.batteryCapacity
				# reqRT based on remainingBattery sign (energy deficit to zero)
				label.reqRT_min = max(0.0, label.batteryCapacity - label.remainingBattery_min)
				label.reqRT_max = 0.0
				#print(f"Reached critical point - Battery min: {label.remainingBattery_min}")
				#raise RuntimeError("Reached critical point - stopping after print")
				sync_window_type = "break"
				sync_window_hours = float(minTimeBreak)
			else:
				# Full recharge is entirely within the break window: synchronized with break
				sync_tag = "break_sync"
				# Full recharge is within the break window: behave like synchronized case
				label.remainingBattery_min = label.batteryCapacity
				label.remainingBattery_max = label.batteryCapacity
				label.reqRT_min = 0.0
				label.reqRT_max = 0.0
				added_time_min = 0.0
				added_time_max = 0.0
				sync_window_type = "break"
				sync_window_hours = float(minTimeBreak)
		# Case 3: Not synchronized and not at a break start
		else:
			sync_tag = "unsync"
			# Check min branch; if negative, add time to reach zero
			if label.remainingBattery_min < 0:
				added_time_to_zero_min = time_to_zero_from(label.remainingBattery_min)
				label.remainingBattery_min = 0.0
				added_time_min = added_time_to_zero_min
				raise RuntimeError("Reached critical point - stopping after print")
				# Max branch: fully recharge
				added_time_max = time_to_full_from(label.remainingBattery_max)
				label.remainingBattery_max = label.batteryCapacity
				label.reqRT_min = max(0.0, label.batteryCapacity - label.remainingBattery_min)
				label.reqRT_max = 0.0
			# FIXED
			else:
				# Min branch: unsynchronized charging costs actual time (same as full recharge)
				added_time_min = time_to_full_from(label.remainingBattery_min)
				label.remainingBattery_min = label.batteryCapacity
				label.reqRT_min = 0.0
				# Max branch: same
				added_time_max = time_to_full_from(label.remainingBattery_max)
				label.remainingBattery_max = label.batteryCapacity
				label.reqRT_max = 0.0
			# else:
			# 	# Battery min positive; keep as-is, no extra time for min
			# 	added_time_min = 0.0
			# 	# Max branch goes to full
			# 	added_time_max = time_to_full_from(label.remainingBattery_max)
			# 	label.remainingBattery_max = label.batteryCapacity
			# 	# reqRT remains based on deficit to zero for min (which is zero if positive)
			# 	label.reqRT_min = max(0.0, label.batteryCapacity - label.remainingBattery_min)
			# 	label.reqRT_max = 0.0
			sync_window_type = None
			sync_window_hours = 0.0

		# Apply time updates and downstream effects
		label.time_min += added_time_min
		label.time_max += added_time_max
		label.timeToNext = time_nm
		# HoS clocks: min branch uses the same increment as time_min (here == added_time_min
		# because time_min is not modified elsewhere in this routine before this block).
		elapsed_delta_min = added_time_min
		elapsed_delta_max = added_time_max  # reserved for a future max-branch HoS treatment
		label.elapsed_R = 0 if _rest_sync_elapsed_r(label.elapsed_R) else label.elapsed_R + elapsed_delta_min
		label.elapsed_B = (
			0 if (cs_service_time > 0 and abs(label.elapsed_B - cs_service_time) < 1e-9)
			else label.elapsed_B + elapsed_delta_min
		)

		# Log the charging activity with explicit synchronization tag so that
		# post-processing can distinguish rest-sync, break-sync, and unsynchronized charges
		label.activityList.append(f'charge[{sync_tag}]: {elapsed_delta_min}')

		# Snapshot departure state and write a structured charge event
		departure_rb_min = label.remainingBattery_min
		departure_rb_max = label.remainingBattery_max
		departure_reqRT_min = label.reqRT_min
		departure_reqRT_max = label.reqRT_max
		departure_time_min = label.time_min
		departure_time_max = label.time_max
		departure_time_to_break_minutes = time_to_break_hours(label.drive_B, label.elapsed_B) * 60.0
		departure_time_to_rest_minutes = time_to_rest_hours(label.drive_R, label.elapsed_R) * 60.0
		arrival_time_interval_minutes = max(0.0, (arrival_time_max - arrival_time_min) * 60.0)
		departure_time_interval_minutes = max(0.0, (departure_time_max - departure_time_min) * 60.0)
		# Diagnostic requested by user: if remaining time-to-break/rest is below interval spread,
		# flag that prior full recharge is unlikely to be consistent with the interval state.
		prev_full_unlikely_by_break = arrival_time_to_break_minutes < arrival_time_interval_minutes
		prev_full_unlikely_by_rest = arrival_time_to_rest_minutes < arrival_time_interval_minutes
		prev_full_unlikely = prev_full_unlikely_by_break or prev_full_unlikely_by_rest

		energy_charged_min_kWh = departure_rb_min - arrival_rb_min
		energy_charged_max_kWh = departure_rb_max - arrival_rb_max

		# How much extra time would be required to fully recharge, even after using the sync window?
		# This is NOT necessarily added to the route time in the current model; it is diagnostic.
		extra_needed_to_full_min_hours = max(0.0, full_time_needed_min - sync_window_hours)
		extra_needed_to_full_max_hours = max(0.0, full_time_needed_max - sync_window_hours)

		if hasattr(label, "charge_events"):
			label.charge_events.append({
				"cs_node": startNode,
				"sync_tag": sync_tag.split("|", 1)[0],
				"sync_tag_raw": sync_tag,
				"sync_fraction_break": sync_fraction_break if "sync_fraction_break" in locals() else None,
				"sync_window_type": sync_window_type,
				"sync_window_minutes": sync_window_hours * 60.0,
				"extra_charge_time_min_minutes": added_time_min * 60.0,
				"extra_charge_time_max_minutes": added_time_max * 60.0,
				"full_time_needed_min_minutes": full_time_needed_min * 60.0,
				"full_time_needed_max_minutes": full_time_needed_max * 60.0,
				"extra_needed_to_full_min_minutes": extra_needed_to_full_min_hours * 60.0,
				"extra_needed_to_full_max_minutes": extra_needed_to_full_max_hours * 60.0,
				"arrival_soc_min_kWh": arrival_rb_min,
				"arrival_soc_max_kWh": arrival_rb_max,
				"departure_soc_min_kWh": departure_rb_min,
				"departure_soc_max_kWh": departure_rb_max,
				"energy_charged_min_kWh": energy_charged_min_kWh,
				"energy_charged_max_kWh": energy_charged_max_kWh,
				"arrival_reqRT_min": arrival_reqRT_min,
				"arrival_reqRT_max": arrival_reqRT_max,
				"departure_reqRT_min": departure_reqRT_min,
				"departure_reqRT_max": departure_reqRT_max,
				"arrival_time_min_hours": arrival_time_min,
				"arrival_time_max_hours": arrival_time_max,
				"departure_time_min_hours": departure_time_min,
				"departure_time_max_hours": departure_time_max,
				"arrival_time_interval_minutes": arrival_time_interval_minutes,
				"departure_time_interval_minutes": departure_time_interval_minutes,
				"arrival_time_to_break_minutes": arrival_time_to_break_minutes,
				"arrival_time_to_rest_minutes": arrival_time_to_rest_minutes,
				"departure_time_to_break_minutes": departure_time_to_break_minutes,
				"departure_time_to_rest_minutes": departure_time_to_rest_minutes,
				"previous_full_recharge_unlikely_by_break": prev_full_unlikely_by_break,
				"previous_full_recharge_unlikely_by_rest": prev_full_unlikely_by_rest,
				"previous_full_recharge_unlikely": prev_full_unlikely,
				"to_full_min": abs(departure_rb_min - label.batteryCapacity) < 1e-9,
				"to_full_max": abs(departure_rb_max - label.batteryCapacity) < 1e-9,
			})

	def invoke_REF(self, label, start_node, end_node, transition_type):
		arc_key = (start_node, end_node, transition_type)
		ref_entry = self.paraArcs.get(arc_key)
		if ref_entry:
			ref_func = ref_entry['REF']

			# Checking if the city has already been visited before starting
			if transition_type == 'start':
				ref_func(label, start_node, end_node)
				label.detailedPath.append(end_node)
			# Calculate delta only for 'drive' transition type
			elif transition_type == 'drive' and label.timeToNext > 0:
				delta = self.delta_l(label, maxTimeDrive_R, maxTimeDrive_B, timeDay, minTimeRest)
				ref_func(label, delta)
				label.detailedPath.append(end_node)
			elif transition_type == 'break':
				ref_func(label, start_node, end_node)
				label.detailedPath.append(end_node)
			elif transition_type == 'rest':
				ref_func(label, start_node, end_node)
				label.detailedPath.append(end_node)
			elif transition_type == 'visit' and label.timeToNext == 0 and label.time_min <= self.nodes[end_node]['timeWindowEnd']:
				ref_func(label, end_node)
				label.detailedPath.append(end_node)
			elif transition_type == 'passingCS' and label.timeToNext == 0:
				ref_func(label, start_node, end_node)
				label.detailedPath.append(end_node)				
			else:
				label.done = True
				# print(f"Paused: Label marked as done. Path: {label.detailedPath}, Time: {label.time}")
				# print()
				# print(f"Detailed activity: {label.activityList}, Time: {label.time}")
				# print()
				# print(f"Transition type: {transition_type}, TimeToNext: {label.timeToNext}")
				# print()
				# print(f"Next nodes is {end_node}: {self.nodes[end_node]}, Its Timewindow is: {self.nodes[end_node]['timeWindowEnd'] if self.nodes[end_node]['nodeType'] == 'City' else None}") 
				# print()
				# print("----------------------------")
				# # Uncomment one of the following options:
				# # Option 1: Stop the algorithm
				# # break  # or add a flag to stop the main algorithm
				# # Option 2: Raise an exception
				# # raise RuntimeError("Algorithm paused at label.done = True.")
				# # Option 3: Set a manual pause
				# pass  # Set a conditional breakpoint here in your debugger





	def _print_nodes(self):
			print("Nodes:")
			for node_id, node_data in self.nodes.items():
				print(f"Node ID: {node_id}")

	def printArcs(self):
		for arc_key, arc in self.arcs.items():
			print(f"Arc from {arc.startNode} to {arc.endNode} with travel time {arc.travelTime}")

	def arcsTotalTime(self):
		return sum(
			arc.travelTime
			for arc in self.arcs.values()
			if self.nodes[arc.startNode]['nodeType'] == 'City' and self.nodes[arc.endNode]['nodeType'] == 'City'
		)
	
	def arcsMaxTime(self):
		return max(arc.travelTime
			for arc in self.arcs.values()
			if self.nodes[arc.startNode]['nodeType'] == 'City' and self.nodes[arc.endNode]['nodeType'] == 'City')
	
	def numberCS(self):
		return sum(1 for node_data in self.nodes.values() if node_data.get('nodeType') == 'CS')

