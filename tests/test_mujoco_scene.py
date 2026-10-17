"""Check generated collision assets and actual gravity/contact behavior."""
import json
from pathlib import Path
import tempfile
import unittest

from ori.reconstruction.mujoco_scene import render, validate


def scene():
    return dict(title='Drop and move', duration=1.5, approximations=[],
                steps=[dict(start=0, end=1.5, title='Drop')], objects=[
                    dict(id='block', mode='dynamic', position=[0, 0, .5], mass=.1,
                         parts=[dict(position=[0,0,0], size=[.05,.05,.05], rgba=[1,1,1,1])]),
                    dict(id='tool', mode='guided', position=[1,0,.5],
                         parts=[dict(position=[0,0,0], size=[.05,.05,.05], rgba=[1,0,0,1])],
                         keys=[dict(time=0, position=[1,0,.5], euler=[0,0,0]),
                               dict(time=1, position=[1,0,1], euler=[0,0,1])])])


class SceneTests(unittest.TestCase):
    def test_gravity_contact_and_guided_track(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = render(scene(), output, movie=False)
            trajectory = json.loads((output/'trajectory.json').read_text())
            self.assertGreater(trajectory[0]['qpos'][2], .49)
            self.assertAlmostEqual(trajectory[-1]['qpos'][2], .05, delta=.003)
            self.assertAlmostEqual(trajectory[-1]['mocap_pos'][0][2], 1, places=5)
            self.assertGreater(report['contact_samples'], 0)
            self.assertLess(report['max_penetration_m'], .01)
            self.assertEqual(len(list((output/'meshes').glob('*.obj'))), 2)

    def test_rejects_nonfinite_geometry_and_hidden_colliders(self):
        bad = scene()
        bad['objects'][0]['parts'][0]['size'][0] = float('nan')
        with self.assertRaises(ValueError):
            validate(bad)
        bad = scene()
        bad['objects'][0]['visible'] = [[0,1]]
        with self.assertRaisesRegex(ValueError, 'noncolliding'):
            validate(bad)


if __name__ == '__main__':
    unittest.main()
