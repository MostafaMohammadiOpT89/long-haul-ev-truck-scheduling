import os
import json
from typing import Dict, Any, List
import pandas as pd


def _extract_wait_metrics(activity_timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
    waits = [e for e in activity_timeline if e.get('type', '').startswith('wait')]
    visits = [e for e in activity_timeline if e.get('type', '').startswith('service')]

    total_wait = sum(e.get('duration_minutes', 0.0) for e in waits)
    visits_with_wait = 0
    # Count a wait before a service as one visit with wait using ordering in timeline
    if activity_timeline:
        for i, e in enumerate(activity_timeline):
            if str(e.get('type', '')).startswith('service'):
                # look back to see if immediate previous event is wait
                prev = activity_timeline[i-1] if i > 0 else None
                if prev and str(prev.get('type', '')).startswith('wait') and prev.get('duration_minutes', 0.0) > 0:
                    visits_with_wait += 1

    share_visits_with_wait = (visits_with_wait / len(visits)) if visits else 0.0
    avg_wait_if_wait = (total_wait / visits_with_wait) if visits_with_wait > 0 else 0.0
    max_wait = max((e.get('duration_minutes', 0.0) for e in waits), default=0.0)

    # Extract node ids from types like wait@<node>:, service@<node>:
    wait_nodes = []
    for e in waits:
        t = e.get('type', '')
        node = t.split('@', 1)[1] if '@' in t else ''
        node = node.split(':', 1)[0]
        wait_nodes.append(node)

    return {
        'total_wait_time_minutes': total_wait,
        'visits_with_wait': visits_with_wait,
        'total_visits': len(visits),
        'share_visits_with_wait': share_visits_with_wait,
        'avg_wait_minutes_if_wait': avg_wait_if_wait,
        'max_wait_minutes': max_wait,
        # serialize as JSON array so CSV keeps it in a single cell safely
        'wait_nodes': json.dumps(wait_nodes, ensure_ascii=False),
    }


def analyze_time_window_effect(results_path: str) -> pd.DataFrame:
    """Analyze time-window effects from an enhanced results JSON.

    Returns a DataFrame with per-scenario metrics, and writes a CSV next to the input file.
    """
    if not os.path.exists(results_path):
        raise FileNotFoundError(results_path)

    if results_path.lower().endswith('.csv'):
        # CSV does not contain activity_timeline; recommend using JSON results
        raise ValueError('Please provide the enhanced JSON results (contains activity_timeline).')

    with open(results_path, 'r') as f:
        data = json.load(f)

    results = data.get('results', [])
    rows = []
    for r in results:
        activity_timeline = r.get('activity_timeline', []) or []
        metrics = _extract_wait_metrics(activity_timeline)

        row = {
            'instance_id': r.get('instance_id'),
            'test_bed_id': r.get('test_bed_id'),
            'battery_capacity_kWh': r.get('battery_capacity_kWh'),
            'charging_station_interval_km': r.get('charging_station_interval_km'),
            'charging_power_kW': r.get('charging_power_kW'),
            'energy_consumption_rate_kWh_per_km': r.get('energy_consumption_rate_kWh_per_km'),
            'number_of_customer_locations': r.get('number_of_customer_locations'),
            'synchronization_enabled': r.get('synchronization_enabled'),
            'feasible': r.get('feasible'),
            'total_route_time_hours': r.get('total_route_time_hours'),
            **metrics,
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    # Write CSV next to source JSON
    out_csv = os.path.join(os.path.dirname(results_path), 'timewindow_effect_summary.csv')
    df.to_csv(out_csv, index=False)
    print(f'Wrote time-window effect summary: {out_csv} (rows={len(df)})')

    # Print concise aggregates
    if not df.empty:
        agg = df[['total_wait_time_minutes', 'visits_with_wait', 'total_visits', 'share_visits_with_wait', 'avg_wait_minutes_if_wait', 'max_wait_minutes']].mean(numeric_only=True)
        print('Aggregate (mean across scenarios):')
        print(agg.to_string())

    return df


if __name__ == '__main__':
    # Example: change the filename if needed
    root = os.path.dirname(__file__)
    default_file = os.path.join(root, 'enhanced_results_20250929_155633.json')
    try:
        analyze_time_window_effect(default_file)
    except Exception as e:
        print(f'Error: {e}')


