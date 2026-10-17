"""Durable local video jobs. UI observations never enter model feedback."""
import argparse
import json
import os
from pathlib import Path
from google import genai
from google.genai import types
from ori.config import load_settings
from ori.reconstruction.batching import atomic_json
from ori.reconstruction.fold_trial import run, APPROXIMATE_TASK
from ori.reconstruction.fold_commands import FoldHarness
from ori.reconstruction.fold_context import DEFAULT_POLICY
from .paper_playback import motion_from_poses, cache_key, compile_playback

MODEL = 'gemini-4-argon'
ROUTING = '''Watch this video and select a simulation engine. Return JSON with
kind ("origami", "lego", "mujoco", or "unsupported"), title (a short object name), and
summary (one sentence describing the visible activity). Choose origami for paper
folding, lego for LEGO or interlocking brick assembly tutorials (including those with specialty parts), mujoco for other objects, mechanisms, or other physical demonstrations that
can be approximated with rigid bodies. Choose unsupported if the video cannot
be understood or neither engine is appropriate. Inspect the END of the video
carefully: title and summary must describe the same finished object, not an
intermediate silhouette. Mention any cutting, gluing, or compound collapses in
the summary. This is classification only.'''


def classify(client, url, output):
    atomic_json(output / 'routing-request.json', dict(model=MODEL, url=url, prompt=ROUTING))
    response = client.models.generate_content(model=MODEL, contents=[
        types.Part(file_data=dict(file_uri=url, mime_type='video/mp4'), video_metadata=dict(fps=2)),
        types.Part.from_text(text=ROUTING)], config=types.GenerateContentConfig(
            response_mime_type='application/json', max_output_tokens=2048,
            thinking_config=dict(thinking_level='LOW')))
    (output / 'routing-response.json').write_text(response.model_dump_json(exclude_none=True))
    route = json.loads(response.text or '')
    if route.get('kind') not in {'origami', 'lego', 'mujoco', 'unsupported'}:
        raise ValueError('Video classification did not select a supported engine')
    return {key: str(route.get(key, ''))[:300] for key in ('kind', 'title', 'summary')}


class Progress:
    def __init__(self, output, url, resume=False):
        self.output = output
        if resume:
            self.data = json.loads((output / 'job.json').read_text())
            self.playback = json.loads((output / 'playback.json').read_text())
            if self.data['url'] != url:
                raise ValueError('Resume must retain the original video')
            self.data['status'] = 'running'
            self.event('resuming', 'Continuing from the saved paper and accepted folds')
            return
        self.data = dict(id=output.name, url=url, status='classifying', events=[], revision=0,
                         commands=[], accepted=0, route=None, attempt=0)
        self.playback = dict(version=1, seconds_per_step=2.6, states=[FoldHarness().state()], motions=[])
        atomic_json(self.output / 'playback.json', self.playback)
        self.event('classifying', 'Watching the video to choose a simulator')

    def begin_run(self):
        number = 1
        self.data.update(attempt=number, commands=[], accepted=0, status='running',
                         command_hash=cache_key([]))
        self.playback = dict(version=1, seconds_per_step=2.6, states=[FoldHarness().state()],
                             motions=[], attempt=number, command_hash=cache_key([]))
        atomic_json(self.output / 'playback.json', self.playback)
        atomic_json(self.output / 'commands.json', dict(commands=[]))
        self.event('planning', 'Building a fold-only approximation', attempt=number)

    def event(self, kind, message, **fields):
        self.data['events'].append(dict(kind=kind, message=message, **fields))
        self.data['revision'] += 1
        atomic_json(self.output / 'job.json', self.data)

    def observe(self, kind, **fields):
        if kind == 'restored':
            commands = fields['harness'].history
            self.playback = compile_playback(commands)
            self.playback.update(attempt=self.data.get('attempt', 1), command_hash=cache_key(commands))
            self.data.update(commands=list(commands), accepted=len(commands), command_hash=cache_key(commands))
            atomic_json(self.output / 'commands.json', dict(commands=commands))
            atomic_json(self.output / 'playback.json', self.playback)
            self.event('resuming', 'Saved physics checkpoint independently replayed and verified')
        elif kind == 'accepted':
            command, poses, harness = fields['command'], fields['poses'], fields['harness']
            self.playback['motions'].append(motion_from_poses(command, poses))
            self.playback['states'].append(harness.state())
            self.playback['metrics'] = harness.metrics()
            self.data['commands'] = list(harness.history)
            self.data['accepted'] = len(harness.history)
            self.playback['command_hash'] = cache_key(harness.history)
            self.data['command_hash'] = self.playback['command_hash']
            atomic_json(self.output / 'playback.json', self.playback)
            atomic_json(self.output / 'commands.json', dict(commands=harness.history))
            self.event(kind, command.get('name', 'Fold accepted'), step=len(harness.history))
        elif kind == 'proposal':
            try:
                proposal = json.loads(fields['text'])
                commands = proposal.get('commands', []) if isinstance(proposal, dict) else []
                names = [str(c.get('name', 'Unnamed fold'))[:180] for c in commands if isinstance(c, dict)]
            except (ValueError, TypeError):
                names = []
            self.event(kind, 'Checking proposed folds' if names else 'Checking model response',
                       names=names, call=fields['call'])
        elif kind == 'working':
            self.data['calls'] = fields['call']
            self.event(kind, 'Argon is choosing its next folds', call=fields['call'])
        elif kind == 'compacted':
            self.event(kind, 'Context refreshed; exact paper geometry, layer contacts, and accepted folds preserved',
                       exchanges=fields['exchanges'], physics_sha256=fields['physics_sha256'])
        elif kind == 'recovering':
            self.event(kind, 'Replanning from the current paper; accepted folds are preserved', call=fields['call'])
        elif kind == 'feedback':
            feedback = fields['feedback']
            if 'probe_result' in feedback:
                probe = feedback['probe_result']
                self.event('tested', 'Candidate motion passed; live paper unchanged' if probe['ok'] else
                           'Refining candidate: ' + probe['error'], call=fields['call'])
            if not feedback['ok']:
                self.event('rejected', feedback['error'], call=fields['call'])
        elif kind == 'finished':
            self.data['report'] = fields['report']
            self.data['status'] = fields['report']['status']
            self.event(kind, 'Run finished: ' + self.data['status'].replace('_', ' '))


def run_paper(client, url, output, progress, route, max_calls=None, resume=False, context_policy=None):
    """One continuous physics history, with lossless state and compacted dialogue."""
    allowance = int(os.environ.get('ORI_LIVE_MAX_CALLS', '512')) if max_calls is None else max_calls
    if allowance < 1:
        raise ValueError('Call allowance must be positive')
    target = json.dumps({'title': route['title'], 'summary': route['summary']})
    task = APPROXIMATE_TASK + """
Live-demo objective (video classification, not execution feedback):
""" + target + """
Keep this finished object as the target throughout the run. Check the video's
ending against this description. Do not switch objects based on an intermediate
silhouette. Work patiently toward a recognizable approximation using supported
folds. Return one new fold at a time, inspecting the resulting geometry and
current panel IDs before choosing the next. Never reuse stale panel IDs.
You have a long working session. A blocked response does not end the session:
reconsider your plan from the CURRENT sheet, using supported folds and legal
unfolding moves when necessary. Never assume the paper was reset. Every change,
including an unfold, must be executed and validated by the harness. For folds
that need multiple hinges moving together, use the precrease and compound tools;
test candidate mechanisms with probe and refine from the returned constraints.
A rejected probe leaves the live paper unchanged and is an opportunity to solve
the motion, not a reason to abandon the demonstrated fold.
The current harness_feedback contains the exact paper, material coordinates,
layer contacts, and ALL already accepted commands. Older dialogue is compacted;
this does not change the physics or undo any fold. Recent exchanges and failed
moves are historical context, not current geometry. Continue toward the same
target. Set done:true only when you believe the approximation is complete.
"""
    policy = dict(DEFAULT_POLICY if context_policy is None else context_policy)
    previous_calls = 0
    if resume:
        config = json.loads((output / 'config.json').read_text())
        if not config.get('context_policy') or not config.get('continue_on_blocked'):
            raise ValueError('This older run cannot be continued by the compacting runner')
        task, policy = config['task'], config['context_policy']
        previous_calls = max((int(p.name.removeprefix('call-')) for p in (output / 'debug').glob('call-*')), default=0)
    else:
        progress.begin_run()
    progress.data.update(max_calls=previous_calls+allowance, resumable=True)
    progress.event('planning' if not resume else 'resuming',
                   'Working toward the target while preserving every validated fold')
    def observe(kind, **fields):
        if kind != 'finished':
            progress.observe(kind, **fields)
    report = run(client, url, MODEL, output, max_calls=previous_calls+allowance, task=task,
                 transport='generate-content', thinking_level='high', max_output_tokens=32768,
                 observer=observe, export=False, resume=resume,
                 context_policy=policy, continue_on_blocked=True)
    complete = report['status'] == 'model_claimed_done' and report['accepted_folds'] > 0
    if not complete:
        report = dict(report, stop_reason=report['status'],
                      status='partial' if report['accepted_folds'] else 'unavailable')
    atomic_json(output / 'result.json', report)
    message = ('Your fold-only approximation is ready.' if complete else
               'The session paused. Your validated folds are saved; continue from the current paper when ready.')
    progress.data.update(status=report['status'], report=report, message=message)
    progress.event('finished' if complete else 'incomplete', message)
    return report


def work(output, url, resume=False):
    progress = Progress(output, url, resume=resume)
    try:
        with genai.Client(api_key=load_settings().gemini_api_key, http_options=types.HttpOptions(
                timeout=600000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
            route = progress.data['route'] if resume else classify(client, url, output)
            progress.data.update(route=route, status='running')
            progress.event('routed', f"Selected {'paper harness' if route['kind'] == 'origami' else route['kind']}: {route['summary']}")
            if route['kind'] == 'origami':
                run_paper(client, url, output, progress, route, resume=resume)
            elif route['kind'] == 'lego':
                from ori.reconstruction.lego import generate, UnsupportedAssembly
                try:
                    report = generate(client, url, output, MODEL, progress.event)
                except UnsupportedAssembly as error:
                    progress.data.update(status='unsupported', message=str(error))
                    progress.event('incomplete', str(error))
                    return
                progress.data.update(status='completed', report=report,
                                     message='Your LEGO assembly is ready. Inspect the inventory and any video uncertainties.')
                progress.event('finished', progress.data['message'])
            elif route['kind'] == 'mujoco':
                from ori.reconstruction.mujoco_scene import generate, render
                progress.event('working', 'Argon is proposing a MuJoCo scene')
                scene = generate(url, output, model=MODEL)
                progress.event('accepted', 'Scene passed compiler validation; rendering dynamics')
                report = render(scene, output, movie=True)
                progress.data.update(status='completed', report=report)
                progress.event('finished', 'MuJoCo recording is ready')
            else:
                progress.data['status'] = 'unsupported'
                progress.event('finished', 'This video needs a different simulator')
    except Exception as exc:
        # Detailed diagnostics stay on disk; never return credential-bearing API errors.
        atomic_json(output / 'job-error.json', dict(type=type(exc).__name__, message=str(exc)))
        progress.data['status'] = 'error'
        progress.event('error', 'The run stopped. Check the local job diagnostics.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('url')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    work(args.output, args.url, resume=args.resume)
