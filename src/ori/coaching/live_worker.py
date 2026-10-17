"""Launch isolated ephemeral live sessions using the project's Gemini runtime."""
import atexit
import json
import os
from pathlib import Path
import selectors
import subprocess
import threading

ROOT=Path(__file__).resolve().parents[3]


class LiveWorker:
    def __init__(self):
        self.process=None;self.owner=None;self.lock=threading.Lock();atexit.register(self.close)

    def close(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
            if self.process.stdout:self.process.stdout.close()
            self.process=None
        self.owner=None

    def start(self,base,origin,owner=None):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                # Another tab/test must never evict the person currently demoing.
                if not owner or self.owner!=owner:
                    raise RuntimeError('Another tab is already using the live coach on this server. Stop that session before starting another; it has been left connected.')
            self.close()
            self.owner=owner
            self.process=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-m','ori.coaching.live_coach',
                str(base/'playback.json'),str(base/'commands.json'),origin],
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,cwd=ROOT,
                env={**os.environ,'PYTHONPATH':str(ROOT/'src')})
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout,selectors.EVENT_READ)
                if not selector.select(15):self.close();raise RuntimeError('Live coach could not start.')
                line=self.process.stdout.readline()
            if not line:self.close();raise RuntimeError('Install the coaching runtime to start Gemini Live.')
            info=json.loads(line)
            return {'url':f"ws://127.0.0.1:{info['port']}/{info['token']}"}


LIVE_WORKER=LiveWorker()
