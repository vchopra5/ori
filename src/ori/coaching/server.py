"""Local studio, saved artifacts, and bounded live video jobs."""
from .lesson_actions import lesson_action
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import json
import subprocess
import os
import sys
import threading
import uuid
import re

JOB_LOCK = threading.Lock()
JOB_PROCESS = None

REPLAY_LOCK = threading.Lock()
OBSERVATION_LOCK = threading.Lock()
LIBRARY_LOCK = threading.RLock()
INSTANCE_ID = uuid.uuid4().hex


def paper_sources():
    sources = {}
    for folder, title in [('fold_commands_fox', 'A fox, one fold at a time'), ('fold_layers_demo', 'The layers beneath a fold')]:
        base = ROOT / 'output' / folder
        if (base / 'commands.json').exists():
            sources[folder] = (base, title, 'Paper harness')
    trials = sorted((ROOT / 'output/fold_trials/runs').glob('*/*/result.json'),
                    key=lambda p: (read_json(p, {}).get('status') in {'model_claimed_done', 'manual_verified'}, p.stat().st_mtime), reverse=True)
    for path in trials:
        result = read_json(path, {})
        if not result.get('accepted_folds') or result.get('status') not in {'model_claimed_done', 'manual_verified'}:
            continue
        from hashlib import sha256
        key = 'trial-' + sha256(str(path.parent.relative_to(ROOT)).encode()).hexdigest()[:16]
        if key not in sources:
            sources[key] = (path.parent, read_json(path.parent / 'job.json', {}).get('route', {}).get('title') or ('An owl, imagined by Argon' if path.parent.parent.name == 'FdBTwMuh1mU' else 'Paper, imagined by Argon'), ('Manual · paper harness' if result.get('authoring_method') == 'manual' else 'Assisted · paper harness') if result.get('status') == 'manual_verified' else 'Argon · paper harness')
    return sources


def paper_source(identifier):
    sources=paper_sources()
    if identifier in sources:
        return sources[identifier]
    # Preserve old links that referred to the latest completed run for a video.
    if re.fullmatch(r'trial-[\w-]{11}',identifier):
        return next((value for value in sources.values() if value[0].parent.name==identifier[6:]),None)
    return None


def replay(base):
    """Cache a validated replay; compile with the project's simulation runtime."""
    from hashlib import sha256
    document = read_json(base / 'commands.json', {})
    commands = document.get('commands', []) if isinstance(document, dict) else document
    digest = sha256(json.dumps(commands, sort_keys=True).encode()).hexdigest()[:20]
    target = base / 'playback.json'
    with REPLAY_LOCK:
        cached = read_json(target, {})
        if cached.get('command_hash') != digest:
            python = ROOT / '.venv/bin/python'
            result = subprocess.run([str(python) if python.exists() else sys.executable,
                       '-m', 'ori.coaching.paper_playback', str(base / 'commands.json'), str(target)],
                       cwd=ROOT, capture_output=True, text=True, timeout=300,
                       env={**os.environ, 'PYTHONPATH': str(ROOT / 'src')})
            if result.returncode:
                raise RuntimeError('Could not prepare this paper replay. Check the simulation dependencies.')
            cached = read_json(target, {})
        return cached

ROOT = Path(__file__).resolve().parents[3]
COACHING = '/src/ori/coaching/'


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def library():
    with LIBRARY_LOCK:
        return _library()


def _library():
    items = []
    for folder, (base, title, engine) in paper_sources().items():
        commands = read_json(base / 'commands.json', {})
        report_name = 'result.json' if (base / 'result.json').exists() else 'report.json'
        report = read_json(base / report_name, {})
        relative = '/' + base.relative_to(ROOT).as_posix()
        metrics = report.get('metrics', report)
        valid = all(isinstance(metrics.get(k), (int, float)) and 0 <= metrics[k] < 1e-8
                    for k in ('max_length_error', 'max_seam_gap'))
        items.append(dict(id=folder, title=title, kind='paper', engine=engine,
                          legacy_id='trial-'+base.parent.name if folder.startswith('trial-') else None,
                          replay_url=f'/api/paper/{folder}',
                          commands=[lesson_action(c) for c in (commands.get('commands', []) if isinstance(commands, dict) else commands)],
                          report={**report, **metrics, 'ok': valid}, report_url=f'{relative}/{report_name}',
                          audit=read_json(base / 'feedback-audit.json', {}),
                          source_url=report.get('video_url'), thumbnail=next((f'{relative}/{name}' for name in ('final.png','fox.png','layer-selection.png') if (base/name).exists()), None)))
    items.sort(key=lambda item: not item['id'].startswith('trial-'))
    for folder, name, title in [('mujoco_origami', 'accordion', 'An accordion in motion'), ('mujoco_fox_3d', 'fox3d', 'A little fox in three dimensions')]:
        base = ROOT / 'output' / folder
        if (base / f'{name}.mp4').exists():
            items.append(dict(id=folder, title=title, kind='recording', engine='MuJoCo',
                              video=f'/output/{folder}/{name}.mp4', report=read_json(base / 'report.json', {}),
                              report_url=f'/output/{folder}/report.json'))
    for scene_path in sorted(list((ROOT / 'output').glob('*/scene.json')) + list((ROOT / 'output/fold_trials/runs').glob('*/*/scene.json'))):
        base = scene_path.parent
        scene = read_json(scene_path, {})
        relative = '/' + base.relative_to(ROOT).as_posix()
        if (base / 'animation.mp4').exists():
            items.append(dict(id=base.name, title=scene.get('title', base.name),
                              kind='recording', engine='MuJoCo',
                              video=f'{relative}/animation.mp4',
                              report=read_json(base / 'report.json', {}),
                              report_url=f'{relative}/report.json'))
    for path in sorted(list((ROOT / 'output').glob('*/lego-playback.json')) +
                       list((ROOT / 'output/fold_trials/runs').glob('*/*/lego-playback.json'))):
        base = path.parent
        playback = read_json(path, {})
        report = read_json(base / 'report.json', {})
        if not report.get('passed'):
            continue
        relative = '/' + base.relative_to(ROOT).as_posix()
        items.append(dict(id=base.name, title=playback.get('title', 'LEGO assembly'),
                          kind='lego', engine='LEGO snap harness', report=report,
                          replay_url=f'{relative}/lego-playback.json',
                          report_url=f'{relative}/report.json', source_url=report.get('source_url')))
    from hashlib import sha256
    from .demo_hints import load_hints
    for item in items:
        if item['kind'] == 'paper' and item.get('source_url'):
            try:
                hints = load_hints(item['source_url'], ROOT / '.local/demo-hints.json')
                item['prefer_fresh_run'] = bool(hints and hints.get('prefer_fresh_run'))
            except (OSError, ValueError):
                item['prefer_fresh_run'] = False
        base=(ROOT/item['report_url'].lstrip('/')).parent
        item['delete_token']=sha256(str(base.relative_to(ROOT)).encode()).hexdigest()
        item['saved_at']=base.stat().st_mtime
    return items


def delete_run(token):
    """Remove one saved run into a recoverable local trash directory."""
    if not isinstance(token,str) or not re.fullmatch(r'[a-f0-9]{64}',token):
        raise ValueError('Choose a saved run to delete')
    with JOB_LOCK, LIBRARY_LOCK, REPLAY_LOCK, OBSERVATION_LOCK:
        # Deleting while reconstruction writes artifacts could corrupt a run.
        if JOB_PROCESS is not None and JOB_PROCESS.poll() is None:
            raise RuntimeError('Wait for the current reconstruction to finish before deleting a run.')
        item=next((item for item in library() if item['delete_token']==token),None)
        if item is None:
            raise ValueError('That saved run no longer exists. Refresh your library.')
        original=(ROOT.resolve()/item['report_url'].lstrip('/')).parent
        base=original.resolve()
        output=(ROOT/'output').resolve()
        if base!=original or not base.is_relative_to(output) or base==output or (output/'.trash') in base.parents:
            raise ValueError('This saved run cannot be deleted')
        trash=output/'.trash'
        trash.mkdir(exist_ok=True)
        if trash.is_symlink():
            raise ValueError('Invalid trash directory')
        identifier=uuid.uuid4().hex
        metadata=trash/(identifier+'.json')
        metadata.write_text(json.dumps(dict(original_path=str(base.relative_to(ROOT.resolve())),title=item['title'])))
        try:
            base.rename(trash/identifier)
        except OSError:
            metadata.unlink(missing_ok=True)
            raise RuntimeError('Could not delete this run. Try again.')
        return dict(deleted=True,title=item['title'])


def job_path(identifier):
    if not re.fullmatch(r'live-[a-f0-9]{32}', identifier):
        return None
    return next((ROOT / 'output/fold_trials/runs').glob(f'*/{identifier}'), None)


def start_job(url):
    global JOB_PROCESS
    from ..reconstruction.video import plan_path
    video_id = plan_path(url).stem
    with JOB_LOCK:
        if JOB_PROCESS is not None and JOB_PROCESS.poll() is None:
            raise RuntimeError('A video is already being reconstructed. Wait for that run to finish.')
        base = ROOT / 'output/fold_trials/runs' / video_id / ('live-' + uuid.uuid4().hex)
        base.mkdir(parents=True)
        (base / 'job.json').write_text(json.dumps(dict(id=base.name, url=url, status='queued', revision=0,
            events=[], commands=[], accepted=0, route=None)))
        python = ROOT / '.venv/bin/python'
        with (base / 'worker.log').open('w') as log:
            JOB_PROCESS = subprocess.Popen([str(python) if python.exists() else sys.executable,
                '-m', 'ori.coaching.jobs', str(base), url], cwd=ROOT, stdout=log, stderr=log,
                env={**os.environ, 'PYTHONPATH': str(ROOT / 'src')})
        return read_json(base / 'job.json')


def resume_job(identifier):
    global JOB_PROCESS
    from ..reconstruction.batching import atomic_json
    base = job_path(identifier)
    if base is None:
        raise ValueError('Unknown saved job')
    with JOB_LOCK:
        if JOB_PROCESS is not None and JOB_PROCESS.poll() is None:
            raise RuntimeError('A video is already being reconstructed. Wait for that run to finish.')
        job = read_json(base / 'job.json', {})
        config = read_json(base / 'config.json', {})
        if not config.get('context_policy') or not (base / 'checkpoint.json').is_file():
            raise ValueError('This older job has no resumable physics checkpoint. Start a new run.')
        if job.get('status') in {'queued', 'classifying', 'running', 'model_claimed_done', 'completed'}:
            raise ValueError('Only paused or incomplete jobs can be continued')
        job['status'] = 'queued'
        atomic_json(base / 'job.json', job)
        python = ROOT / '.venv/bin/python'
        try:
            with (base / 'worker.log').open('a') as log:
                JOB_PROCESS = subprocess.Popen([str(python) if python.exists() else sys.executable,
                    '-m', 'ori.coaching.jobs', str(base), job['url'], '--resume'], cwd=ROOT,
                    stdout=log, stderr=log, env={**os.environ, 'PYTHONPATH': str(ROOT / 'src')})
        except Exception:
            job['status'] = 'error'
            atomic_json(base / 'job.json', job)
            raise
        return job


def observe_request(body):
    import math
    identifier, step, frame = body.get('run_id'), body.get('step'), body.get('frame')
    point=body.get('point')
    if point is not None and (not isinstance(point,list) or len(point)!=2 or
            not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<=v<=1 for v in point)):
        raise ValueError('Choose a point inside the camera guide')
    if not isinstance(identifier, str) or isinstance(step, bool) or not isinstance(step, int) or step < 0:
        raise ValueError('Choose a paper lesson and valid step')
    if not isinstance(frame, str) or not 100 < len(frame) <= 900000:
        raise ValueError('Provide a bounded JPEG camera frame')
    base = job_path(identifier) if identifier.startswith('live-') else None
    if base is None:
        source = paper_source(identifier)
        if source is None:
            raise ValueError('This lesson has no paper reference')
        base = source[0]
        replay(base)
    playback = read_json(base / 'playback.json', {})
    if step >= len(playback.get('states', [])):
        raise ValueError('Unknown lesson step')
    if not OBSERVATION_LOCK.acquire(blocking=False):
        raise RuntimeError('Another camera check is finishing. Try again shortly.')
    try:
        from .vision_worker import WORKER
        return WORKER.request(dict(playback=str(base / 'playback.json'),
                                   commands=str(base / 'commands.json'),step=step,frame=frame,point=point))
    finally:
        OBSERVATION_LOCK.release()


def live_request(body,origin):
    identifier=body.get('run_id')
    owner=body.get('client_id')
    if owner is not None and (not isinstance(owner,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',owner)):
        raise ValueError('Invalid browser session ID')
    if not isinstance(identifier,str):raise ValueError('Choose a paper lesson')
    base=job_path(identifier) if identifier.startswith('live-') else None
    if base is None:
        source=paper_source(identifier)
        if source is None:raise ValueError('This lesson has no paper reference')
        base=source[0]
    replay(base)
    from .live_worker import LIVE_WORKER
    return LIVE_WORKER.start(base,origin,owner)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_error(self,code,message=None,explain=None):
        if urlsplit(self.path).path.startswith('/api/'):
            self.json_response(dict(error=message or self.responses.get(code,('API request failed',))[0]),code)
        else:
            super().send_error(code,message,explain)

    def json_response(self, value, status=200):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path not in {'/api/jobs', '/api/observe', '/api/library/delete', '/api/live/session'}:
            self.send_error(404)
            return
        if urlsplit('http://' + self.headers.get('Host', '')).hostname not in {'127.0.0.1', 'localhost'}:
            self.send_error(403)
            return
        origin = self.headers.get('Origin')
        if (origin and origin != 'http://' + self.headers.get('Host', '')) or self.headers.get_content_type() != 'application/json':
            self.send_error(403)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= (1000000 if self.path == '/api/observe' else 4096):
                raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected an object with a YouTube URL')
            if self.path == '/api/live/session':
                self.json_response(live_request(body,'http://'+self.headers['Host']))
                return
            if self.path == '/api/observe':
                self.json_response(observe_request(body))
                return
            if self.path == '/api/library/delete':
                self.json_response(delete_run(body.get('token')))
                return
            if 'resume_id' in body:
                if not isinstance(body['resume_id'], str):
                    raise ValueError('Provide a saved job ID')
                self.json_response(resume_job(body['resume_id']), 202)
                return
            url = body.get('url')
            if not isinstance(url, str):
                raise ValueError('Provide a YouTube URL')
            self.json_response(start_job(url), 202)
        except (ValueError, TypeError) as exc:
            self.json_response(dict(error=str(exc)), 400)
        except subprocess.TimeoutExpired:
            self.json_response(dict(error='Camera check timed out. Try again.'), 503)
        except RuntimeError as exc:
            self.json_response(dict(error=str(exc)), 409)
        except OSError:
            self.json_response(dict(error='The coaching runtime could not start. Check the local server and try again.'),503)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            self.json_response(dict(service='ori-coaching',live_protocol=4,instance_id=INSTANCE_ID,port=self.server.server_port))
            return
        if path.startswith('/api/jobs/'):
            pieces = path.removeprefix('/api/jobs/').split('/')
            base = job_path(pieces[0])
            if base is None or len(pieces) > 2 or len(pieces) == 2 and pieces[1] != 'playback':
                self.send_error(404)
                return
            value = read_json(base / ('playback.json' if len(pieces) == 2 else 'job.json'))
            if value is None:
                self.send_error(404)
                return
            if len(pieces) == 1 and isinstance(value.get('commands'), list):
                value = {**value, 'commands': [lesson_action(c) for c in value['commands']]}
            self.json_response(value)
            return
        if path in {'/', COACHING.rstrip('/')}:
            self.send_response(302)
            self.send_header('Location', COACHING + ('?' + urlsplit(self.path).query if urlsplit(self.path).query else ''))
            self.end_headers()
            return
        if path == '/api/library' or path.startswith('/api/paper/'):
            try:
                if path == '/api/library':
                    value = library()
                else:
                    source = paper_source(path.removeprefix('/api/paper/'))
                    if source is None:
                        self.send_error(404)
                        return
                    value = replay(source[0])
            except (RuntimeError, subprocess.TimeoutExpired):
                self.send_error(503, 'Paper replay could not be prepared')
                return
            payload = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        # Serve only frontend assets, the bundled renderer, and saved artifacts.
        # In particular, never serve .env, source code, symlinks outside allowed roots, or .git.
        target = Path(self.translate_path(self.path)).resolve()
        allowed = [ROOT / 'src/ori/coaching', ROOT / 'output',
                   ROOT / 'src/ori/reconstruction/simulator/vendor/origami-simulator/dependencies']
        if not any(target.is_relative_to(base) for base in allowed) or target.is_dir() and path != COACHING:
            self.send_error(404)
            return
        if target.suffix not in {'.html', '.css', '.mjs', '.js', '.json', '.mp4', '.png', '.gif', '.svg', ''}:
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):
        # Apply the same path restrictions to HEAD requests.
        self.send_error(405)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Ori studio: http://127.0.0.1:{server.server_port}{COACHING}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
