"""Bounded endpoint-first experiment on the crane's square-base collapse.

Run: python -m ori.reconstruction.endpoint_trial
Three model calls maximum, no retries, no publication into the main extraction.
The analytic endpoint family and existing motion library are separate components.
"""
import base64
import json
from pathlib import Path
import subprocess

from .animation import SIMULATOR
from .batching import atomic_json
from .outputs import new_run, save_request
from .video import VIDEO_URL, plan_path

MODEL = 'gemini-3.8-flash'
OBSERVE = '''Observe only the square-base collapse in this clip. Specify the state immediately after the collapse completes, before the next edge fold. Do not output motion or commands.
Return JSON {"start_seconds":number,"end_seconds":number,"state_family":"square_base" or "other","closed_direction":"top"|"right"|"bottom"|"left"|"uncertain","open_direction":same enums,"flat_at_end":boolean,"center_becomes_closed_tip":boolean,"original_corners_meet_at_open_tip":boolean,"visible_evidence":string,"unobservable":[string]}.
Times must be absolute seconds in the full video (clip is 74 through 94 seconds), NOT minutes.seconds. The closed tip is the original sheet center. Admit hidden material identities or stacking order you cannot observe. A separate geometry engine will construct the endpoint from these relationships.'''


def request(prompt, images=()):
    content = [{'type': 'video', 'uri': VIDEO_URL, 'processing': {
        'type': 'static', 'start_offset': '74s', 'end_offset': '94s', 'fps': 2}},
        {'type': 'text', 'text': prompt}]
    for img in images:
        content.extend([{'type': 'text', 'text': f"{img['phase'] if 'phase' in img else 'after'}: {img['description']}; {img['view']}"},
            {'type': 'image', 'mime_type': 'image/png', 'data': base64.b64encode(Path(img['path']).read_bytes()).decode()}])
    return {'model': MODEL, 'input': content, 'response_format': {'type': 'text', 'mime_type': 'application/json'},
            'generation_config': {'max_output_tokens': 2400}, 'store': False}


def call(client, run, name, prompt, images=()):
    body = request(prompt, images)
    save_request(run / f'{name}.request.json', body, images)
    response = client.interactions.create(**body)
    atomic_json(run / f'{name}.response.json', response.model_dump(mode='json', exclude_none=True))
    if response.status != 'completed' or not response.output_text:
        raise RuntimeError(f'{name}: incomplete model response; saved without retry.')
    result = json.loads(response.output_text)
    atomic_json(run / f'{name}.json', result)
    return result


def continue_trial(client, run):
    """Continue from a saved observation; no repeated observation/API retry."""
    spec = json.loads((run / 'endpoint-spec.json').read_text())
    result = subprocess.run(['node', str(SIMULATOR / 'endpoint-bridge.mjs')],
        input=json.dumps({'spec': spec}), capture_output=True, text=True, check=True, timeout=60)
    geometry = json.loads(result.stdout)
    atomic_json(run / 'geometry.json', geometry)
    if not geometry['candidates']:
        raise RuntimeError('No available motion reached the independently specified endpoint.')
    # Prefer the coordinated mechanism. Invisible material assignments remain
    # unverified even when a library path can reach one of them.
    candidate = geometry['candidates'][0]
    target = next(t for t in geometry['targets'] if t['id'] == candidate['target_id'])
    doc = {'engine': 'orisim3d', 'source': 'engine_candidate', 'video_url': VIDEO_URL,
           'model': MODEL, 'steps': candidate['steps'], 'review_start': 1, 'review_target': target}
    atomic_json(run / 'candidate.json', doc)
    print('Constructed independent targets; rendering the matching motion and target…', flush=True)
    rendered = subprocess.run(['node', str(SIMULATOR / 'render-script.mjs'), str(run / 'preview')],
        input=json.dumps(doc), capture_output=True, text=True, check=True, timeout=90)
    images = json.loads(rendered.stdout)['images']
    atomic_json(run / 'images.json', images)
    target_images = [i for i in images if i.get('phase') == 'target']
    endpoint_review = call(client, run, 'endpoint-review', '''Check ONLY this independent target endpoint against the end of the square-base collapse (about 84–91 seconds), before subsequent edge folds. Motion is deliberately not supplied yet. Palette and screen translation are arbitrary. Layer stacking is unspecified; do not treat rendered front/back colors as evidence of correct hidden material order.
Return {"visible_endpoint_matches":true|false,"reason":string,"hidden_layer_order":"verified"|"unverified","missing_evidence":[string]}. Judge the visible geometry, closed/open tip positions and orientation. Keep uncertainty explicit.
Observed target constraints: ''' + json.dumps(spec), target_images)
    if endpoint_review.get('visible_endpoint_matches') is not True:
        atomic_json(run / 'result.json', {'status': 'endpoint_rejected', 'review': endpoint_review})
        return
    print('Endpoint review passed for visible shape; checking actual intermediate motion…', flush=True)
    review = call(client, run, 'motion-review', '''Compare the supplied actual intermediate engine renders against the square-base collapse at about 84–91 seconds, before the next edge fold. The independent target was constructed first, and the engine fitted a library motion to it. Check motion separately from the final silhouette. The flat initial sheet is a prepared starting fixture, not a reconstruction of preceding video actions. Global camera angle/translation and palette can differ, but open/closed tip orientation and which paper regions move matter. Layer ordering in these images is approximate and cannot certify hidden layers. Do not infer physical validity from the target agreement.
Return {"visible_endpoint_matches":true|false,"visible_motion_matches":true|false,"reason":string,"visible_defects":[string],"hidden_layer_order":"verified"|"unverified","self_collision":"observed"|"not_observed_in_samples"|"uncertain"}.
Judge the visible evidence; identify any spike, clipping, wrong movement, or mismatch instead of approving based on the numeric checks.
Numeric checks (not a proof of collision freedom): ''' + json.dumps(candidate['checks']), images)
    passed = review.get('visible_endpoint_matches') is True and review.get('visible_motion_matches') is True
    report = {'status': 'visible_match' if passed else 'motion_rejected', 'model': MODEL,
              'endpoint_review': endpoint_review, 'motion_review': review, 'checks': candidate['checks'],
              'limits': candidate['unresolved'], 'generated_full_crane': False,
              'starting_state': 'Verified flat precreased square fixture; earlier video actions were not regenerated.'}
    atomic_json(run / 'result.json', report)
    print(json.dumps(report, indent=2), flush=True)


def main():
    from google import genai
    from google.genai import types
    from ori.config import load_settings
    run = new_run(plan_path(VIDEO_URL), 'endpoint-trial')
    print(f'Endpoint-first square-base experiment · {MODEL}\n{run}\nAt most three API calls; no retries.', flush=True)
    with genai.Client(api_key=load_settings().gemini_api_key, http_options=types.HttpOptions(
            timeout=180000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
        call(client, run, 'endpoint-spec', OBSERVE)
        continue_trial(client, run)


if __name__ == '__main__':
    main()
