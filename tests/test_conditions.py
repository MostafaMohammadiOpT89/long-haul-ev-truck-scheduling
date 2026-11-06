"""Guard the approved sensitivity comparison against inconsistent scales/cohorts."""
import json
import re
import unittest
import zipfile

import matplotlib.pyplot as plt
import numpy as np

from analysis.conditions.data import ROOT, PARAMETERS, load_pairs, matched_slices
from analysis.conditions.plot_helpers import class_statistics
from analysis.conditions.run import draw_sensitivity, shared_limit
from analysis.conditions.operations import analyze, charging_summary, penalty_summary, CONTEXTS


class ConditionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ev, cls.base = load_pairs()
        cls.frames, cls.cohorts, _ = matched_slices(ev)
        cls.stats = class_statistics(cls.frames)

    def test_four_panels_use_identical_scales_without_clipping(self):
        ymax = shared_limit(self.stats)
        fig, axes = plt.subplots(2, 2)
        try:
            for index, (ax, parameter) in enumerate(zip(axes.flat, PARAMETERS)):
                draw_sensitivity(ax, parameter, self.stats, self.cohorts[parameter], index, ymax)
                self.assertEqual(ax.get_ylim(), (0, ymax))
                np.testing.assert_array_equal(ax.get_yticks(), axes.flat[0].get_yticks())
                self.assertTrue(self.stats.q75.le(ymax).all())
                self.assertTrue(self.stats.mean_gap_pct.le(ymax).all())
            # A future larger IQR raises the single shared limit for every panel.
            future = self.stats.copy()
            future.loc[future.index[0], 'q75'] = 8.2
            self.assertGreater(shared_limit(future), 8.2)
        finally:
            plt.close(fig)

    def test_class_samples_are_fixed_within_each_panel(self):
        self.assertEqual(self.base.instance_id.nunique(), 43)
        for parameter, frame in self.frames.items():
            for route, group in frame.groupby('route_class'):
                sets = [set(level.instance_id) for _, level in group.groupby(parameter)]
                self.assertTrue(all(ids == sets[0] for ids in sets))
                self.assertEqual(len(sets[0]), self.cohorts[parameter]['route_classes'][route])

    def test_overleaf_bundle_uses_descriptive_existing_assets(self):
        folder = ROOT / 'analysis/conditions'
        with zipfile.ZipFile(folder / 'conditions.zip') as bundle:
            names = set(bundle.namelist())
            pdfs = {n.rsplit('/', 1)[-1] for n in names if n.endswith('.pdf')}
            self.assertEqual(pdfs, {'time_penalty.pdf', 'extra_time.pdf', 'battery.pdf',
                                    'power.pdf', 'spacing.pdf', 'consumption.pdf',
                                    'penalty_parts.pdf', 'charge_split.pdf', 'rest_overlap.pdf',
                                    'early_charge.pdf', 'extra_breaks.pdf'})
            for name in names:
                if name.endswith('.tex'):
                    content = bundle.read(name).decode()
                    for path in re.findall(r'\\includegraphics(?:\[[^]]*\])?\s*\{([^}]+)\}', content):
                        self.assertTrue(path in names or 'figures/conditions/' + path in names, path)
            self.assertIsNone(bundle.testzip())
            self.assertIn('tables/conditions/penalty_summary.tex', names)
            self.assertIn('operational_paragraph.tex', names)
            # Draft prose and captions must reference labels included in the bundle.
            content = '\n'.join(bundle.read(n).decode() for n in names if n.endswith('.tex'))
            labels = set(re.findall(r'\\label\{([^}]+)\}', content))
            references = set(re.findall(r'\\(?:sub)?ref\{([^}]+)\}', content))
            self.assertFalse(references - labels, references - labels)
        metadata = json.loads((folder / 'audit.json').read_text())
        self.assertEqual(metadata['sensitivity_y_limits'], [0, shared_limit(self.stats)])

    def test_operational_components_and_physical_charging(self):
        data, events, _, _ = analyze(self.base)
        self.assertEqual(len(data), 43)
        np.testing.assert_allclose(data.penalty_minutes, data.outside_minutes + data.extra_break_minutes,
                                   rtol=0, atol=1e-6)
        # A fully synchronized example still has four additional 45-minute breaks.
        outlier = data.set_index('instance_id').loc['med_cl3_cu13_Balanced']
        self.assertAlmostEqual(outlier.outside_minutes, 0)
        self.assertAlmostEqual(outlier.extra_break_minutes, 180)
        np.testing.assert_allclose(events.physical_minutes,
                                   60 * (events.display_end_hours - events.display_start_hours),
                                   rtol=0, atol=1e-6)
        stats = charging_summary(events)
        for route, group in stats.groupby('route_class'):
            self.assertEqual(set(group.context), set(CONTEXTS))
            self.assertAlmostEqual(group.energy_share_pct.sum(), 100)
            self.assertAlmostEqual(group.stop_share_pct.sum(), 100)
        # Constant power: energy and physical-time shares must agree.
        all_stats = stats[stats.route_class.eq('all')]
        np.testing.assert_allclose(all_stats.energy_share_pct,
                                   100 * all_stats.physical_minutes / all_stats.physical_minutes.sum())
        summary = penalty_summary(data).set_index('route_class')
        for field in ['n', 'no_penalty', 'with_extra_breaks']:
            self.assertEqual(summary.loc['all', field], summary.loc[['short', 'med', 'long'], field].sum())
        for source, mean in [('outside_minutes', 'mean_outside_minutes'),
                             ('extra_break_minutes', 'mean_extra_break_minutes'),
                             ('penalty_minutes', 'mean_penalty_minutes')]:
            self.assertAlmostEqual(summary.loc['all', mean], data[source].sum() / 43)
        self.assertEqual(summary.loc['short', 'no_penalty'], 8)
        self.assertEqual(summary.loc['all', 'with_extra_breaks'], 11)
