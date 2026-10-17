import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ori.reconstruction.fold_commands import FoldHarness
from ori.reconstruction.fold_context import DEFAULT_POLICY, compact_context, physics_checkpoint
from ori.reconstruction.fold_trial import run
from ori.reconstruction.fold_audit import audit
from ori.reconstruction.batching import atomic_json


def reply(value):
    text = json.dumps(value)
    return SimpleNamespace(status='completed', output_text=text, model_dump=lambda **_: dict(output_text=text))


class ContextTests(unittest.TestCase):
    def test_compaction_is_lossless_for_physics_and_bounded_for_dialogue(self):
        h = FoldHarness()
        feedback = h.execute([])
        # Large state makes accidental removal/rounding or duplicated snapshots visible.
        feedback['state'] *= 100
        history = [dict(model_output='invalid ' * 1000, harness_feedback=copy.deepcopy(feedback)) for _ in range(50)]
        before = copy.deepcopy((feedback, history))
        policy = dict(DEFAULT_POLICY, recent_chars=1000)
        result = compact_context(feedback, history, policy)
        self.assertEqual(result['harness_feedback'], feedback)
        self.assertEqual((feedback, history), before)
        self.assertEqual(result['continuity']['compacted_exchanges'], 50)
        self.assertLess(len(json.dumps(result['recent_model_harness_exchanges'])), 1000)
        self.assertEqual(result, compact_context(feedback, history, policy))
        self.assertNotIn('state', json.dumps(result['recent_model_harness_exchanges']))

    def test_compaction_remembers_rejected_command_and_frequency(self):
        h = FoldHarness()
        command = dict(crease=[[-1, 0, 0], [1, 0, 0]], normal=[0, 0, 1], moving_side='left', angle_degrees=999)
        proposal = json.dumps(dict(commands=[command]))
        feedback = h.submit_text(proposal)
        history = [dict(model_output=proposal, harness_feedback=feedback)] * 30
        result = compact_context(feedback, history, DEFAULT_POLICY)
        self.assertEqual(result['failed_move_memory'][0]['command'], command)
        self.assertEqual(result['failed_move_memory'][0]['count'], 30)
        self.assertEqual(result['failed_move_memory'][0]['error'], feedback['error'])
        self.assertEqual(result['harness_feedback']['state'], h.state())

    def test_checkpoint_precedes_publication_and_resume_verifies_exact_state(self):
        command = dict(crease=[[-1, 0, 0], [1, 0, 0]], normal=[0, 0, 1], moving_side='left', angle_degrees=180)
        client = MagicMock()
        client.interactions.create.side_effect = [reply(dict(commands=[command], done=False)), reply(dict(commands=[], done=True))]
        with TemporaryDirectory() as directory:
            base = Path(directory)
            def observer(kind, **fields):
                if kind == 'accepted':
                    saved = json.loads((base / 'checkpoint.json').read_text())
                    self.assertEqual(saved['physics_checkpoint'], physics_checkpoint(fields['harness']))
            args = dict(context_policy=DEFAULT_POLICY, continue_on_blocked=True, export=False)
            run(client, 'url', 'model', base, max_calls=1, observer=observer, **args)
            self.assertTrue(audit(base)['passed'])
            checkpoint = json.loads((base / 'checkpoint.json').read_text())
            checkpoint['physics_checkpoint']['physics']['state'][0]['vertices'][0][0] += .1
            (base / 'checkpoint.json').write_text(json.dumps(checkpoint))
            with self.assertRaisesRegex(ValueError, 'Physics checkpoint differs'):
                run(client, 'url', 'model', base, max_calls=2, resume=True, **args)
            self.assertEqual(client.interactions.create.call_count, 1)

    def test_crash_before_commit_does_not_publish_or_reexecute_a_partial_transaction(self):
        command = dict(crease=[[-1, 0, 0], [1, 0, 0]], normal=[0, 0, 1], moving_side='left', angle_degrees=180)
        client = MagicMock()
        client.interactions.create.side_effect = [reply(dict(commands=[command], done=True))] * 2
        with TemporaryDirectory() as directory:
            base = Path(directory)
            published = []
            def write(path, value):
                if path.name == 'checkpoint.json' and value['history']:
                    raise OSError('simulated crash before checkpoint commit')
                atomic_json(path, value)
            args = dict(context_policy=DEFAULT_POLICY, continue_on_blocked=True, export=False)
            with patch('ori.reconstruction.fold_trial.atomic_json', side_effect=write):
                with self.assertRaises(OSError):
                    run(client, 'url', 'model', base, max_calls=1,
                        observer=lambda kind, **_: published.append(kind), **args)
            self.assertNotIn('accepted', published)
            self.assertTrue((base / 'debug/call-01/harness-feedback.json').exists())
            run(client, 'url', 'model', base, max_calls=2, resume=True, **args)
            checkpoint = json.loads((base / 'checkpoint.json').read_text())
            self.assertEqual(checkpoint['committed_calls'], [2])
            self.assertEqual(checkpoint['physics_checkpoint']['physics']['accepted_commands'], [command])
            self.assertTrue(audit(base)['passed'])

    def test_audit_crosses_three_digit_calls_and_detects_compacted_context_tampering(self):
        client = MagicMock()
        client.interactions.create.side_effect = [reply(dict(commands=[], blocked='Replan'))] * 101 + [reply(dict(commands=[], done=True))]
        with TemporaryDirectory() as directory:
            base = Path(directory)
            run(client, 'url', 'model', base, max_calls=105, context_policy=DEFAULT_POLICY,
                continue_on_blocked=True, export=False)
            self.assertEqual(audit(base)['requests_checked'], 102)
            path = base / 'debug/call-100/request.json'
            value = json.loads(path.read_text())
            payload = json.loads(value['input'][2]['text'])
            payload['harness_feedback']['state'][0]['vertices'][0][0] += 1
            value['input'][2]['text'] = json.dumps(payload)
            path.write_text(json.dumps(value))
            with self.assertRaises(AssertionError):
                audit(base)


if __name__ == '__main__':
    unittest.main()
