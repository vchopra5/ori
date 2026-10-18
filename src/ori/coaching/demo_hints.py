"""Optional local rehearsal guidance; never substitutes for model/harness output."""
import json
from pathlib import Path

from ..reconstruction.video import plan_path

HINTS_PATH = Path(__file__).resolve().parents[3] / '.local' / 'demo-hints.json'


def load_hints(url, path=None):
    """Match canonical video IDs, never titles, URL substrings, or other videos."""
    video_id = plan_path(url).stem
    path = HINTS_PATH if path is None else Path(path)
    if not path.exists():
        return None
    document = json.loads(path.read_text())
    if document.get('version') != 1 or not isinstance(document.get('videos'), dict):
        raise ValueError('Local demo hints require version 1 and a videos object')
    hints = document['videos'].get(video_id)
    if hints is None:
        return None
    if not isinstance(hints, dict):
        raise ValueError('Video demo hints must be an object')
    return dict(video_id=video_id, **hints)


def prompt_for(hints):
    return '''
Local demo rehearsal hints for this exact source video:
These are operator-provided planning suggestions, not observations or harness
feedback. Use them to avoid rediscovering known geometry. Still submit every
action through the harness and inspect the actual returned state. Never invent
an acceptance, rejection, correction, or video observation. A requested rehearsal
mistake is intentional demo choreography, not an independently discovered error.
Use one action per response. Follow the rehearsal sequence once, then finish the
reference solution. Use the accepted history AND recent undo exchanges to track
progress; do not repeat the deliberate mistake after undo or resume. If geometry
differs, adapt to the current state. Review the real result before done:true.
''' + json.dumps(hints, ensure_ascii=False)
