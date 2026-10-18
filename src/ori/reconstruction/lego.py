"""Video-to-LEGO plans with deterministic grid snaps, not clutch-force simulation."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .batching import atomic_json

# Dimensions follow https://www.ldraw.org/article/218.html (20/24/8 LDU).
# Deliberately limited catalog: rectangular, top-studded parts only.
CATALOG = {f'{kind}_{w}x{d}': dict(width=w, depth=d, height=h)
           for kind, h in [('brick', 3), ('plate', 1)]
           for w, d in [(1, 1), (1, 2), (1, 3), (1, 4), (1, 6), (1, 8),
                        (2, 2), (2, 3), (2, 4), (2, 6), (2, 8)]}
COLORS = dict(red='#c91a09', blue='#0055bf', yellow='#f2cd37', green='#237841',
              white='#f4f4f4', black='#202020', gray='#a0a5a9', orange='#fe8a18',
              tan='#e4cd9e', brown='#583927')
from .lego_connections import CATALOG as CONNECTOR_CATALOG, compile_assembly
COLORS.update(light_bluish_gray='#a0a5a9', dark_bluish_gray='#6c6e68')
CONTRACT = """Watch the LEGO tutorial and reconstruct the actual visible build.
If the tutorial builds several independent models, reconstruct the largest
connected model. Name that selected model in the title and list the omitted
models in uncertainties. Detached alternative models are outside this selection,
not unsupported parts of the selected model. Do not omit unsupported parts from
the selected model itself.
Return JSON only: {"version":2,"title":string,"uncertainties":[string],"unsupported":[string],
"pieces":[{"id":"base","part":"plate_6x8","color":"green"},...],
"steps":[{"piece":"base","position":[0,0,0],"rotation":0,"instruction":string},
{"piece":"p2","attach":{"to":"base","connector":"stud:2:1","self":"socket:0:0","turn":0},"instruction":string},...]}.
Use catalog names below, or listed part IDs. List every physical piece once.
Piece IDs must match [a-z][a-z0-9_]{0,39}: lowercase letters, digits and underscores,
starting with a lowercase letter. Use those exact IDs in all steps and attachments.
All later placements must ATTACH using named connectors; do not guess world poses.
Local x/y index studs from 0. A w-by-d plate has socket:x:y on its underside and
stud:x:y on top, x in [0,w-1], y in [0,d-1]. Tiles have sockets only, NO studs. The 48x48 baseplate (4186) has top studs
only, NO underside sockets, and is half a plate thick. Use it as the root.
Slopes have all underside sockets but top studs only at y=0. Side-stud brick
also has side_stud facing local -y. Snap turn is 0/90/180/270 degrees around
parent connector normal. Snap placement inherits the parent's tilt automatically.
3937 hinge base is locally x=2,y=1. It has underside sockets and a hinge
connector, NO top studs. 6134 hinge top is x=2,y=2; 3938 is x=2,y=1.
Hinge tops have top studs and a hinge connector, NO underside sockets.
Attach a hinge top with {"to":"hinge_base_id","connector":"hinge","self":"hinge","angle":45}.
Hinge angle is -90 to 90 degrees about the base local +x axis; at zero the top
is horizontal. Positive angle raises local +y. Top mating surface is 1.2 stud
lengths above base underside at zero. Hinges are locked at chosen angles.
To rotate an already placed hinge and ALL attached descendants, add
{"action":"rotate_hinge","piece":"hinge_top_id","angle":45,"instruction":string}.
Such actions add steps, not pieces. No connector reuse or solid overlaps allowed.
Root starts on the ground. Build from root outward; reorder detached subassembly
steps into attached placements if necessary, and disclose the reordered sequence
in uncertainties. Do not invent parts to evade constraints. Explicitly list only
truly unsupported parts/connections in unsupported (e.g. Technic pins, clips).
Do not shrink, simplify, or substitute parts to fit the piece limit. If the
observed build exceeds the limit, report that in unsupported instead.
Retain uncertainty about colors, counts, hidden pieces and hinge angles. Geometric
validation alone never establishes a match to the video. Max 384 pieces, 768 steps.
Catalog (name: local x,y,z dimensions; z in plate heights; optional LEGO ID):
""" + json.dumps({k:dict(size=v['size'],part_id=v['part_id']) for k,v in CONNECTOR_CATALOG.items()}) + "\nColors: " + ', '.join(COLORS)


class UnsupportedAssembly(ValueError):
    """The observed build needs parts or connections the harness cannot model."""


def compile_plan(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get('title'), str):
        raise ValueError('A title and assembly object are required')
    for key in ('uncertainties', 'unsupported'):
        if not isinstance(plan.get(key), list) or any(not isinstance(s, str) for s in plan[key]):
            raise ValueError(f'{key} must be a list of strings')
    if plan['unsupported']:
        raise UnsupportedAssembly('Unsupported assembly: ' + '; '.join(plan['unsupported']))
    if plan.get('version') == 2:
        return compile_assembly(plan, COLORS)
    pieces, steps = plan.get('pieces'), plan.get('steps')
    if not isinstance(pieces, list) or not 1 <= len(pieces) <= 384 or not isinstance(steps, list) or len(steps) != len(pieces):
        raise ValueError('Require 1–384 pieces and exactly one placement per piece')
    inventory = {}
    for p in pieces:
        if not isinstance(p, dict) or not isinstance(p.get('id'), str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', p['id']) or p['id'] in inventory:
            raise ValueError('Each piece needs a unique safe id')
        if p.get('part') not in CATALOG or p.get('color') not in COLORS:
            raise ValueError('Unknown catalog part or color')
        inventory[p['id']] = p
    placed, connections = [], []
    used = set()
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or step.get('piece') not in inventory or step['piece'] in used:
            raise ValueError('Place each inventory piece exactly once')
        pos, rotation = step.get('position'), step.get('rotation')
        if not isinstance(pos, list) or len(pos) != 3 or any(type(v) is not int or abs(v) > 128 for v in pos) or pos[2] < 0:
            raise ValueError('Position must use bounded integer stud/plate coordinates above ground')
        if type(rotation) is not int or rotation not in (0, 90, 180, 270):
            raise ValueError('Only upright quarter-turn rotations are supported')
        if not isinstance(step.get('instruction'), str) or not step['instruction'].strip():
            raise ValueError('Every step needs an instruction')
        p = inventory[step['piece']]
        dim = CATALOG[p['part']]
        w, d = dim['width'], dim['depth']
        if rotation % 180:
            w, d = d, w
        x, y, z = pos
        cells = {(x+i, y+j) for i in range(w) for j in range(d)}
        attached = []
        for other in placed:
            ox, oy, oz = other['position']
            ow, od, oh = other['size']
            overlap = cells & {(ox+i, oy+j) for i in range(ow) for j in range(od)}
            if overlap and max(z, oz) < min(z+dim['height'], oz+oh):
                raise ValueError(f"Step {index+1}: {p['id']} overlaps {other['id']}")
            if overlap and (z == oz+oh or z+dim['height'] == oz):
                attached.append(dict(a=other['id'], b=p['id'], studs=len(overlap)))
        if index == 0 and z != 0:
            raise ValueError('The first piece must rest at z=0')
        if index and not attached:
            raise ValueError(f"Step {index+1}: no compatible stud connection to the assembly")
        connections.extend(attached)
        placed.append(dict(**p, position=pos, rotation=rotation, size=[w, d, dim['height']],
                           hex=COLORS[p['color']], instruction=step['instruction']))
        used.add(p['id'])
    counts = Counter((p['part'], p['color']) for p in pieces)
    return dict(version=1, title=plan['title'], pieces=placed, connections=connections,
                seconds_per_step=2.6, uncertainties=plan['uncertainties'],
                inventory=[dict(part=part, color=color, count=count) for (part, color), count in sorted(counts.items())])


def export_xml(playback, path):
    """Fixed-body MuJoCo assembly: snaps are rigid, the initial base is anchored."""
    if playback.get('version') == 2:
        from .lego_export import export_assembly
        return export_assembly(playback, path)
    root = ET.Element('mujoco', model='lego_snap_assembly')
    world = ET.SubElement(root, 'worldbody')
    assembly = ET.SubElement(world, 'body', name='assembly')
    for p in playback['pieces']:
        x, y, z = p['position']; w, d, h = p['size']
        body = ET.SubElement(assembly, 'body', name=p['id'],
                             pos=f'{(x+w/2)*.008} {(y+d/2)*.008} {(z+h/2)*.0032}')
        rgb = [int(p['hex'][i:i+2], 16)/255 for i in (1, 3, 5)]
        rgba = ' '.join(map(str, rgb+[1]))
        ET.SubElement(body, 'geom', type='box', size=f'{w*.004-.0001} {d*.004-.0001} {h*.0016}', rgba=rgba)
        for i in range(w):
            for j in range(d):
                ET.SubElement(body, 'geom', type='cylinder', size='.0024 .0008',
                              pos=f'{(i+.5-w/2)*.008} {(j+.5-d/2)*.008} {h*.0016+.0008}',
                              rgba=rgba, contype='0', conaffinity='0')
    ET.ElementTree(root).write(path, encoding='unicode')


def save_run(plan, output, url=None):
    playback = compile_plan(plan)
    output.mkdir(parents=True, exist_ok=True)
    report = dict(engine='LEGO snap harness', passed=True, pieces=len(playback['pieces']),
                  connections=len(playback['connections']), inventory=playback['inventory'],
                  uncertainties=playback['uncertainties'], source_url=url, video_match_verified=False,
                  assumptions=['Catalog connector frames and simplified convex collision geometry.',
                               'Initial piece anchored; valid stud connections are rigid.',
                               'No friction, deformation, insertion-path or stability simulation.'])
    export_xml(playback, output / 'assembly.xml')
    atomic_json(output / 'lego-plan.json', plan)
    atomic_json(output / 'report.json', report)
    atomic_json(output / 'lego-playback.json', playback)
    return report


def generate(client, url, output, model, observer=lambda *a: None):
    from google.genai import types
    from .video import plan_path
    plan_path(url)
    contract = CONTRACT
    if plan_path(url).stem == 'SNSSXXXndMM':
        contract += ('\nFor this castle only, the user explicitly authorizes substituting a standard '
                     'baseplate_48x48 (4186) for the green support base whose exact dimensions '
                     'are uncertain. Use one 48x48 baseplate as root and disclose this substitution '
                     'in uncertainties. Preserve the full castle walls, four towers, courtyard, '
                     'entrance and battlements without reducing their height or size. The loose '
                     'minifigure is a scale reference, not part of the connected castle; omit it '
                     'and disclose the omission. Do not list the authorized baseplate substitution '
                     'or detached minifigure as unsupported. Do report other unsupported parts.')
    prompt = contract
    for attempt in range(3):
        observer('working', f'Identifying standard pieces and placements (attempt {attempt+1}/3)')
        response = client.models.generate_content(model=model, contents=[
            types.Part(file_data=dict(file_uri=url, mime_type='video/mp4')),
            types.Part.from_text(text=prompt)], config=types.GenerateContentConfig(
                response_mime_type='application/json', max_output_tokens=65536))
        atomic_json(output / f'lego-response-{attempt+1}.json', dict(text=response.text))
        try:
            plan = json.loads(response.text or '')
            report = save_run(plan, output, url)
        except UnsupportedAssembly as error:
            atomic_json(output / 'lego-unsupported.json', plan)
            observer('rejected', str(error))
            raise
        except (ValueError, KeyError, TypeError) as error:
            observer('rejected', str(error)[:500])
            atomic_json(output / f'lego-error-{attempt+1}.json', dict(error=str(error)))
            prompt = contract + '\nPrevious candidate:\n' + (response.text or '') + '\nValidation error: ' + str(error) + '\nCorrect the plan without changing the observed build.'
            continue
        observer('accepted', f"Validated {report['pieces']} pieces and {report['connections']} connections")
        return report
    raise ValueError('LEGO assembly did not pass validation after three proposals; inspect saved diagnostics')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    save_run(json.loads(args.plan.read_text()), args.output)
