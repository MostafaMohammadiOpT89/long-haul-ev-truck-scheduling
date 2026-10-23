> Preserved method notes. The existing sequence-based post-analysis implementation is in `common/metrics.py`; policy result classes retain their existing metric calculations. Reconciling these definitions is a scientific change, separate from directory restructuring.

# Metrics Calculation Rules for TDSPEVRP Algorithms

## Overview
This document defines the rules for calculating activity and synchronization metrics consistently across all three algorithms:
1. **Full Recharge** (enhanced_main.py)
2. **Partial Recharge** (enhanced_main.py)  
3. **Greedy Scheduler** (greedy_scheduler.py)

## Core Metrics

### 1. Basic Activity Counts

**Rule**: Count occurrences of each activity type in the activity timeline.

- **`number_of_cs_stops`** (or `num_charges`): Count of "charge" activities
- **`number_of_breaks`** (or `num_breaks`): Count of "break" activities
- **`number_of_rests`** (or `num_rests`): Count of "rest" activities

**Implementation**: 
- For Full/Partial: Parse `label.activityList` and count activity types
- For Greedy: Count from `activity_list` returned by `greedy_scheduler()`

---

### 2. Synchronization Detection

**Rule**: A charging event is **synchronized** if it has **ANY time overlap** with a break OR rest event.

**Time Overlap Definition**:
- Two events overlap if: `max(start1, start2) < min(end1, end2)`
- Overlap duration = `min(end1, end2) - max(start1, start2)`

**Metrics**:
- **`number_of_synchronized_events`**: Count of charging events that overlap with break OR rest
- **`number_of_unsynchronized_charging_events`**: Count of charging events with NO overlap
  - Formula: `total_charges - synchronized_events`

---

### 3. Unsynchronized Breaks and Rests

**Rule**: A break/rest is **unsynchronized** if it has **NO time overlap** with ANY charging event.

**Metrics**:
- **`number_of_unsynchronized_breaks`**: Breaks with zero overlap with any charge
- **`number_of_unsynchronized_rests`**: Rests with zero overlap with any charge

**Calculation**:
1. For each break/rest event, check if it overlaps with ANY charging event
2. Count those with zero overlap

---

### 4. Idle Charging Time

**Rule**: Total charging time that does NOT overlap with break/rest activities.

**Metric**: **`total_idle_charging_time_minutes`**

**Calculation**:
```
total_charging_time_minutes = sum(all charge durations in minutes)
total_overlap_duration_minutes = sum(overlap durations in minutes)
idle_time = total_charging_time_minutes - total_overlap_duration_minutes
```

**Note**: This represents "wasted" charging time where the driver is not taking a break/rest.

---

### 5. Synchronization Percentage

**Rule**: Percentage of charging events that are synchronized.

**Metric**: **`percentage_of_charging_events_synchronized`**

**Calculation**:
```
percentage = (synchronized_events / total_charges) * 100
```

If `total_charges == 0`, then `percentage = 0.0`.

---

## Algorithm-Specific Implementation

### Full Recharge & Partial Recharge (Labeling Algorithms)

**Source**: `bestLabel.activityList` (list of strings like "charge: 0.5", "break: 0.75", etc.)

**Process**:
1. Parse `activityList` to extract activity types and durations (in hours)
2. Build timeline with start/end times for each activity
3. Calculate overlaps between charging events and break/rest events
4. Count synchronized/unsynchronized events based on overlaps

**Key Points**:
- Durations in `activityList` are in **hours**
- Convert to minutes for `duration_minutes` field
- Use time overlap (not pattern matching) for synchronization detection

---

### Greedy Scheduler

**Source**: `activity_list` returned by `greedy_scheduler()` function

**Current Implementation**:
- Tracks `num_synchronized_events` when `enforce_with_sync_at_cs()` returns `True`
- This happens when break/rest is applied overlapping with charging

**What's Missing**:
- `number_of_unsynchronized_charging_events`
- `number_of_unsynchronized_breaks`
- `number_of_unsynchronized_rests`
- `total_idle_charging_time_minutes`
- `percentage_of_charging_events_synchronized`

**Recommended Fix**:
- Post-process `activity_list` similar to Full/Partial algorithms
- Build timeline and calculate overlaps
- Add missing metrics to `GreedySchedulerResult` class

---

## Consistency Requirements

All three algorithms must:
1. Use the **same time overlap definition** for synchronization
2. Calculate metrics from the **actual activity timeline** (not assumptions)
3. Report metrics in the **same units** (minutes for time, counts for events)
4. Handle edge cases consistently (no charges, no breaks, etc.)

---

## Edge Cases

1. **No charging events**: 
   - `synchronized_events = 0`
   - `unsynchronized_charging_events = 0`
   - `percentage = 0.0`
   - All breaks/rests are unsynchronized

2. **No breaks/rests**:
   - All charging events are unsynchronized
   - `idle_time = total_charging_time`

3. **Perfect synchronization**:
   - Every charge overlaps with a break/rest
   - `synchronized_events = total_charges`
   - `unsynchronized_charging_events = 0`
   - `percentage = 100.0`

---

## Validation

To verify correctness:
1. Check that: `synchronized_events + unsynchronized_charging_events = total_charges`
2. Check that: `unsynchronized_breaks + synchronized_breaks = total_breaks`
3. Check that: `unsynchronized_rests + synchronized_rests = total_rests`
4. Verify: `idle_time >= 0` and `idle_time <= total_charging_time`
