import math
import pandas as pd
import matplotlib.pyplot as plt
import os
import json
import csv
from datetime import datetime
import logging
import arcClass
import network
import CSVreader

# Configure logging
logging.basicConfig(
    filename='greedy_scheduler.log',
    level=logging.INFO,
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Constants and parameters
driving_speed = 70  # km/h
maxElapsed_R = 13  # max elapsed time before rest
maxElapsed_B = 6   # max elapsed time before break
maxTimeDrive_B = 4.5
maxTimeDrive_R = 9
minTimeBreak = 0.75
minTimeRest = 11

# Test parameters (same as enhanced_main.py)
consumptionBest = 1.12
consumptionAverage = 1.49
consumptionWorst = 2.08
battery350 = 350  # kWh
battery500 = 500  # kWh
battery750 = 750  # kWh
battery1000 = 1000  # kWh

# Parameter grids
consumptionRates = [consumptionBest, consumptionAverage, consumptionWorst]
distancesPerCS = [40, 50, 60, 70, 80, 90, 100]
batteryCaps = [battery350, battery500, battery750]
CPs = [350, 1000]
# Safety buffer sweep (fraction of battery capacity reserved as untouchable)
SAFETY_BUFFER_FRACS = [0.10, 0.20, 0.30]
# Minimum acceptable feasibility rate when picking best fraction
MIN_FEASIBILITY = 0.99
class GreedySchedulerResult:
    def __init__(self, instance_id, distance_per_cs, battery_capacity, charging_power, 
                 consumption_rate, total_time, num_charges, num_breaks, num_rests, 
                 num_synchronized_events, feasible, computation_time, activity_list=None,
                 safety_buffer_frac: float = 0.30):
        self.instance_id = instance_id
        self.distance_per_cs = distance_per_cs
        self.battery_capacity = battery_capacity
        self.charging_power = charging_power
        self.consumption_rate = consumption_rate
        self.total_time = total_time
        self.num_charges = num_charges
        self.num_breaks = num_breaks
        self.num_rests = num_rests
        self.num_synchronized_events = num_synchronized_events
        self.feasible = feasible
        self.computation_time = computation_time
        self.safety_buffer_frac = safety_buffer_frac
        
        # Process activity timeline
        self.activity_timeline = []
        if activity_list:
            self._process_activity_timeline(activity_list)
    
    def _process_activity_timeline(self, activity_list):
        """Process activity list to create timeline similar to enhanced_main.py"""
        current_time = 0.0
        timeline = []
        
        for activity in activity_list:
            if ':' not in activity:
                continue
                
            activity_type, duration_str = activity.split(':', 1)
            activity_type = activity_type.strip()
            
            try:
                duration = float(duration_str.strip())
            except ValueError:
                continue
            
            # Create timeline entry
            timeline_entry = {
                "type": activity_type,
                "start_time": current_time,
                "end_time": current_time + duration,
                "duration_minutes": duration * 60  # Convert hours to minutes
            }
            
            # Add specific details based on activity type
            if activity_type == "drive":
                timeline_entry["distance_km"] = duration * driving_speed  # Convert hours to km
            elif activity_type == "charge":
                timeline_entry["power_kW"] = self.charging_power
                timeline_entry["location"] = "CS"
            elif activity_type in ["break", "rest"]:
                timeline_entry["location"] = "Rest Area"
            
            timeline.append(timeline_entry)
            current_time += duration
        
        self.activity_timeline = timeline
        
    def to_dict(self):
        return {
            "instance_id": self.instance_id,
            "distance_per_cs": self.distance_per_cs,
            "battery_capacity": self.battery_capacity,
            "charging_power": self.charging_power,
            "consumption_rate": self.consumption_rate,
            "total_time": self.total_time,
            "num_charges": self.num_charges,
            "num_breaks": self.num_breaks,
            "num_rests": self.num_rests,
            "num_synchronized_events": self.num_synchronized_events,
            "feasible": self.feasible,
            "computation_time": self.computation_time,
            "safety_buffer_frac": self.safety_buffer_frac,
            "synchronization_enabled": (self.num_synchronized_events > 0),
            "activity_timeline": self.activity_timeline
        }
    
    def to_csv_row(self):
        return [
            self.instance_id,
            self.distance_per_cs,
            self.battery_capacity,
            self.charging_power,
            self.consumption_rate,
            self.total_time,
            self.num_charges,
            self.num_breaks,
            self.num_rests,
            self.num_synchronized_events,
            self.feasible,
            self.computation_time,
            self.safety_buffer_frac,
            (self.num_synchronized_events > 0)  # synchronization_enabled (used in this run)
        ]
    
    @staticmethod
    def get_csv_headers():
        return [
            "instance_id",
            "distance_per_cs",
            "battery_capacity", 
            "charging_power",
            "consumption_rate",
            "total_time",
            "num_charges",
            "num_breaks",
            "num_rests",
            "num_synchronized_events",
            "feasible",
            "computation_time",
            "safety_buffer_frac",
            "synchronization_enabled"
        ]

def read_test_instance(filename):
    """Read test instance file and extract route information"""
    import csv
    
    nodes = []
    depot = None
    
    try:
        with open(filename, 'r') as file:
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
                    # Parse depot
                    vehicle_id, location, location_id = row
                    depot = {
                        'id': vehicle_id,
                        'location': location,
                        'locationId': int(location_id)
                    }
                    isFirstVehicleRow = False
                elif section == 'nodes':
                    # Parse nodes
                    node_id, location, location_id, start, end, _, _, _, serviceTime = row
                    nodes.append({
                        'id': node_id,
                        'location': location,
                        'locationId': int(location_id),
                        'timeWindowStart': int(start),
                        'timeWindowEnd': int(end),
                        'serviceTime': float(serviceTime)
                    })
    except Exception as e:
        logging.error(f"Error reading test instance {filename}: {e}")
        return None, []
    
    return depot, nodes

def create_simple_route(depot, nodes, cityArcs):
    """Create a simple route from depot through all nodes and back to depot"""
    route = []
    
    # Start from depot
    current_node = depot
    
    # Visit all nodes in order
    for node in nodes:
        # Find distance from current node to this node
        from_location = current_node['location']
        to_location = node['location']
        
        # Get distance from cityArcs
        distance = 0
        if from_location in cityArcs:
            if to_location in cityArcs[from_location].times:
                time = float(cityArcs[from_location].times[to_location])
                distance = time * driving_speed  # Convert time to distance
        
        route.append({
            "from": from_location,
            "to": to_location,
            "distance": distance
        })
        
        current_node = node
    
    # Return to depot
    from_location = current_node['location']
    to_location = depot['location']
    
    distance = 0
    if from_location in cityArcs:
        if to_location in cityArcs[from_location].times:
            time = float(cityArcs[from_location].times[to_location])
            distance = time * driving_speed
    
    route.append({
        "from": from_location,
        "to": to_location,
        "distance": distance
    })
    
    return route

def greedy_scheduler(route, consumption_rate, battery_capacity, charging_power, distance_per_cs,
                    cs_positions_map=None, service_time_map=None, include_service_times=False,
                    safety_buffer_frac: float = 0.30):
    """
    Greedy scheduler without synchronization
    """
    import time
    start_time = time.time()
    
    time_total = 0
    soc = battery_capacity
    drive_since_rest = 0
    drive_since_break = 0
    elapsed_since_rest = 0
    elapsed_since_break = 0
    num_charges = 0
    num_breaks = 0
    num_rests = 0
    num_synchronized_events = 0  # Always 0 for greedy scheduler
    feasible = True
    activity_list = []

    # Helper: compute CS positions (km from arc start) for a single city-to-city arc
    def cs_positions_for_arc(from_node, to_node, distance_km, interval_km):
        total_dist = float(distance_km or 0.0)
        if total_dist <= 0:
            return []
        if total_dist > interval_km:
            num_cs = math.floor(total_dist / interval_km)
        else:
            num_cs = 1
        if num_cs == 1:
            return [total_dist / 2.0]
        return [k * interval_km for k in range(1, num_cs + 1)]

    # Expand route by inserting on-route CS nodes between cities based on distance_per_cs (kept for potential reuse)
    def expand_route_with_cs(route_in, interval_km):
        expanded = []
        for seg in route_in:
            from_node = seg["from"]
            to_node = seg["to"]
            distance_km = float(seg.get("distance", 0) or 0)
            if distance_km <= 0:
                expanded.append({"from": from_node, "to": to_node, "distance": 0.0})
                continue
            # Positions of CS along the arc based on requested policy
            total_dist = distance_km
            if total_dist > interval_km:
                num_cs = math.floor(total_dist / interval_km)
            else:
                num_cs = 1  # Ensure at least one CS between cities

            if num_cs == 1:
                # Place single CS at midpoint
                positions = [total_dist / 2.0]
            else:
                # Place CS at multiples of interval
                positions = [(i + 1) * interval_km for i in range(num_cs)]

            previous_position = 0.0
            previous_node = from_node
            cs_index = 1
            for pos in positions:
                sub_distance = pos - previous_position
                cs_node = f"CS_{from_node}_{to_node}_{cs_index}"
                expanded.append({"from": previous_node, "to": cs_node, "distance": sub_distance})
                previous_node = cs_node
                previous_position = pos
                cs_index += 1

            remaining = distance_km - previous_position
            if remaining > 0:
                expanded.append({"from": previous_node, "to": to_node, "distance": remaining})
        return expanded

    # Iterate original route; keep previous arc CS info for backtracking
    prev_from = None
    prev_to = None
    prev_distance = 0.0
    prev_cs_positions = []
    # Helper: get cumulative CS positions on arc (from_node→to_node) from extended_route
    def cs_positions_from_extended(a_node, b_node):
        positions = []
        cum_dist = 0.0
        started = False
        expected_from = None
        for seg in extended_route:
            seg_from = seg.get("from")
            seg_to = seg.get("to")
            seg_dist = float(seg.get("distance", 0.0) or 0.0)
            if not started:
                if seg_from == a_node:
                    started = True
                    expected_from = seg_to
                    cum_dist += seg_dist
                    if isinstance(seg_to, str) and seg_to.startswith("CS_"):
                        positions.append(cum_dist)
                    if seg_to == b_node:
                        break
                continue
            else:
                if seg_from != expected_from:
                    continue
                cum_dist += seg_dist
                if isinstance(seg_to, str) and seg_to.startswith("CS_"):
                    positions.append(cum_dist)
                if seg_to == b_node:
                    break
                expected_from = seg_to
        return positions
    # Create extended route with charging stations
    extended_route = expand_route_with_cs(route, distance_per_cs)

    for idx, segment in enumerate(route):
        from_node = segment["from"]
        to_node = segment["to"]
        distance = segment["distance"]
        energy_needed = distance * consumption_rate
        drive_time = distance / driving_speed

        # Check if we need to take a break
        if drive_since_break + drive_time > maxTimeDrive_B or elapsed_since_break + drive_time > maxElapsed_B:
            time_total += minTimeBreak
            drive_since_break = 0
            elapsed_since_break = 0
            num_breaks += 1
            activity_list.append(f'break: {minTimeBreak}')

        # Check if we need to rest
        if drive_since_rest + drive_time > maxTimeDrive_R or elapsed_since_rest + drive_time > maxElapsed_R:
            time_total += minTimeRest
            drive_since_rest = 0
            elapsed_since_rest = 0
            # When resting, also reset break counters
            drive_since_break = 0
            elapsed_since_break = 0
            num_rests += 1
            activity_list.append(f'rest: {minTimeRest}')
        # Drive from city to city using Algorithm 2 (forward CS selection with one-step look-ahead)
        b_safety = safety_buffer_frac * battery_capacity  # safety buffer in kWh
        cs_positions_current = cs_positions_from_extended(from_node, to_node)

        def enforce_hos_for(leg_time_hours: float):
            nonlocal time_total, drive_since_break, elapsed_since_break, drive_since_rest, elapsed_since_rest, num_breaks, num_rests
            if drive_since_break + leg_time_hours > maxTimeDrive_B or elapsed_since_break + leg_time_hours > maxElapsed_B:
                time_total += minTimeBreak
                drive_since_break = 0
                elapsed_since_break = 0
                num_breaks += 1
                activity_list.append(f'break: {minTimeBreak}')
            if drive_since_rest + leg_time_hours > maxTimeDrive_R or elapsed_since_rest + leg_time_hours > maxElapsed_R:
                time_total += minTimeRest
                drive_since_rest = 0
                elapsed_since_rest = 0
                drive_since_break = 0
                elapsed_since_break = 0
                num_rests += 1
                activity_list.append(f'rest: {minTimeRest}')

        def apply_service_time(city_node: str):
            nonlocal time_total, drive_since_break, drive_since_rest, elapsed_since_break, elapsed_since_rest
            if not include_service_times:
                return
            if not service_time_map:
                return
            # service_time_map is keyed by location names; route nodes are location names
            service = float(service_time_map.get(city_node, 0.0) or 0.0)
            if service > 0:
                time_total += service
                activity_list.append(f'service: {service}')
                # Service contributes to both driving and elapsed counters per user's policy
                drive_since_break += service
                drive_since_rest += service
                elapsed_since_break += service
                elapsed_since_rest += service

        def enforce_with_sync_at_cs(leg_time_hours: float, charge_time_hours: float, extra_horizon_hours: float = 0.0) -> bool:
            """Apply break/rest overlapping with charging at CS if due before the leg.
            Returns True if a stop was applied (and overlapped), else False.
            """
            nonlocal time_total, num_breaks, num_rests, num_synchronized_events
            nonlocal drive_since_break, drive_since_rest, elapsed_since_break, elapsed_since_rest

            # Consider the upcoming leg plus a one-step look-ahead horizon (e.g., B→first CS)
            total_future_time = leg_time_hours + max(0.0, extra_horizon_hours)
            rest_due = (
                (drive_since_rest + total_future_time > maxTimeDrive_R)
                or (elapsed_since_rest + charge_time_hours + total_future_time > maxElapsed_R)
            )
            break_due = (
                (drive_since_break + total_future_time > maxTimeDrive_B)
                or (elapsed_since_break + charge_time_hours + total_future_time > maxElapsed_B)
            )

            if not (rest_due or break_due):
                return False

            required = minTimeRest if rest_due else minTimeBreak
            extra = max(0.0, required - charge_time_hours)
            if extra > 0:
                time_total += extra
                activity_list.append(f'{"rest" if rest_due else "break"}: {extra}')

            if rest_due:
                drive_since_rest = 0
                elapsed_since_rest = 0
                drive_since_break = 0
                elapsed_since_break = 0
                num_rests += 1
            else:
                drive_since_break = 0
                elapsed_since_break = 0
                num_breaks += 1

            num_synchronized_events += 1
            return True

        def onward_requirement(idx_current: int) -> float:
            if (idx_current + 1) >= len(route):
                return b_safety
            next_seg = route[idx_current + 1]
            next_distance = float(next_seg.get("distance", 0.0) or 0.0)
            energy_next = next_distance * consumption_rate
            if energy_next <= battery_capacity:
                return energy_next + b_safety
            positions = cs_positions_from_extended(next_seg["from"], next_seg["to"])
            feasible_positions = [p for p in positions if p * consumption_rate <= battery_capacity]
            if feasible_positions:
                furthest = max(feasible_positions)
                return furthest * consumption_rate + b_safety
            return b_safety

        energy_A_to_B = distance * consumption_rate

        # STEP 1 — Decide feasibility of A→B without charging
        if soc < energy_A_to_B + b_safety:
            # Need to charge on A→B at last possible CS before B
            reachable_cs = [p for p in cs_positions_current if p * consumption_rate <= soc]
            if not reachable_cs:
                # Fallback: backtrack to last CS on previous arc if possible (otherwise infeasible)
                if not prev_cs_positions:
                    feasible = False
                    pass  # fall through and mark infeasible below when we cannot proceed
                else:
                    last_pos = prev_cs_positions[-1]
                    distance_back = max(0.0, prev_distance - last_pos)
                    energy_back = distance_back * consumption_rate
                    back_drive_time = distance_back / driving_speed if distance_back > 0 else 0.0
                    if soc < energy_back:
                        feasible = False
                    else:
                        enforce_hos_for(back_drive_time)
                        time_total += back_drive_time
                        activity_list.append(f'drive: {back_drive_time}')
                        soc -= energy_back
                        drive_since_rest += back_drive_time
                        drive_since_break += back_drive_time
                        elapsed_since_rest += back_drive_time
                        elapsed_since_break += back_drive_time
                        # Charge to full
                        charge_time = (battery_capacity - soc) / charging_power
                        if charge_time > 0:
                            time_total += charge_time
                            soc = battery_capacity
                            num_charges += 1
                            activity_list.append(f'charge: {charge_time}')
                        # Return to city
                        enforce_hos_for(back_drive_time)
                        time_total += back_drive_time
                        activity_list.append(f'drive: {back_drive_time}')
                        soc -= energy_back
                        drive_since_rest += back_drive_time
                        drive_since_break += back_drive_time
                        elapsed_since_rest += back_drive_time
                        elapsed_since_break += back_drive_time

            if not feasible:
                break

            if reachable_cs:
                s_pos = max(reachable_cs)
                # Drive A→s*
                leg_dist = s_pos
                leg_time = leg_dist / driving_speed
                enforce_hos_for(leg_time)
                time_total += leg_time
                activity_list.append(f'drive: {leg_time}')
                soc -= leg_dist * consumption_rate
                drive_since_rest += leg_time
                drive_since_break += leg_time
                elapsed_since_rest += leg_time
                elapsed_since_break += leg_time

                # STEP 3 — Charge at s* (full) for onward requirement at B
                req_B = onward_requirement(idx)
                energy_s_to_B = (distance - s_pos) * consumption_rate
                target_soc = battery_capacity
                charge_energy = max(0.0, target_soc - soc)
                charge_time = charge_energy / charging_power
                time_total += charge_time
                soc += charge_energy
                num_charges += 1
                activity_list.append(f'charge: {charge_time}')

                # Drive s*→B (apply HoS overlap with charging if due)
                leg_time2 = (distance - s_pos) / driving_speed
                # One-step look-ahead: include time to first CS on B→C if exists
                extra_horizon = 0.0
                if (idx + 1) < len(route):
                    next_seg = route[idx + 1]
                    next_positions = cs_positions_from_extended(next_seg["from"], next_seg["to"]) 
                    if next_positions:
                        extra_horizon = (next_positions[0] / driving_speed)
                applied_sync = enforce_with_sync_at_cs(leg_time2, charge_time, extra_horizon)
                if not applied_sync:
                    enforce_hos_for(leg_time2)
                time_total += leg_time2
                activity_list.append(f'drive: {leg_time2}')
                soc -= energy_s_to_B
                # Apply service at B first (service contributes to HoS counters)
                apply_service_time(to_node)
                # Then add drive leg contribution
                drive_since_rest += leg_time2
                drive_since_break += leg_time2
                elapsed_since_rest += leg_time2
                elapsed_since_break += leg_time2

        else:
            # Can drive A→B; check look-ahead before committing
            req_B = onward_requirement(idx)
            if soc - energy_A_to_B >= req_B:
                # Direct to B is safe
                leg_time = distance / driving_speed
                enforce_hos_for(leg_time)
                time_total += leg_time
                activity_list.append(f'drive: {leg_time}')
                soc -= energy_A_to_B
                # Apply service at B first
                apply_service_time(to_node)
                # Then add drive leg contribution
                drive_since_rest += leg_time
                drive_since_break += leg_time
                elapsed_since_rest += leg_time
                elapsed_since_break += leg_time
            else:
                # New policy: if any CS on B→C is reachable after arriving at B, allow direct A→B
                if (idx + 1) < len(route):
                    next_seg = route[idx + 1]
                    next_distance = float(next_seg.get("distance", 0.0) or 0.0)
                    positions_next = cs_positions_from_extended(next_seg["from"], next_seg["to"]) 
                    soc_after_B = soc - energy_A_to_B
                    reachable_after_B = any((p * consumption_rate) <= soc_after_B for p in positions_next)
                else:
                    # Last leg: no look-ahead gating; allow direct A→B
                    reachable_after_B = True

                if reachable_after_B:
                    # Proceed A→B now; B→C will be handled next iteration
                    leg_time = distance / driving_speed
                    enforce_hos_for(leg_time)
                    time_total += leg_time
                    activity_list.append(f'drive: {leg_time}')
                    soc -= energy_A_to_B
                    drive_since_rest += leg_time
                    drive_since_break += leg_time
                    elapsed_since_rest += leg_time
                    elapsed_since_break += leg_time
                else:
                    # No CS after B is reachable with SoC_after_B → pre-boost at last CS before B
                    reachable_cs = [p for p in cs_positions_current if p * consumption_rate <= soc]
                    if not reachable_cs:
                        feasible = False
                        break
                    s_pos = max(reachable_cs)
                    # Drive A→s†
                    leg_dist = s_pos
                    leg_time = leg_dist / driving_speed
                    enforce_hos_for(leg_time)
                    time_total += leg_time
                    activity_list.append(f'drive: {leg_time}')
                    soc -= leg_dist * consumption_rate
                    drive_since_rest += leg_time
                    drive_since_break += leg_time
                    elapsed_since_rest += leg_time
                    elapsed_since_break += leg_time

                    # Charge to cover s†→B and onward requirement
                    energy_s_to_B = (distance - s_pos) * consumption_rate
                    # Charge enough to reach B and meet onward requirement, capped at battery capacity
                    target_soc = battery_capacity  # Always recharge to full battery capacity
                    charge_energy = max(0.0, target_soc - soc)
                    charge_time = charge_energy / charging_power
                    time_total += charge_time
                    soc += charge_energy
                    num_charges += 1
                    activity_list.append(f'charge: {charge_time}')

                    # Drive s†→B (apply HoS overlap with charging if due)
                    leg_time2 = (distance - s_pos) / driving_speed
                    extra_horizon = 0.0
                    if (idx + 1) < len(route):
                        next_seg = route[idx + 1]
                        next_positions = cs_positions_from_extended(next_seg["from"], next_seg["to"]) 
                        if next_positions:
                            extra_horizon = (next_positions[0] / driving_speed)
                    applied_sync = enforce_with_sync_at_cs(leg_time2, charge_time, extra_horizon)
                    if not applied_sync:
                        enforce_hos_for(leg_time2)
                    time_total += leg_time2
                    activity_list.append(f'drive: {leg_time2}')
                    soc -= energy_s_to_B
                    # Apply service at B first
                    apply_service_time(to_node)
                    # Then add drive leg contribution
                    drive_since_rest += leg_time2
                    drive_since_break += leg_time2
                    elapsed_since_rest += leg_time2
                    elapsed_since_break += leg_time2
        # After arrival to next city, update previous arc info
        prev_from = from_node
        prev_to = to_node
        prev_distance = float(distance or 0.0)
        prev_cs_positions = cs_positions_from_extended(prev_from, prev_to)

        # No immediate forward CS move here; next arc will be handled in the next iteration

    computation_time = time.time() - start_time
    
    return {
        "total_time": time_total,
        "charges": num_charges,
        "breaks": num_breaks,
        "rests": num_rests,
        "synchronized_events": num_synchronized_events,
        "feasible": feasible,
        "computation_time": computation_time,
        "activity_list": activity_list
    }

def save_greedy_results(all_results, timestamp):
    """Save greedy scheduler results to files"""
    
    # Create Results/Greedy_Scheduler_Results directory
    results_dir = os.path.join('Results', 'Greedy_Scheduler_Results')
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
        print(f"Created directory: {results_dir}")
    
    # Save to JSON
    json_filename = os.path.join(results_dir, f'greedy_results_{timestamp}.json')
    with open(json_filename, 'w') as json_file:
        json_data = {
            'metadata': {
                'timestamp': timestamp,
                'algorithm': 'greedy_scheduler',
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
    
    # Save to CSV
    csv_filename = os.path.join(results_dir, f'greedy_results_{timestamp}.csv')
    with open(csv_filename, 'w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(GreedySchedulerResult.get_csv_headers())
        for result in all_results:
            writer.writerow(result.to_csv_row())
    
    print(f"Greedy scheduler results saved to {json_filename} and {csv_filename}")
    logging.info(f"Greedy scheduler results saved to {json_filename} and {csv_filename}")

def main():
    """Main execution function for greedy scheduler"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.info(f"Starting greedy scheduler analysis at {timestamp}")
    
    # Set working directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print("Working directory set to:", os.getcwd())
    
    # Load city arcs data
    distanceMatrix = 'DistanceMatrix.csv'
    timeMatrix = 'TimeMatrix.csv'
    
    # Load data using the integrated CSVreader
    distanceData = CSVreader.CSVreader(distanceMatrix)
    timeData = CSVreader.CSVreader(timeMatrix)
    citiesArcs = arcClass.cityArcs.createArcs(distanceData, timeData)
    
    # Test instances to run
    test_instances = [1,2]
    
    all_results = []
    
    for i in test_instances:
        print(f"Processing greedy scheduler for Instance {i}...")
        logging.info(f"Starting Instance {i}")
        
        for CP in CPs:
            for batteryCap in batteryCaps:
                for consumption in consumptionRates:
                    for distancePerCS in distancesPerCS:
                        for safetyFrac in SAFETY_BUFFER_FRACS:
                            logging.info(f"Processing: Instance {i}, CP: {CP}, Battery: {batteryCap}, Consumption: {consumption}, CS Distance: {distancePerCS}, SafetyFrac: {safetyFrac}")
                        
                        # Read test instance
                        testingInstanceFilename = f'testInstance{i}.txt'
                        depot, nodes = read_test_instance(testingInstanceFilename)
                        
                        if not depot or not nodes:
                            print(f"Could not read test instance from {testingInstanceFilename}")
                            continue
                        
                        # Create route
                        route = create_simple_route(depot, nodes, citiesArcs)
                        
                        if not route:
                            print(f"Could not create route for {testingInstanceFilename}")
                            continue
                        
                        # Build service time map from test instance nodes (keyed by location name)
                        service_time_map = {n['location']: float(n.get('serviceTime', 0.0) or 0.0) for n in nodes}

                        # Run greedy scheduler (include service times)
                        result = greedy_scheduler(
                            route,
                            consumption,
                            batteryCap,
                            CP,
                            distancePerCS,
                            cs_positions_map=None,
                            service_time_map=service_time_map,
                            include_service_times=True,
                            safety_buffer_frac=safetyFrac,
                        )
                        
                        # Create result object
                        greedy_result = GreedySchedulerResult(
                            instance_id=i,
                            distance_per_cs=distancePerCS,
                            battery_capacity=batteryCap,
                            charging_power=CP,
                            consumption_rate=consumption,
                            total_time=result["total_time"],
                            num_charges=result["charges"],
                            num_breaks=result["breaks"],
                            num_rests=result["rests"],
                            num_synchronized_events=result["synchronized_events"],
                            feasible=result["feasible"],
                            computation_time=result["computation_time"],
                            activity_list=result["activity_list"],
                            safety_buffer_frac=safetyFrac,
                        )
                        
                        all_results.append(greedy_result)
                        
                        print(f"  Completed: Instance {i}, CP: {CP}, Battery: {batteryCap}, Consumption: {consumption}, CS Distance: {distancePerCS}")
                        print(f"    Total time: {result['total_time']:.2f} hours, Charges: {result['charges']}, Breaks: {result['breaks']}, Rests: {result['rests']}, Sync: {result['synchronized_events']}")
    
    # Save full-grid results
    save_greedy_results(all_results, timestamp)

    # Pareto analysis: pick safety_buffer_frac with highest feasibility, then lowest median time
    try:
        csv_path = os.path.join('Results', 'Greedy_Scheduler_Results', f'greedy_results_{timestamp}.csv')
        df = pd.read_csv(csv_path)
        # Sanity: show how many rows per safety fraction made it into results
        try:
            counts = df['safety_buffer_frac'].value_counts().sort_index()
            print("Rows per safety_buffer_frac:")
            for frac, cnt in counts.items():
                print(f"  {frac:.2f}: {cnt}")
        except Exception:
            pass
        # Feasibility rate per safety fraction
        feas = df.groupby('safety_buffer_frac')['feasible'].mean().rename('feas_rate')
        # Median time among feasible only
        med = df[df['feasible'] == True].groupby('safety_buffer_frac')['total_time'].median().rename('median_time')
        met = pd.concat([feas, med], axis=1).dropna()
        if not met.empty:
            # Filter by minimum feasibility threshold, fallback to all if none meet threshold
            met_ok = met[met['feas_rate'] >= MIN_FEASIBILITY]
            cand = met_ok if not met_ok.empty else met
            # Rank: higher feasibility is better, then lower median time
            best_frac = cand.sort_values(['feas_rate', 'median_time'], ascending=[False, True]).index[0]
            logging.info(f"Recommended safety_buffer_frac={best_frac} (feas={met.loc[best_frac, 'feas_rate']:.3f}, median_time={met.loc[best_frac, 'median_time']:.2f} h)")
            print(f"Recommended safety_buffer_frac={best_frac} (feas={met.loc[best_frac, 'feas_rate']:.3f}, median_time={met.loc[best_frac, 'median_time']:.2f} h)")

            # Plot feasibility vs median time
            fig_out = os.path.join('Results', 'Greedy_Scheduler_Results', f'pareto_safety_buffer_{timestamp}.png')
            plt.figure(figsize=(6, 4))
            plt.scatter(met['feas_rate'], met['median_time'], c=met.index, cmap='viridis', s=80)
            for frac, row in met.iterrows():
                plt.annotate(f"{frac:.2f}", (row['feas_rate'], row['median_time']), textcoords="offset points", xytext=(5,5), fontsize=8)
            plt.xlabel('Feasibility rate')
            plt.ylabel('Median total time (h)')
            plt.title('Safety buffer trade-off')
            plt.tight_layout()
            plt.savefig(fig_out, dpi=200)
            plt.close()

            # Save filtered results for the recommended fraction
            sel = df[df['safety_buffer_frac'] == best_frac]
            sel_path = os.path.join('Results', 'Greedy_Scheduler_Results', f'greedy_results_recommended_{timestamp}.csv')
            sel.to_csv(sel_path, index=False)
            print(f"Saved recommended-fraction results to {sel_path}")
    except Exception as e:
        logging.warning(f"Pareto analysis failed: {e}")
    
    # Print summary
    total_scenarios = len(all_results)
    feasible_scenarios = sum(1 for r in all_results if r.feasible)
    print(f"\nGreedy scheduler analysis completed!")
    print(f"Total scenarios tested: {total_scenarios}")
    print(f"Feasible scenarios: {feasible_scenarios}")
    print(f"Infeasible scenarios: {total_scenarios - feasible_scenarios}")
    print(f"Results saved with timestamp: {timestamp}")

if __name__ == "__main__":
    main() 