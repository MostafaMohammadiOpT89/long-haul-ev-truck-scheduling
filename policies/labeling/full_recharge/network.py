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

def setGlobalParams(consumptionRate, distPerCS, batteryCap, chargingPower):
    global consumption
    global distance_per_cs
    global batteryCapacity
    global CP
    consumption = consumptionRate
    distance_per_cs = distPerCS
    batteryCapacity = batteryCap
    CP = chargingPower


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
							'serviceTime': 0.08,
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
	
	
	def _fpassby_start(self,label, startNode, endNode):
		endNodeData=self.nodes.get(endNode)
		realEndNode = endNodeData['endNode']
		startNodeData=self.nodes.get(startNode)
		realStartNode_afterpassing = startNodeData['endNode']
		time_CSM=self.arcs[(realStartNode_afterpassing, realEndNode)].travelTime

		label.timeToNext=time_CSM




	def _fdrive_delta(self, label, delta_l):
		label.time += delta_l
		label.timeToNext -= delta_l
		label.drive_B += delta_l
		label.drive_R += delta_l
		label.elapsed_R += delta_l
		label.elapsed_B += delta_l
		label.latest_B = min(label.latest_B, label.latest_R + maxElapsed_R - label.elapsed_B - delta_l)
		label.reqRT += delta_l * consumption * velocity #alpha
		# Decrease battery level based on driving energy use (kWh)
		if hasattr(label, "remainingBattery"):
			label.remainingBattery = max(0.0, label.remainingBattery - delta_l * consumption * velocity)
		
		label.activityList.append(f'drive: {delta_l}')

	def _fbreak_delta(self, label, startNode, endNode):
		label.time += minTimeBreak
		label.drive_B = 0
		label.elapsed_R += minTimeBreak
		label.elapsed_B = 0
		label.latest_B = float('inf')

		label.activityList.append(f'break: {minTimeBreak}')

	def _frest_delta(self, label, startNode, endNode):
		label.time += minTimeRest
		label.drive_R = 0
		label.drive_B = 0
		label.elapsed_R = 0
		label.elapsed_B = 0
		label.latest_R = float('inf')
		label.latest_B = float('inf')

		label.activityList.append(f'rest: {minTimeRest}')

	def _fvisit_nm(self, label, endNode):
		t_min_m, t_max_m, serviceTime_m = self.nodes[endNode]['timeWindowStart'], self.nodes[endNode]['timeWindowEnd'], self.nodes[endNode]['serviceTime']
		label.time = max(label.time, t_min_m) + serviceTime_m
		#label.time += serviceTime_m
		label.elapsed_R = max(label.elapsed_R, t_min_m - label.latest_R) + serviceTime_m
		#label.elapsed_R += serviceTime_m
		label.elapsed_B = max(label.elapsed_B, t_min_m - label.latest_B) + serviceTime_m
		#label.elapsed_B += serviceTime_m
		label.latest_R = min(label.latest_R, t_max_m + serviceTime_m - label.elapsed_R)
		label.latest_B = min(label.latest_B, t_max_m + serviceTime_m - label.elapsed_B)
		label.path.append(endNode)
		label.timeToNext = 0
		
		label.activityList.append(f'wait and service: {serviceTime_m + t_min_m - label.time}' if t_min_m > label.time else f'service: {serviceTime_m}')

	def _fcharge_cs(self, label, startNode, endNode):
		endNodeData = self.nodes.get(endNode)
		realEndNode = endNodeData['endNode']
		time_nm = self.arcs[(startNode, realEndNode)].travelTime
		tempTime = label.time
		added_time = 0.0

		# Case 1: Synchronized with rest (all charging within rest window)
		if label.elapsed_R == 0 or label.elapsed_R == 0.08:
			sync_tag = "rest_sync"
			added_time = 0.0
		# Case 2: At a break start (drive_B == 0)
		elif label.drive_B == 0:
			full_time = (label.reqRT) / CP if CP else 0.0
			# If required charging fits entirely inside the break window -> fully break-synchronized
			if full_time <= minTimeBreak:
				sync_tag = "break_sync"
				added_time = 0.0
			else:
				# Charging uses the whole break window (synchronized part),
				# but still needs extra time beyond the break (unsynchronized part).
				# Mark this as a partially break-synchronized charging event and compute fraction.
				if full_time > 0:
					sync_fraction_break = min(1.0, minTimeBreak / full_time)
				else:
					sync_fraction_break = 1.0
				sync_tag = f"break_partial_sync|{sync_fraction_break:.6f}"
				added_time = max(0.0, full_time - minTimeBreak)
		# Case 3: Not synchronized (no rest or break to align with)
		else:
			sync_tag = "unsync"
			added_time = (label.reqRT) / CP if CP else 0.0

		label.time += added_time

		label.timeToNext = time_nm
		#label.drive_B = 0 if label.time - tempTime >= 0.75 else label.drive_B
		label.elapsed_R = 0 if label.elapsed_R == 0 or label.elapsed_R == 0.08 else label.elapsed_R + label.time - tempTime
		#label.elapsed_B = 0 if label.elapsed_B == 0 or label.elapsed_B == 0.08 or label.time - tempTime >= 0.75 else label.elapsed_B + label.time - tempTime
		label.elapsed_B = 0 if label.elapsed_B == 0.08 else label.elapsed_B + label.time - tempTime
		label.reqRT = 0
		# Full recharge at CS: reset SOC to battery capacity
		if hasattr(label, "remainingBattery"):
			label.remainingBattery = label.batteryCapacity

		# Extra route time spent charging (beyond synchronized rest/break windows)
		extra_charge_time = label.time - tempTime

		# Log the charging activity with explicit synchronization tag so that
		# post-processing can distinguish rest-sync, break-sync, partial-break-sync, and unsynchronized charges
		label.activityList.append(f'charge[{sync_tag}]: {extra_charge_time}')
		#label.time = label.time if label.elapsed_R == 0 else (max(label.time - minTimeBreak + min(label.reqRT, batteryCap/CP), 0) if label.drive_B == 0 else label.time + min(label.reqRT, batteryCap/CP))

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
			elif transition_type == 'visit' and label.timeToNext == 0 and label.time <= self.nodes[end_node]['timeWindowEnd']:
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

