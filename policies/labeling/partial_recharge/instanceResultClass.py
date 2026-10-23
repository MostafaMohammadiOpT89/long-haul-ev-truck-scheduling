import json
import math
from datetime import datetime

class EnhancedInstanceResult:
    def __init__(self, instanceName, distancePerCS, batteryCap, chargingPower, maxRT, consumption, 
                 bestLabel, bestTime, labelsGenerated, labelsDominated, profilingStats, totalTime,
                 cityNodesCount, synchronization_enabled=True):
        # Instance Metadata / Configuration Info
        # Handle both old format (testInstance1.txt) and new format (long_cl1_cu2 or long_cl1_cu2.txt)
        instance_name_clean = instanceName.replace('testInstance', '').replace('.txt', '')
        try:
            # Try to parse as integer (old format)
            self.instance_id = int(instance_name_clean)
            self.test_bed_id = f"TB{instance_name_clean}"
        except ValueError:
            # New format: use the instance name as-is
            self.instance_id = instance_name_clean
            self.test_bed_id = f"TB_{instance_name_clean}"
        self.battery_capacity_kWh = batteryCap
        self.charging_station_interval_km = distancePerCS
        self.charging_power_kW = chargingPower
        self.energy_consumption_rate_kWh_per_km = consumption
        self.number_of_customer_locations = cityNodesCount
        self.synchronization_enabled = synchronization_enabled
        
        # Feasibility and Runtime Info
        self.feasible = bestLabel != 'No valid path' and bestTime != float('inf')
        self.reason_if_infeasible = None if self.feasible else "No valid path found"
        self.total_route_time_hours = bestTime if self.feasible else None
        self.total_route_time_min_hours = None
        self.total_route_time_max_hours = None
        if self.feasible and bestLabel:
            self.total_route_time_min_hours = getattr(bestLabel, "time_min", None)
            self.total_route_time_max_hours = getattr(bestLabel, "time_max", None)
        self.computation_time_seconds = totalTime
        self.number_of_labels_generated = labelsGenerated
        self.number_of_labels_dominated = labelsDominated
        
        # Activity Analysis (calculated from bestLabel if available)
        self.number_of_cs_stops = 0
        self.number_of_breaks = 0
        self.number_of_rests = 0
        # Charging synchronization counts (label-based)
        self.number_of_synchronized_events = 0
        self.number_of_unsynchronized_charging_events = 0
        self.number_of_rest_synchronized_charging_events = 0
        # Fully and partially break-synchronized charging events
        self.number_of_break_fully_synchronized_charging_events = 0
        self.number_of_break_partial_synchronized_charging_events = 0
        # Aggregate break-synchronized count (full + partial)
        self.number_of_break_synchronized_charging_events = 0
        # Break/rest synchronization counts (overlap-based)
        self.number_of_unsynchronized_breaks = 0
        self.number_of_unsynchronized_rests = 0
        self.total_idle_charging_time_minutes = 0
        
        # Activity Timeline
        self.activity_timeline = []
        
        # Synchronization Metrics
        self.percentage_of_charging_events_synchronized = 0.0
        self.average_sync_overlap_duration_minutes = 0.0
        self.synchronization_efficiency_score = 0.0

        # End-of-route battery state (based on final label)
        self.final_battery_energy_min_kWh = None
        self.final_battery_energy_max_kWh = None
        
        # Populate end-of-route battery state if available.
        # For Partial Recharge, `reqRT_min/max` represent the energy deficit (kWh) at CP/charging-power semantics,
        # so SOC(kWh) = battery_capacity_kWh - reqRT(kWh).
        if self.feasible and bestLabel and hasattr(bestLabel, "reqRT_min") and hasattr(bestLabel, "reqRT_max"):
            soc_min = self.battery_capacity_kWh - bestLabel.reqRT_min
            soc_max = self.battery_capacity_kWh - bestLabel.reqRT_max
            # Clamp for numerical safety
            soc_min = max(0.0, min(self.battery_capacity_kWh, soc_min))
            soc_max = max(0.0, min(self.battery_capacity_kWh, soc_max))
            self.final_battery_energy_min_kWh = soc_min
            self.final_battery_energy_max_kWh = soc_max

        # Legacy fields for backward compatibility
        self.instanceName = instanceName
        self.distancePerCS = distancePerCS
        self.batteryCap = batteryCap
        self.chargingPower = chargingPower
        self.maxRT = maxRT
        self.consumption = consumption
        self.bestLabel = bestLabel
        self.bestTime = bestTime
        self.labelsGenerated = labelsGenerated
        self.labelsDominated = labelsDominated
        self.profilingStats = profilingStats
        self.totalTime = totalTime
        
        # Analyze the best label if available
        if self.feasible and bestLabel and hasattr(bestLabel, 'activityList'):
            self._analyze_activities(bestLabel)
    
    def _analyze_activities(self, label):
        """Analyze the activity list to extract detailed metrics"""
        current_time = 0.0
        timeline = []
        
        charging_events = []
        break_events = []
        rest_events = []
        driving_events = []

        # Also keep raw parsed events (type, duration) in original order
        raw_events = []
        charge_event_idx = 0
        
        for activity in label.activityList:
            if ':' not in activity:
                continue

            # activity may be like "charge[rest_sync]: 0.5" or "drive: 1.0"
            activity_type_raw, duration_str = activity.split(':', 1)
            activity_type_raw = activity_type_raw.strip()

            sync_type = None
            sync_fraction = None
            # Extract synchronization tag for charging activities, if present.
            # Supports tags like:
            #   charge[rest_sync]
            #   charge[break_sync]
            #   charge[break_partial_sync|0.6]
            if activity_type_raw.startswith("charge") and "[" in activity_type_raw and activity_type_raw.endswith("]"):
                base, tag = activity_type_raw.split("[", 1)
                activity_type = base.strip()
                tag = tag.rstrip("]").strip()
                if "|" in tag:
                    sync_type_str, frac_str = tag.split("|", 1)
                    sync_type = sync_type_str.strip()
                    try:
                        sync_fraction = float(frac_str.strip())
                    except ValueError:
                        sync_fraction = None
                else:
                    sync_type = tag
            else:
                activity_type = activity_type_raw
            
            try:
                duration = float(duration_str.strip())
            except ValueError:
                continue
            
            # Create timeline entry (duration is in hours, convert to minutes for timeline)
            timeline_entry = {
                "type": activity_type,
                "start_time": current_time,
                "end_time": current_time + duration,
                "duration_minutes": duration * 60  # Convert hours to minutes
            }
            
            # Add specific details based on activity type
            if activity_type == "drive":
                timeline_entry["distance_km"] = duration * 60  # Assuming 60 km/h average speed
                driving_events.append(timeline_entry)
            elif activity_type == "charge":
                timeline_entry["power_kW"] = self.charging_power_kW
                timeline_entry["location"] = "CS"  # Will be updated with actual location
                if sync_type is not None:
                    # Persist the classification from the labeling algorithm
                    timeline_entry["sync_type"] = sync_type  # "rest_sync", "break_sync", "break_partial_sync", or "unsync"
                if sync_fraction is not None:
                    # Fraction of total charging duration (min-branch) that is synchronized with the break
                    timeline_entry["sync_fraction_break"] = sync_fraction
                # Attach structured charge-event diagnostics if available (one per charge REF)
                if hasattr(label, "charge_events") and charge_event_idx < len(label.charge_events):
                    ce = label.charge_events[charge_event_idx]
                    charge_event_idx += 1
                    # Keep keys explicit and stable for downstream analysis
                    timeline_entry.update({
                        "cs_node": ce.get("cs_node"),
                        "sync_window_type": ce.get("sync_window_type"),
                        "sync_window_minutes": ce.get("sync_window_minutes"),
                        "extra_charge_time_min_minutes": ce.get("extra_charge_time_min_minutes"),
                        "extra_charge_time_max_minutes": ce.get("extra_charge_time_max_minutes"),
                        "full_time_needed_min_minutes": ce.get("full_time_needed_min_minutes"),
                        "full_time_needed_max_minutes": ce.get("full_time_needed_max_minutes"),
                        "extra_needed_to_full_min_minutes": ce.get("extra_needed_to_full_min_minutes"),
                        "extra_needed_to_full_max_minutes": ce.get("extra_needed_to_full_max_minutes"),
                        "arrival_soc_min_kWh": ce.get("arrival_soc_min_kWh"),
                        "arrival_soc_max_kWh": ce.get("arrival_soc_max_kWh"),
                        "departure_soc_min_kWh": ce.get("departure_soc_min_kWh"),
                        "departure_soc_max_kWh": ce.get("departure_soc_max_kWh"),
                        "energy_charged_min_kWh": ce.get("energy_charged_min_kWh"),
                        "energy_charged_max_kWh": ce.get("energy_charged_max_kWh"),
                        "arrival_time_min_hours": ce.get("arrival_time_min_hours"),
                        "arrival_time_max_hours": ce.get("arrival_time_max_hours"),
                        "departure_time_min_hours": ce.get("departure_time_min_hours"),
                        "departure_time_max_hours": ce.get("departure_time_max_hours"),
                        "arrival_time_interval_minutes": ce.get("arrival_time_interval_minutes"),
                        "departure_time_interval_minutes": ce.get("departure_time_interval_minutes"),
                        "arrival_time_to_break_minutes": ce.get("arrival_time_to_break_minutes"),
                        "arrival_time_to_rest_minutes": ce.get("arrival_time_to_rest_minutes"),
                        "departure_time_to_break_minutes": ce.get("departure_time_to_break_minutes"),
                        "departure_time_to_rest_minutes": ce.get("departure_time_to_rest_minutes"),
                        "previous_full_recharge_unlikely_by_break": ce.get("previous_full_recharge_unlikely_by_break"),
                        "previous_full_recharge_unlikely_by_rest": ce.get("previous_full_recharge_unlikely_by_rest"),
                        "previous_full_recharge_unlikely": ce.get("previous_full_recharge_unlikely"),
                        "to_full_min": ce.get("to_full_min"),
                        "to_full_max": ce.get("to_full_max"),
                    })
                charging_events.append(timeline_entry)
            elif activity_type == "break":
                break_events.append(timeline_entry)
            elif activity_type == "rest":
                rest_events.append(timeline_entry)
            
            timeline.append(timeline_entry)
            raw_events.append((activity_type, duration))
            current_time += duration
        
        self.activity_timeline = timeline
        self.number_of_cs_stops = len(charging_events)
        self.number_of_breaks = len(break_events)
        self.number_of_rests = len(rest_events)
        
        # Calculate synchronization metrics (charge synchronized with break/rest by time overlap)
        # This will set: synchronized_events, unsynchronized_charging_events, 
        # unsynchronized_breaks, unsynchronized_rests, total_idle_charging_time_minutes
        self._calculate_synchronization_metrics(charging_events, break_events, rest_events)
    
    def _calculate_synchronization_metrics(self, charging_events, break_events, rest_events):
        """Calculate synchronization metrics between charging and rest events.

        Charging-event synchronization (counts) is derived from the label-based
        classification written in activityList (sync_type), while overlap is
        still used for idle-time and unsynchronized break/rest metrics.
        """
        # --- 1) Charging synchronization from label tags ---
        sync_rest_events = sum(1 for ev in charging_events if ev.get("sync_type") == "rest_sync")
        sync_break_full_events = sum(1 for ev in charging_events if ev.get("sync_type") == "break_sync")
        sync_break_partial_events = sum(1 for ev in charging_events if ev.get("sync_type") == "break_partial_sync")
        # Treat any explicitly tagged "unsync" (or missing/unknown tag) as unsynchronized
        unsync_events = 0
        for ev in charging_events:
            tag = ev.get("sync_type")
            if tag in ("rest_sync", "break_sync", "break_partial_sync"):
                continue
            # "unsync" or None or any other unexpected value
            unsync_events += 1

        self.number_of_rest_synchronized_charging_events = sync_rest_events
        self.number_of_break_fully_synchronized_charging_events = sync_break_full_events
        self.number_of_break_partial_synchronized_charging_events = sync_break_partial_events
        self.number_of_break_synchronized_charging_events = sync_break_full_events + sync_break_partial_events
        self.number_of_synchronized_events = sync_rest_events + sync_break_full_events + sync_break_partial_events
        self.number_of_unsynchronized_charging_events = unsync_events

        # --- 2) Overlap-based metrics for breaks/rests and idle charging time ---
        total_overlap_duration = 0.0  # in hours
        overlapped_break_idx = set()
        overlapped_rest_idx = set()

        for charge_event in charging_events:
            charge_start = charge_event["start_time"]
            charge_end = charge_event["end_time"]

            # Rest overlaps
            for ridx, rest_event in enumerate(rest_events):
                rest_start = rest_event["start_time"]
                rest_end = rest_event["end_time"]
                overlap_start = max(charge_start, rest_start)
                overlap_end = min(charge_end, rest_end)
                if overlap_end > overlap_start:
                    overlap_duration = overlap_end - overlap_start
                    total_overlap_duration += overlap_duration
                    overlapped_rest_idx.add(ridx)

            # Break overlaps
            for bidx, br_event in enumerate(break_events):
                br_start = br_event["start_time"]
                br_end = br_event["end_time"]
                overlap_start = max(charge_start, br_start)
                overlap_end = min(charge_end, br_end)
                if overlap_end > overlap_start:
                    overlap_duration = overlap_end - overlap_start
                    total_overlap_duration += overlap_duration
                    overlapped_break_idx.add(bidx)

        # Unsynchronized breaks/rests are those with zero overlap with any charge
        self.number_of_unsynchronized_breaks = max(0, len(break_events) - len(overlapped_break_idx))
        self.number_of_unsynchronized_rests = max(0, len(rest_events) - len(overlapped_rest_idx))

        # Percent of charging events that are synchronized (label-based)
        if charging_events:
            self.percentage_of_charging_events_synchronized = (
                self.number_of_synchronized_events / len(charging_events)
            ) * 100
        else:
            self.percentage_of_charging_events_synchronized = 0.0

        # Average overlap duration per synchronized event (using overlap for minutes)
        if self.number_of_synchronized_events > 0:
            self.average_sync_overlap_duration_minutes = (total_overlap_duration * 60) / self.number_of_synchronized_events
        else:
            self.average_sync_overlap_duration_minutes = 0.0

        # Total idle charging time (charging time not overlapping with break/rest), in minutes
        total_charging_time_minutes = sum(event["duration_minutes"] for event in charging_events)
        total_overlap_duration_minutes = total_overlap_duration * 60  # hours -> minutes
        self.total_idle_charging_time_minutes = total_charging_time_minutes - total_overlap_duration_minutes

        # Composite synchronization efficiency score (unchanged definition)
        if charging_events and total_charging_time_minutes > 0:
            sync_ratio = self.number_of_synchronized_events / len(charging_events)
            overlap_ratio = total_overlap_duration_minutes / total_charging_time_minutes
            self.synchronization_efficiency_score = (sync_ratio + overlap_ratio) / 2 * 100
        else:
            self.synchronization_efficiency_score = 0.0
    
    def to_dict(self):
        """Convert the result to a dictionary for JSON serialization"""
        return {
            # Instance Metadata
            "instance_id": self.instance_id,
            "test_bed_id": self.test_bed_id,
            "battery_capacity_kWh": self.battery_capacity_kWh,
            "charging_station_interval_km": self.charging_station_interval_km,
            "charging_power_kW": self.charging_power_kW,
            "energy_consumption_rate_kWh_per_km": self.energy_consumption_rate_kWh_per_km,
            "number_of_customer_locations": self.number_of_customer_locations,
            "synchronization_enabled": self.synchronization_enabled,
            
            # Feasibility and Runtime
            "feasible": self.feasible,
            "reason_if_infeasible": self.reason_if_infeasible,
            "total_route_time_hours": self.total_route_time_hours,
            "total_route_time_min_hours": self.total_route_time_min_hours,
            "total_route_time_max_hours": self.total_route_time_max_hours,
            "computation_time_seconds": self.computation_time_seconds,
            "number_of_labels_generated": self.number_of_labels_generated,
            "number_of_labels_dominated": self.number_of_labels_dominated,
            
            # Activity Analysis
            "number_of_cs_stops": self.number_of_cs_stops,
            "number_of_breaks": self.number_of_breaks,
            "number_of_rests": self.number_of_rests,
            "number_of_synchronized_events": self.number_of_synchronized_events,
            "number_of_unsynchronized_charging_events": self.number_of_unsynchronized_charging_events,
            "number_of_rest_synchronized_charging_events": self.number_of_rest_synchronized_charging_events,
            "number_of_break_fully_synchronized_charging_events": self.number_of_break_fully_synchronized_charging_events,
            "number_of_break_partial_synchronized_charging_events": self.number_of_break_partial_synchronized_charging_events,
            "number_of_break_synchronized_charging_events": self.number_of_break_synchronized_charging_events,
            "number_of_unsynchronized_breaks": self.number_of_unsynchronized_breaks,
            "number_of_unsynchronized_rests": self.number_of_unsynchronized_rests,
            "total_idle_charging_time_minutes": self.total_idle_charging_time_minutes,
            
            # Activity Timeline
            "activity_timeline": self.activity_timeline,
            
            # Synchronization Metrics
            "percentage_of_charging_events_synchronized": self.percentage_of_charging_events_synchronized,

            # End-of-route battery state
            "final_battery_energy_min_kWh": self.final_battery_energy_min_kWh,
            "final_battery_energy_max_kWh": self.final_battery_energy_max_kWh,
        }
    
    def to_csv_row(self):
        """Convert the result to a CSV row format"""
        return [
            self.instance_id,
            self.test_bed_id,
            self.battery_capacity_kWh,
            self.charging_station_interval_km,
            self.charging_power_kW,
            self.energy_consumption_rate_kWh_per_km,
            self.number_of_customer_locations,
            self.synchronization_enabled,
            self.feasible,
            self.reason_if_infeasible or "",
            self.total_route_time_hours or "",
            self.total_route_time_min_hours if self.total_route_time_min_hours is not None else "",
            self.total_route_time_max_hours if self.total_route_time_max_hours is not None else "",
            self.computation_time_seconds,
            self.number_of_labels_generated,
            self.number_of_labels_dominated,
            self.number_of_cs_stops,
            self.number_of_breaks,
            self.number_of_rests,
            self.number_of_synchronized_events,
            self.number_of_unsynchronized_charging_events,
            self.number_of_rest_synchronized_charging_events,
            self.number_of_break_fully_synchronized_charging_events,
            self.number_of_break_partial_synchronized_charging_events,
            self.number_of_break_synchronized_charging_events,
            self.number_of_unsynchronized_breaks,
            self.number_of_unsynchronized_rests,
            self.total_idle_charging_time_minutes,
            self.percentage_of_charging_events_synchronized,
            self.final_battery_energy_min_kWh if self.final_battery_energy_min_kWh is not None else "",
            self.final_battery_energy_max_kWh if self.final_battery_energy_max_kWh is not None else "",
        ]
    
    @staticmethod
    def get_csv_headers():
        """Get CSV headers for the enhanced result format"""
        return [
            "instance_id",
            "test_bed_id",
            "battery_capacity_kWh",
            "charging_station_interval_km", 
            "charging_power_kW",
            "energy_consumption_rate_kWh_per_km",
            "number_of_customer_locations",
            "synchronization_enabled",
            "feasible",
            "reason_if_infeasible",
            "total_route_time_hours",
            "total_route_time_min_hours",
            "total_route_time_max_hours",
            "computation_time_seconds",
            "number_of_labels_generated",
            "number_of_labels_dominated",
            "number_of_cs_stops",
            "number_of_breaks",
            "number_of_rests",
            "number_of_synchronized_events",
            "number_of_unsynchronized_charging_events",
            "number_of_rest_synchronized_charging_events",
            "number_of_break_fully_synchronized_charging_events",
            "number_of_break_partial_synchronized_charging_events",
            "number_of_break_synchronized_charging_events",
            "number_of_unsynchronized_breaks",
            "number_of_unsynchronized_rests",
            "total_idle_charging_time_minutes",
            "percentage_of_charging_events_synchronized",
            "final_battery_energy_min_kWh",
            "final_battery_energy_max_kWh",
        ]

# Legacy class for backward compatibility
class InstanceResult:
    def __init__(self, instanceName, distancePerCS, batteryCap, chargingPower, maxRT, consumption, bestLabel, bestTime, labelsGenerated, labelsDominated, profilingStats, totalTime):
        self.instanceName = instanceName
        self.distancePerCS = distancePerCS
        self.batteryCap = batteryCap
        self.chargingPower = chargingPower
        self.maxRT = maxRT
        self.consumption = consumption
        self.bestLabel = bestLabel
        self.bestTime = bestTime
        self.labelsGenerated = labelsGenerated
        self.labelsDominated = labelsDominated
        self.profilingStats = profilingStats
        self.totalTime = totalTime  # Add total time here
    # Adding __str__ method for clean output
    def __str__(self):
        return (
            f"Instance: {self.instanceName}\n"
            f"Distance per CS: {self.distancePerCS} km\n"
            f"Battery Capacity: {self.batteryCap} kWh\n"
            f"Charging Power: {self.chargingPower} kW\n"
            f"Max RT: {self.maxRT:.2f} hours\n"
            f"Consumption: {self.consumption} kWh/km\n"
            f"Best Path Label: {self.bestLabel}\n"
            f"Best Time: {self.bestTime:.2f} minutes\n"
            f"Labels Generated: {self.labelsGenerated}\n"
            f"Labels Dominated: {self.labelsDominated}\n"
            f"Profiling Stats: {self.profilingStats}\n"
            f"Total Time: {self.totalTime:.6f} seconds"
        )

