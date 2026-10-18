import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from ori.coaching.demo_hints import load_hints
from ori.coaching.jobs import Progress, run_paper, classify
from ori.coaching import server


class DemoHintsTests(unittest.TestCase):
    def test_demo_pacing_selects_three_or_four_steps_and_sleeps_only_there(self):
        hints = dict(random_step_pauses=True, rehearsal_sequence=[{} for _ in range(7)])
        def run_fake(*args, **kwargs):
            for call in range(1, 8):
                kwargs['observer']('proposal', call=call, text='{}')
            return dict(status='max_calls', accepted_folds=0)
        with TemporaryDirectory() as directory, patch('ori.coaching.jobs.load_hints', return_value=hints), patch('ori.coaching.jobs.run', side_effect=run_fake), patch('ori.coaching.jobs.time.sleep') as sleep:
            base = Path(directory)
            progress = Progress(base, 'https://youtu.be/10KurnMH_6o')
            run_paper(MagicMock(), progress.data['url'], base, progress, dict(title='Fox', summary='Fox face'))
            pacing = json.loads((base / 'demo-pacing.json').read_text())
            self.assertIn(len(pacing), [3, 4])
            self.assertTrue(all(3 <= delay <= 5 for delay in pacing.values()))
            self.assertEqual(sleep.call_count, len(pacing))
            self.assertFalse(any(event['kind'] == 'demo_pause' for event in progress.data['events']))

    def test_classification_hint_skips_api_only_for_exact_video(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            route = dict(kind='origami', title='Paper Fox Face', summary='Fold a fox face')
            path = base / 'hints.json'
            path.write_text(json.dumps(dict(version=1, videos={'10KurnMH_6o': {'classification': route}})))
            client = MagicMock()
            client.models.generate_content.return_value.text = json.dumps(route)
            client.models.generate_content.return_value.model_dump_json.return_value = '{}'
            with patch('ori.coaching.jobs.load_hints', side_effect=lambda url: load_hints(url, path)):
                self.assertEqual(classify(client, 'https://youtu.be/10KurnMH_6o?t=5', base), route)
                client.models.generate_content.assert_not_called()
                classify(client, 'https://youtu.be/abcdefghijk', base)
                call = client.models.generate_content.call_args.kwargs
                self.assertEqual(call['model'], 'gemini-4-argon')
                self.assertEqual(call['contents'][0].video_metadata.fps, 2)

    def test_model_override_is_scoped_and_resume_keeps_saved_model(self):
        with TemporaryDirectory() as directory:
            hints_path = Path(directory) / 'hints.json'
            hints_path.write_text(json.dumps(dict(version=1, videos={
                '10KurnMH_6o': {'model': 'gemini-3.8-flash', 'video_sampling_fps': 0.5}})))
            for video, expected in [('10KurnMH_6o', 'gemini-3.8-flash'),
                                    ('abcdefghijk', 'gemini-4-argon')]:
                base = Path(directory) / video
                base.mkdir()
                url = 'https://youtu.be/' + video
                with patch('ori.coaching.jobs.load_hints', side_effect=lambda url: load_hints(url, hints_path)), patch('ori.coaching.jobs.run', return_value=dict(status='max_calls', accepted_folds=0)) as runner:
                    progress = Progress(base, url)
                    run_paper(MagicMock(), url, base, progress, dict(title='Paper', summary='Paper'), max_calls=1)
                    self.assertEqual(runner.call_args.args[2], expected)
                    fps = 0.5 if video == '10KurnMH_6o' else 2
                    self.assertEqual(runner.call_args.kwargs['video_sampling_fps'], fps)
                    (base / 'config.json').write_text(json.dumps(dict(
                        task='saved task', context_policy={'version': 1},
                        continue_on_blocked=True, model=expected, thinking_level='low', video_sampling_fps=fps)))
                with patch('ori.coaching.jobs.load_hints', side_effect=AssertionError('Resume must not reload hints')), patch('ori.coaching.jobs.run', return_value=dict(status='max_calls', accepted_folds=0)) as runner:
                    run_paper(MagicMock(), url, base, progress, dict(title='Paper', summary='Paper'), max_calls=1, resume=True)
                    self.assertEqual(runner.call_args.args[2], expected)
                    self.assertEqual(runner.call_args.kwargs['video_sampling_fps'], fps)

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
