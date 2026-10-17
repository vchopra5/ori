"""Layer order must come from motion and remain a physical constraint."""
import copy
import unittest

import numpy as np

from ori.reconstruction.fold_commands import FoldHarness
from ori.reconstruction.fold_layers import ordered


def half(angle=180):
    return dict(crease=[[-1, 0, 0], [1, 0, 0]], normal=[0, 0, 1],
                moving_side='left', angle_degrees=angle)


def tip(layers='all', angle=-180):
    return dict(crease=[[-1, -.5, 0], [1, -.5, 0]], normal=[0, 0, 1],
                moving_side='right', angle_degrees=angle, layers=layers)


def material_top(panels):
    return float(np.mean(ordered(panels)[-1].uv[:, 1]))


class LayerTests(unittest.TestCase):
    def test_first_fold_side_determines_contact_order(self):
        for angle in (180, -180):
            with self.subTest(angle=angle):
                h = FoldHarness()
                poses = h.fold(half(angle))
                self.assertEqual(len(h.layer_state()['contacts']), 1)
                self.assertEqual(material_top(h.panels) > 0, angle > 0)
                self.assertEqual(material_top(poses[-1]) > 0, angle > 0)
                for p in h.panels:
                    np.testing.assert_allclose(p.xyz[:, 2], 0, atol=1e-10)

    def test_packet_turnover_reverses_internal_order(self):
        h = FoldHarness(); h.fold(half())
        h.fold(tip())
        folded_tip = [p for p in h.panels if np.min(abs(p.uv[:, 1])) >= .5 - 1e-8]
        self.assertEqual(len(folded_tip), 2)
        self.assertLess(material_top(folded_tip), 0)
        self.assertGreater(material_top(h.panels[:2]), 0)  # stationary packet retains order

    def test_top_layer_folds_alone_without_tearing_or_moving_other_material(self):
        h = FoldHarness(); h.fold(half())
        h.fold(tip('top'))
        for p in h.panels:
            if np.mean(p.uv[:, 1]) < 0:
                np.testing.assert_allclose(p.xyz[:, :2], p.uv, atol=1e-10)
        self.assertLess(h.metrics()['max_seam_gap'], 1e-10)
        self.assertGreater(len(h.layer_state()['contacts']), 1)

    def test_buried_layer_cannot_pass_through_covering_layer(self):
        h = FoldHarness(); h.fold(half())
        before, contacts, history = h.state(), h.layer_state(), copy.deepcopy(h.history)
        result = h.execute([tip('bottom')])
        self.assertFalse(result['ok'])
        self.assertIn('pass through', result['error'])
        self.assertEqual(h.state(), before)
        self.assertEqual(h.layer_state(), contacts)
        self.assertEqual(h.history, history)

    def test_bottom_layer_can_fold_away_from_stack(self):
        h = FoldHarness(); h.fold(half())
        h.fold(tip('bottom', 180))
        self.assertLess(h.metrics()['max_seam_gap'], 1e-10)

    def test_selection_respects_normal_and_explicit_panel_ids(self):
        h = FoldHarness(); h.fold(half())
        top_id = ordered(h.panels)[-1].id
        a, b = copy.deepcopy(h), copy.deepcopy(h)
        a.fold(tip([top_id]))
        command = tip('bottom'); command['normal'] = [0, 0, -1]; command['moving_side'] = 'left'
        b.fold(command)
        self.assertEqual(a.state(), b.state())
        before = h.state()
        with self.assertRaisesRegex(ValueError, 'unknown'):
            h.fold(tip(['nonexistent']))
        self.assertEqual(h.state(), before)

    def test_unfold_removes_obsolete_contacts(self):
        h = FoldHarness(); h.fold(half())
        command = half(-180); command['moving_side'] = 'right'; command['layers'] = 'top'
        h.fold(command)
        self.assertEqual(h.layer_state()['contacts'], [])
        for p in h.panels:
            np.testing.assert_allclose(p.xyz[:, :2], p.uv, atol=1e-10)

    def test_selected_layer_still_cannot_tear_shared_material_seam(self):
        h = FoldHarness(); h.fold(half())
        before = h.state()
        command = dict(crease=[[0, -1, 0], [0, 1, 0]], normal=[0, 0, 1],
                       moving_side='left', angle_degrees=180, layers='top')
        with self.assertRaisesRegex(ValueError, 'Paper constraint failed'):
            h.fold(command)
        self.assertEqual(h.state(), before)

    def test_renderer_uses_contact_order_even_when_input_is_reversed(self):
        h = FoldHarness(); h.fold(half())
        expected = [p.id for p in ordered(h.panels)]
        self.assertEqual([p.id for p in ordered(h.panels[::-1])], expected)
        self.assertEqual([p.id for p in ordered(h.panels, [0, 0, -1])], expected[::-1])

    def test_cycle_is_reported_rather_than_arbitrarily_rendered(self):
        h = FoldHarness(); h.fold(half()); h.fold(tip())
        panels = copy.deepcopy(h.panels[:3])
        for i, p in enumerate(panels):
            p.contacts = {panels[(i + 1) % 3].id: [0, 0, 1]}
        with self.assertRaisesRegex(ValueError, 'cycle'):
            ordered(panels)


if __name__ == '__main__':
    unittest.main()
