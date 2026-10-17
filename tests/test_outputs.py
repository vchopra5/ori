import base64
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ori.reconstruction.batching import atomic_json
from ori.reconstruction.outputs import (
    clip_directory, migrate_outputs, new_run, resolve_checkpoint, save_request,
)


VIDEO = 'GC_Szxdqh2Y'


class OutputTests(unittest.TestCase):
    def test_migration_preserves_outputs_and_resume_images_and_is_repeatable(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            plan = root / f'{VIDEO}.json'
            plan.write_text('{"steps":[]}\n')
            old_run = root / f'{VIDEO}.animation-abc'
            old_run.mkdir()
            image = old_run / 'clip-1.front.png'
            image.write_bytes(b'unchanged pixels')
            checkpoint = old_run / 'progress.checkpoint.json'
            original = {'completed_seconds': 180, 'steps': [{'commands': 'test'}],
                        'pending_feedback': {'images': [{'path': str(image)}]}}
            atomic_json(checkpoint, original)
            checkpoint_bytes = checkpoint.read_bytes()
            (old_run / f'{VIDEO}.json').write_bytes(plan.read_bytes())
            legacy = root / f'{VIDEO}.clip-0-30.abc.response.json'
            legacy.write_text('{"raw":"keep"}')
            (root / 'personal-notes.json').write_text('{}')

            moves = migrate_outputs(root)
            moved = resolve_checkpoint(checkpoint)
            self.assertEqual(moved, root / 'runs' / VIDEO / 'animation-abc/progress.checkpoint.json')
            state = json.loads(moved.read_text())
            self.assertEqual(state['steps'], original['steps'])
            self.assertEqual(state['completed_seconds'], 180)
            self.assertEqual(Path(state['pending_feedback']['images'][0]['path']).read_bytes(), b'unchanged pixels')
            self.assertEqual((moved.parent / 'debug/legacy/checkpoint-before-migration.json').read_bytes(), checkpoint_bytes)
            self.assertEqual(plan.read_text(), '{"steps":[]}\n')
            self.assertEqual((root / 'archive' / VIDEO / legacy.name).read_text(), '{"raw":"keep"}')
            self.assertTrue((root / 'personal-notes.json').exists())
            self.assertFalse(old_run.exists())
            self.assertEqual(migrate_outputs(root), moves)
            self.assertEqual(resolve_checkpoint(checkpoint), moved)

    def test_migration_refuses_to_overwrite_existing_history(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / f'{VIDEO}.animation-abc/progress.checkpoint.json'
            target = root / f'runs/{VIDEO}/animation-abc/progress.checkpoint.json'
            atomic_json(source, {'steps': ['source']})
            atomic_json(target, {'steps': ['target']})
            with self.assertRaises(FileExistsError):
                migrate_outputs(root)
            self.assertTrue(source.exists())
            self.assertEqual(json.loads(target.read_text())['steps'], ['target'])

    def test_runs_and_resumed_clip_logs_do_not_overwrite(self):
        with TemporaryDirectory() as directory:
            base = Path(directory) / f'{VIDEO}.json'
            first = new_run(base, 'animation')
            second = new_run(base, 'animation')
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, (base.parent / 'runs' / VIDEO).resolve())
            old = clip_directory(first, 175, 210)
            (old / 'turn-01.response.json').write_text('original')
            new = clip_directory(first, 175, 210)
            self.assertEqual(new.name, 'pass-002')
            self.assertEqual((old / 'turn-01.response.json').read_text(), 'original')
            self.assertEqual(list(base.parent.iterdir()), [base.parent / 'runs'])

    def test_request_logs_reference_images_without_altering_api_payload(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / 'preview.png'
            image.write_bytes(b'pixels')
            encoded = base64.b64encode(b'pixels').decode()
            request = {'input': [{'type': 'image', 'mime_type': 'image/png', 'data': encoded}]}
            log = root / 'debug/turn-01.request.json'
            save_request(log, request, [{'path': str(image)}])
            logged = json.loads(log.read_text())['input'][0]
            self.assertNotIn('data', logged)
            self.assertEqual((log.parent / logged['data_file']).read_bytes(), image.read_bytes())
            self.assertEqual(request['input'][0]['data'], encoded)
            # Also preserve pixels if the request contains an image not in the catalog.
            save_request(log, request, [])
            logged = json.loads(log.read_text())['input'][0]
            self.assertEqual((log.parent / logged['data_file']).read_bytes(), b'pixels')

    def test_symbolic_trial_exports_fold_and_keeps_diagnostics_in_run(self):
        from ori.reconstruction.symbolic import trial

        def reply(value):
            return SimpleNamespace(output_text=json.dumps(value), model_dump=lambda **_: value)

        initial = {'ok': True, 'fold': {'vertices_coords': []}, 'state': {}}
        compiled = {'ok': True, 'fold': {'vertices_coords': [[0, 0, 0]], 'file_frames': []}, 'state': {}}
        client = MagicMock()
        client.interactions.create.return_value = reply({'steps': [{'id': 'fold1'}], 'done': True})
        with TemporaryDirectory() as directory:
            base = Path(directory) / f'{VIDEO}.json'
            base.write_text('{"engine":"orisim3d"}')

            def render(_, path):
                image = path.with_suffix('.png')
                image.write_bytes(b'image')
                return [{'path': str(image)}]

            with patch.object(trial, 'plan_path', return_value=base), \
                 patch.object(trial, 'compile_plan', side_effect=[initial, compiled]), \
                 patch.object(trial, 'render', side_effect=render), \
                 patch.object(trial, 'load_settings', return_value=SimpleNamespace(gemini_api_key='fake')), \
                 patch.object(trial.genai, 'Client') as factory, redirect_stdout(io.StringIO()):
                factory.return_value.__enter__.return_value = client
                trial.main()
            self.assertEqual(json.loads(base.with_suffix('.fold').read_text()), compiled['fold'])
            self.assertEqual(json.loads(base.read_text()), {'engine': 'orisim3d'})
            runs = list((base.parent / 'runs' / VIDEO).iterdir())
            self.assertEqual(len(runs), 1)
            run = runs[0]
            self.assertEqual(json.loads((run / 'plan.json').read_text())['steps'], [{'id': 'fold1'}])
            self.assertTrue((run / 'debug/call-01/model.request.json').exists())
            self.assertTrue((run / 'debug/call-01/compiler.json').exists())
            self.assertEqual(json.loads((run / 'status.json').read_text())['compiled_steps'], 1)


if __name__ == '__main__':
    unittest.main()
