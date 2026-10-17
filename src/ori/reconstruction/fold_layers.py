"""Local contact order for convex, zero-thickness paper panels.

A contact vector on panel A points from B toward A. It describes the limiting
side of contact, not a displacement of either panel's physical coordinates.
"""
import numpy as np

EPS = 1e-8


def plane_normal(panel):
    normal = sum((np.cross(a, b) for a, b in zip(panel.xyz, np.roll(panel.xyz, -1, axis=0))), np.zeros(3))
    normal /= np.linalg.norm(normal)
    if normal[np.argmax(abs(normal))] < 0:
        normal = -normal
    return normal


def overlap(a, b):
    """Positive-area coplanar overlap; edges touching alone are not layers."""
    normal = plane_normal(a)
    if max(abs((b.xyz - a.xyz[0]) @ normal)) > EPS:
        return False
    drop = np.argmax(abs(normal))
    poly = np.delete(a.xyz, drop, axis=1)
    clip = np.delete(b.xyz, drop, axis=1)
    signed = sum(p[0] * q[1] - p[1] * q[0] for p, q in zip(clip, np.roll(clip, -1, axis=0)))
    if signed < 0:
        clip = clip[::-1]
    for c, d in zip(clip, np.roll(clip, -1, axis=0)):
        result = []
        for p, q in zip(poly, np.roll(poly, -1, axis=0)):
            edge = d - c
            x = edge[0] * (p - c)[1] - edge[1] * (p - c)[0]
            y = edge[0] * (q - c)[1] - edge[1] * (q - c)[0]
            if x >= -EPS:
                result.append(p)
            if (x > EPS and y < -EPS) or (x < -EPS and y > EPS):
                result.append(p + x / (x - y) * (q - p))
        poly = np.array(result)
        if len(poly) < 3:
            return False
    return abs(sum(p[0] * q[1] - p[1] * q[0] for p, q in zip(poly, np.roll(poly, -1, axis=0)))) > 2 * EPS


def ordered(panels, view_normal=(0, 0, 1)):
    """Back-to-front order constrained by actual contacts, with depth tie breaks."""
    by_id = {p.id: p for p in panels}
    if len(by_id) != len(panels):
        raise ValueError('Panel IDs must be unique')
    incoming = {p.id: set() for p in panels}
    for p in panels:
        for other, vector in p.contacts.items():
            if other in by_id and np.dot(vector, view_normal) > EPS:
                incoming[p.id].add(other)
    result = []
    while incoming:
        ready = [key for key, deps in incoming.items() if not deps]
        if not ready:
            raise ValueError('Contradictory layer order: contact cycle')
        key = min(ready, key=lambda k: (float(np.mean(by_id[k].xyz, axis=0) @ view_normal), k))
        result.append(by_id[key])
        del incoming[key]
        for deps in incoming.values():
            deps.discard(key)
    return result


def inherit(panels, parents, sources):
    """Subdivided faces inherit their parents' contact sides where they overlap."""
    for p in panels:
        p.contacts = {}
    for i, p in enumerate(panels):
        for q in panels[i + 1:]:
            vector = sources[parents[p.id]].contacts.get(parents[q.id])
            if vector is not None and overlap(p, q):
                p.contacts[q.id] = list(vector)
                q.contacts[p.id] = (-np.array(vector)).tolist()


def select(candidates, layers, normal, parents):
    if isinstance(layers, list):
        if not layers or any(not isinstance(x, str) for x in layers) or len(set(layers)) != len(layers):
            raise ValueError('layers must be a nonempty list of unique current panel IDs')
        available = {parents[p.id] for p in candidates}
        if set(layers) - available:
            raise ValueError('Layer selection contains unknown or stationary panel IDs')
        return [p for p in candidates if parents[p.id] in layers]
    if layers == 'all':
        return candidates
    if layers not in ('top', 'bottom'):
        raise ValueError('layers must be all, top, bottom, or current panel IDs')
    sign = 1 if layers == 'top' else -1
    ids = {p.id for p in candidates}
    return [p for p in candidates if not any(
        other in ids and np.dot(vector, normal) * sign < -EPS
        for other, vector in p.contacts.items())]


def check_departure(moving, fixed, matrix, origin):
    for p in moving:
        displacement = (np.mean(p.xyz, axis=0) - origin) @ matrix.T + origin - np.mean(p.xyz, axis=0)
        for q in fixed:
            vector = p.contacts.get(q.id)
            if vector is not None and np.dot(displacement, vector) < -EPS:
                raise ValueError(f'Layer {p.id} would pass through {q.id} on departure; select an exposed layer or reverse the fold')


def resolve(panels, initial, moving_ids, matrix, near):
    """Preserve stationary order, rotate packet order, infer new landing sides."""
    by_id = {p.id: p for p in initial}
    for p in panels:
        p.contacts = {}
    for i, p in enumerate(panels):
        for q in panels[i + 1:]:
            if not overlap(p, q):
                continue
            pm, qm = p.id in moving_ids, q.id in moving_ids
            previous = by_id[p.id].contacts.get(q.id)
            if pm == qm:
                if previous is None:
                    raise ValueError(f'Unresolved contact between {p.id} and {q.id}')
                vector = np.array(previous)
                if pm:
                    vector = matrix @ vector
            else:
                normal = plane_normal(p)
                separation = np.dot(np.mean(near[p.id], axis=0) - np.mean(near[q.id], axis=0), normal)
                if abs(separation) < EPS:
                    raise ValueError(f'Ambiguous landing between {p.id} and {q.id}')
                vector = normal * np.sign(separation)
            p.contacts[q.id] = vector.tolist()
            q.contacts[p.id] = (-vector).tolist()
    # Each parallel contact cluster must have an acyclic order.
    for p in panels:
        ordered(panels, plane_normal(p))
