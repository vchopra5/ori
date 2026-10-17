"""Bounded Gemini/video trial with feedback exclusively from FoldHarness.

No observer model, reviewer, templates, manual corrections, or API retries.
Every request, response, and harness result is retained in a unique run directory.
"""
import argparse
import base64
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from .batching import atomic_json
from .fold_commands import FoldHarness, MODEL_INSTRUCTIONS, LEGACY_MODEL_INSTRUCTIONS
from .fold_render import render, export_history
from .outputs import new_run, save_request
from .fold_context import compact_context, physics_checkpoint
from .video import plan_path

TASK = '''Reconstruct the folds demonstrated in the supplied video, in order,
starting with the harness's square. You choose the folds, coordinates, directions
and layers by observing the video. Infer the video's paper orientation relative
to this square; camera/paper reorientations do not themselves require a fold.
Return {"commands":[...],"done":false}, with only NEW commands to execute now.
Prefer one fold at a time when later choices depend on new geometry. Do not
repeat accepted commands; a failed batch retains its accepted prefix. Set done
true only when you believe every demonstrated fold has been reconstructed.
If the next demonstrated action cannot be expressed, return
{"commands":[],"done":false,"blocked":"specific unsupported action"}.
All execution feedback and state images below come directly from the harness.
There is no external reviewer or corrective advice. Passing geometry checks is
not evidence that you matched the video. Inspect it yourself, and acknowledge
limitations rather than substituting an easier shape or claiming success.
'''

APPROXIMATE_TASK = '''Watch the supplied video and identify its finished origami
object. Make a recognizable approximation of that FINAL OUTPUT with the fold
harness, starting from its square. A loose resemblance to the demonstration is
enough: the final recognizable shape matters more than matching its procedure.
Choose your own feasible sequence. You may skip preliminary creases, reorder
folds, or replace unsupported demonstrated operations with simpler folds that
approach the final shape. Do not stop merely because the exact video uses a
compound collapse or reverse fold: use precrease, compound mechanisms and dry-run
probes to construct it before considering a simpler route. Derive motions from
the material constraints, and use failed probe feedback to refine them.
All paper constraints still apply; do not invent geometry or bypass validation.
Return {"commands":[...],"done":false}, containing only NEW commands to execute.
Prefer one fold at a time when later choices depend on resulting geometry.
Never replay accepted commands. A failed batch retains its accepted prefix.
Inspect the video and current harness renders yourself. Set done:true when you
believe the result is a recognizable approximation of the finished object.
If you cannot find a feasible approximation, you may return
{"commands":[],"done":false,"blocked":"specific remaining limitation"}.
All execution feedback and state images come directly from the harness.
There is no external reviewer or corrective advice. Physical validity alone
does not mean you achieved the target shape; use your own visual judgment.
'''


FOLD_GEOMETRY_GUIDANCE = """Geometry reminder: partial folds ARE supported.
For a SMALL FLAT FLAP, choose a crease close to that corner and usually rotate
180 degrees. A smaller angle makes an OPEN 3D hinge; it does not make a smaller
flat flap. Creases can use arbitrary finite coordinates, not just midpoints,
diagonals or existing edges. Choose the moving side and exposed layers explicitly.
For a flat 180-degree fold, the crease is the perpendicular bisector between
the current tip and its intended destination in the paper plane. Check the
predicted tip position before committing. Preserve intended protrusions: ears,
wings, and small tips should not disappear into the central silhouette.
Judge the rendered outline against the video's finished object, not command
names. A physically legal fold is not automatically the correct fold.
Completion requires inspecting the resulting final render on a subsequent turn.
After your last fold, return done:false. Once you see its rendered result, either
correct it with legal actions, or return {"commands":[],"done":true} if it matches.
"""

def build_request(url, model, feedback, history, images, task=TASK, max_output_tokens=32768, context_policy=None):
    payload = compact_context(feedback, history, context_policy) if context_policy else dict(
        harness_feedback=feedback, recent_model_harness_exchanges=history[-3:])
    inputs = [dict(type='video', uri=url, processing=dict(type='static', fps=2)),
              dict(type='text', text=task + '\nAction contract:\n' + MODEL_INSTRUCTIONS),
              dict(type='text', text=json.dumps(payload))]
    for image in images:
        inputs.extend([dict(type='text', text=image['view']),
                       dict(type='image', mime_type='image/png',
                            data=base64.b64encode(Path(image['path']).read_bytes()).decode())])
    # Let the harness parse JSON. Provider JSON enforcement can discard malformed
    # output before the harness gets to return its own syntax diagnostics.
    return dict(model=model, input=inputs, response_format=dict(type='text'),
                generation_config=dict(max_output_tokens=max_output_tokens), store=False)


def generate_content(client, request, directory, thinking_level='low'):
    """Same model inputs through the direct API, without Interactions video tools."""
    from google.genai import types
    parts, logged = [], []
    for item in request['input']:
        if item['type'] == 'video':
            fields = dict(file_data=dict(file_uri=item['uri'], mime_type='video/mp4'),
                          video_metadata=dict(fps=item['processing']['fps']))
            parts.append(types.Part(**fields))
            logged.append(fields)
        elif item['type'] == 'text':
            parts.append(types.Part.from_text(text=item['text']))
            logged.append(dict(text=item['text']))
        else:
            parts.append(types.Part.from_bytes(data=base64.b64decode(item['data']), mime_type=item['mime_type']))
            logged.append(dict(image_sha256=__import__('hashlib').sha256(base64.b64decode(item['data'])).hexdigest(),
                               mime_type=item['mime_type']))
    config = dict(max_output_tokens=request['generation_config']['max_output_tokens'],
                  thinking_config=dict(thinking_level=thinking_level.upper()), automatic_continuation=False)
    atomic_json(directory / 'direct-api-request.json', dict(model=request['model'], contents=logged, config=config))
    response = client.models.generate_content(model=request['model'], contents=parts,
                                              config=types.GenerateContentConfig(**config))
    text = response.text or ''
    return SimpleNamespace(status='completed' if text else 'incomplete', output_text=text,
                           model_dump=lambda **kwargs: response.model_dump(**kwargs))


def run(client, url, model, output, max_calls=12, resume=False, task=TASK, transport='interactions',
        thinking_level='low', max_output_tokens=32768, observer=None, export=True,
        context_policy=None, continue_on_blocked=False, require_final_review=False):
    emit = observer or (lambda *args, **kwargs: None)
    harness = FoldHarness()
    history = []
    feedback = harness.execute([])
    status = 'call_budget_exhausted'
    calls = 0
    last_compacted = 0
    committed_calls = []
    if resume:
        config = json.loads((output / 'config.json').read_text())
        if config['video_url'] != url or config['model'] != model:
            raise ValueError('Resume must use the original model and video')
        if config.get('transport', 'interactions') != transport:
            raise ValueError('Resume must use the original API transport')
        original_contract = (output / 'contract.txt').read_text()
        if original_contract not in (task + '\n' + MODEL_INSTRUCTIONS, task + '\n' + LEGACY_MODEL_INSTRUCTIONS):
            raise ValueError('Cannot resume with an unrecognized model contract')
        if config.get('context_policy') != context_policy or config.get('continue_on_blocked', False) != continue_on_blocked:
            raise ValueError('Resume must retain the original context and continuation policy')
        checkpoint = json.loads((output / 'checkpoint.json').read_text())
        history = checkpoint['history']
        if context_policy:
            committed_calls = checkpoint.get('committed_calls', [])
            if len(committed_calls) != len(history) or committed_calls != sorted(set(committed_calls)):
                raise ValueError('Invalid committed-call checkpoint')
            for call, exchange in zip(committed_calls, history):
                directory = output / 'debug' / f'call-{call:02d}'
                if ((directory / 'model-output.txt').read_text() != exchange['model_output'] or
                        json.loads((directory / 'harness-feedback.json').read_text()) != exchange['harness_feedback']):
                    raise ValueError('Committed call differs from checkpoint')
        for exchange in history:
            replayed = harness.submit_text(exchange['model_output'])
            if replayed != exchange['harness_feedback']:
                raise ValueError('Harness replay differs from the recorded feedback; cannot resume')
        if context_policy and checkpoint.get('physics_checkpoint') != physics_checkpoint(harness):
            raise ValueError('Physics checkpoint differs from replay; cannot resume')
        calls = max((int(p.name.removeprefix('call-')) for p in (output / 'debug').glob('call-*')), default=0)
        feedback = history[-1]['harness_feedback'] if history else feedback
        if max_calls <= calls:
            raise ValueError('Resume requires a total call budget above the recorded call count')
        if (output / 'result.json').exists():
            atomic_json(output / f'result-through-{calls}.json', json.loads((output / 'result.json').read_text()))
        if original_contract != task + '\n' + MODEL_INSTRUCTIONS and not config.get('action_contract_upgrades'):
            config['action_contract_upgrades'] = [dict(after_call=calls, instructions=MODEL_INSTRUCTIONS)]
        config.setdefault('budget_extensions', []).append(dict(after_call=calls, total_max_calls=max_calls))
        config.setdefault('generation_changes', []).append(dict(after_call=calls,
                    thinking_level=thinking_level, max_output_tokens=max_output_tokens))
        atomic_json(output / 'config.json', config)
    else:
        atomic_json(output / 'config.json', dict(video_url=url, model=model, max_calls=max_calls,
                    feedback_source='FoldHarness only; no observer, reviewer or manual corrections',
                    video_sampling_fps=2, api_retry_attempts=1, json_validation='harness_only', task=task,
                    transport=transport, thinking_level=thinking_level, max_output_tokens=max_output_tokens,
                    context_policy=context_policy, continue_on_blocked=continue_on_blocked))
        (output / 'contract.txt').write_text(task + '\n' + MODEL_INSTRUCTIONS)
    if context_policy and not resume:
        atomic_json(output / 'checkpoint.json', dict(history=history, feedback=feedback,
                    physics_checkpoint=physics_checkpoint(harness), committed_calls=[]))
    if resume and context_policy:
        emit('restored', harness=harness)
    saved_config = json.loads((output / 'config.json').read_text())
    require_final_review = require_final_review or 'final_review_after_call' in saved_config
    if require_final_review:
        saved_config.setdefault('final_review_after_call', calls)
        atomic_json(output / 'config.json', saved_config)
    for turn in range(calls + 1, max_calls + 1):
        call_dir = output / 'debug' / f'call-{turn:02d}'
        call_dir.mkdir(parents=True)
        images = []
        for view, oblique in [('Harness current state, front', False), ('Harness current state, oblique', True)]:
            image_path = call_dir / ('oblique.png' if oblique else 'front.png')
            render(harness.panels, f'Harness: {len(harness.history)} accepted folds', oblique).save(image_path)
            images.append(dict(view=view, path=str(image_path)))
        request = build_request(url, model, feedback, history, images, task, max_output_tokens, context_policy)
        if require_final_review:
            request['input'][1]['text'] += '\n' + FOLD_GEOMETRY_GUIDANCE
        if context_policy:
            continuity = json.loads(request['input'][2]['text'])['continuity']
            atomic_json(call_dir / 'context.json', continuity)
            compacted = continuity['compacted_exchanges']
            if compacted and (not last_compacted or compacted-last_compacted >= context_policy['recent_exchanges']):
                emit('compacted', exchanges=compacted, accepted=len(harness.history), physics_sha256=continuity['physics_sha256'])
                last_compacted = compacted
        save_request(call_dir / 'request.json', request, images)
        print(f'Call {turn}/{max_calls}: {model}, {len(harness.history)} accepted folds', flush=True)
        calls = turn
        emit("working", call=turn, accepted=len(harness.history))
        try:
            response = (generate_content(client, request, call_dir, thinking_level) if transport == 'generate-content'
                        else client.interactions.create(**request))
            atomic_json(call_dir / 'response.json', response.model_dump(mode='json', exclude_none=True))
            if response.status != 'completed' or not response.output_text:
                status = 'incomplete_api_response'
                break
        except Exception as exc:
            atomic_json(call_dir / 'api-error.json', dict(type=type(exc).__name__, message=str(exc)))
            status = 'api_error'
            print(f'API stopped: {type(exc).__name__}: {exc}', flush=True)
            break
        raw_text = response.output_text
        (call_dir / 'model-output.txt').write_text(raw_text)
        # This is the sole source of corrective information passed to the model.
        emit("proposal", text=raw_text, call=turn)
        accepted_events = []
        def accepted(command, poses, state):
            if context_policy:
                accepted_events.append(dict(command=command, poses=poses, harness=copy.deepcopy(state)))
            else:
                emit('accepted', command=command, poses=poses, harness=state)
        accepted_before = len(harness.history)
        feedback = harness.submit_text(raw_text, accepted)
        atomic_json(call_dir / 'harness-feedback.json', feedback)
        history.append(dict(model_output=raw_text, harness_feedback=feedback))
        committed_calls.append(turn)
        atomic_json(output / 'checkpoint.json', dict(history=history, feedback=feedback,
                    **({'physics_checkpoint': physics_checkpoint(harness), 'committed_calls': committed_calls} if context_policy else {})))
        atomic_json(output / 'commands.json', dict(commands=harness.history))
        # Publish live folds only after the physics checkpoint is durable.
        for event in accepted_events:
            emit('accepted', **event)
        emit('feedback', feedback=feedback, call=turn)
        print(f'  Harness ok={feedback["ok"]}; accepted={len(harness.history)}; '
              f'error={feedback.get("error", "none")}; done={feedback.get("model_claimed_done", False)}; '
              f'blocked={feedback.get("model_reported_blocked", "")}', flush=True)
        if feedback['ok'] and feedback.get('model_reported_blocked'):
            if continue_on_blocked:
                emit('recovering', call=turn, accepted=len(harness.history))
                continue
            status = 'model_reported_blocked'
            break
        if feedback['ok'] and feedback.get('model_claimed_done'):
            if require_final_review and len(harness.history)>accepted_before:
                emit('reviewing', call=turn, accepted=len(harness.history))
                continue  # The next request includes renders of the actual final pose.
            status = 'model_claimed_done'
            break
    report = dict(status=status, calls=calls, accepted_folds=len(harness.history), model=model,
                  video_url=url, feedback_source='harness_only', metrics=harness.metrics(),
                  transport=transport, context_policy=context_policy,
                  thinking_level=thinking_level, max_output_tokens=max_output_tokens,
                  layer_state=harness.layer_state(),
                  rejected_proposals=sum(not h['harness_feedback']['ok'] for h in history),
                  model_reported_blocked=feedback.get('model_reported_blocked', ''),
                  video_match='Not independently verified; completion is a model claim, not a harness measurement')
    atomic_json(output / 'result.json', report)
    atomic_json(output / 'final-state.json', harness.state())
    atomic_json(output / 'commands.json', dict(commands=harness.history))
    if export:
        export_history(harness.history, output)
    emit("finished", report=report)
    print(json.dumps(report, indent=2), flush=True)
    return report


def main():
    from google import genai
    from google.genai import types
    from ori.config import load_settings
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--model', default='gemini-4-argon')
    parser.add_argument('--max-calls', type=int, default=12)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--objective', choices=['strict', 'approximate'], default='strict')
    parser.add_argument('--transport', choices=['interactions', 'generate-content'], default='interactions')
    parser.add_argument('--thinking-level', choices=['minimal', 'low', 'medium', 'high'], default='low', help='Reasoning level for the direct content API')
    parser.add_argument('--max-output-tokens', type=int, default=32768)
    parser.add_argument('--resume', type=Path, help='Continue the exact saved model/harness exchange; max-calls is the total budget')
    args = parser.parse_args()
    base = plan_path(args.url)  # Validate the supplied YouTube URL without fetching it.
    if args.max_calls < 1:
        parser.error('--max-calls must be positive')
    if args.max_output_tokens < 1:
        parser.error('--max-output-tokens must be positive')
    if args.resume and args.output:
        parser.error('Choose either --resume or --output')
    output = args.resume.resolve() if args.resume else (args.output.resolve() if args.output else new_run(Path('output/fold_trials') / base.name, 'argon-harness'))
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'config.json').exists() and not args.resume:
        parser.error('Output already contains a trial; choose a fresh directory')
    print(f'Artifacts: {output}', flush=True)
    with genai.Client(api_key=load_settings().gemini_api_key, http_options=types.HttpOptions(
            timeout=600000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
        run(client, args.url, args.model, output, args.max_calls, resume=bool(args.resume),
            task=APPROXIMATE_TASK if args.objective == 'approximate' else TASK, transport=args.transport,
            thinking_level=args.thinking_level, max_output_tokens=args.max_output_tokens)


if __name__ == '__main__':
    main()
