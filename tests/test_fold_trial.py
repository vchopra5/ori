"""Enforce harness-only feedback and preserve raw experimental evidence."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ori.reconstruction.fold_commands import FoldHarness
from ori.reconstruction.fold_trial import run
from ori.reconstruction.fold_audit import audit


def reply(text):
    return SimpleNamespace(status='completed', output_text=text,
                           model_dump=lambda **_: {'status': 'completed', 'output_text': text})


class FoldTrialTests(unittest.TestCase):
    def test_only_harness_results_and_fixed_contract_are_sent_after_failure(self):
        command = dict(crease=[[-1, 0, 0], [1, 0, 0]], normal=[0, 0, 1],
                       moving_side='left', angle_degrees=180)
        first = 'not JSON'
        second = json.dumps(dict(commands=[command], done=True))
        client = MagicMock()
        client.interactions.create.side_effect = [reply(first), reply(second)]
        with TemporaryDirectory() as directory, patch('ori.reconstruction.fold_trial.export_history'):
            output = Path(directory)
            result = run(client, 'https://www.youtube.com/shorts/FdBTwMuh1mU', 'gemini-4-argon', output, 3)
            requests = [c.kwargs for c in client.interactions.create.call_args_list]
            self.assertEqual(len(requests), 2)
            self.assertEqual(requests[0]['input'][1], requests[1]['input'][1])
            feedback = json.loads((output / 'debug/call-01/harness-feedback.json').read_text())
            payload = json.loads(requests[1]['input'][2]['text'])
            self.assertEqual(payload['harness_feedback'], feedback)
            self.assertEqual(feedback, FoldHarness().submit_text(first))
            self.assertEqual(payload['recent_model_harness_exchanges'],
                             [{'model_output': first, 'harness_feedback': feedback}])
            for i, response in enumerate((first, second), 1):
                self.assertEqual((output / f'debug/call-{i:02d}/model-output.txt').read_text(), response)
            self.assertEqual(result['status'], 'model_claimed_done')
            self.assertEqual(result['accepted_folds'], 1)
            self.assertEqual(result['rejected_proposals'], 1)
            self.assertIn('Not independently verified', result['video_match'])
            self.assertEqual(requests[0]['model'], 'gemini-4-argon')
            self.assertEqual(requests[0]['response_format'], {'type': 'text'})
            verified = audit(output)
            self.assertTrue(verified['passed'])
            self.assertEqual(verified['harness_images_verified'], 4)
            path = output / 'debug/call-02/request.json'
            tampered = json.loads(path.read_text())
            tampered['input'][2]['text'] = json.dumps({'human_hint': 'change the direction'})
            path.write_text(json.dumps(tampered))
            with self.assertRaises(AssertionError):
                audit(output)

    def test_harness_envelope_errors_leave_paper_unchanged(self):
        harness = FoldHarness()
        before = harness.state()
        for proposal in ([], {'commands': 'code'}, {'commands': [], 'done': 'yes'},
                         {'commands': [], 'blocked': True}, {'commands': [], 'review': 'change shape'}):
            self.assertFalse(harness.submit(proposal)['ok'])
            self.assertEqual(before, harness.state())

    def test_resume_preserves_prior_evidence_and_exact_harness_feedback(self):
        command = dict(crease=[[-1, 0, 0], [1, 0, 0]], normal=[0, 0, 1],
                       moving_side='left', angle_degrees=180)
        client = MagicMock()
        client.interactions.create.side_effect = [reply(json.dumps(dict(commands=[command], done=False))),
                                                  reply('{"commands":[],"done":true}')]
        with TemporaryDirectory() as directory, patch('ori.reconstruction.fold_trial.export_history'):
            output = Path(directory)
            url = 'https://www.youtube.com/shorts/FdBTwMuh1mU'
            run(client, url, 'gemini-4-argon', output, 1)
            old_request = (output / 'debug/call-01/request.json').read_bytes()
            old_feedback = json.loads((output / 'debug/call-01/harness-feedback.json').read_text())
            result = run(client, url, 'gemini-4-argon', output, 2, resume=True)
            self.assertEqual(result['calls'], 2)
            self.assertEqual(result['accepted_folds'], 1)
            self.assertEqual((output / 'debug/call-01/request.json').read_bytes(), old_request)
            second = client.interactions.create.call_args.kwargs
            self.assertEqual(json.loads(second['input'][2]['text'])['harness_feedback'], old_feedback)
            self.assertTrue((output / 'result-through-1.json').is_file())

    def test_direct_api_sends_same_harness_inputs_without_interactions(self):
        command = dict(crease=[[-1, 0, 0], [1, 0, 0]], normal=[0, 0, 1],
                       moving_side='left', angle_degrees=180)
        raw = json.dumps(dict(commands=[command], done=True))
        client = MagicMock()
        client.models.generate_content.return_value = SimpleNamespace(
            text=raw, model_dump=lambda **_: {'text': raw})
        with TemporaryDirectory() as directory, patch('ori.reconstruction.fold_trial.export_history'):
            output = Path(directory)
            url = 'https://www.youtube.com/shorts/FdBTwMuh1mU'
            result = run(client, url, 'gemini-4-argon', output, 1, transport='generate-content')
            client.interactions.create.assert_not_called()
            request = client.models.generate_content.call_args.kwargs
            self.assertEqual(request['contents'][0].file_data.file_uri, url)
            self.assertEqual(request['contents'][0].video_metadata.fps, 2)
            self.assertEqual(request['contents'][4].inline_data.mime_type, 'image/png')
            self.assertEqual(request['config'].thinking_config.thinking_level, 'LOW')
            self.assertIsNone(request['config'].thinking_config.thinking_budget)
            self.assertEqual(request['config'].max_output_tokens, 32768)
            self.assertFalse(request['config'].automatic_continuation)
            self.assertEqual(result['accepted_folds'], 1)
            self.assertTrue(audit(output)['passed'])

    def test_resume_after_incomplete_response_keeps_failed_attempt_and_audits(self):
        command = dict(crease=[[-1, 0, 0], [1, 0, 0]], normal=[0, 0, 1],
                       moving_side='left', angle_degrees=180)
        client = MagicMock()
        client.interactions.create.side_effect = [reply(json.dumps(dict(commands=[command], done=False))),
                                                  reply(''), reply('{"commands":[],"done":true}')]
        with TemporaryDirectory() as directory, patch('ori.reconstruction.fold_trial.export_history'):
            output = Path(directory)
            url = 'https://www.youtube.com/shorts/FdBTwMuh1mU'
            first = run(client, url, 'gemini-4-argon', output, 2)
            self.assertEqual(first['status'], 'incomplete_api_response')
            failed_request = (output / 'debug/call-02/request.json').read_bytes()
            result = run(client, url, 'gemini-4-argon', output, 3, resume=True)
            self.assertEqual(result['calls'], 3)
            self.assertEqual((output / 'debug/call-02/request.json').read_bytes(), failed_request)
            self.assertTrue((output / 'debug/call-03/harness-feedback.json').is_file())
            checked = audit(output)
            self.assertEqual(checked['requests_checked'], 3)
            self.assertEqual(checked['feedback_exchanges_replayed'], 2)


if __name__ == '__main__':
    unittest.main()
