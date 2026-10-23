"""Ensure active analysis selections use the catalog without changing cohorts."""
import unittest
from analysis.common.inputs import INPUTS, input_source
from common.results import read_records, read_frame, ResultSelection
from experiments.consolidate import discover_sources, read_source, encode, ROOT


class AnalysisCatalogTests(unittest.TestCase):
    def test_selections_reproduce_original_records(self):
        sources = {s['id']: s for s in discover_sources()}
        for name, spec in INPUTS.items():
            with self.subTest(name=name):
                selection = input_source(name)
                self.assertIsInstance(selection, ResultSelection)
                self.assertEqual(selection.path, ROOT / 'output/runs/details.jsonl')
                expected = read_source(ROOT / sources[spec['source_id']]['path'])
                if spec.get('algorithm'):
                    expected = [r for r in expected if r['_runner_algorithm'] == spec['algorithm']]
                actual = read_records(selection)
                self.assertEqual(encode(actual), encode(expected))
                self.assertEqual(len(read_frame(selection)), len(expected))

    def test_runs_directory_has_no_old_batch_folders(self):
        self.assertFalse(any(p.is_dir() for p in (ROOT / 'output/runs').iterdir()))


if __name__ == '__main__':
    unittest.main()
