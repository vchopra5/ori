"""Gemini video -> declarative scene -> generated OBJ assets -> MuJoCo movie.

Run with --url URL --output DIRECTORY, or replay a saved --scene JSON offline.
Model output is data only; generated Python is never executed.
"""
import argparse
from contextlib import ExitStack
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

CONTRACT = '''Create a simplified instructional animation of the GENERAL STEPS
in this video, with all required objects. You control a MuJoCo scene via JSON.
Return JSON only, following this exact contract:
{"title":string,"duration":number,"approximations":[string],
 "steps":[{"start":number,"end":number,"title":string}],
 "objects":[{"id":string,"mode":"static"|"guided"|"dynamic",
   "position":[x,y,z], "parts":[{"position":[x,y,z],
   "size":[half_x,half_y,half_z],"rgba":[r,g,b,a]}],
   "mass":number,
   "keys":[{"time":number,"position":[x,y,z],"euler":[rx,ry,rz]}],
   "visible":[[start,end]]}]}
All units meters, seconds, radians. z is UP. Every part is a local box and
will become an actual triangle OBJ mesh plus a matching box collision geom.
Make recognizable tools with several parts (handle/blade etc). Keep objects
under 65, parts under 20 each, duration 24-60 seconds, steps under 12.
Use an upright wall centered [0,0,0.95], facing camera on NEGATIVE y.
Camera sees x in [-0.8,0.8], z in [0,1.8]. Work area near [0,-0.04,1.0].
Represent a hole with separate surrounding wall pieces, NEVER a solid wall
box behind the opening. Interior dark backing may sit at positive y.
Guided tools use mocap bodies: keys prescribe position/orientation, with
smooth interpolation. First key MUST be time 0 at position; last key <=duration.
Static and dynamic objects have no keys. Dynamic bodies have free joints,
gravity, contacts, positive mass; use for loose debris resting on floor.
Include a few relevant loose dynamic objects to demonstrate actual gravity and
contacts when appropriate. Mark pre-staged debris as an approximation.
Visible defaults to whole animation. Visibility controls VISUALS ONLY: objects
with partial visibility MUST be static, noncolliding material state overlays.
Use overlays for material changes such as filling/paint. Do not present these
as simulated cutting, fluid flow, sanding removal, adhesion or drying.
Structural wall pieces must stay visible for the whole animation.
Use visible tool movement across the repair area for each relevant step.
Do not hide the tools for the entire animation or leave them stationary.
No human anatomy required. Show the observed repair method, in order.
Include clear approximations. This is guided animation with rigid body physics,
not autonomous manipulation. IDs must match [a-z][a-z0-9_]{0,39}.
'''


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def validate(scene):
    def number(v, lo, hi):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f'Expected finite number in [{lo}, {hi}], got {v!r}')
    def vector(v, n, lo, hi):
        if not isinstance(v, list) or len(v) != n:
            raise ValueError(f'Expected {n}-element vector')
        for x in v:
            number(x, lo, hi)
    number(scene['duration'], 1, 90)
    duration = scene['duration']
    if not isinstance(scene['title'], str) or not isinstance(scene['approximations'], list):
        raise ValueError('Title and approximation list required')
    if not 1 <= len(scene['steps']) <= 12 or not 1 <= len(scene['objects']) <= 65:
        raise ValueError('Scene object/step budget exceeded')
    previous_end = 0
    for step in scene['steps']:
        number(step['start'], previous_end, duration)
        number(step['end'], step['start'] + 0.001, duration)
        previous_end = step['end']
        if not isinstance(step['title'], str):
            raise ValueError('Step title must be text')
    ids = set()
    for obj in scene['objects']:
        name = obj['id']
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', name) or name in ids:
            raise ValueError('Invalid or duplicate object ID')
        ids.add(name)
        if obj['mode'] not in ('static', 'guided', 'dynamic'):
            raise ValueError('Unknown body mode')
        vector(obj['position'], 3, -5, 5)
        number(obj.get('mass', 0.1), 0.001 if obj['mode'] == 'dynamic' else 0, 100)
        if not 1 <= len(obj['parts']) <= 20:
            raise ValueError('Part budget exceeded')
        for part in obj['parts']:
            vector(part['position'], 3, -3, 3)
            vector(part['size'], 3, 0.0001, 3)
            vector(part['rgba'], 4, 0, 1)
        keys = obj.get('keys', [])
        if obj['mode'] == 'guided':
            if not 2 <= len(keys) <= 150 or keys[0]['time'] != 0 or keys[0]['position'] != obj['position']:
                raise ValueError(f'{name}: guided keys must start at initial position, time zero')
            last = -1
            for key in keys:
                number(key['time'], 0, duration)
                if key['time'] <= last:
                    raise ValueError('Key times must strictly increase')
                last = key['time']
                vector(key['position'], 3, -5, 5)
                vector(key['euler'], 3, -20, 20)
        elif keys:
            raise ValueError('Only guided bodies can have keys')
        visible = obj.get('visible', [[0, duration]])
        for interval in visible:
            vector(interval, 2, 0, duration)
            if interval[1] <= interval[0]:
                raise ValueError('Invalid visibility interval')
        if visible != [[0, duration]] and obj['mode'] != 'static':
            raise ValueError('Only noncolliding static overlays support partial visibility')
    return scene


def box_mesh(path, size):
    vertices = [(x*size[0], y*size[1], z*size[2])
                for x, y, z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                                (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    faces = [(1,3,2),(1,4,3),(5,6,7),(5,7,8),(1,2,6),(1,6,5),
             (2,3,7),(2,7,6),(3,4,8),(3,8,7),(4,1,5),(4,5,8)]
    path.write_text(''.join('v %g %g %g\n' % v for v in vertices)
                    + ''.join('f %d %d %d\n' % f for f in faces))


def compile_scene(scene, output):
    validate(scene)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'meshes').mkdir(exist_ok=True)
    fmt = lambda values: ' '.join(str(x) for x in values)
    root = ET.Element('mujoco', model='video_reconstruction')
    ET.SubElement(root, 'compiler', angle='radian', meshdir='meshes')
    ET.SubElement(root, 'option', timestep='0.002', gravity='0 0 -9.81', integrator='implicitfast')
    defaults = ET.SubElement(root, 'default')
    ET.SubElement(defaults, 'geom', solref='.006 1', solimp='.95 .99 .001')
    visual = ET.SubElement(root, 'visual')
    ET.SubElement(visual, 'global', offwidth='960', offheight='720')
    ET.SubElement(visual, 'headlight', ambient='.25 .25 .25', diffuse='.4 .4 .4')
    asset = ET.SubElement(root, 'asset')
    world = ET.SubElement(root, 'worldbody')
    ET.SubElement(world, 'light', pos='-1 -3 4', dir='0 1 -1', directional='true', diffuse='.65 .65 .65')
    ET.SubElement(world, 'geom', name='floor', type='plane', size='3 3 .1', rgba='.16 .19 .24 1')
    for obj in scene['objects']:
        attrs = dict(name=obj['id'], pos=fmt(obj['position']))
        if obj['mode'] == 'guided':
            attrs['mocap'] = 'true'
        body = ET.SubElement(world, 'body', **attrs)
        if obj['mode'] == 'dynamic':
            ET.SubElement(body, 'freejoint')
        overlay = obj.get('visible', [[0, scene['duration']]]) != [[0, scene['duration']]]
        for i, part in enumerate(obj['parts']):
            name = f"{obj['id']}_{i}"
            box_mesh(output / 'meshes' / f'{name}.obj', part['size'])
            ET.SubElement(asset, 'mesh', name=name, file=f'{name}.obj')
            ET.SubElement(body, 'geom', name=name, type='mesh', mesh=name,
                          pos=fmt(part['position']), rgba=fmt(part['rgba']),
                          contype='0', conaffinity='0', mass='0', group='1')
            if not overlay:
                ET.SubElement(body, 'geom', name=name+'_collision', type='box',
                              size=fmt(part['size']), pos=fmt(part['position']),
                              mass=str(obj.get('mass', .1)/len(obj['parts'])),
                              rgba='0 0 0 0', group='3', friction='.7 .01 .001')
    ET.indent(root)
    ET.ElementTree(root).write(output / 'scene.xml', encoding='unicode')
    save(output / 'scene.json', scene)
    return output / 'scene.xml'


def render(scene, output, movie=True, fps=24):
    import mujoco
    import numpy as np
    xml = compile_scene(scene, output)
    model = mujoco.MjModel.from_xml_path(str(xml))
    data = mujoco.MjData(model)
    guided, overlays = [], []
    for obj in scene['objects']:
        body = model.body(obj['id']).id
        if obj['mode'] == 'guided':
            guided.append((model.body_mocapid[body], obj['keys']))
        if obj.get('visible', [[0, scene['duration']]]) != [[0, scene['duration']]]:
            for i, part in enumerate(obj['parts']):
                overlays.append((model.geom(f"{obj['id']}_{i}").id, part['rgba'][3], obj['visible']))
    def pose(t):
        for index, keys in guided:
            a = keys[0]
            b = keys[-1]
            for k in keys[1:]:
                b = k
                if t <= b['time']:
                    break
                a = b
            u = np.clip((t-a['time']) / max(b['time']-a['time'], 1e-8), 0, 1)
            u = u*u*(3-2*u)
            data.mocap_pos[index] = (1-u)*np.array(a['position']) + u*np.array(b['position'])
            qa, qb, q = np.zeros(4), np.zeros(4), np.zeros(4)
            mujoco.mju_euler2Quat(qa, np.array(a['euler'], dtype=float), 'xyz')
            mujoco.mju_euler2Quat(qb, np.array(b['euler'], dtype=float), 'xyz')
            dot = float(np.dot(qa, qb))
            if dot < 0:
                qb = -qb
                dot = -dot
            if dot > .9995:
                q = (1-u)*qa + u*qb
                q /= np.linalg.norm(q)
            else:
                angle = math.acos(np.clip(dot, -1, 1))
                q = (math.sin((1-u)*angle)*qa + math.sin(u*angle)*qb)/math.sin(angle)
            data.mocap_quat[index] = q
        for geom, alpha, intervals in overlays:
            model.geom_rgba[geom, 3] = alpha if any(a <= t < b for a,b in intervals) else 0
    pose(0)
    mujoco.mj_forward(model, data)
    contacts, penetration, frames, samples = 0, 0., [], []
    with ExitStack() as stack:
        if movie:
            import imageio.v2 as imageio
            from PIL import Image, ImageDraw
            renderer = stack.enter_context(mujoco.Renderer(model, height=720, width=960))
            writer = stack.enter_context(imageio.get_writer(str(output/'animation.mp4'), fps=fps))
            camera = mujoco.MjvCamera()
            camera.lookat[:] = [0, 0, .85]
            camera.distance, camera.azimuth, camera.elevation = 2.8, 90, -12
        for frame in range(math.ceil(scene['duration']*fps)):
            target = frame / fps
            while data.time < target:
                pose(data.time)
                mujoco.mj_step(model, data)
                if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
                    raise RuntimeError('Nonfinite simulation state')
                contacts += data.ncon
                penetration = max(penetration, max((max(0., -c.dist) for c in data.contact), default=0.))
            pose(target)
            mujoco.mj_forward(model, data)
            samples.append(dict(time=float(data.time), qpos=data.qpos.tolist(), mocap_pos=data.mocap_pos.tolist()))
            if movie:
                renderer.update_scene(data, camera=camera)
                image = Image.fromarray(renderer.render())
                draw = ImageDraw.Draw(image)
                draw.rectangle((0,0,960,86), fill='#18212d')
                draw.text((24,12), scene['title'][:68], fill='white', font_size=24)
                step = next((s for s in scene['steps'] if s['start'] <= target < s['end']), None)
                draw.text((24,48), step['title'][:90] if step else 'Preparing the scene', fill='#f6c27d', font_size=19)
                draw.rectangle((0,679,960,720), fill='#18212d')
                draw.text((24,690), f'{target:04.1f}s  |  Guided tools + rigid-body contacts  |  Material changes are staged', fill='white', font_size=16)
                writer.append_data(np.asarray(image))
                if frame % max(1,round(fps*scene['duration']/8)) == 0:
                    image.save(output/f'frame-{len(frames):02d}.png')
                    frames.append(image.copy())
        if movie and frames:
            sheet = Image.new('RGB', (1280,480))
            for i, image in enumerate(frames[:8]):
                sheet.paste(image.resize((320,240)), ((i%4)*320,(i//4)*240))
            sheet.save(output/'contact-sheet.png')
    save(output/'trajectory.json', samples)
    report = dict(engine='MuJoCo', version=mujoco.__version__, objects=len(scene['objects']),
                  mesh_count=sum(len(o['parts']) for o in scene['objects']),
                  contact_samples=contacts, max_penetration_m=penetration,
                  finite_state=True, simulated_seconds=float(data.time),
                  approximations=scene['approximations'],
                  physics='Guided mocap tools; dynamic free bodies; static state overlays are noncolliding.')
    save(output/'report.json', report)
    return report


def generate(url, output, model=None, attempts=3):
    from google import genai
    from google.genai import types
    from ori.config import load_settings
    from .video import plan_path
    plan_path(url)  # Validate the supplied URL before sending it.
    settings = load_settings()
    model = model or settings.gemini_model
    output.mkdir(parents=True, exist_ok=True)
    parts = [types.Part(file_data=types.FileData(file_uri=url, mime_type='video/mp4')),
             types.Part.from_text(text=CONTRACT)]
    with genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(
            timeout=240000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
        for attempt in range(attempts):
            save(output/f'generate-{attempt+1}.request.json', dict(url=url, model=model,
                 contract=CONTRACT, feedback=[p.text for p in parts[2:]]))
            response = client.models.generate_content(model=model, contents=parts,
                config=types.GenerateContentConfig(response_mime_type='application/json', max_output_tokens=20000))
            (output/f'generate-{attempt+1}.response.json').write_text(response.model_dump_json(exclude_none=True))
            try:
                scene = validate(json.loads(response.text or ''))
                compile_scene(scene, output)
                import mujoco
                mujoco.MjModel.from_xml_path(str(output/'scene.xml'))
                save(output/'source.json', dict(url=url, model=model, generated_by='Gemini'))
                return scene
            except (ValueError, KeyError, TypeError) as error:
                save(output/f'generate-{attempt+1}.error.json', dict(error=str(error)))
                parts.append(types.Part.from_text(text=f'Your previous scene:\n{response.text}\nCompiler error: {error}. Return the FULL corrected scene.'))
        raise RuntimeError('Scene failed validation; requests and errors are saved.')


def review(url, output, model=None):
    """Ask Gemini to compare real rendered frames with the source video."""
    from google import genai
    from google.genai import types
    from ori.config import load_settings
    settings = load_settings()
    prompt = '''Compare these ACTUAL MuJoCo renders with the supplied tutorial.
The goal is an approximate animation of its general steps. Identify missing
steps, missing tools, invisible repairs, bad framing or motions. Compiler
success is not evidence of fidelity. Do not claim physical material simulation:
tools are guided; filling/cutting/paint use staged geometry. Return JSON with
general_steps_match:boolean, covered_steps:[string], missing_steps:[string],
visible_defects:[string], physics_limitations:[string], assessment:string.
Physics report:\n''' + (output/'report.json').read_text()
    images = sorted(output.glob('frame-*.png'))
    save(output/'review.request.json', dict(url=url, model=model or settings.gemini_model,
         prompt=prompt, images=[str(p) for p in images]))
    parts = [types.Part(file_data=types.FileData(file_uri=url, mime_type='video/mp4')),
             types.Part.from_text(text=prompt)]
    for path in images:
        parts.extend([types.Part.from_text(text=path.name),
                      types.Part.from_bytes(data=path.read_bytes(), mime_type='image/png')])
    with genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(
            timeout=180000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
        response = client.models.generate_content(model=model or settings.gemini_model,
            contents=parts, config=types.GenerateContentConfig(
                response_mime_type='application/json', max_output_tokens=4000))
    (output/'review.response.json').write_text(response.model_dump_json(exclude_none=True))
    result = json.loads(response.text or '')
    save(output/'review.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--url')
    source.add_argument('--scene', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model')
    parser.add_argument('--no-render', action='store_true')
    parser.add_argument('--review', action='store_true', help='Compare renders to source video with Gemini')
    args = parser.parse_args()
    if args.review and args.no_render:
        parser.error('--review requires rendered frames')
    source_info = {}
    if args.scene and (args.scene.parent/'source.json').exists():
        source_info = json.loads((args.scene.parent/'source.json').read_text())
    if args.review and not args.url and not source_info.get('url'):
        parser.error('--review of a saved scene requires source.json beside the input scene')
    scene = json.loads(args.scene.read_text()) if args.scene else generate(args.url, args.output, args.model)
    print(json.dumps(render(scene, args.output, movie=not args.no_render), indent=2))
    if source_info:
        save(args.output/'source.json', source_info)
    if args.review:
        print(json.dumps(review(args.url or source_info['url'], args.output,
                                args.model or source_info.get('model')), indent=2))


if __name__ == '__main__':
    main()
