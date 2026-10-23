"""
Charging synchronization analysis from activity_timeline.
Uses sequence-based logic: for each charge, look backward to the most recent driver-regulation
event (rest or break). If no drive between that and the charge → synchronized.
Rule: if both rest and break are the two previous activities → sync_with_rest.
"""

import ast
import pandas as pd


def parse_activity_timeline(tl):
    """Parse activity_timeline string/list into list of event dicts (chronological order)."""
    if tl is None or (isinstance(tl, float) and pd.isna(tl)):
        return []
    if isinstance(tl, list):
        events = tl
    else:
        try:
            events = ast.literal_eval(tl) if isinstance(tl, str) else []
        except (ValueError, SyntaxError):
            return []

    # Ensure chronological order by start_time
    events = sorted(events, key=lambda e: float(e.get('start_time', 0)))
    return events


def _is_driver_regulation(t):
    """Rest and break are driver-regulation events."""
    t = str(t).lower()
    return t in ('rest', 'break')


def _is_drive(t):
    t = str(t).lower()
    return t == 'drive'


def _is_charge(t):
    t = str(t).lower()
    return t == 'charge'


def compute_charging_sync_counts(tl):
    """
    Compute charging event counts from activity_timeline using sequence-based logic.

    For each charge: look backward to the most recent rest or break.
    - If no drive between that rest/break and the charge → synchronized.
    - If both rest and break appear as previous activities (no drive before charge) → sync_with_rest.
    - Else if most recent is rest → sync_with_rest.
    - Else if most recent is break → sync_with_break.
    - Otherwise → unsynchronized.

    Returns dict with:
        num_charges, num_synchronized, num_unsynchronized,
        num_sync_with_break, num_sync_with_rest,
        num_unsynchronized_breaks, num_unsynchronized_rests
    """
    events = parse_activity_timeline(tl)
    if not events:
        return {
            'num_charges': 0,
            'num_synchronized': 0,
            'num_unsynchronized': 0,
            'num_sync_with_break': 0,
            'num_sync_with_rest': 0,
            'num_unsynchronized_breaks': 0,
            'num_unsynchronized_rests': 0,
        }

    # Build list of (index, type) for charges and driver-regulation events
    charge_indices = [i for i, e in enumerate(events) if _is_charge(e.get('type', ''))]
    num_charges = len(charge_indices)

    num_sync_with_break = 0
    num_sync_with_rest = 0

    for ci in charge_indices:
        # Look backward from charge to find most recent rest or break
        most_recent_reg_idx = None
        most_recent_reg_type = None
        for j in range(ci - 1, -1, -1):
            t = str(events[j].get('type', '')).lower()
            if t in ('rest', 'break'):
                most_recent_reg_idx = j
                most_recent_reg_type = t
                break

        if most_recent_reg_idx is None:
            # No rest/break before this charge → unsynchronized
            continue

        # Check: is there any drive between the rest/break and the charge?
        has_drive_between = any(
            _is_drive(events[k].get('type', ''))
            for k in range(most_recent_reg_idx + 1, ci)
        )

        if has_drive_between:
            # Drive between rest/break and charge → unsynchronized
            continue

        # No drive: synchronized. Check if both rest and break are previous activities.
        # Window: from (inclusive) the most recent regulation event backwards to the last drive or start
        # Actually: the "previous activities" before charge = events between last drive and charge
        last_drive_before_charge = None
        for k in range(ci - 1, -1, -1):
            if _is_drive(events[k].get('type', '')):
                last_drive_before_charge = k
                break

        start_idx = (last_drive_before_charge + 1) if last_drive_before_charge is not None else 0
        window_events = events[start_idx:ci]
        has_rest_in_window = any(str(e.get('type', '')).lower() == 'rest' for e in window_events)
        has_break_in_window = any(str(e.get('type', '')).lower() == 'break' for e in window_events)

        if has_rest_in_window and has_break_in_window:
            # Both rest and break as previous activities → sync_with_rest
            num_sync_with_rest += 1
        elif most_recent_reg_type == 'rest':
            num_sync_with_rest += 1
        elif most_recent_reg_type == 'break':
            num_sync_with_break += 1

    num_synchronized = num_sync_with_break + num_sync_with_rest
    num_unsynchronized = num_charges - num_synchronized

    # Unsynchronized breaks: breaks that have no charge immediately after them (no drive in between)
    # Per user: "unsynchronized breaks" = breaks not used by charging
    # A break is "used" if there's a charge after it with no drive between
    unsync_breaks = 0
    unsync_rests = 0
    for i, e in enumerate(events):
        t = str(e.get('type', '')).lower()
        if t == 'break':
            # Check if any charge follows with no drive between
            used = False
            for j in range(i + 1, len(events)):
                if _is_drive(events[j].get('type', '')):
                    break
                if _is_charge(events[j].get('type', '')):
                    used = True
                    break
            if not used:
                unsync_breaks += 1
        elif t == 'rest':
            used = False
            for j in range(i + 1, len(events)):
                if _is_drive(events[j].get('type', '')):
                    break
                if _is_charge(events[j].get('type', '')):
                    used = True
                    break
            if not used:
                unsync_rests += 1

    return {
        'num_charges': num_charges,
        'num_synchronized': num_synchronized,
        'num_unsynchronized': num_unsynchronized,
        'num_sync_with_break': num_sync_with_break,
        'num_sync_with_rest': num_sync_with_rest,
        'num_unsynchronized_breaks': unsync_breaks,
        'num_unsynchronized_rests': unsync_rests,
    }


def add_charging_sync_columns(df, col='activity_timeline'):
    """Add charging sync count columns to DataFrame. Returns df with new columns."""
    if col not in df.columns:
        return df.copy()

    rows = []
    for _, row in df.iterrows():
        counts = compute_charging_sync_counts(row[col])
        rows.append({**row.to_dict(), **counts})

    out = pd.DataFrame(rows)
    return out
