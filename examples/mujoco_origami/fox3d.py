"""Fold a single unprinted square into a volumetric sitting fox in MuJoCo.

All facets retain their original metric. An outer corner reverses down into
the muzzle while the body closes into a V-shaped volume. Shared
material vertices are measured every step to detect separation of the sheet.
"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
SCALE = 0.16
HEIGHT = 0.23
THICKNESS = 0.00016
COLOR = '0.88 0.285 0.065 1'
DURATION = 20.0


def numbers(values):
    return ' '.join(f'{v:.10g}' for v in values)


def smooth(t, start, duration=2.0):
    u = np.clip((t - start) / duration, 0, 1)
    return u * u * (3 - 2 * u)


def control_targets(t):
    body = np.deg2rad(148) * smooth(t, 7.0, 3.0)
    return {
        'lift': -0.228 * smooth(t, 13.5, 1.5),
        'stand': np.deg2rad(90) * smooth(t, 11.5, 1.7),
        'diagonal': np.pi * smooth(t, 1.0),
        'body': body, 'left_ear': np.deg2rad(172) * smooth(t, 3.5),
        'right_ear': np.deg2rad(-155) * smooth(t, 4.7),
        'left_head': 0, 'right_head': 0,
        'snout': np.deg2rad(-155) * smooth(t, 9.5, 1.8),
        'back_body': body,
        'back_left_ear': np.deg2rad(172) * smooth(t, 3.5),
        'back_right_ear': np.deg2rad(-155) * smooth(t, 4.7),
        'back_left_head': 0, 'back_right_head': 0,
        'back_snout': np.deg2rad(-155) * smooth(t, 9.5, 1.8),
    }


def build_model(path):
    root = ET.Element('mujoco', model='Single-square monochrome 3D fox')
    ET.SubElement(root, 'compiler', angle='radian')
    ET.SubElement(root, 'option', timestep='0.001', integrator='implicitfast',
                  gravity='0 0 -9.81', iterations='100', tolerance='1e-10')
    visual = ET.SubElement(root, 'visual')
    ET.SubElement(visual, 'global', offwidth='1024', offheight='800')
    ET.SubElement(visual, 'quality', shadowsize='4096')
    ET.SubElement(root, 'statistic', center='-0.03 0 0.12', extent='0.45')
    default = ET.SubElement(root, 'default')
    ET.SubElement(default, 'joint', type='hinge', damping='0.00008', armature='0.000002',
                  limited='true', range='-3.16 3.16')
    ET.SubElement(default, 'position', kp='0.4', kv='0.005', forcelimited='true', forcerange='-0.08 0.08')
    # All paper facets use exactly the same material on both sides.
    assets = ET.SubElement(root, 'asset')
    ET.SubElement(assets, 'material', name='plain_orange_paper', rgba=COLOR,
                  specular='0.04', shininess='0.02')
    world = ET.SubElement(root, 'worldbody')
    ET.SubElement(world, 'geom', name='table', type='plane', size='1 1 0.01', rgba='0.14 0.17 0.21 1')
    ET.SubElement(world, 'light', pos='-0.3 -0.5 1', dir='0.2 0.4 -1', diffuse='0.8 0.8 0.8')
    ET.SubElement(world, 'light', pos='0.4 0.3 0.7', dir='-0.4 -0.3 -0.7', diffuse='0.4 0.4 0.4')
    support = ET.SubElement(world, 'body', name='support', pos=f'0 0 {HEIGHT}')
    ET.SubElement(support, 'joint', name='lift', type='slide', axis='0 0 1', range='-0.24 0.01')
    ET.SubElement(support, 'joint', name='stand', axis='1 0 0', range='-0.01 1.59')
    # A fixed in-plane turn presents the square axis-aligned initially and the
    # traditional sitting silhouette upright after the final 90-degree lift.
    front = ET.SubElement(support, 'body', name='front_left_body', euler=f'0 0 {np.pi / 4}')
    records = []

    def hinge(parent, name, origin, axis):
        body = ET.SubElement(parent, 'body', name=name, pos=numbers(origin))
        ET.SubElement(body, 'joint', name=name, axis=numbers(axis))
        return body

    def panel(body, name, points, origin=(0, 0), mirror=1, z=0):
        # points/origin are sheet coordinates before any fold, in units of SCALE.
        xy = np.asarray(points, float)
        local = np.column_stack(((xy[:, 0] - origin[0]) * SCALE,
                                 (xy[:, 1] - origin[1]) * SCALE * mirror,
                                 np.full(len(points), z)))
        vertices = np.concatenate([local + [0, 0, -THICKNESS / 2], local + [0, 0, THICKNESS / 2]])
        area = abs(float(np.dot(xy[:, 0], np.roll(xy[:, 1], -1)) - np.dot(xy[:, 1], np.roll(xy[:, 0], -1)))) * SCALE ** 2 / 2
        ET.SubElement(assets, 'mesh', name=name, vertex=numbers(vertices.ravel()))
        ET.SubElement(body, 'geom', name=name, type='mesh', mesh=name,
                      material='plain_orange_paper', mass=str(area * 0.16),
                      contype='2', conaffinity='1')  # table contact; layered self-contact omitted
        material = np.column_stack((xy[:, 0] * SCALE, xy[:, 1] * SCALE * mirror))
        records.append(dict(body=body.attrib['name'], local=local.tolist(),
                            material=material.tolist(), area=area, name=name))

    body_left = [(0, 0), (-0.5, 0.5), (-0.15, 0.85), (0, 0.7)]
    body_right = [(0, 0), (0, 0.7), (0.15, 0.85), (0.5, 0.5)]
    head_left = [(0, 0.7), (-0.15, 0.85), (0, 1)]
    head_right = [(0, 0.7), (0, 1), (0.15, 0.85)]
    ear_left = [(0, 0), (-0.7, 0), (-0.85, 0.15), (-0.5, 0.5)]
    snout_points = [(-0.7, 0), (-1, 0), (-0.85, 0.15)]
    ear_right = [(0, 0), (0.5, 0.5), (1, 0)]

    def half(parent, prefix='', mirror=1, z=0):
        panel(parent, prefix + 'body_left_paper', body_left, mirror=mirror, z=z)
        left_ear = hinge(parent, prefix + 'left_ear', [0, 0, z], [-1, mirror, 0])
        panel(left_ear, prefix + 'ear_left_paper', ear_left, mirror=mirror)
        snout = hinge(left_ear, prefix + 'snout', [-0.7 * SCALE, 0, 0], [-1, mirror, 0])
        panel(snout, prefix + 'snout_paper', snout_points, origin=(-0.7, 0), mirror=mirror)
        left_head = hinge(parent, prefix + 'left_head', [0, 0.7 * SCALE * mirror, z], [-1, mirror, 0])
        panel(left_head, prefix + 'head_left_paper', head_left, origin=(0, 0.7), mirror=mirror)
        right = hinge(parent, prefix + 'body', [0, 0, z], [0, mirror, 0])
        panel(right, prefix + 'body_right_paper', body_right, mirror=mirror)
        right_ear = hinge(right, prefix + 'right_ear', [0, 0, 0], [1, mirror, 0])
        panel(right_ear, prefix + 'ear_right_paper', ear_right, mirror=mirror)
        right_head = hinge(right, prefix + 'right_head', [0, 0.7 * SCALE * mirror, 0], [1, mirror, 0])
        panel(right_head, prefix + 'head_right_paper', head_right, origin=(0, 0.7), mirror=mirror)
        # The head triangles share the original square corner. This loop closure
        # is essential: omitting it would allow the single sheet to tear.
        for body, suffix in [(left_head, 'left'), (right_head, 'right')]:
            ET.SubElement(body, 'site', name=prefix + 'muzzle_' + suffix,
                          pos=numbers([0, 0.3 * SCALE * mirror, 0]), size='0.0001', rgba='0 0 0 0')

    half(front)
    back = hinge(front, 'diagonal', [0, 0, -THICKNESS], [1, 0, 0])
    half(back, 'back_', mirror=-1, z=THICKNESS)
    equality = ET.SubElement(root, 'equality')
    for prefix in ['', 'back_']:
        ET.SubElement(equality, 'connect', site1=prefix + 'muzzle_left',
                      site2=prefix + 'muzzle_right', solref='0.002 1')
    for name in ['body', 'left_ear', 'right_ear', 'left_head', 'right_head', 'snout']:
        ET.SubElement(equality, 'joint', joint1='back_' + name, joint2=name,
                      polycoef='0 1 0 0 0', solref='0.002 1')
    actuators = ET.SubElement(root, 'actuator')
    for name in control_targets(0):
        attributes = dict(name=name + '_actuator', joint=name)
        if name in ['stand', 'diagonal']:
            attributes.update(kp='2', kv='0.025', forcerange='-0.4 0.4')
        if name == 'lift':
            attributes.update(kp='200', kv='5', forcerange='-5 5')
        ET.SubElement(actuators, 'position', **attributes)
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding='unicode')
    return records


def shared_vertices(records):
    groups = {}
    for record in records:
        for material, local in zip(record['material'], record['local']):
            key = tuple(np.round(material, 8))
            groups.setdefault(key, []).append((record['body'], np.array(local)))
    return [group for group in groups.values() if len(group) > 1]


def run(output, render=True, timestep=0.001):
    output.mkdir(parents=True, exist_ok=True)
    records = build_model(output / 'fox3d.xml')
    area = sum(record['area'] for record in records)
    if abs(area - 2 * SCALE ** 2) > 1e-10:
        raise RuntimeError('Panels do not cover the original square area')
    model = mujoco.MjModel.from_xml_path(str(output / 'fox3d.xml'))
    model.opt.timestep = timestep
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    groups = shared_vertices(records)
    actuators = {name: model.actuator(name + '_actuator').id for name in control_targets(0)}
    angles = list(control_targets(0))
    samples, frames, snapshots = [], [], {}
    max_separation = 0.0
    max_table_penetration = 0.0
    next_frame = 0
    with ExitStack() as stack:
        renderer = None
        if render:
            import imageio.v2 as imageio
            from PIL import Image, ImageDraw
            renderer = stack.enter_context(mujoco.Renderer(model, height=800, width=1024))
            video = stack.enter_context(imageio.get_writer(str(output / 'fox3d.mp4'), fps=30))
            camera = mujoco.MjvCamera()
        for step in range(round(DURATION / timestep)):
            targets = control_targets(data.time)
            for name, value in targets.items():
                data.ctrl[actuators[name]] = value
            mujoco.mj_step(model, data)
            if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
                raise RuntimeError('Nonfinite simulation state')
            # Geometric closure is evaluated every step, not just in the final pose.
            for group in groups:
                positions = [data.body(name).xpos + data.body(name).xmat.reshape(3, 3) @ local for name, local in group]
                max_separation = max(max_separation, float(np.max(np.linalg.norm(np.array(positions) - positions[0], axis=1))))
            if data.ncon:
                max_table_penetration = max(max_table_penetration, max(0, -min(c.dist for c in data.contact)))
            if data.time >= next_frame / 30:
                samples.append([data.time, *[float(data.joint(name).qpos[0]) for name in angles]])
                if renderer:
                    stand = smooth(data.time, 11.5, 1.7)
                    lower = smooth(data.time, 13.5, 1.5)
                    orbit = smooth(data.time, 15.0, 5.0)
                    camera.lookat[:] = [-0.055 * stand, 0.005 * stand, HEIGHT - 0.228 * lower + 0.058 * stand]
                    camera.distance = 0.66 - 0.31 * stand
                    camera.elevation = -68 + 48 * stand
                    camera.azimuth = 90 - 35 * stand + 80 * orbit
                    renderer.update_scene(data, camera=camera)
                    frame = Image.fromarray(renderer.render())
                    draw = ImageDraw.Draw(frame)
                    phase = ('ONE PLAIN SQUARE' if data.time < 1 else '1 / Diagonal fold' if data.time < 3.5
                             else '2 / Fold corner flaps' if data.time < 7 else '3 / Close body and reverse muzzle' if data.time < 11.5
                             else '4 / Stand upright' if data.time < 15 else '3D SITTING FOX  /  orbit view')
                    draw.text((32, 28), 'MuJoCo | Single-sheet fox', fill='white', font_size=30)
                    draw.text((32, 76), phase, fill='#f5bd86', font_size=23)
                    draw.text((32, 745), 'One square / one paper color / connected crease panels', fill='#d7dce3', font_size=19)
                    video.append_data(np.asarray(frame))
                    if next_frame % 3 == 0:
                        frames.append(frame.resize((700, 560)))
                    for name, timestamp in [('square', 0.7), ('folding', 8.8), ('fox', 15.2), ('side', 18.0)]:
                        if name not in snapshots and data.time >= timestamp:
                            snapshots[name] = frame.copy()
                next_frame += 1
        if render:
            # A fixed palette keeps the looping preview compact and avoids flicker.
            palette = frames[-1].quantize(colors=96)
            gif = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
            gif[0].save(output / 'fox3d.gif', save_all=True, append_images=gif[1:], duration=100, loop=0)
            for name, frame in snapshots.items():
                frame.save(output / f'{name}.png')
    warnings = {mujoco.mjtWarning(i).name: int(w.number) for i, w in enumerate(data.warning) if w.number}
    # Pose targets in meters for the support slide, radians for every hinge.
    errors = {name: abs(float(data.joint(name).qpos[0]) - value) for name, value in control_targets(DURATION).items()}
    vertices = np.concatenate([np.array(record['local']) @ data.body(record['body']).xmat.reshape(3, 3).T
                               + data.body(record['body']).xpos for record in records])
    extent = np.ptp(vertices, axis=0)
    passed = (not warnings and max_separation < 0.002 and max_table_penetration < 0.001
              and max(v for k, v in errors.items() if k != 'lift') < np.deg2rad(4)
              and min(extent) > 0.015)
    report = dict(mujoco_version=mujoco.__version__, seconds=data.time,
                  square_side_m=float(SCALE * np.sqrt(2)), paper_area_m2=area,
                  panels=len(records), paper_materials=1,
                  max_shared_vertex_separation_m=max_separation,
                  final_extent_xyz_m=extent.tolist(), max_table_penetration_m=max_table_penetration,
                  final_joint_error_degrees={k: float(np.rad2deg(v)) for k, v in errors.items() if k != 'lift'},
                  warnings=warnings, passed=bool(passed),
                  limitations='Rigid pre-creased panels. Servo-held folds and presentation support. Paper-paper self-contact omitted; table contact enabled. No flexible paper or permanent creasing.')
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    (output / 'crease_panels.json').write_text(json.dumps(records, indent=2) + '\n')
    np.savetxt(output / 'trajectory.csv', samples, delimiter=',', header=','.join(['time'] + angles), comments='')
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit('3D fox validation failed; see report.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE.parent.parent / 'output' / 'mujoco_fox_3d')
    parser.add_argument('--no-render', action='store_true')
    parser.add_argument('--timestep', type=float, default=0.001)
    args = parser.parse_args()
    if not 0 < args.timestep <= 0.001:
        parser.error('--timestep must be positive and at most 0.001 seconds')
    run(args.output, render=not args.no_render, timestep=args.timestep)
