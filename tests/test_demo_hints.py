import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from ori.coaching.demo_hints import load_hints
from ori.coaching.jobs import Progress, run_paper
from ori.coaching import server


class DemoHintsTests(unittest.TestCase):
    def test_thinking_override_is_optional_and_explicit_caller_wins(self):
        for hints, explicit, expected in [(None, None, 'medium'),
                                          ({'thinking_level': 'low'}, None, 'low'),
                                          ({'thinking_level': 'low'}, 'high', 'high')]:
            with self.subTest(expected=expected), TemporaryDirectory() as directory, patch('ori.coaching.jobs.load_hints', return_value=hints), patch('ori.coaching.jobs.run', return_value=dict(status='max_calls', accepted_folds=0)) as runner:
                base = Path(directory)
                progress = Progress(base, 'https://youtu.be/10KurnMH_6o')
                run_paper(MagicMock(), progress.data['url'], base, progress, dict(title='Fox', summary='Fox face'), max_calls=1, thinking_level=explicit)
                self.assertEqual(runner.call_args.kwargs['thinking_level'], expected)

    def test_exact_video_matching_and_absent_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'hints.json'
            self.assertIsNone(load_hints('https://youtu.be/10KurnMH_6o', path))
            path.write_text(json.dumps(dict(version=1, videos={'10KurnMH_6o': {'guidance': ['fox only']}})))
            for url in ['https://youtu.be/10KurnMH_6o?t=5',
                        'https://www.youtube.com/watch?v=10KurnMH_6o&feature=shared',
                        'https://www.youtube.com/shorts/10KurnMH_6o']:
                self.assertEqual(load_hints(url, path)['guidance'], ['fox only'])
            self.assertIsNone(load_hints('https://youtube.com/watch?v=abcdefghijk&hint=10KurnMH_6o', path))
            with self.assertRaises(ValueError):
                load_hints('https://example.com/watch?v=10KurnMH_6o', path)

    def test_hints_enter_task_and_snapshot_but_never_execute_commands(self):
        hints = dict(video_id='10KurnMH_6o', guidance=['rehearsal'], reference_commands=[{'invalid': True}])
        with TemporaryDirectory() as directory, patch('ori.coaching.jobs.load_hints', return_value=hints), patch('ori.coaching.jobs.run', return_value=dict(status='max_calls', accepted_folds=0)) as runner:
            base = Path(directory)
            progress = Progress(base, 'https://youtu.be/10KurnMH_6o')
            run_paper(MagicMock(), progress.data['url'], base, progress, dict(title='Fox', summary='Fox face'), max_calls=1)
            self.assertIn(json.dumps(hints), runner.call_args.kwargs['task'])
            self.assertEqual(json.loads((base / 'demo-hints.json').read_text()), hints)
            self.assertEqual(progress.data['commands'], [])

    def test_library_fresh_run_flag_is_scoped_to_configured_video(self):
        with TemporaryDirectory() as directory, patch.object(server, 'ROOT', Path(directory)):
            root = Path(directory)
            hints = root / '.local/demo-hints.json'
            hints.parent.mkdir()
            hints.write_text(json.dumps(dict(version=1, videos={'10KurnMH_6o': {'prefer_fresh_run': True}})))
            for video in ['10KurnMH_6o', 'abcdefghijk']:
                base = root / 'output/fold_trials/runs' / video / 'complete'
                base.mkdir(parents=True)
                (base / 'result.json').write_text(json.dumps(dict(status='model_claimed_done', accepted_folds=1, video_url='https://youtu.be/' + video)))
                (base / 'commands.json').write_text('{"commands":[]}')
            items = {item['source_url']: item for item in server.library()}
            self.assertTrue(items['https://youtu.be/10KurnMH_6o']['prefer_fresh_run'])
            self.assertFalse(items['https://youtu.be/abcdefghijk']['prefer_fresh_run'])
