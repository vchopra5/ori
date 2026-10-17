"""Behavioral checks for executable paper folds and model feedback."""
import copy
import json
from pathlib import Path
import unittest

import numpy as np

from ori.reconstruction.fold_commands import FoldHarness, Panel, crossings

ROOT = Path(__file__).resolve().parents[1]


def fold(**changes):
    return dict(name='half', crease=[[-1, 0, 0], [1, 0, 0]],
                normal=[0, 0, 1], moving_side='left', angle_degrees=180, **changes)


class FoldCommandTests(unittest.TestCase):
    def test_half_fold_matches_analytic_reflection(self):
        harness = FoldHarness()
        harness.fold(fold())
        for panel in harness.panels:
            for uv, xyz in zip(panel.uv, panel.xyz):
                np.testing.assert_allclose(xyz, [uv[0], -abs(uv[1]), 0], atol=1e-10)
        self.assertAlmostEqual(harness.metrics()['material_area'], 2)
        self.assertLess(harness.metrics()['max_seam_gap'], 1e-10)

    def test_fox_ears_are_symmetric_and_above_forehead(self):
        commands = json.loads((ROOT / 'examples/fold_commands/fox.json').read_text())['commands']
        harness = FoldHarness()
        feedback = harness.execute(commands)
        self.assertTrue(feedback['ok'], feedback)
        tips = {}
        for panel in harness.panels:
            for uv, xyz in zip(panel.uv, panel.xyz):
                if abs(uv[0]) == 1:
                    tips[int(uv[0])] = xyz
        self.assertGreater(tips[-1][1], .2)
        np.testing.assert_allclose(tips[-1] * [-1, 1, 1], tips[1], atol=1e-10)
        self.assertLess(feedback['metrics']['max_length_error'], 1e-10)
        self.assertLess(feedback['metrics']['max_seam_gap'], 1e-10)

    def test_invalid_command_returns_accepted_prefix_and_leaves_state_intact(self):
        harness = FoldHarness()
        harness.fold(fold())
        before = copy.deepcopy(harness.state())
        bad = fold(); bad['crease'] = [[4, 0, 0], [4, 1, 0]]
        result = harness.execute([bad])
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['accepted_commands']), 1)
        self.assertEqual(result['state'], before)
        self.assertEqual(harness.state(), before)

    def test_bent_paper_cannot_be_cut_away_from_hinge(self):
        harness = FoldHarness()
        command = fold(); command['angle_degrees'] = 90
        harness.fold(command)
        before = harness.state()
        command = fold(); command['crease'] = [[.2, -1, 0], [.2, 1, 0]]
        with self.assertRaisesRegex(ValueError, 'hinge axis'):
            harness.fold(command)
        self.assertEqual(harness.state(), before)

    def test_crossing_detection_distinguishes_piercing_from_flat_layers(self):
        uv = np.array([[0., 0.], [1., 0.], [0., 1.]])
        flat = Panel(uv, np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]))
        through = Panel(uv, np.array([[.2, .2, -1.], [.3, .2, 1.], [.2, .3, 1.]]))
        self.assertTrue(crossings([through], [flat]))
        self.assertFalse(crossings([flat], [flat]))

    def test_nonfinite_or_degenerate_commands_are_rejected(self):
        for field, value in [('angle_degrees', float('nan')), ('normal', [0, 0, 0]),
                             ('crease', [[0, 0, 0], [0, 0, 0]]), ('moving_side', 'maybe')]:
            with self.subTest(field=field):
                harness = FoldHarness()
                command = fold(); command[field] = value
                before = harness.state()
                with self.assertRaises(ValueError):
                    harness.fold(command)
                self.assertEqual(harness.state(), before)


if __name__ == '__main__':
    unittest.main()
