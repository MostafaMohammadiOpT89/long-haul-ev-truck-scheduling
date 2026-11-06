"""Check coverage and lossless preservation of the exported research catalog."""
import csv
import hashlib
import json
import unittest
from collections import defaultdict
from experiments.consolidate import ROOT, DESTINATION, discover_sources, read_source, encode


class ConsolidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (DESTINATION / 'summary.csv').open(encoding='utf-8', newline='') as f:
            cls.summary = list(csv.DictReader(f))
        with (DESTINATION / 'summary_all.csv').open(encoding='utf-8', newline='') as f:
            cls.all_summary = list(csv.DictReader(f))
        with (DESTINATION / 'details.jsonl').open(encoding='utf-8') as f:
            cls.details = [json.loads(line) for line in f]

    def test_complete_grid_and_one_to_one_join(self):
        ids = [r['model_run_id'] for r in self.summary]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(set(ids) <= {r['model_run_id'] for r in self.details})
        all_ids = [r['model_run_id'] for r in self.all_summary]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(set(all_ids), {r['model_run_id'] for r in self.details})
        templates = defaultdict(set)
        for row in self.details:
            config = row['configuration'].copy()
            instance = config.pop('instance_id')
            templates[json.dumps(config, sort_keys=True)].add(instance)
        expected = {p.name for p in (ROOT / 'instances/benchmark_v1').iterdir() if p.is_dir()}
        self.assertEqual(len(expected), 45)
        for instances in templates.values():
            self.assertEqual(instances, expected)

    def test_summary_is_one_at_a_time_and_covers_missing_partial_runs(self):
        fields = ['battery_kwh', 'charging_power_kw', 'station_spacing_km', 'consumption_kwh_per_km']
        expected = {
            (350., 350., 60., 1.49), (750., 350., 60., 1.49),
            (500., 350., 60., 1.49), (1000., 350., 60., 1.49),
            (750., 1000., 60., 1.49),
            (750., 350., 40., 1.49), (750., 350., 80., 1.49), (750., 350., 100., 1.49),
            (750., 350., 60., 1.12), (750., 350., 60., 2.08),
        }
        partial = defaultdict(set)
        for row in self.summary:
            self.assertEqual(row['in_current_appendix'], 'True')
            if row['vehicle_type'] == 'diesel_proxy':
                continue
            values = tuple(float(row[k]) for k in fields)
            self.assertIn(values, expected)
            self.assertEqual(row['matches_confirmed_paper_base'] == 'True', values == (750., 350., 60., 1.49))
            if row['policy'] == 'partial_labeling':
                partial[values].add(row['instance_id'])
        self.assertEqual(set(partial), expected)
        self.assertTrue(all(len(instances) == 43 for instances in partial.values()))
        self.assertTrue(any(r['vehicle_type'] == 'electric' and
                            tuple(float(r[k]) for k in fields) not in expected for r in self.all_summary))

    def test_coverage_and_catalog_match_exports(self):
        with (DESTINATION / 'missing_partial_runs.csv').open(newline='', encoding='utf-8') as f:
            missing = list(csv.DictReader(f))
        with (DESTINATION / 'one_at_a_time_coverage.csv').open(newline='', encoding='utf-8') as f:
            coverage = list(csv.DictReader(f))
        self.assertEqual(len(coverage), 10)
        self.assertEqual(sum(int(r['missing_instances']) for r in coverage), len(missing))
        self.assertTrue(all(int(r['available_instances']) + int(r['missing_instances']) == 43 for r in coverage))
        catalog = json.loads((DESTINATION / 'catalog.json').read_text())
        self.assertEqual(catalog['summary_row_count'], len(self.summary))
        self.assertEqual(catalog['model_run_count'], len(self.all_summary))
        for name, expected_hash in catalog['outputs'].items():
            self.assertEqual(hashlib.sha256((DESTINATION / name).read_bytes()).hexdigest(), expected_hash)

    def test_missing_results_are_not_infeasible(self):
        missing = [r for r in self.summary if r['record_status'] == 'no_record_available']
        self.assertTrue(missing)
        for row in missing:
            for field in ['makespan_hours', 'feasible_reported', 'schedule_available', 'termination_status', 'selected_observation_id']:
                self.assertEqual(row[field], '')
            self.assertEqual(row['observation_count'], '0')
        for row in self.details:
            if row['record_status'] == 'no_record_available':
                self.assertEqual(row['observations'], [])
                self.assertIsNone(row['selected_observation_id'])

    def test_every_source_record_preserved_exactly_once(self):
        observations = defaultdict(dict)
        for row in self.details:
            for obs in row['observations']:
                source = observations[obs['source_id']]
                self.assertNotIn(obs['source_row'], source)
                source[obs['source_row']] = obs['result']
        for spec in discover_sources():
            original = read_source(ROOT / spec['path'])
            restored = observations[spec['id']]
            self.assertEqual(len(original), len(restored))
            for index, record in enumerate(original):
                self.assertEqual(encode(record), restored[index])

    def test_paper_instance_set_is_locked(self):
        paper = {ln.strip() for ln in (ROOT / 'instances/PAPER_INSTANCE_SET_43.txt').read_text(encoding='utf-8').splitlines() if ln.strip()}
        appendix = {r['instance_id'] for r in self.summary if r['in_current_appendix'] == 'True'}
        base = {r['instance_id'] for r in self.summary if r['in_saved_base_case'] == 'True'}
        self.assertEqual(paper, appendix)
        self.assertEqual(paper, base)
        self.assertEqual(len(paper), 43)
        self.assertNotIn('short_cl2_cu2_Balanced', paper)
        self.assertNotIn('short_cl2_cu2_Unbalanced', paper)


if __name__ == '__main__':
    unittest.main()
