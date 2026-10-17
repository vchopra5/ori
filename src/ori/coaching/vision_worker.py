"""Keep the NN and reference embeddings warm in an isolated local runtime."""
import atexit
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]


class VisionWorker:
    def __init__(self):
        self.process=None
        self.selector=None
        atexit.register(self.close)

    def close(self):
        if self.selector:
            self.selector.close()
            self.selector=None
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            for pipe in (self.process.stdin,self.process.stdout):
                if pipe:
                    pipe.close()
            self.process=None

    def request(self,body,timeout=100):
        if self.process is None or self.process.poll() is not None:
            self.close()
            python=ROOT/'.venv/bin/python'
            self.process=subprocess.Popen([str(python) if python.exists() else sys.executable,
                '-m','ori.coaching.observe','--worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,text=True,bufsize=1,cwd=ROOT,
                env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'HF_HUB_OFFLINE':'1',
                     'TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1'})
            self.selector=selectors.DefaultSelector()
            self.selector.register(self.process.stdout,selectors.EVENT_READ)
        try:
            self.process.stdin.write(json.dumps(body)+'\n')
            self.process.stdin.flush()
            if not self.selector.select(timeout):
                raise RuntimeError('The camera check timed out. Try again.')
            line=self.process.stdout.readline()
            if not line:
                raise RuntimeError('The camera checker could not start. Check the Gemini configuration.')
            result=json.loads(line)
            if 'error' in result:
                raise RuntimeError(result['error'])
            return result
        except (OSError,ValueError,RuntimeError) as exc:
            self.close()
            if isinstance(exc,RuntimeError):
                raise
            raise RuntimeError('The camera checker is unavailable. Try again.') from exc


WORKER=VisionWorker()
