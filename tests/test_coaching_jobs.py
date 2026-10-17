"""Live observers must preserve the harness feedback and committed prefix."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ori.coaching.jobs import Progress, classify, run_paper
from ori.coaching.paper_playback import compile_playback
from ori.coaching.server import job_path, start_job, paper_sources, resume_job
from ori.reconstruction.fold_trial import run
from ori.reconstruction.fold_audit import audit


class LiveJobTests(unittest.TestCase):
    def test_live_prefix_matches_replay_and_feedback_audit(self):
        command = dict(name='Fold the top down', crease=[[-1, 0, 0], [1, 0, 0]],
                       normal=[0, 0, 1], moving_side='left', angle_degrees=180)
        bad = dict(command, angle_degrees=999)
        text = json.dumps(dict(commands=[command, bad], done=False))
        response = SimpleNamespace(status='completed', output_text=text,
                                   model_dump=lambda **_: dict(output_text=text))
        client = MagicMock()
        client.interactions.create.return_value = response
        with TemporaryDirectory() as directory:
            base = Path(directory)
            progress = Progress(base, 'https://youtu.be/FdBTwMuh1mU')
            report = run(client, progress.data['url'], 'gemini-4-argon', base,
                         max_calls=1, observer=progress.observe, export=False)
            self.assertEqual(report['accepted_folds'], 1)
            self.assertEqual([e['kind'] for e in progress.data['events']],
                             ['classifying', 'working', 'proposal', 'accepted', 'rejected', 'finished'])
            playback = json.loads((base / 'playback.json').read_text())
            expected = compile_playback([command])
            self.assertEqual(playback['states'], expected['states'])
            self.assertEqual(playback['motions'], expected['motions'])
            self.assertTrue(audit(base)['passed'])
            self.assertNotIn('999', json.dumps(playback))

    def test_live_blocked_responses_continue_past_24_calls_without_reset(self):
        command = dict(name='Fold', crease=[[-1, 0, 0], [1, 0, 0]],
                       normal=[0, 0, 1], moving_side='left', angle_degrees=180)
        outputs = [dict(commands=[command], done=False)] + [dict(commands=[], blocked='Replanning')] * 26 + [dict(commands=[], done=True)]
        def response(*args, **kwargs):
            text = json.dumps(outputs.pop(0))
            return SimpleNamespace(status='completed', output_text=text, model_dump=lambda **_: dict(output_text=text))
        with TemporaryDirectory() as directory, patch('ori.reconstruction.fold_trial.generate_content', side_effect=response):
            base = Path(directory)
            progress = Progress(base, 'https://youtu.be/YqxG296KMz8')
            report = run_paper(MagicMock(), progress.data['url'], base, progress,
                               dict(title='Turtle', summary='Paper turtle'), max_calls=40)
            self.assertEqual(report['status'], 'model_claimed_done')
            self.assertEqual(report['calls'], 28)
            self.assertEqual(progress.data['commands'], [command])
            self.assertEqual(progress.playback['states'], compile_playback([command])['states'])
            self.assertEqual(progress.data['attempt'], 1)
            self.assertTrue(audit(base)['passed'])
            self.assertIn('compacted', [e['kind'] for e in progress.data['events']])
            self.assertFalse((base / 'attempt-02').exists())

    def test_live_budget_is_configurable_and_checkpoint_continues_same_paper(self):
        command = dict(name='Fold', crease=[[-1, 0, 0], [1, 0, 0]],
                       normal=[0, 0, 1], moving_side='left', angle_degrees=180)
        inverse = dict(command, name='Unfold', moving_side='right', angle_degrees=-180, layers=['paper/m'])
        outputs = [dict(commands=[command], done=False), dict(commands=[inverse], done=True)]
        def response(*args, **kwargs):
            text = json.dumps(outputs.pop(0))
            return SimpleNamespace(status='completed', output_text=text, model_dump=lambda **_: dict(output_text=text))
        with TemporaryDirectory() as directory, patch('ori.reconstruction.fold_trial.generate_content', side_effect=response), patch.dict('os.environ', {'ORI_LIVE_MAX_CALLS': '1'}):
            base = Path(directory)
            progress = Progress(base, 'https://youtu.be/YqxG296KMz8')
            route = dict(title='Turtle', summary='Paper turtle')
            progress.data['route'] = route
            first = run_paper(MagicMock(), progress.data['url'], base, progress, route)
            self.assertEqual(first['status'], 'partial')
            self.assertEqual(progress.data['max_calls'], 1)
            progress = Progress(base, progress.data['url'], resume=True)
            result = run_paper(MagicMock(), progress.data['url'], base, progress, route, max_calls=512, resume=True)
            self.assertEqual(progress.data['max_calls'], 513)
            self.assertEqual(result['calls'], 2)
            self.assertEqual(progress.data['commands'], [command, inverse])
            self.assertEqual(progress.playback['states'], compile_playback([command, inverse])['states'])
            self.assertTrue(audit(base)['passed'])
            self.assertTrue((base / 'result-through-1.json').exists())

    def test_transport_failure_does_not_reset_paper_or_loop(self):
        response = SimpleNamespace(status='incomplete', output_text='', model_dump=lambda **_: {})
        with TemporaryDirectory() as directory, patch('ori.reconstruction.fold_trial.generate_content', return_value=response) as generate, patch.dict('os.environ', {}, clear=True):
            base = Path(directory)
            progress = Progress(base, 'https://youtu.be/YqxG296KMz8')
            result = run_paper(MagicMock(), progress.data['url'], base, progress, dict(title='Turtle', summary='Paper turtle'))
            self.assertEqual(progress.data['max_calls'], 512)
            self.assertEqual(result['stop_reason'], 'incomplete_api_response')
            self.assertEqual(generate.call_count, 1)
            self.assertTrue(audit(base)['passed'])

    def test_failed_trials_are_not_reused_as_finished_tutorials(self):
        with TemporaryDirectory() as directory, patch('ori.coaching.server.ROOT', Path(directory)):
            root = Path(directory) / 'output/fold_trials/runs/video'
            for name, status in [('failed', 'model_reported_blocked'), ('partial', 'partial')]:
                base = root / name
                base.mkdir(parents=True)
                (base / 'result.json').write_text(json.dumps(dict(status=status, accepted_folds=6)))
            self.assertEqual(paper_sources(), {})
            base = root / 'complete'
            base.mkdir()
            (base / 'result.json').write_text(json.dumps(dict(status='model_claimed_done', accepted_folds=4)))
            sources = paper_sources()
            self.assertEqual(len(sources), 1)
            self.assertEqual(next(iter(sources.values()))[0], base)

    def test_classifier_uses_video_and_rejects_unknown_engine(self):
        client = MagicMock()
        client.models.generate_content.return_value = SimpleNamespace(
            text='{"kind":"origami","title":"Owl","summary":"Folding paper"}',
            model_dump_json=lambda **_: '{}')
        with TemporaryDirectory() as directory:
            self.assertEqual(classify(client, 'https://youtu.be/FdBTwMuh1mU', Path(directory))['kind'], 'origami')
            request = client.models.generate_content.call_args.kwargs
            self.assertEqual(request['model'], 'gemini-4-argon')
            self.assertEqual(request['contents'][0].file_data.file_uri, 'https://youtu.be/FdBTwMuh1mU')
            client.models.generate_content.return_value.text = '{"kind":"execute_shell"}'
            with self.assertRaises(ValueError):
                classify(client, 'url', Path(directory))

    def test_submission_validates_url_and_limits_active_workers(self):
        with TemporaryDirectory() as directory, patch('ori.coaching.server.ROOT', Path(directory)), \
                patch('ori.coaching.server.JOB_PROCESS', None), \
                patch('ori.coaching.server.subprocess.Popen') as process:
            with self.assertRaises(ValueError):
                start_job('https://example.com/not-youtube')
            process.assert_not_called()
            job = start_job('https://youtu.be/FdBTwMuh1mU')
            self.assertEqual(job['status'], 'queued')
            self.assertEqual(job_path(job['id']).name, job['id'])
            invocation = process.call_args.args[0]
            self.assertIn('ori.coaching.jobs', invocation)
            process.return_value.poll.return_value = None
            with self.assertRaises(RuntimeError):
                start_job('https://youtu.be/FdBTwMuh1mU')

    def test_resume_api_reuses_job_and_preserves_saved_artifacts(self):
        with TemporaryDirectory() as directory, patch('ori.coaching.server.ROOT', Path(directory)), patch('ori.coaching.server.JOB_PROCESS', None), patch('ori.coaching.server.subprocess.Popen') as process:
            identifier = 'live-' + 'a'*32
            base = Path(directory) / 'output/fold_trials/runs/video' / identifier
            base.mkdir(parents=True)
            job = dict(id=identifier, url='https://youtu.be/YqxG296KMz8', status='partial', accepted=1, commands=[{'name':'saved fold'}])
            (base / 'job.json').write_text(json.dumps(job))
            (base / 'config.json').write_text('{"context_policy":{"version":1}}')
            (base / 'checkpoint.json').write_text('preserved checkpoint')
            (base / 'playback.json').write_text('preserved playback')
            result = resume_job(identifier)
            self.assertEqual(result['id'], identifier)
            self.assertEqual(result['accepted'], 1)
            self.assertEqual((base / 'checkpoint.json').read_text(), 'preserved checkpoint')
            self.assertEqual((base / 'playback.json').read_text(), 'preserved playback')
            invocation = process.call_args.args[0]
            self.assertIn('--resume', invocation)
            self.assertIn(str(base), invocation)
            process.return_value.poll.return_value = None
            with self.assertRaises(RuntimeError):
                resume_job(identifier)

    def test_job_lookup_rejects_paths(self):
        self.assertIsNone(job_path('../../.env'))
        self.assertIsNone(job_path('live-not-a-uuid'))


if __name__ == '__main__':
    unittest.main()
