"""Compile accepted fold commands into a compact, rigid-motion browser replay."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from ..reconstruction.batching import atomic_json
from ..reconstruction.fold_commands import FoldHarness


def motion_from_poses(command, poses):
    start, middle, end = poses[0], poses[len(poses) // 2], poses[-1]
    moving = [a.id for a, b in zip(start, middle)
          if abs(a.xyz - b.xyz).max() > 1e-9]
    if command.get('type') == 'reorient':
        import numpy as np
        origin=np.asarray(command['origin'],dtype=float);axis=np.asarray(command['axis'],dtype=float)
        axis=axis/np.linalg.norm(axis)
        return dict(type='reorient',crease=[origin.tolist(),(origin+axis).tolist()],
                    angle_degrees=command['angle_degrees'],moving=[p.id for p in start],
                    panels=[dict(id=p.id,material=p.uv.tolist(),vertices=p.xyz.tolist(),
                                 contacts=p.contacts,end_contacts=q.contacts) for p,q in zip(start,end)])
    if command.get('type') == 'compound':
        from ..reconstruction.fold_compound import compile_paths
        return dict(type='compound', paths=compile_paths(command, start), moving=moving,
                    panels=[dict(id=p.id, material=p.uv.tolist(), vertices=p.xyz.tolist(),
                                 contacts=p.contacts, end_contacts=q.contacts) for p, q in zip(start, end)])
    return dict(crease=command['crease'], angle_degrees=command.get('angle_degrees', 0), moving=moving,
                panels=[dict(id=p.id, material=p.uv.tolist(), vertices=p.xyz.tolist(),
                     contacts=p.contacts, end_contacts=q.contacts)
                    for p, q in zip(start, end)])


def compile_playback(commands):
    harness = FoldHarness()
    states = [harness.state()]
    motions = []
    for command in commands:
        poses = harness.fold(command)
        motions.append(motion_from_poses(command, poses))
        states.append(harness.state())
    return dict(version=1, states=states, motions=motions, metrics=harness.metrics(), seconds_per_step=2.6)


def cache_key(commands):
    return sha256(json.dumps(commands, sort_keys=True).encode()).hexdigest()[:20]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('commands', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    document = json.loads(args.commands.read_text())
    commands = document['commands'] if isinstance(document, dict) else document
    replay = compile_playback(commands)
    replay['command_hash'] = cache_key(commands)
    atomic_json(args.output, replay)
    print(f'Prepared {len(commands)} validated fold motions: {args.output}', flush=True)


if __name__ == '__main__':
    main()
