"""Check coverage and lossless preservation of the exported research catalog."""
import csv
import json
import unittest
from collections import defaultdict
from experiments.consolidate import ROOT, DESTINATION, discover_sources, read_source, encode


class ConsolidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (DESTINATION / 'summary.csv').open(encoding='utf-8', newline='') as f:
            cls.summary = list(csv.DictReader(f))
        with (DESTINATION / 'details.jsonl').open(encoding='utf-8') as f:
            cls.details = [json.loads(line) for line in f]

    def test_complete_grid_and_one_to_one_join(self):
        ids = [r['model_run_id'] for r in self.summary]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {r['model_run_id'] for r in self.details})
        templates = defaultdict(set)
        for row in self.details:
            config = row['configuration'].copy()
            instance = config.pop('instance_id')
            templates[json.dumps(config, sort_keys=True)].add(instance)
        expected = {p.name for p in (ROOT / 'instances/benchmark_v1').iterdir() if p.is_dir()}
        self.assertEqual(len(expected), 45)
        for instances in templates.values():
            self.assertEqual(instances, expected)

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

    def test_benchmark_disagreement_is_exposed(self):
        appendix = {r['instance_id'] for r in self.summary if r['in_current_appendix'] == 'True'}
        base = {r['instance_id'] for r in self.summary if r['in_saved_base_case'] == 'True'}
        self.assertEqual(len(appendix), 43)
        self.assertEqual(len(base), 43)
        self.assertEqual(len(appendix & base), 41)
        self.assertEqual(len(appendix | base), 45)


if __name__ == '__main__':
    unittest.main()
