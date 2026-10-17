"""Replay a trial to verify that every feedback payload and image is from the harness."""
import argparse
import json
from pathlib import Path

from PIL import Image

from .batching import atomic_json
from .fold_commands import FoldHarness, MODEL_INSTRUCTIONS, LEGACY_MODEL_INSTRUCTIONS, PRE_ROTATION_MODEL_INSTRUCTIONS
from .fold_render import render
from .fold_trial import TASK, FOLD_GEOMETRY_GUIDANCE
from .fold_context import compact_context, physics_checkpoint


def audit(output):
    output = Path(output).resolve()
    config = json.loads((output / 'config.json').read_text())
    task = config.get('task', TASK)
    original_contract = (output / 'contract.txt').read_text()
    assert original_contract.startswith(task + '\n')
    original_instructions = original_contract[len(task)+1:]
    assert original_instructions in (MODEL_INSTRUCTIONS, LEGACY_MODEL_INSTRUCTIONS, PRE_ROTATION_MODEL_INSTRUCTIONS)
    harness = FoldHarness()
    feedback = harness.execute([])
    history = []
    requests = 0
    image_count = 0
    checkpoint = json.loads((output / 'checkpoint.json').read_text()) if config.get('context_policy') else None
    committed = checkpoint['committed_calls'] if checkpoint is not None else None
    if committed is not None:
        assert committed == sorted(set(committed))
        assert len(committed) == len(checkpoint['history'])
    seen_committed = []
    for directory in sorted((output / 'debug').glob('call-*'), key=lambda p: int(p.name.removeprefix('call-'))):
        request = json.loads((directory / 'request.json').read_text())
        inputs = request['input']
        assert request['model'] == config['model']
        assert len(inputs) == 7
        assert inputs[0] == dict(type='video', uri=config['video_url'], processing=dict(type='static', fps=2))
        instructions = original_instructions
        for upgrade in config.get('action_contract_upgrades', []):
            assert upgrade['instructions'] in (MODEL_INSTRUCTIONS, PRE_ROTATION_MODEL_INSTRUCTIONS)
            if int(directory.name.removeprefix('call-')) > upgrade['after_call']:
                instructions = upgrade['instructions']
        prompt = task + '\nAction contract:\n' + instructions
        if 'final_review_after_call' in config and int(directory.name.removeprefix('call-')) > config['final_review_after_call']:
            prompt += '\n' + FOLD_GEOMETRY_GUIDANCE
        assert inputs[1] == dict(type='text', text=prompt)
        expected_context = (compact_context(feedback, history, config['context_policy'])
                            if config.get('context_policy') else dict(harness_feedback=feedback,
                                recent_model_harness_exchanges=history[-3:]))
        assert json.loads(inputs[2]['text']) == expected_context
        if config.get('context_policy'):
            assert json.loads((directory / 'context.json').read_text()) == expected_context['continuity']
        for index, (label, oblique) in enumerate([('Harness current state, front', False), ('Harness current state, oblique', True)]):
            assert inputs[3 + 2 * index] == dict(type='text', text=label)
            ref = inputs[4 + 2 * index]
            assert ref['type'] == 'image' and ref['mime_type'] == 'image/png'
            expected = render(harness.panels, f'Harness: {len(harness.history)} accepted folds', oblique)
            with Image.open(directory / ref['data_file']) as actual:
                assert actual.convert('RGB').tobytes() == expected.tobytes()
            image_count += 1
        requests += 1
        call = int(directory.name.removeprefix('call-'))
        if committed is not None and call not in committed:
            continue  # A crash before atomic checkpoint commit cannot advance physics.
        if not (directory / 'harness-feedback.json').exists():
            continue  # An API failure/pending call does not become model feedback.
        seen_committed.append(call)
        raw = (directory / 'model-output.txt').read_text()
        feedback = harness.submit_text(raw)
        assert feedback == json.loads((directory / 'harness-feedback.json').read_text())
        history.append(dict(model_output=raw, harness_feedback=feedback))
    if config.get('context_policy'):
        checkpoint = json.loads((output / 'checkpoint.json').read_text())
        assert seen_committed == committed
        assert checkpoint['history'] == history
        assert checkpoint['feedback'] == feedback
        assert checkpoint['physics_checkpoint'] == physics_checkpoint(harness)
    report = dict(passed=True, requests_checked=requests, feedback_exchanges_replayed=len(history),
                  harness_images_verified=image_count, accepted_folds=len(harness.history),
                  checks=['Fixed model contract and original video unchanged',
                          'Every dynamic text payload exactly equals replayed harness feedback and prior model/harness exchanges',
                          'Every supplied image matches a render of the replayed harness state',
                          'Every saved execution result exactly matches harness replay'],
                  does_not_verify='Whether model-selected folds match the source video')
    atomic_json(output / 'feedback-audit.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.output), indent=2))


if __name__ == '__main__':
    main()
