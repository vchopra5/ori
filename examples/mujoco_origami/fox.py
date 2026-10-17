"""Generate and simulate a rigid-origami fox face starting from a square sheet."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
ORANGE = '0.94 0.36 0.07 1'
CREAM = '1 0.91 0.73 1'
INK = '0.075 0.045 0.035 1'
HALF_THICKNESS = 0.00020
JOINTS = ['left_ear', 'right_ear', 'nose', 'diagonal',
          'reverse_left_ear', 'reverse_right_ear', 'reverse_nose']
TARGET = np.deg2rad([-172, 172, -172, -180, -172, 172, -172])
SHEET_HEIGHT = 0.19
DURATION = 14.0


def nums(values):
    return ' '.join(f'{x:.9g}' for x in values)


def build_model(path):
    root = ET.Element('mujoco', model='Origami fox face')
    ET.SubElement(root, 'compiler', angle='degree')
    ET.SubElement(root, 'option', timestep='0.001', integrator='implicitfast', gravity='0 0 -9.81')
    visual = ET.SubElement(root, 'visual')
    ET.SubElement(visual, 'global', offwidth='960', offheight='800')
    ET.SubElement(visual, 'quality', shadowsize='2048')
    ET.SubElement(root, 'statistic', center=f'0 0 {SHEET_HEIGHT}', extent='0.40')
    defaults = ET.SubElement(root, 'default')
    ET.SubElement(defaults, 'joint', type='hinge', limited='true', range='-179 179',
                  damping='0.00002', armature='0.0000005')
    ET.SubElement(defaults, 'position', kp='0.12', kv='0.0015',
                  ctrllimited='true', ctrlrange='-3.124 3.124',
                  forcelimited='true', forcerange='-0.02 0.02')
    assets = ET.SubElement(root, 'asset')
    world = ET.SubElement(root, 'worldbody')
    ET.SubElement(world, 'light', pos='-0.3 -0.1 0.7', dir='0.3 0.1 -0.7', diffuse='0.9 0.9 0.9')
    ET.SubElement(world, 'light', pos='0.3 0.3 0.5', dir='-0.3 -0.3 -0.5', diffuse='0.5 0.5 0.5')
    ET.SubElement(world, 'geom', name='table', type='plane', size='0.5 0.5 0.01', rgba='0.12 0.16 0.21 1')

    def polygon(body, name, points, color, mass=0, z=0, half=HALF_THICKNESS):
        # Convex polygon extruded into a genuine thin solid for MuJoCo inertia/contact.
        vertices = [(x, y, z + side * half) for side in [-1, 1] for x, y in points]
        ET.SubElement(assets, 'mesh', name=name, vertex=nums(np.array(vertices).ravel()))
        attributes = dict(name=name, type='mesh', mesh=name, rgba=color, mass=str(mass))
        if not mass:
            attributes.update(contype='0', conaffinity='0', group='1')
        ET.SubElement(body, 'geom', **attributes)

    def decoration(body, name, points, color, back=False):
        polygon(body, name, points, color, z=(-1 if back else 1) * 0.00024, half=0.000015)

    def outline(body, points):
        for side in [-1, 1]:
            for a, b in zip(points, points[1:] + points[:1]):
                ET.SubElement(body, 'geom', type='capsule',
                              fromto=nums([*a, side * 0.00022, *b, side * 0.00022]),
                              size='0.00016', rgba='0.61 0.22 0.04 1',
                              mass='0', contype='0', conaffinity='0', group='1')

    face = ET.SubElement(world, 'body', name='face', pos=f'0 0 {SHEET_HEIGHT}')
    face_points = [(-0.10, 0), (0.10, 0), (0.06, -0.08),
                   (0.032, -0.108), (-0.032, -0.108), (-0.06, -0.08)]
    polygon(face, 'orange_face', face_points, ORANGE, mass=0.003)
    outline(face, face_points)
    cheek = [(-0.06, -0.08), (-0.032, -0.108), (0, -0.108),
             (0, -0.075), (-0.043, -0.048)]
    decoration(face, 'left_cream_cheek', cheek, CREAM)
    decoration(face, 'right_cream_cheek', [(-x, y) for x, y in cheek], CREAM)
    for side in [-1, 1]:
        ET.SubElement(face, 'geom', name=f'eye_{side}', type='ellipsoid',
                      pos=nums([side * 0.044, -0.034, 0.00055]),
                      size='0.0037 0.0052 0.0003', rgba=INK,
                      mass='0', contype='0', conaffinity='0', group='1')
        ET.SubElement(face, 'geom', type='ellipsoid',
                      pos=nums([side * 0.044 - 0.0009, -0.0325, 0.00085]),
                      size='0.0009 0.0012 0.00006', rgba='1 0.97 0.9 1',
                      mass='0', contype='0', conaffinity='0', group='1')

    for side, name in [(-1, 'left_ear'), (1, 'right_ear')]:
        # In the unfolded triangular base these tips are the outer corners.
        # Reflection about the slanted crease lifts each corner above the forehead.
        ear = ET.SubElement(face, 'body', name=name, pos=nums([side * 0.10, 0, 0]))
        ET.SubElement(ear, 'joint', name=name, axis=nums([-side * 0.04, -0.08, 0]))
        triangle = [(0, 0), (-side * 0.04, -0.08), (side * 0.04, 0)]
        polygon(ear, name + '_paper', triangle, ORANGE, mass=0.0006)
        outline(ear, triangle)
        # Printed inner-ear color is on the reverse, revealed by folding.
        centroid = np.mean(triangle, axis=0)
        inset = [(centroid + 0.65 * (np.array(p) - centroid)).tolist() for p in triangle]
        decoration(ear, name + '_inner', inset, CREAM, back=True)

    nose = ET.SubElement(face, 'body', name='nose', pos='0 -0.108 0')
    ET.SubElement(nose, 'joint', name='nose', axis='1 0 0')
    nose_points = [(-0.032, 0), (0.032, 0), (0, -0.032)]
    polygon(nose, 'nose_paper', nose_points, ORANGE, mass=0.00035)
    outline(nose, nose_points)
    decoration(nose, 'white_muzzle_reverse', nose_points, CREAM, back=True)
    decoration(nose, 'black_nose_reverse', [(-0.010, -0.022), (0.010, -0.022), (0, -0.032)], INK, back=True)

    # The other half of the SAME square, subdivided at the mirrored creases.
    # It folds underneath the decorated half; both layers then fold together.
    # Offset the diagonal axis by one half-thickness to accommodate stacked paper.
    reverse = ET.SubElement(face, 'body', name='reverse_face', pos='0 0 -0.0004')
    ET.SubElement(reverse, 'joint', name='diagonal', axis='1 0 0', range='-180.2 0.2')
    polygon(reverse, 'reverse_face_paper', [(x, -y) for x, y in face_points],
            ORANGE, mass=0.003, z=0.0004)
    for side, name in [(-1, 'left_ear'), (1, 'right_ear')]:
        ear = ET.SubElement(reverse, 'body', name='reverse_' + name,
                            pos=nums([side * 0.10, 0, 0.0004]))
        ET.SubElement(ear, 'joint', name='reverse_' + name,
                      axis=nums([-side * 0.04, 0.08, 0]))
        polygon(ear, 'reverse_' + name + '_paper',
                [(0, 0), (-side * 0.04, 0.08), (side * 0.04, 0)], ORANGE, mass=0.0006)
    reverse_nose = ET.SubElement(reverse, 'body', name='reverse_nose', pos='0 0.108 0.0004')
    ET.SubElement(reverse_nose, 'joint', name='reverse_nose', axis='1 0 0')
    polygon(reverse_nose, 'reverse_nose_paper', [(x, -y) for x, y in nose_points], ORANGE, mass=0.00035)

    contacts = ET.SubElement(root, 'contact')
    # Exclude connected hinge neighbors and the two layers of the same paper.
    # Finite-thickness layer separation is approximated, not contact-resolved.
    for name in ['left_ear', 'right_ear', 'nose']:
        ET.SubElement(contacts, 'exclude', body1='face', body2=name)
        ET.SubElement(contacts, 'exclude', body1='reverse_face', body2='reverse_' + name)
    for front in ['face', 'left_ear', 'right_ear', 'nose']:
        for back in ['reverse_face', 'reverse_left_ear', 'reverse_right_ear', 'reverse_nose']:
            ET.SubElement(contacts, 'exclude', body1=front, body2=back)
    equality = ET.SubElement(root, 'equality')
    for name in ['left_ear', 'right_ear', 'nose']:
        ET.SubElement(equality, 'joint', joint1='reverse_' + name, joint2=name,
                      polycoef='0 1 0 0 0', solref='0.003 1')
    actuators = ET.SubElement(root, 'actuator')
    for name in JOINTS:
        attributes = dict(name=name + '_fold', joint=name)
        if name == 'diagonal':
            attributes.update(kp='1.2', kv='0.015', ctrlrange='-3.146 0.004', forcerange='-0.15 0.15')
        ET.SubElement(actuators, 'position', **attributes)
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding='unicode')


def controls(t):
    starts = np.array([4.0, 6.3, 8.6, 1.0, 4.0, 6.3, 8.6])
    ramp = np.clip((t - starts) / 2.0, 0, 1)
    return TARGET * ramp * ramp * (3 - 2 * ramp)


def run(output, render=True, viewer=False, timestep=0.001):
    output.mkdir(parents=True, exist_ok=True)
    build_model(output / 'fox.xml')
    model = mujoco.MjModel.from_xml_path(str(output / 'fox.xml'))
    model.opt.timestep = timestep
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    samples = []
    max_penetration = 0.0
    max_speed = 0.0
    max_seam_gap = 0.0
    frames = []
    snapshots = {}
    with ExitStack() as stack:
        window = None
        if viewer:
            from mujoco import viewer as mj_viewer
            window = stack.enter_context(mj_viewer.launch_passive(model, data))
        renderer = None
        if render:
            import imageio.v2 as imageio
            from PIL import Image, ImageDraw
            renderer = stack.enter_context(mujoco.Renderer(model, height=800, width=960))
            video = stack.enter_context(imageio.get_writer(str(output / 'fox.mp4'), fps=30))
            camera = mujoco.MjvCamera()
            camera.lookat[:] = [0, 0, SHEET_HEIGHT]
            camera.distance = 0.64
            camera.azimuth = 90
            camera.elevation = -72
        next_frame = 0
        for _ in range(round(DURATION / timestep)):
            wall_start = time.monotonic()
            data.ctrl[:] = controls(data.time)
            mujoco.mj_step(model, data)
            if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
                raise RuntimeError('Nonfinite simulation state')
            max_speed = max(max_speed, float(np.max(np.abs(data.qvel))))
            # Across the original diagonal, the two ear layers must remain joined.
            for side, name in [(-1, 'left_ear'), (1, 'right_ear')]:
                front, back = data.body(name), data.body('reverse_' + name)
                for x in [0, side * 0.04]:
                    point = np.array([x, 0, 0])
                    a = front.xpos + front.xmat.reshape(3, 3) @ point
                    b = back.xpos + back.xmat.reshape(3, 3) @ point
                    max_seam_gap = max(max_seam_gap, float(np.linalg.norm(a - b)))
            if data.ncon:
                max_penetration = max(max_penetration, max(0, -min(c.dist for c in data.contact)))
            if data.time >= next_frame / 30:
                samples.append([data.time, *np.rad2deg(data.qpos), *data.actuator_force])
                if renderer:
                    zoom = np.clip((data.time - 3.0) / 1.0, 0, 1)
                    zoom = zoom * zoom * (3 - 2 * zoom)
                    camera.lookat[:] = [0, -0.042 * zoom, SHEET_HEIGHT]
                    camera.distance = 0.64 - 0.17 * zoom
                    renderer.update_scene(data, camera=camera)
                    frame = Image.fromarray(renderer.render())
                    draw = ImageDraw.Draw(frame)
                    phase = ('SQUARE SHEET  /  19.8 x 19.8 cm' if data.time < 1 else '1 / Fold square diagonally' if data.time < 3.2
                             else 'TRIANGULAR BASE' if data.time < 4 else '2 / Fold the left ear' if data.time < 6.3
                             else '3 / Fold the right ear' if data.time < 8.6 else '4 / Fold the nose' if data.time < 10.8
                             else 'FOX FACE')
                    draw.text((32, 26), 'MuJoCo | Origami fox', fill='white', font_size=30)
                    draw.text((32, 72), phase, fill='#ffbf78', font_size=24)
                    draw.text((32, 738), 'Rigid paper panels  /  torque-driven crease folds', fill='#e6e9ef', font_size=19)
                    video.append_data(np.asarray(frame))
                    if next_frame % 2 == 0:
                        frames.append(frame.resize((720, 600)))
                    for name, timestamp in [('square', 0.7), ('diagonal_fold', 2.0), ('base', 3.8), ('left_ear', 6.2), ('ears', 8.5), ('fox', 13.0)]:
                        if name not in snapshots and data.time >= timestamp:
                            snapshots[name] = frame.copy()
                next_frame += 1
            if window:
                if not window.is_running():
                    break
                window.sync()
                time.sleep(max(0, timestep - (time.monotonic() - wall_start)))
        if render:
            frames[0].save(output / 'fox.gif', save_all=True, append_images=frames[1:], duration=67, loop=0)
            for name, frame in snapshots.items():
                frame.save(output / f'{name}.png')
    warnings = {mujoco.mjtWarning(i).name: int(w.number) for i, w in enumerate(data.warning) if w.number}
    error = float(np.max(np.abs(np.rad2deg(data.qpos - TARGET))))
    # Verify the ear tips actually end above the forehead in material coordinates.
    tips = {}
    for side, name in [(-1, 'left_ear'), (1, 'right_ear')]:
        body = data.body(name)
        tips[name] = (body.xpos + body.xmat.reshape(3, 3) @ np.array([side * 0.04, 0, 0])).tolist()
    passed = (data.time > DURATION - 0.1 and error < 3 and not warnings and max_penetration < 0.001
              and max_seam_gap < 0.002
              and all(tip[1] > 0.02 for tip in tips.values()))
    report = dict(mujoco_version=mujoco.__version__, simulation_seconds=data.time,
                  timestep_seconds=timestep, panels=8, creases=model.nq,
                  initial_sheet='Square with corners (-0.14,0), (0,0.14), (0.14,0), (0,-0.14) m',
                  square_side_m=float(0.14 * np.sqrt(2)),
                  max_diagonal_seam_gap_m=max_seam_gap,
                  target_degrees=np.rad2deg(TARGET).tolist(), final_degrees=np.rad2deg(data.qpos).tolist(),
                  max_angle_error_degrees=error, max_contact_penetration_m=max_penetration,
                  max_joint_speed_rad_s=max_speed, ear_tip_world_positions_m=tips,
                  warnings=warnings, passed=passed,
                  assumptions='Starts with a square; one central panel held fixed. Rigid panels, actuated pre-existing creases, paired layer hinges. Printed face details. Connected and cross-layer contacts excluded; finite-thickness layering approximated. No paper plasticity or robot hands.')
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    np.savetxt(output / 'trajectory.csv', samples, delimiter=',',
               header=','.join(['time'] + [j + '_deg' for j in JOINTS] + [j + '_torque_Nm' for j in JOINTS]), comments='')
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit('Fox fold failed validation; see report.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE.parent.parent / 'output' / 'mujoco_fox')
    parser.add_argument('--no-render', action='store_true')
    parser.add_argument('--viewer', action='store_true', help='Use mjpython on macOS')
    parser.add_argument('--timestep', type=float, default=0.001)
    args = parser.parse_args()
    if not 0 < args.timestep <= 0.001:
        parser.error('--timestep must be greater than zero and at most 0.001 seconds')
    run(args.output, render=not args.no_render, viewer=args.viewer, timestep=args.timestep)
