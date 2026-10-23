"""Build one summary row per configuration and preserve every source observation.

python -m experiments.consolidate
Historical files are selected explicitly, avoiding their CSV/JSON mirror exports.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from common.paths import ROOT, OUTPUT

CONFIG = ROOT / 'experiments/configs/result_sources.json'
DESTINATION = OUTPUT / 'runs'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def encode(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {'__nonfinite_float__': repr(value)}
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [encode(v) for v in value]
    return value


def decode(value):
    if isinstance(value, dict):
        if set(value) == {'__nonfinite_float__'}:
            return float(value['__nonfinite_float__'])
        return {k: decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode(v) for v in value]
    return value


def first(row, *names):
    for name in names:
        value = row.get(name)
        if value is not None and value != '':
            return value
    return None


def number(row, *names):
    value = first(row, *names)
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def boolean(value):
    if value is None or value == '':
        return None
    if value is True or str(value).lower() == 'true':
        return True
    if value is False or str(value).lower() == 'false':
        return False
    raise ValueError(f'Unknown boolean: {value!r}')


def configuration(row, spec):
    algorithm = row.get('_runner_algorithm') or spec.get('algorithm')
    if not algorithm:
        raise ValueError(f'Missing algorithm in {spec["id"]}')
    battery = number(row, 'battery_capacity_kWh', 'battery_capacity')
    diesel = row.get('_runner_tag') == 'diesel_lb' or (battery is not None and battery >= 1e7)
    charging_policy = row.get('policy') or {'partial_labeling': 'partial', 'full_labeling': 'full', 'greedy': 'greedy_default'}.get(algorithm)
    return dict(instance_id=row['instance_id'], input_version=spec.get('input_version', 'historical_unverified'),
                policy=algorithm, charging_policy=charging_policy,
                vehicle_type='diesel_proxy' if diesel else 'electric', battery_kwh=battery,
                charging_power_kw=number(row, 'charging_power_kW', 'charging_power'),
                station_spacing_km=number(row, 'charging_station_interval_km', 'distance_per_cs'),
                consumption_kwh_per_km=number(row, 'energy_consumption_rate_kWh_per_km', 'consumption_rate'),
                t_sync_hours=number(row, 't_sync_hours'), safety_buffer_fraction=number(row, 'safety_buffer_frac'),
                synchronization_enabled=boolean(row.get('synchronization_enabled')))


def model_run_name(config):
    def fmt(value):
        return 'unknown' if value is None else f'{value:g}'.replace('.', 'p')
    return (f"{config['instance_id']}__{config['policy']}__{config['charging_policy']}__{config['vehicle_type']}"
            f"__B{fmt(config['battery_kwh'])}_P{fmt(config['charging_power_kw'])}_D{fmt(config['station_spacing_km'])}"
            f"_E{fmt(config['consumption_kwh_per_km'])}_sync{fmt(config['t_sync_hours'])}__{digest(config)[:12]}")


def metrics(row):
    aliases = {
        'makespan_hours': ('total_route_time_hours', 'total_time'),
        'computation_seconds': ('computation_time_seconds', 'computation_time'),
        'charging_stops': ('number_of_cs_stops', 'num_charges'),
        'breaks': ('number_of_breaks', 'num_breaks'), 'daily_rests': ('number_of_rests', 'num_rests'),
        'labels_generated': ('number_of_labels_generated',), 'labels_dominated': ('number_of_labels_dominated',),
        'synchronized_events': ('number_of_synchronized_events', 'num_synchronized_events'),
        'unsynchronized_charging_events': ('number_of_unsynchronized_charging_events', 'num_unsynchronized_charging_events'),
        'idle_charging_minutes': ('total_idle_charging_time_minutes',),
        'charging_minutes': ('total_charging_time_minutes',), 'energy_charged_kwh': ('total_energy_charged_kWh',),
        'driving_hours': ('total_driving_time_hours',), 'service_hours': ('total_service_time_hours',),
        'break_hours': ('total_break_time_hours',), 'rest_hours': ('total_rest_time_hours',),
        'charging_events_synchronized_pct': ('percentage_of_charging_events_synchronized',),
    }
    out = {name: number(row, *keys) for name, keys in aliases.items()}
    out['feasible_reported'] = boolean(row.get('feasible'))
    out['schedule_valid_reported'] = boolean(row.get('schedule_valid'))
    out['reason_if_infeasible'] = row.get('reason_if_infeasible')
    out['termination_status'] = row.get('termination_status') or 'unknown'
    out['schedule_available'] = bool(row.get('activity_timeline'))
    return out


def appendix_ids():
    text = (ROOT / 'manuscript/synch_paper_latex/main.tex').read_text(encoding='utf-8')
    section = text.split(r'\section{Summary of benchmark instances}', 1)[1].split(r'\end{longtable}', 1)[0]
    return {s.replace(r'\_', '_').strip() for s in re.findall(r'(?m)^\s*((?:short|med|long)(?:\\_|_)[^&\n]+?)\s*&', section)}


def read_source(path):
    if path.suffix == '.jsonl':
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    payload = json.loads(path.read_text(encoding='utf-8'))
    return payload['results'] if isinstance(payload, dict) else payload


def discover_sources():
    specs = json.loads(CONFIG.read_text())['sources']
    for path in sorted((OUTPUT / 'executions').glob('*/results.jsonl')):
        manifest_path = path.parent / 'manifest.json'
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        # Failed and partial batches remain visible, but are never labeled complete.
        specs.append(dict(id='execution_' + path.parent.name, path=path.relative_to(ROOT).as_posix(),
                          input_version=manifest.get('dataset', 'unknown') + ':' + digest(manifest.get('input_sha256', {}))[:12],
                          batch_status=manifest.get('status', 'unknown'), recorded_at=manifest.get('created_at', '')))
    return specs


def consolidate(destination=DESTINATION):
    destination = Path(destination)
    specs = discover_sources()
    groups, sources = {}, []
    paper_ids = appendix_ids()
    base_ids = set()
    for priority, spec in enumerate(specs):
        path = ROOT / spec['path']
        rows = read_source(path)
        timestamp = spec.get('recorded_at') or ''.join(re.findall(r'\d{8}_\d{6}', path.name))
        source = {**spec, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'record_count': len(rows)}
        sources.append(source)
        for index, row in enumerate(rows):
            if spec['id'] == 'base':
                base_ids.add(row['instance_id'])
            config = configuration(row, spec)
            key = digest(config)
            group = groups.setdefault(key, {'configuration': config, 'observations': []})
            payload = encode(row)
            observation = dict(observation_id=digest([spec['id'], index, payload])[:20],
                               source_id=spec['id'], source_row=index, recorded_at=timestamp,
                               source_priority=priority, result=payload)
            group['observations'].append(observation)
    # Complete each observed setting across the stored pool, without inventing results.
    stored_ids = {p.name for p in (ROOT / 'instances/benchmark_v1').iterdir() if p.is_dir()}
    templates = {}
    for group in list(groups.values()):
        template = {k: v for k, v in group['configuration'].items() if k != 'instance_id'}
        templates[digest(template)] = template
    # The confirmed paper base has not necessarily been executed. Keep it distinct
    # from historical inputs whose exact version has not been established.
    for policy, charging, sync, buffer in [
        ('partial_labeling', 'partial', None, None),
        ('full_labeling', 'full', None, None),
        ('greedy', 'greedy_default', None, .1),
        ('driver_heuristic', 'full', 1., None),
        ('driver_heuristic', 'overlap', 1., None),
    ]:
        template = dict(input_version='planned_paper_base_unverified', policy=policy,
                        charging_policy=charging, vehicle_type='electric', battery_kwh=500.,
                        charging_power_kw=350., station_spacing_km=50., consumption_kwh_per_km=1.49,
                        t_sync_hours=sync, safety_buffer_fraction=buffer, synchronization_enabled=None)
        templates[digest(template)] = template
    for template in templates.values():
        for instance_id in stored_ids:
            config = dict(instance_id=instance_id, **template)
            groups.setdefault(digest(config), {'configuration': config, 'observations': []})
    summaries, detail_rows = [], []
    for key, group in sorted(groups.items()):
        config, observations = group['configuration'], group['observations']
        # Deterministic display choice, never a claim that the newest result is correct.
        chosen = max(observations, key=lambda o: (re.sub(r'\D', '', o['recorded_at']), o['source_priority'], o['source_row'])) if observations else None
        ms = [metrics(decode(o['result'])) for o in observations]
        values = [m['makespan_hours'] for m in ms if m['makespan_hours'] is not None]
        different_feasibility = len({m['feasible_reported'] for m in ms}) > 1
        conflict = different_feasibility or (bool(values) and max(values) - min(values) > 1e-7)
        name = model_run_name(config)
        selected_metrics = metrics(decode(chosen['result'])) if chosen else {k: None for k in metrics({})}
        row = dict(model_run_id=name, **config, **selected_metrics,
                   record_status='record_available' if chosen else 'no_record_available',
                   in_current_appendix=config['instance_id'] in paper_ids,
                   in_saved_base_case=config['instance_id'] in base_ids,
                   matches_confirmed_paper_base=(config['vehicle_type'] == 'electric' and
                       [config[k] for k in ['battery_kwh', 'charging_power_kw', 'station_spacing_km', 'consumption_kwh_per_km']] == [500., 350., 50., 1.49]),
                   observation_count=len(observations), result_conflict=bool(conflict),
                   observed_min_makespan_hours=min(values) if values else None,
                   observed_max_makespan_hours=max(values) if values else None,
                   selected_observation_id=chosen['observation_id'] if chosen else None, selected_source=chosen['source_id'] if chosen else None,
                   source_groups=';'.join(sorted({o['source_id'] for o in observations})))
        summaries.append(row)
        detail_rows.append(dict(model_run_id=name, configuration=config, record_status=row['record_status'], selected_observation_id=row['selected_observation_id'],
                                result_conflict=bool(conflict), observations=observations))
    summaries.sort(key=lambda r: r['model_run_id'])
    detail_rows.sort(key=lambda r: r['model_run_id'])
    assert len({r['model_run_id'] for r in summaries}) == len(summaries)
    destination.mkdir(parents=True, exist_ok=True)
    temp = destination / 'summary.csv.tmp'
    with temp.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
        writer.writeheader(); writer.writerows(summaries)
    temp.replace(destination / 'summary.csv')
    temp = destination / 'details.jsonl.tmp'
    with temp.open('w', encoding='utf-8') as stream:
        for row in detail_rows:
            stream.write(json.dumps(row, separators=(',', ':'), allow_nan=False) + '\n')
    temp.replace(destination / 'details.jsonl')
    manifest = dict(schema_version=1, model_run_count=len(summaries), observation_count=sum(len(x['observations']) for x in detail_rows),
                    stored_instance_count=len(stored_ids), parameter_policy_template_count=len(templates),
                    records_available=sum(bool(r['observation_count']) for r in summaries),
                    records_missing=sum(not r['observation_count'] for r in summaries),
                    configurations_with_conflicts=sum(r['result_conflict'] for r in summaries),
                    confirmed_paper_base_count=sum(r['matches_confirmed_paper_base'] for r in summaries),
                    selection_rule='Latest recorded source timestamp, then source priority. Review conflicts before analysis.',
                    historical_input_version='Unverified; grouping by recorded settings does not prove identical input files or code.',
                    sources=sources, outputs={n: hashlib.sha256((destination / n).read_bytes()).hexdigest() for n in ['summary.csv', 'details.jsonl']})
    (destination / 'catalog.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f"Consolidated {manifest['observation_count']} observations into {len(summaries)} model runs; {manifest['configurations_with_conflicts']} conflicts flagged.")
    return manifest


def source_records(source_id, path=DESTINATION / 'details.jsonl'):
    """Reproduce one original source's records losslessly for pinned analyses."""
    rows = []
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            for observation in json.loads(line)['observations']:
                if observation['source_id'] == source_id:
                    rows.append((observation['source_row'], decode(observation['result'])))
    return [row for _, row in sorted(rows)]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    consolidate()
