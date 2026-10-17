"""Constrained parametric mechanisms on existing material vertices.

Expressions are data, never Python/JavaScript code. All poses are generated on
existing panels and validated before any state changes. Validation is sampled,
like the straight-fold harness; this is not a continuous collision certificate.
"""
import ast
import copy
import math
import numpy as np
from . import fold_layers

FUNCTIONS = {'sin': math.sin, 'cos': math.cos, 'sqrt': math.sqrt,
             'atan2': math.atan2}


def expression(value, variables=None):
    variables = variables or {}
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    if not isinstance(value, str) or len(value) > 1024:
        raise ValueError('Path expressions must be finite numbers or short math expressions')
    try:
        root = ast.parse(value, mode='eval')
    except (SyntaxError, RecursionError) as exc:
        raise ValueError('Invalid path expression') from exc
    if sum(1 for _ in ast.walk(root)) > 128:
        raise ValueError('Path expression is too complex')
    def convert(node):
        if isinstance(node, ast.Constant):
            return expression(node.value)
        if isinstance(node, ast.Name):
            if node.id == 't': return ['t']
            if node.id == 'pi': return math.pi
            if node.id in variables: return copy.deepcopy(variables[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return ['*', -1 if isinstance(node.op, ast.USub) else 1, convert(node.operand)]
        if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div):
            return [{ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/'}[type(node.op)], convert(node.left), convert(node.right)]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
            if len(node.args) == (2 if node.func.id == 'atan2' else 1):
                return [node.func.id, *map(convert, node.args)]
        raise ValueError('Use only t, pi, named parameters, arithmetic, sin/cos/sqrt/atan2')
    result = convert(root.body)
    # Named parameters cannot expand into unbounded expression trees.
    def size(node): return 1 if isinstance(node, (int, float)) else 1 + sum(size(x) for x in node[1:])
    if size(result) > 1024: raise ValueError('Expanded path expression is too complex')
    return result


def evaluate(node, t):
    if isinstance(node, (int, float)): return node
    op, *args = node
    if op == 't': return t
    args = [evaluate(x, t) for x in args]
    if op == '+': return args[0] + args[1]
    if op == '-': return args[0] - args[1]
    if op == '*': return args[0] * args[1]
    if op == '/': return args[0] / args[1]
    return FUNCTIONS[op](*args)


def compile_paths(command, panels):
    if set(command) - {'type', 'name', 'parameters', 'paths'}:
        raise ValueError('Compound accepts type, name, parameters and paths')
    parameters = command.get('parameters', {})
    if not isinstance(parameters, dict) or len(parameters) > 16:
        raise ValueError('parameters must be an object with at most 16 entries')
    variables = {}
    for name, value in parameters.items():
        if not name.isidentifier() or name in {'t', 'pi', *FUNCTIONS}:
            raise ValueError('Invalid parameter name')
        variables[name] = expression(value, variables)
    paths = command.get('paths')
    if not isinstance(paths, list) or not paths or len(paths) > 256:
        raise ValueError('paths must contain 1 to 256 material-vertex trajectories')
    compiled = []
    for path in paths:
        if not isinstance(path, dict) or set(path) != {'material', 'position'}:
            raise ValueError('Each path needs material:[u,v] and position:[x(t),y(t),z(t)]')
        uv = np.asarray(path['material'], dtype=float)
        if uv.shape != (2,) or not np.isfinite(uv).all() or not any(np.linalg.norm(v-uv) < 1e-8 for p in panels for v in p.uv):
            raise ValueError('Path must address an existing material vertex; precrease first')
        if any(np.linalg.norm(np.array(p['material'])-uv) < 1e-8 for p in compiled):
            raise ValueError('Duplicate material vertex path')
        if not isinstance(path['position'], list) or len(path['position']) != 3:
            raise ValueError('position needs three expressions')
        compiled.append(dict(material=uv.tolist(), position=[expression(v, variables) for v in path['position']]))
    return compiled


def compound(harness, command):
    from .fold_commands import crossings
    paths = compile_paths(command, harness.panels)
    initial = copy.deepcopy(harness.panels)
    def pose(t):
        panels = copy.deepcopy(initial)
        for p in panels:
            p.contacts = {}
            for i, uv in enumerate(p.uv):
                path = next((x for x in paths if np.linalg.norm(uv-np.array(x['material'])) < 1e-8), None)
                if path:
                    p.xyz[i] = [evaluate(x, t) for x in path['position']]
        return panels
    poses = []
    try:
        # Include staggered samples to avoid only inspecting simple phase angles.
        for t in sorted(set(np.linspace(0, 1, 121).tolist() + [(i+.381966)/120 for i in range(120)])):
            panels = pose(t)
            metrics = harness.metrics(panels)
            if abs(metrics['material_area']-2) > 1e-8 or max(metrics['max_length_error'], metrics['max_seam_gap']) > 1e-8:
                raise ValueError(f'Paper constraint failed at t={t:.9f}: {metrics}')
            if t == 0:
                if any(np.max(abs(p.xyz-q.xyz)) > 1e-8 for p, q in zip(panels, initial)):
                    raise ValueError('Compound path must start at the exact current paper pose')
                panels = copy.deepcopy(initial)
            else:
                previous = poses[-1]
                if any(np.max(np.linalg.norm(p.xyz-q.xyz, axis=1)) > .05 for p, q in zip(panels, previous)):
                    raise ValueError(f'Motion too fast to validate at t={t:.9f}; split into smaller continuous motions')
                for i, p in enumerate(panels):
                    for j in range(i+1, len(panels)):
                        q = panels[j]
                        if crossings([p], [q]):
                            raise ValueError(f'Paper intersection at t={t:.9f} between {p.id} and {q.id}')
                        before_p, before_q = previous[i], previous[j]
                        old = before_p.contacts.get(q.id)
                        relative = np.mean(p.xyz-before_p.xyz, axis=0)-np.mean(q.xyz-before_q.xyz, axis=0)
                        touching = fold_layers.overlap(p, q)
                        if old is not None and not touching and np.dot(relative, old) < -1e-8:
                            raise ValueError(f'Layer {p.id} passes through {q.id} at t={t:.9f}')
                        if not touching: continue
                        normal = fold_layers.plane_normal(p)
                        separation = np.dot(np.mean(before_p.xyz, axis=0)-np.mean(before_q.xyz, axis=0), normal)
                        if abs(separation) > 1e-8:
                            vector = normal*np.sign(separation)
                        elif old is not None:
                            # Carry a contacting packet's order through rigid motion.
                            a = before_p.xyz-before_p.xyz.mean(axis=0)
                            b = p.xyz-p.xyz.mean(axis=0)
                            u, _, vt = np.linalg.svd(a.T @ b)
                            correction = np.diag([1, 1, np.linalg.det(vt.T @ u.T)])
                            vector = vt.T @ correction @ u.T @ np.array(old)
                        else:
                            raise ValueError(f'Ambiguous contact between {p.id} and {q.id} at t={t:.9f}')
                        p.contacts[q.id] = vector.tolist()
                        q.contacts[p.id] = (-vector).tolist()
                for p in panels: fold_layers.ordered(panels, fold_layers.plane_normal(p))
            poses.append(panels)
    except (ArithmeticError, TypeError) as exc:
        raise ValueError(f'Invalid compound path: {exc}') from exc
    if all(np.max(abs(p.xyz-q.xyz)) < 1e-8 for p, q in zip(initial, poses[-1])):
        raise ValueError('Compound motion must change the paper pose')
    harness.panels = poses[-1]
    harness.history.append(copy.deepcopy(command))
    return poses
