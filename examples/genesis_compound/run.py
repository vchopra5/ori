"""Execute Gemini's material/trajectory plan with real Genesis MPM contacts.

No particle positions are prescribed after initialization. Use the separate
Genesis environment: .local/genesis-venv/bin/python examples/genesis_compound/run.py
"""
import argparse
import json
import math
from pathlib import Path
import time


def validate(plan):
    for name, low, high in [('E',1000,20000), ('nu',.15,.4), ('rho',1000,2000), ('duration',2,4)]:
        value = plan[name]
        if not isinstance(value, (int,float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'Invalid {name}')
    keys = plan['keys']
    if not 10 <= plan.get('yield_stress',100) <= 5000:
        raise ValueError('Invalid yield stress')
    for name, default in [('panel_coupling_friction',.1),('blade_friction',.3)]:
        if not 0 <= plan.get(name,default) <= 2:
            raise ValueError(f'Invalid {name}')
    if not -60 <= plan.get('blade_tilt_degrees',0) <= 60:
        raise ValueError('Invalid blade tilt')
    if not 4 <= len(keys) <= 10 or keys[0]['time'] != 0 or keys[-1]['time'] != plan['duration']:
        raise ValueError('Keys must cover the full duration')
    previous = -1
    for key in keys:
        t, pos = key['time'], key['position']
        if not math.isfinite(t) or not previous < t <= plan['duration']:
            raise ValueError('Key times must strictly increase')
        previous = t
        if len(pos) != 3 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in pos):
            raise ValueError('Invalid position')
        if not -.2 <= pos[0] <= .2 or abs(pos[1]) > .03 or not .088 <= pos[2] <= .2:
            raise ValueError('Blade would leave the work area or penetrate the panel')
    return plan


def position(keys, t):
    import numpy as np
    for a, b in zip(keys, keys[1:]):
        if t <= b['time']:
            u = max(0, min(1, (t-a['time'])/(b['time']-a['time'])))
            u = u*u*(3-2*u)
            return (1-u)*np.array(a['position']) + u*np.array(b['position'])
    return np.array(keys[-1]['position'])


def run(plan, output, backend='metal', render=True, duration=None):
    import numpy as np
    import trimesh
    import genesis as gs
    validate(plan)
    output.mkdir(parents=True, exist_ok=True)
    (output/'meshes').mkdir(exist_ok=True)
    gs.init(backend=getattr(gs, backend), seed=0, logging_level='warning')
    dt = .004
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=dt, substeps=40),
        mpm_options=gs.options.MPMOptions(grid_density=160, particle_size=.004,
            lower_bound=(-.25,-.18,0), upper_bound=(.25,.18,.3)),
        vis_options=gs.options.VisOptions(ambient_light=(.4,.4,.4)),
        show_viewer=False)
    scene.add_entity(morph=gs.morphs.Plane(), surface=gs.surfaces.Rough(color=(.16,.19,.23)))
    # The supported coupon isolates spreading from vertical-wall adhesion.
    scene.add_entity(morph=gs.morphs.Box(pos=(0,0,.04), size=(.36,.24,.024), fixed=True),
                     material=gs.materials.Rigid(friction=.8,
                         coup_friction=plan.get('panel_coupling_friction',.1)),
                     surface=gs.surfaces.Rough(color=(.72,.69,.59)))
    compound = scene.add_entity(
        morph=gs.morphs.Box(pos=(-.07,0,.075), size=(.06,.06,.03)),
        material=gs.materials.MPM.ElastoPlastic(E=plan['E'],nu=plan['nu'],rho=plan['rho'],
            von_mises_yield_stress=plan.get('yield_stress',100)),
        surface=gs.surfaces.Rough(color=(.94,.93,.88), vis_mode='recon'))
    blade_file = output/'meshes'/'blade.obj'
    trimesh.creation.box(extents=(.006,.12,.07)).export(blade_file)
    blade = scene.add_entity(
        morph=gs.morphs.Mesh(file=str(blade_file.resolve()),scale=.12,
                            pos=tuple(plan['keys'][0]['position']),euler=(0,plan.get('blade_tilt_degrees',0),0)),
        material=gs.materials.Tool(friction=plan.get('blade_friction',.3), coup_softness=.0005, sdf_res=64),
        surface=gs.surfaces.Default(color=(.7,.74,.78), metallic=.8, roughness=.25))
    handle_file = output/'meshes'/'handle.obj'
    handle_mesh = trimesh.creation.capsule(height=.07, radius=.012)
    handle_mesh.export(handle_file)
    handle_offset = .035 + float(handle_mesh.extents[2])/2 - .003
    angle = math.radians(plan.get('blade_tilt_degrees',0))
    handle_delta = np.array([math.sin(angle),0,math.cos(angle)])*handle_offset
    handle = scene.add_entity(
        morph=gs.morphs.Mesh(file=str(handle_file.resolve()),scale=float(handle_mesh.extents.max()),
                            pos=tuple(np.array(plan['keys'][0]['position'])+handle_delta),
                            euler=(0,plan.get('blade_tilt_degrees',0),0)),
        material=gs.materials.Tool(collision=False, sdf_res=32),
        surface=gs.surfaces.Rough(color=(.15,.22,.32)))
    camera = None
    if render:
        camera = scene.add_camera(res=(960,720),pos=(.38,-.48,.4),lookat=(0,0,.06),fov=38,GUI=False)
    print('Building Genesis MPM kernels...',flush=True)
    scene.build()
    print('Simulating physical contact...',flush=True)
    states, frames, times = [], [], []
    begun = time.monotonic()
    initial = compound.get_particles_pos().detach().cpu().numpy().copy()
    limit = min(plan['duration'], duration) if duration else plan['duration']
    fps, stride = 25, 10
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    writer = imageio.get_writer(str(output/'animation.mp4'),fps=fps) if render else None
    try:
        for step in range(round(limit/dt)+1):
            t = step*dt
            pos, following = position(plan['keys'],t), position(plan['keys'],t+dt)
            velocity = (following-pos)/dt
            blade.set_position(pos[None,:])
            blade.set_velocity(vel=velocity[None,:])
            handle.set_position((pos + handle_delta)[None,:])
            handle.set_velocity(vel=velocity[None,:])
            if step % stride == 0:
                points = compound.get_particles_pos().detach().cpu().numpy().copy()
                if not np.isfinite(points).all():
                    raise RuntimeError('Nonfinite particle positions')
                states.append(points)
                times.append(t)
                if render:
                    rgb, *_ = camera.render()
                    img = Image.fromarray(rgb)
                    draw = ImageDraw.Draw(img)
                    draw.rectangle((0,0,960,64),fill='#18212d')
                    draw.text((20,12),'Genesis | Gemini-designed compound spreading test',fill='white',font_size=24)
                    draw.rectangle((0,675,960,720),fill='#18212d')
                    draw.text((20,688),f'{t:.2f}s | Physical elastoplastic particles + guided blade | Horizontal test panel',fill='white',font_size=17)
                    writer.append_data(np.asarray(img))
                    if step % 100 == 0:
                        img.save(output/f'frame-{step:04d}.png')
                        frames.append(img)
            if step % 100 == 0:
                print(f'  {t:.2f}/{limit:.2f}s, wall time {time.monotonic()-begun:.1f}s',flush=True)
            if step < round(limit/dt):
                scene.step()
    finally:
        if writer:
            writer.close()
    final = compound.get_particles_pos().detach().cpu().numpy().copy()
    if not np.isfinite(final).all():
        raise RuntimeError('Nonfinite final particle state')
    if abs(times[-1]-limit) > dt/2:
        states.append(final)
        times.append(round(limit/dt)*dt)
    np.savez_compressed(output/'particles.npz',positions=np.asarray(states),times=np.asarray(times))
    def metrics(points):
        return dict(span_m=np.ptp(points,axis=0).tolist(),centroid_m=points.mean(axis=0).tolist(),
                    min_z_m=float(points[:,2].min()),max_z_m=float(points[:,2].max()))
    result = dict(engine='Genesis',backend=backend,particle_count=len(initial),finite=True,
        initial=metrics(initial),final=metrics(final),
        rms_particle_displacement_m=float(np.sqrt(np.mean(np.sum((final-initial)**2,axis=1)))),
        material_particle_positions_prescribed=False, simulated_seconds=limit,
        material=dict(E=plan['E'],nu=plan['nu'],rho=plan['rho'],yield_stress=plan.get('yield_stress',100)),
        panel_coupling_friction=plan.get('panel_coupling_friction',.1),
        blade_friction=plan.get('blade_friction',.3),
        blade_tilt_degrees=plan.get('blade_tilt_degrees',0),
        wall_seconds=time.monotonic()-begun,
        approximations=plan['approximations'] + ['Uncalibrated elastoplastic material; no drying or chemical adhesion.'])
    (output/'report.json').write_text(json.dumps(result,indent=2))
    (output/'plan.json').write_text(json.dumps(plan,indent=2))
    if frames:
        sheet=Image.new('RGB',(960,480))
        selected=[frames[i] for i in np.linspace(0,len(frames)-1,min(6,len(frames)),dtype=int)]
        for i,img in enumerate(selected):
            sheet.paste(img.resize((320,240)),((i%3)*320,(i//3)*240))
        sheet.save(output/'contact-sheet.png')
    print(json.dumps(result,indent=2),flush=True)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,default=Path('output/genesis_compound/plan.json'))
    parser.add_argument('--output',type=Path,default=Path('output/genesis_compound'))
    parser.add_argument('--backend',choices=['metal','cpu','cuda'],default='metal')
    parser.add_argument('--no-render',action='store_true')
    parser.add_argument('--duration',type=float)
    args=parser.parse_args()
    run(json.loads(args.plan.read_text()),args.output,args.backend,not args.no_render,args.duration)
