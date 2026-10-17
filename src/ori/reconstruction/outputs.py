"""Keep importable plans separate from checkpoints and diagnostic artifacts."""
import base64
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from .batching import atomic_json


def new_run(base: Path, kind: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run = base.parent / 'runs' / base.stem / f'{kind}-{stamp}-{uuid4().hex[:8]}'
    run.mkdir(parents=True)
    return run.resolve()


def clip_directory(run: Path, start: float, end: float) -> Path:
    """A resumed clip gets another pass, preserving every earlier attempt."""
    clip = run / 'debug' / 'clips' / f'{start:g}-{end:g}'
    clip.mkdir(parents=True, exist_ok=True)
    attempt = 1
    while True:
        path = clip / f'pass-{attempt:03d}'
        try:
            path.mkdir()
            return path
        except FileExistsError:
            attempt += 1


def save_request(path: Path, request: dict, images: list[dict]) -> None:
    """Log requests using image references, without duplicating base64 pixels.

    data_file is relative to this log. The actual API request is never changed.
    An unmatched inline image is saved once in the run's local assets directory.
    """
    path = path.resolve()
    references = {}
    for image in images:
        source = Path(image['path']).resolve()
        if source.is_file():
            references[sha256(source.read_bytes()).hexdigest()] = source

    def compact(value):
        if isinstance(value, list):
            return [compact(item) for item in value]
        if not isinstance(value, dict):
            return value
        if value.get('type') == 'image' and isinstance(value.get('data'), str):
            pixels = base64.b64decode(value['data'], validate=True)
            digest = sha256(pixels).hexdigest()
            source = references.get(digest)
            if source is None:
                source = path.parent / 'assets' / digest
                source.parent.mkdir(parents=True, exist_ok=True)
                if not source.exists():
                    source.write_bytes(pixels)
            return {**{k: compact(v) for k, v in value.items() if k != 'data'},
                    'data_file': os.path.relpath(source, path.parent)}
        return {k: compact(v) for k, v in value.items()}

    atomic_json(path, compact(request))


def resolve_checkpoint(path: Path) -> Path:
    """Honor resume paths printed before the output-directory migration."""
    path = path.resolve()
    if path.is_file():
        return path
    for root in path.parents:
        manifest = root / 'runs' / 'migrations.json'
        if manifest.is_file():
            target = json.loads(manifest.read_text()).get(str(path.relative_to(root)))
            if target:
                return root / target
    return path


def migrate_outputs(root: Path) -> dict[str, str]:
    """Move recognized legacy outputs without deleting history or changing plans.

    The durable manifest also lets interrupted migrations finish on rerun.
    Unknown files and top-level VIDEO_ID.json/.txt/.fold exports stay untouched.
    """
    root = root.resolve()
    manifest = root / 'runs' / 'migrations.json'
    moves = json.loads(manifest.read_text()) if manifest.exists() else {}
    for entry in sorted(root.iterdir()):
        match = re.fullmatch(r'([\w-]{11})\.(animation|static)-([\w-]+)', entry.name)
        if entry.is_dir() and (match or entry.name.startswith('symbolic-trial-')):
            if match:
                video, kind, identifier = match.groups()
                target = root / 'runs' / video / f'{kind}-{identifier}'
            else:
                from .video import plan_path
                plan = entry / 'plan.json'
                if not plan.exists():
                    continue
                video = plan_path(json.loads(plan.read_text())['video_url']).stem
                target = root / 'runs' / video / entry.name
            for source in sorted(entry.rglob('*')):
                if not source.is_file():
                    continue
                relative = source.relative_to(entry)
                name = relative.as_posix()
                exports = {f'{video}.json': 'plan.json', f'{video}.txt': 'animation.txt',
                           'progress.checkpoint.json': 'progress.checkpoint.json',
                           'plan.json': 'plan.json', 'compiled.fold': 'compiled.fold',
                           'status.json': 'status.json', 'final.png': 'final.png'}
                dest = target / exports.get(name, f'debug/legacy/{name}')
                moves[str(source.relative_to(root))] = str(dest.relative_to(root))
        elif entry.is_file() and re.fullmatch(r'[\w-]{11}\.(?:checkpoint|request|clip-[\w.-]+)\.json', entry.name):
            moves[entry.name] = f'archive/{entry.name[:11]}/{entry.name}'

    # Check for collisions before any mutation. Existing targets from a completed
    # migration are expected only when the corresponding source no longer exists.
    for old, new in moves.items():
        if (root / old).exists() and (root / new).exists():
            raise FileExistsError(f'Refusing to overwrite {root / new}')
    if not moves:
        return moves
    atomic_json(manifest, moves)
    for old, new in moves.items():
        source, target = root / old, root / new
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)

    def rebase(value):
        if isinstance(value, dict):
            return {k: rebase(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rebase(v) for v in value]
        if isinstance(value, str):
            try:
                relative = str(Path(value).resolve().relative_to(root))
            except (ValueError, OSError):
                return value
            if relative in moves:
                return str(root / moves[relative])
        return value

    for new in moves.values():
        if new.endswith('progress.checkpoint.json'):
            checkpoint = root / new
            original = json.loads(checkpoint.read_text())
            updated = rebase(original)
            if updated != original:
                # Retain the original checkpoint bytes alongside the raw logs.
                backup = checkpoint.parent / 'debug' / 'legacy' / 'checkpoint-before-migration.json'
                backup.parent.mkdir(parents=True, exist_ok=True)
                if not backup.exists():
                    backup.write_bytes(checkpoint.read_bytes())
                atomic_json(checkpoint, updated)
    # Only remove empty directories that contained files we just moved.
    for old in moves:
        parent = (root / old).parent
        while parent != root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    return moves
