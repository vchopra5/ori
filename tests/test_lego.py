import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ori.reconstruction.lego import compile_plan, save_run, generate
from ori.coaching.jobs import classify
from ori.coaching.server import library

FIXTURE = Path(__file__).resolve().parents[1] / 'examples/lego/bridge.json'


class LegoTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(FIXTURE.read_text())

    def test_bridge_connects_both_supports_and_counts_inventory(self):
        result = compile_plan(self.plan)
        self.assertEqual(len(result['connections']), 4)
        self.assertEqual(result['pieces'][1]['size'], [2, 1, 3])
        self.assertEqual(sum(p['count'] for p in result['inventory']), 4)
        self.assertEqual([c['a'] for c in result['connections'] if c['b'] == 'roof'], ['left', 'right'])

    def test_invalid_placements(self):
        for field, value in [('position', [0,0,0]), ('position', [0,0,2]),
                             ('position', [8,0,1]), ('position', [.5,0,1]),
                             ('position', [True,0,1]), ('rotation', 45), ('rotation', False)]:
            with self.subTest(field=field, value=value):
                plan = copy.deepcopy(self.plan);plan['steps'][1][field] = value
                with self.assertRaises(ValueError): compile_plan(plan)

    def test_occupied_studs_and_duplicate_placements(self):
        self.plan['steps'][2]['position'] = [0,0,1]
        with self.assertRaisesRegex(ValueError, 'overlaps'): compile_plan(self.plan)
        self.plan['steps'][2]['piece'] = 'left'
        with self.assertRaisesRegex(ValueError, 'exactly once'): compile_plan(self.plan)

    def test_unknown_and_unsupported_parts_rejected(self):
        self.plan['pieces'][0]['part'] = 'technic_pin'
        with self.assertRaisesRegex(ValueError, 'Unknown'): compile_plan(self.plan)
        self.plan['unsupported'] = ['Side-stud connection']
        with self.assertRaisesRegex(ValueError, 'Unsupported'): compile_plan(self.plan)

    def test_underside_connection(self):
        # A second plate attaches beneath the overhanging end of a top plate.
        self.plan['pieces'] = self.plan['pieces'][:3]
        self.plan['pieces'][0]['part'] = 'brick_1x1'
        self.plan['pieces'][1]['part'] = 'plate_1x2'
        self.plan['pieces'][2]['part'] = 'brick_1x1'
        self.plan['steps'] = self.plan['steps'][:3]
        for step, pos in zip(self.plan['steps'], [[0,0,0],[0,0,3],[1,0,0]]): step['position'] = pos
        result = compile_plan(self.plan)
        self.assertEqual(len(result['connections']), 2)

    def test_artifacts_library_and_mujoco_compile(self):
        import mujoco
        with TemporaryDirectory() as directory, patch('ori.coaching.server.ROOT', Path(directory)):
            base = Path(directory)/'output/lego_demo'
            report = save_run(self.plan, base, 'https://youtu.be/FdBTwMuh1mU')
            model = mujoco.MjModel.from_xml_path(str(base/'assembly.xml'))
            self.assertEqual(model.njnt, 0)  # All pieces rigidly fixed to anchored assembly.
            self.assertEqual(model.nbody, 6)
            self.assertFalse(report['video_match_verified'])
            items = library()
            self.assertEqual(items[0]['kind'], 'lego')
            self.assertEqual(items[0]['source_url'], report['source_url'])

    def test_generation_retries_validation_and_keeps_uncertainties(self):
        bad = copy.deepcopy(self.plan);bad['steps'][1]['position'] = [0,0,0]
        self.plan['uncertainties'] = ['Base color obscured']
        client = MagicMock()
        client.models.generate_content.side_effect = [SimpleNamespace(text=json.dumps(p)) for p in [bad, self.plan]]
        with TemporaryDirectory() as directory:
            result = generate(client, 'https://youtu.be/FdBTwMuh1mU', Path(directory), 'test')
            self.assertEqual(client.models.generate_content.call_count, 2)
            self.assertEqual(result['uncertainties'], ['Base color obscured'])
            self.assertTrue((Path(directory)/'lego-error-1.json').exists())

    def test_unsupported_video_stops_without_retrying_or_publishing(self):
        from ori.reconstruction.lego import UnsupportedAssembly
        self.plan['unsupported'] = ['Two hinge tops and tilted roof plates']
        client = MagicMock()
        client.models.generate_content.return_value = SimpleNamespace(text=json.dumps(self.plan))
        with TemporaryDirectory() as directory:
            base = Path(directory)
            with self.assertRaises(UnsupportedAssembly):
                generate(client, 'https://youtu.be/5Q6UToMwGws', base, 'test')
            self.assertEqual(client.models.generate_content.call_count, 1)
            self.assertTrue((base/'lego-unsupported.json').exists())
            self.assertFalse((base/'lego-playback.json').exists())

    def test_classify_lego(self):
        client = MagicMock()
        client.models.generate_content.return_value = SimpleNamespace(text='{"kind":"lego","title":"Bridge","summary":"LEGO build"}', model_dump_json=lambda **_: '{}')
        with TemporaryDirectory() as directory:
            self.assertEqual(classify(client, 'https://youtu.be/FdBTwMuh1mU', Path(directory))['kind'], 'lego')


if __name__ == '__main__': unittest.main()
