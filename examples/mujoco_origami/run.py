"""Run actual MuJoCo dynamics for a clamped, rigid-panel accordion fold."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import time

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
TARGET = np.deg2rad([-65.0, 130.0, -130.0])


def fold_amount(t):
    """Flat, fold, hold, unfold, hold; cubic ramps have zero endpoint velocity."""
    def smooth(x):
        x = np.clip(x, 0, 1)
        return x * x * (3 - 2 * x)
    return float(smooth((t - 1) / 3) * (1 - smooth((t - 6) / 3)))


def run(output, render=True, viewer=False):
    output.mkdir(parents=True, exist_ok=True)
    model = mujoco.MjModel.from_xml_path(str(HERE / 'accordion.xml'))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    trajectory = []
    snapshots = {}
    max_penetration = 0.0
    folded_angles = None
    with ExitStack() as stack:
        window = None
        if viewer:
            from mujoco import viewer as mj_viewer
            window = stack.enter_context(mj_viewer.launch_passive(model, data))
        renderer = None
        if render:
            import imageio.v2 as imageio
            from PIL import Image, ImageDraw
            renderer = stack.enter_context(mujoco.Renderer(model, height=720, width=960))
            video = stack.enter_context(imageio.get_writer(str(output / 'accordion.mp4'), fps=30))
            frames = []
            camera = mujoco.MjvCamera()
            camera.lookat[:] = [-0.015, 0, 0.06]
            camera.distance = 0.60
            camera.azimuth = 120
            camera.elevation = -28
        steps_per_frame = round(1 / (30 * model.opt.timestep))
        for step in range(round(10 / model.opt.timestep)):
            start = time.monotonic()
            data.ctrl[:] = TARGET * fold_amount(data.time)
            # qpos is never prescribed: position actuators apply hinge torques.
            mujoco.mj_step(model, data)
            if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
                raise RuntimeError('Nonfinite simulation state')
            if data.ncon:
                max_penetration = max(max_penetration, max(0, -min(c.dist for c in data.contact)))
            if step % steps_per_frame == 0:
                trajectory.append([data.time, *np.rad2deg(data.qpos), *data.actuator_force])
                if 5.5 < data.time < 5.6:
                    folded_angles = data.qpos.copy()
                if renderer:
                    renderer.update_scene(data, camera=camera)
                    frame = Image.fromarray(renderer.render())
                    draw = ImageDraw.Draw(frame)
                    phase = 'FLAT' if data.time < 1 else 'FOLDING' if data.time < 4 else 'FOLDED' if data.time < 6 else 'UNFOLDING' if data.time < 9 else 'FLAT AGAIN'
                    draw.text((28, 24), 'MuJoCo | Four-panel accordion', fill='white', font_size=26)
                    draw.text((28, 62), f'{phase}   {data.time:4.1f} s', fill='#f8c678', font_size=22)
                    angles = ', '.join(f'{a:+.1f}' for a in np.rad2deg(data.qpos))
                    draw.text((28, 662), f'Creases: {angles} deg | rigid panels + torque-driven hinges', fill='white', font_size=18)
                    video.append_data(np.asarray(frame))
                    if len(trajectory) % 2 == 0:
                        frames.append(frame.resize((640, 480)))
                    for name, timestamp in [('flat', 0.8), ('folding', 2.5), ('folded', 5.5)]:
                        if name not in snapshots and data.time >= timestamp:
                            snapshots[name] = frame.copy()
            if window:
                if not window.is_running():
                    break
                window.sync()
                time.sleep(max(0, model.opt.timestep - (time.monotonic() - start)))
        if render:
            frames[0].save(output / 'accordion.gif', save_all=True, append_images=frames[1:], duration=66, loop=0)
            for name, frame in snapshots.items():
                frame.save(output / f'{name}.png')
    warnings = {mujoco.mjtWarning(i).name: int(w.number) for i, w in enumerate(data.warning) if w.number}
    folded_error = float(np.max(np.abs(np.rad2deg(folded_angles - TARGET)))) if folded_angles is not None else None
    flat_error = float(np.max(np.abs(np.rad2deg(data.qpos))))
    passed = folded_error is not None and folded_error < 3 and flat_error < 3 and not warnings and max_penetration < 0.001
    report = {
        'mujoco_version': mujoco.__version__, 'simulation_seconds': data.time,
        'timestep_seconds': model.opt.timestep, 'panels': 4, 'creases': model.nq,
        'target_degrees': np.rad2deg(TARGET).tolist(),
        'folded_degrees': np.rad2deg(folded_angles).tolist() if folded_angles is not None else None,
        'max_folded_error_degrees': folded_error, 'max_final_flat_error_degrees': flat_error,
        'max_contact_penetration_m': max_penetration, 'warnings': warnings,
        'passed': passed,
        'assumptions': 'Rigid panels, clamped first panel, actuated pre-existing creases; no paper bending or plastic crease formation.',
    }
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    np.savetxt(output / 'trajectory.csv', trajectory, delimiter=',', header='time,crease_1_deg,crease_2_deg,crease_3_deg,torque_1_Nm,torque_2_Nm,torque_3_Nm', comments='')
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit('Simulation did not meet validation thresholds; see report.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE.parent.parent / 'output' / 'mujoco_origami')
    parser.add_argument('--no-render', action='store_true')
    parser.add_argument('--viewer', action='store_true', help='Live interactive view; use mjpython on macOS')
    args = parser.parse_args()
    run(args.output, render=not args.no_render, viewer=args.viewer)
