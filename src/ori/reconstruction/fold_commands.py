"""Executable straight folds on a convex, zero-thickness sheet.

Commands use CURRENT world coordinates, right-hand angles, and an explicit
half-plane. Geometry is generated here, never supplied by a language model.
"""
from dataclasses import dataclass, field
import copy
import math

import numpy as np

from . import fold_layers

EPS = 1e-8
MODEL_INSTRUCTIONS = """Return JSON {"commands":[...]} only. Start with a square
with corners [-1,0,0], [0,-1,0], [1,0,0], [0,1,0]. Each command is
{"name":"short instruction", "crease":[[x,y,z],[x,y,z]],
"normal":[0,0,1], "moving_side":"left" or "right", "angle_degrees":180}.
Crease points and normal are in the CURRENT world frame. Left is the positive
side of cross(normal, crease_end-crease_start). Angles follow the right-hand
rule about crease_start -> crease_end. Optional "layers" selects "all" (default),
"top", "bottom", or a list of current panel IDs from state. Top/bottom are
relative to the supplied normal; selection occurs on the moving half-plane.
Contacts carry vectors pointing from the other panel toward this panel.
Use exposed layers and fold away from their contacting neighbors. Buried-layer
extraction, contradictory contacts, and broken material seams are rejected.
The crease must cross paper and every cut must lie on the hinge axis. Use
the tools below for compound folds; never add material, cuts or decorations.
The harness returns state and failure feedback. Failed commands commit nothing.
Flat layers have explicit contact order inferred from fold approach; turning a
packet over reverses its order. A successful run does not certify real paper physics.

Additional constructive tools (not a fixed library of origami recipes):
1. Precrease: a straight command with "type":"precrease" and NO angle_degrees.
It subdivides the existing panels along the hinge, without moving the sheet;
layers must be all. Read the returned material vertices and new panel IDs.
2. Coordinated mechanism: {"type":"compound","name":"...",
"parameters":{"a":"pi*t"},"paths":[{"material":[u,v],
"position":["x expression","y expression","z expression"]},...]}.
You may define simultaneous trajectories for ANY existing material vertices.
Omitted vertices remain fixed. Every occurrence of a shared material vertex
moves together. t runs continuously from 0 to 1; expressions describe CURRENT
WORLD coordinates, not displacements. Use numbers, t, pi, + - * /, sin, cos,
sqrt and atan2(y,x). Named parameters may reference earlier parameters.
No Python, JavaScript, conditionals, meshes or new vertices. Precrease first
when you need extra hinges. Derive a rigid linkage from fixed panel edge lengths;
linear interpolation of target vertices usually stretches the paper and fails.
All trajectories must begin at the exact current pose. Every sampled pose must
preserve ALL panel dimensions and seams, avoid intersections and respect layer
order. Invalid motion is rejected atomically with a failing time and constraint.
This can express simultaneous collapses and reverse folds when you derive a
valid mechanism; it does not automatically solve arbitrary crease patterns.
3. Dry run: {"commands":[],"probe":[candidate commands],"done":false}.
Runs the candidate sequence on a copy, returning probe_result with predicted
state/metrics or a precise rejection. NOTHING is committed or shown as a fold.
Use probes to refine difficult mechanisms before submitting them in commands.
Never continue from a probe's predicted state until you actually commit it.
Try these tools before declaring a fold unsupported. Existing accepted actions
are permanent history; work from the authoritative state, not a fresh sheet.
"""


PRE_ROTATION_MODEL_INSTRUCTIONS = MODEL_INSTRUCTIONS
MODEL_INSTRUCTIONS += """
4. Whole-sheet reorientation (NOT a fold):
{"type":"reorient","name":"Turn the whole model over",
 "origin":[0,0,0],"axis":[1,0,0],"angle_degrees":180}.
This applies ONE rigid rotation to ALL paper panels and their contact vectors.
It adds no crease, changes no layer adjacency, and preserves the folded shape.
Use axis [0,0,1] for an in-plane turn; [1,0,0] or [0,1,0] for a turnover
when the paper lies in XY. Use CURRENT world coordinates after every action.
Do not add crease, moving_side, normal or layers to reorient commands.
Never encode 'turn the model over', 'rotate upright' or 'change the view' as a
crease fold. A fold rotates ONLY the selected half-plane and deforms the shape;
reorient rotates the entire existing model. When only the video camera turns,
you may simply interpret that view without changing the paper at all.
"""


PRE_UNDO_MODEL_INSTRUCTIONS = MODEL_INSTRUCTIONS
MODEL_INSTRUCTIONS += """
5. Planning undo (NOT an unfold): {"commands":[],"undo":1,"done":false}.
undo must be a positive integer no greater than the current accepted action count.
It removes that many trailing accepted actions and restores the exact earlier
paper: geometry, panel IDs, layer contacts, and crease subdivisions. These mistaken
actions disappear from the lesson; the raw proposal/undo log remains for auditing.
Use undo when your last action was a planning mistake. Inspect the restored state
and submit a corrected command on the next turn, using its restored panel IDs.
Do not combine undo with commands, probe, blocked or done:true. A rejected proposal
already changed nothing except any explicitly accepted prefix; inspect the history
before deciding what to undo. Unfolding is different: it is a real physical fold
back that retains crease subdivisions and remains a teaching step. Use it only
when that physical fold/unfold belongs in the demonstrated procedure. Accepted
actions remain history EXCEPT when explicitly removed by this planning undo.
"""


# Retain the previous straight-fold contract for verified checkpoint upgrades.
# Its geometry semantics are unchanged; only the available action vocabulary grows.
LEGACY_MODEL_INSTRUCTIONS = MODEL_INSTRUCTIONS.split('\nAdditional constructive tools')[0].replace(
    'the tools below for compound folds; never add material, cuts or decorations.',
    'straight folds; do not generate meshes, disconnected parts, cuts or decorations.').replace(
    'packet over reverses its order. A successful run does not certify real paper physics.\n',
    'packet over reverses its order. Compound collapses are unsupported. A successful\nrun does not certify real paper physics.\n')


@dataclass
class Panel:
    uv: np.ndarray
    xyz: np.ndarray
    id: str = 'paper'
    contacts: dict = field(default_factory=dict)


def area(points):
    return abs(sum(a[0] * b[1] - a[1] * b[0]
                   for a, b in zip(points, np.roll(points, -1, axis=0)))) / 2


def rotation(axis, radians):
    x, y, z = axis
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + math.sin(radians) * k + (1 - math.cos(radians)) * k @ k


def _pierces(a, b, triangle):
    """Strict segment/triangle interior intersection; seam contact is allowed."""
    p, q, r = triangle
    direction, e1, e2 = b - a, q - p, r - p
    h = np.cross(direction, e2)
    determinant = np.dot(e1, h)
    if abs(determinant) < EPS:
        return False  # Coplanar layers/contact are explicitly permitted.
    s = (a - p) / determinant
    u = np.dot(s, h)
    cross = np.cross(s, e1)
    v = np.dot(direction, cross)
    t = np.dot(e2, cross)
    return EPS < t < 1 - EPS and u > EPS and v > EPS and u + v < 1 - EPS


def crossings(moving, fixed):
    for a in moving:
        for b in fixed:
            for source, target in ((a.xyz, b.xyz), (b.xyz, a.xyz)):
                for p, q in zip(source, np.roll(source, -1, axis=0)):
                    for i in range(1, len(target) - 1):
                        if _pierces(p, q, target[[0, i, i + 1]]):
                            return True
    return False


class FoldHarness:
    def __init__(self):
        uv = np.array([[-1., 0.], [0., -1.], [1., 0.], [0., 1.]])
        self.panels = [Panel(uv, np.column_stack((uv, np.zeros(4))))]
        self.history = []

    def state(self):
        return [{"id": p.id, "material": p.uv.tolist(), "vertices": p.xyz.tolist(),
                 "contacts": copy.deepcopy(p.contacts)} for p in self.panels]

    def layer_state(self):
        """Explicit local contact sides, without artificial thickness offsets."""
        return {'contacts': [dict(panel=p.id, other=other, toward_panel=vector)
                             for p in self.panels for other, vector in p.contacts.items()
                             if p.id < other],
                'back_to_front_z': [p.id for p in fold_layers.ordered(self.panels)]}

    def metrics(self, panels=None):
        panels = self.panels if panels is None else panels
        length_error = 0.
        seam_error = 0.
        for p in panels:
            if not np.isfinite(p.xyz).all():
                raise ValueError('Non-finite paper coordinates')
            for i in range(len(p.uv)):
                for j in range(i):
                    length_error = max(length_error, abs(np.linalg.norm(p.uv[i] - p.uv[j]) - np.linalg.norm(p.xyz[i] - p.xyz[j])))
            # Compare each material vertex with every incident material edge,
            # including T junctions introduced by clipping neighboring faces.
            for uv, xyz in zip(p.uv, p.xyz):
                for q in panels:
                    for i, start in enumerate(q.uv):
                        j = (i + 1) % len(q.uv)
                        edge = q.uv[j] - start
                        t = np.dot(uv - start, edge) / np.dot(edge, edge)
                        if -EPS <= t <= 1 + EPS and np.linalg.norm(start + t * edge - uv) < EPS:
                            seam_error = max(seam_error, np.linalg.norm(q.xyz[i] + t * (q.xyz[j] - q.xyz[i]) - xyz))
        return {"material_area": float(sum(area(p.uv) for p in panels)),
                "max_length_error": float(length_error), "max_seam_gap": float(seam_error),
                "panel_count": len(panels)}

    def reorient(self, command, frames=30):
        """Rigid whole-sheet rotation: retain topology, UVs, and relative layers."""
        if set(command)-{'type','name','origin','axis','angle_degrees'}:
            raise ValueError('Reorientation moves ALL paper; use origin, axis and angle_degrees, not crease or layers')
        try:
            origin=np.asarray(command['origin'],dtype=float)
            axis=np.asarray(command['axis'],dtype=float)
            angle=float(command['angle_degrees'])
        except (KeyError,TypeError,ValueError,OverflowError) as exc:
            raise ValueError('Expected reorientation origin, axis and angle_degrees') from exc
        if (origin.shape!=(3,) or axis.shape!=(3,) or not np.isfinite(origin).all()
                or not np.isfinite(axis).all() or not math.isfinite(angle)
                or not EPS<abs(angle)<=180):
            raise ValueError('Reorientation needs finite 3D vectors and a nonzero angle in [-180,180]')
        length=np.linalg.norm(axis)
        if not math.isfinite(length) or length<EPS:raise ValueError('Reorientation axis must have nonzero finite length')
        axis=axis/length
        poses=[]
        for fraction in np.linspace(0,1,max(frames,math.ceil(abs(angle)/3))+1):
            matrix=rotation(axis,math.radians(angle)*fraction)
            panels=copy.deepcopy(self.panels)
            for panel in panels:
                panel.xyz=(panel.xyz-origin)@matrix.T+origin
                panel.contacts={other:(matrix@np.asarray(vector)).tolist() for other,vector in panel.contacts.items()}
            if any(not np.isfinite(panel.xyz).all() for panel in panels):
                raise ValueError('Reorientation produced non-finite coordinates')
            poses.append(panels)
        metrics=self.metrics(poses[-1])
        if metrics['max_length_error']>EPS or metrics['max_seam_gap']>EPS:
            raise ValueError('Reorientation failed rigid paper constraints')
        self.panels=poses[-1];self.history.append(copy.deepcopy(command))
        return poses

    def fold(self, command, frames=30):
        """Validate every sampled pose, then commit atomically; return animation."""
        if not isinstance(command, dict):
            raise ValueError('Fold command must be an object')
        kind = command.get('type', 'fold')
        if kind == 'reorient':return self.reorient(command,frames)
        if kind == 'compound':
            from .fold_compound import compound
            try:
                return compound(self, command)
            except (TypeError, OverflowError, RecursionError) as exc:
                raise ValueError(f'Invalid compound command: {exc}') from exc
        if kind not in ('fold', 'precrease'):
            raise ValueError('Unknown action type; use fold, precrease, compound or reorient')
        precrease = kind == 'precrease'
        allowed = {'type', 'name', 'crease', 'normal', 'moving_side', 'angle_degrees', 'layers'}
        if set(command) - allowed:
            raise ValueError('Unknown fold command fields')
        try:
            crease = np.array(command['crease'], dtype=float)
            normal = np.array(command['normal'], dtype=float)
            angle = 0. if precrease else float(command['angle_degrees'])
            side_name = command['moving_side']
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Expected crease, normal, moving_side and angle_degrees') from exc
        if crease.shape != (2, 3) or normal.shape != (3,) or not np.isfinite(crease).all() or not np.isfinite(normal).all() or not math.isfinite(angle):
            raise ValueError('Expected finite 3D crease points, normal and angle')
        if side_name not in ('left', 'right') or (not precrease and not EPS < abs(angle) <= 180):
            raise ValueError('Choose left/right and a nonzero angle in [-180,180]')
        origin = crease[0]
        axis = crease[1] - origin
        if np.linalg.norm(axis) < EPS or np.linalg.norm(normal) < EPS:
            raise ValueError('Crease and normal must have nonzero length')
        axis /= np.linalg.norm(axis)
        normal /= np.linalg.norm(normal)
        if abs(np.dot(normal, axis)) > EPS:
            raise ValueError('Crease must be perpendicular to normal')
        side = np.cross(normal, axis) * (1 if side_name == 'left' else -1)
        moving, fixed = [], []
        parents = {}
        for panel in self.panels:
            distances = (panel.xyz - origin) @ side
            if min(distances) >= -EPS:
                moving.append(copy.deepcopy(panel))
                parents[panel.id] = panel.id
                continue
            if max(distances) <= EPS:
                fixed.append(copy.deepcopy(panel))
                parents[panel.id] = panel.id
                continue
            for sign, destination in ((1, moving), (-1, fixed)):
                uv, xyz = [], []
                for i, point in enumerate(panel.xyz):
                    j = (i + 1) % len(panel.xyz)
                    d, e = distances[i] * sign, distances[j] * sign
                    if d >= -EPS:
                        uv.append(panel.uv[i]); xyz.append(point)
                    if (d > EPS and e < -EPS) or (d < -EPS and e > EPS):
                        t = d / (d - e)
                        cut = point + t * (panel.xyz[j] - point)
                        if np.linalg.norm(np.cross(cut - origin, axis)) > EPS:
                            raise ValueError('Cut is off the hinge axis; compound fold required')
                        uv.append(panel.uv[i] + t * (panel.uv[j] - panel.uv[i])); xyz.append(cut)
                if len(uv) >= 3 and area(np.array(uv)) > EPS:
                    child_id = panel.id + ('/m' if sign == 1 else '/s')
                    destination.append(Panel(np.array(uv), np.array(xyz), child_id))
                    parents[child_id] = panel.id
        initial = fixed + moving
        fold_layers.inherit(initial, parents, {p.id: p for p in self.panels})
        selected = fold_layers.select(moving, command.get('layers', 'all'), normal, parents)
        selected_ids = {p.id for p in selected}
        fixed.extend(p for p in moving if p.id not in selected_ids)
        moving = selected
        if not moving or not fixed:
            raise ValueError('Crease must separate moving paper from stationary paper')
        if precrease:
            if 'angle_degrees' in command or command.get('layers', 'all') != 'all':
                raise ValueError('precrease has no angle and subdivides all intersected layers')
            self.panels = initial
            self.history.append(copy.deepcopy(command))
            return [copy.deepcopy(initial), copy.deepcopy(initial)]
        fold_layers.check_departure(moving, fixed, rotation(axis, math.radians(angle) * .001), origin)
        poses = []
        samples = max(frames, math.ceil(abs(angle) / 3))
        for fraction in np.linspace(0, 1, samples + 1):
            matrix = rotation(axis, math.radians(angle) * fraction)
            rotated = [Panel(p.uv.copy(), (p.xyz - origin) @ matrix.T + origin, p.id) for p in moving]
            panels = copy.deepcopy(fixed) + rotated
            metrics = self.metrics(panels)
            if abs(metrics['material_area'] - 2) > EPS or metrics['max_length_error'] > EPS or metrics['max_seam_gap'] > EPS:
                raise ValueError(f'Paper constraint failed: {metrics}')
            if crossings(rotated, fixed):
                raise ValueError(f'Paper intersection at {fraction * angle:.2f} degrees')
            if fraction == 0:
                fold_layers.inherit(panels, {p.id: p.id for p in initial}, {p.id: p for p in initial})
            else:
                approach = rotation(axis, math.radians(angle) * max(0, fraction - .001))
                near = {p.id: ((p.xyz - origin) @ approach.T + origin if p.id in selected_ids else p.xyz)
                        for p in initial}
                fold_layers.resolve(panels, initial, selected_ids, matrix, near)
            poses.append(copy.deepcopy(panels))
        self.panels = poses[-1]
        self.history.append(copy.deepcopy(command))
        return poses

    def execute(self, commands, on_accepted=None):
        """Model-facing feedback: retain accepted prefix on a failed command."""
        for index, command in enumerate(commands):
            try:
                poses = self.fold(command)
            except ValueError as exc:
                return {'ok': False, 'failed_command': index + 1, 'error': str(exc),
                        'accepted_commands': copy.deepcopy(self.history), 'state': self.state(),
                        'layers': self.layer_state()}
            if on_accepted:
                on_accepted(command, poses, self)
        return {'ok': True, 'accepted_commands': copy.deepcopy(self.history),
                'metrics': self.metrics(), 'state': self.state(), 'layers': self.layer_state()}

    def submit(self, proposal, on_accepted=None):
        """Model envelope validation belongs to the harness, as does feedback."""
        error = None
        if not isinstance(proposal, dict):
            error = 'Expected an object with commands, done and optional blocked'
        elif set(proposal) - {'commands', 'done', 'blocked', 'probe', 'undo'}:
            error = 'Unknown proposal fields; use commands, done, blocked, probe or undo'
        elif not isinstance(proposal.get('commands'), list):
            error = 'commands must be an array of new fold commands'
        elif not isinstance(proposal.get('done', False), bool):
            error = 'done must be boolean'
        elif 'blocked' in proposal and not isinstance(proposal['blocked'], str):
            error = 'blocked must be a string'
        if error is None and 'probe' in proposal and (not isinstance(proposal['probe'], list) or not proposal['probe'] or len(proposal['probe']) > 16 or proposal['commands'] or proposal.get('done') or proposal.get('blocked')):
            error = 'probe requires 1 to 16 candidate commands, empty commands, done:false and no blocked'
        if error is None and 'undo' in proposal:
            count=proposal['undo']
            if (type(count) is not int or not 1<=count<=len(self.history) or proposal['commands']
                    or 'probe' in proposal or 'blocked' in proposal or proposal.get('done',False)):
                error='undo requires an available positive action count, empty commands, done:false and no probe or blocked'
        if error:
            return {'ok': False, 'error': error, 'accepted_commands': copy.deepcopy(self.history),
                    'state': self.state(), 'layers': self.layer_state(), 'metrics': self.metrics()}
        if 'undo' in proposal:
            count=proposal['undo'];removed=copy.deepcopy(self.history[-count:])
            restored=FoldHarness()
            replayed=restored.execute(self.history[:-count])
            if not replayed['ok']:raise ValueError('Could not replay the saved prefix for undo')
            self.panels=restored.panels;self.history=restored.history
            return dict(self.execute([]),undo_count=count,undone_commands=removed,
                        model_claimed_done=False,model_reported_blocked='')
        if 'probe' in proposal:
            trial = copy.deepcopy(self)
            tested = trial.execute(proposal['probe'])
            result = self.execute([])
            result['probe_result'] = tested
            result['model_claimed_done'] = False
            result['model_reported_blocked'] = ''
            return result
        result = self.execute(proposal['commands'], on_accepted)
        result['model_claimed_done'] = proposal.get('done', False)
        result['model_reported_blocked'] = proposal.get('blocked', '')
        return result

    def submit_text(self, text, on_accepted=None):
        """Malformed JSON also receives only harness-authored diagnostics."""
        import json
        try:
            proposal = json.loads(text)
        except (ValueError, TypeError):
            return {'ok': False, 'error': 'Invalid JSON; return a JSON object without Markdown fences',
                    'accepted_commands': copy.deepcopy(self.history), 'state': self.state(),
                    'layers': self.layer_state(), 'metrics': self.metrics()}
        return self.submit(proposal, on_accepted)
