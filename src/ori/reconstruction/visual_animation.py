"""Gemini-authored Genesis illustrations with deterministic step comparison frames.

This is scripted visual reconstruction, not recovered real-world dynamics.
Generate with Ori's environment; render with the installed Genesis environment.
"""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import copy

ROOT=Path(__file__).resolve().parents[3]

PROMPT='''Watch this tutorial and create a GOOD-LOOKING, clear 3D instructional
animation of a coherent demonstrated sequence. We want clean per-step images
that a neural network can compare to video. This is a scripted animation, not
a physics research task. Do NOT estimate material physics or write solver code.
Use pleasing, restrained colors, recognizable multi-part tools, beveled forms,
visible movement and clear changes to the workpiece. No human hands required.
Choose one complete coherent process rather than combining alternative methods.
Include important tools, materials and visible state changes. Do not combine
alternative methods as if they were consecutive steps in a single procedure.
Return JSON only:
{"title":string,"source_url":URL,"approximation_notes":[string],
 "views":{"hero":{"position":[x,y,z],"target":[x,y,z]},
          "front":{"position":[x,y,z],"target":[x,y,z]}},
 "steps":[{"id":"step_01","title":string,"duration":seconds,
    "source_start":video seconds,"source_end":video seconds,
    "comparison_focus":[strings describing visible before/after differences]}],
 "objects":[{"id":"object_id","label":string,
    "parts":[{"shape":"box"|"sphere"|"cylinder","size":[FULL x,y,z sizes],
               "position":[local x,y,z],"rotation":[degrees x,y,z],
               "color":"#rrggbb","finish":"matte"|"metal"|"rubber"}],
    "keys":[{"time":GLOBAL animation seconds,"position":[x,y,z],"rotation":[degrees x,y,z]}],
    "visible":[[GLOBAL start,GLOBAL end]]}]}
METERS, Z UP, rotations extrinsic xyz DEGREES. Cylinder runs along local Z.
All motion uses GLOBAL seconds across the whole animation. First pose at t0.
At least 2 keys for moving objects; static objects use 1 key. Positions and
rotations are smoothly interpolated. Objects persist unless visibility excludes
the time. Complete state changes by 85% of each step so after frames show them.
Use the demonstrated object's real scale. Fit both cameras to the work area:
the assembly should occupy 55–75% of the image, including its staged parts.
For tabletop assembly use an elevated three-quarter hero view and a near-top
front view. Keep the assembly above the floor, including its lowest details.
Use realistic material colors and consistent scale. Temporary tools should be
visible only when used; park away from the work area between actions. Correct
occlusion and physical placement matter: joined surfaces should be flush, not
floating. Represent openings with actual gaps in geometry, not painted squares.
Source timestamps must be plausible absolute seconds; state in approximation_notes
that their exact alignment is unverified. Attached components MUST stay fixed
relative to their parent through subsequent steps. Do not interpolate a static
base between t0 and a final demonstration pose across the entire assembly.
Hold poses with explicit keys at each movement's start AND finish. Every step
must produce a visible geometry or placement change; include connecting wires,
fasteners and leg bends when relevant. Prefer a stationary completed assembly.
Use 6–9 steps of 3–4 seconds each (total <=36s), <=36 objects, <=6 parts per
object, <=30 keys per object. Avoid clutter. Details may be as thin as .0003m
for miniature electronics. Shapes: boxes use size; spheres are ellipsoids of size; cylinders use
elliptical x/y diameter and z height. Box corners are gently beveled by renderer.
For continuous wires/legs/springs, a part may instead use shape "tube" with
"points":[[local x,y,z],...] (2–96 distinct consecutive points); size[0] is its
diameter. Still include size,position,rotation,color,finish. Prefer tubes to
independently guessed cylinder rotations, so bent segments join exactly.
No arbitrary code, file paths, mesh arrays, text geometry, or invented claims
of physical fidelity. Labels/titles go in metadata, not on 3D surfaces.
'''


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2)+'\n')


def validate(plan):
    def num(x,lo,hi):
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not lo<=x<=hi:
            raise ValueError(f'Expected finite number in [{lo},{hi}]')
    def vec(v,lo=-10,hi=10):
        if not isinstance(v,list) or len(v)!=3: raise ValueError('Expected 3-vector')
        for x in v:num(x,lo,hi)
    if not isinstance(plan['title'],str) or not isinstance(plan['approximation_notes'],list):
        raise ValueError('Title and notes required')
    if not 1<=len(plan['steps'])<=12: raise ValueError('Invalid step count')
    duration=0; names=set()
    for step in plan['steps']:
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',step['id']) or step['id'] in names: raise ValueError('Invalid step ID')
        names.add(step['id']); num(step['duration'],1,8); duration+=step['duration']
        num(step['source_start'],0,7200); num(step['source_end'],step['source_start']+.001,7200)
        if not isinstance(step['comparison_focus'],list): raise ValueError('Missing comparison focus')
    num(duration,1,60)
    for view in plan['views'].values():vec(view['position']); vec(view['target'])
    if not {'hero','front'}<=plan['views'].keys(): raise ValueError('Hero and front views required')
    if not 1<=len(plan['objects'])<=45: raise ValueError('Invalid object count')
    names=set()
    for obj in plan['objects']:
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',obj['id']) or obj['id'] in names: raise ValueError('Invalid object ID')
        names.add(obj['id'])
        if not 1<=len(obj['parts'])<=8:raise ValueError('Part budget exceeded')
        for part in obj['parts']:
            if part['shape'] not in ('box','sphere','cylinder','tube') or part['finish'] not in ('matte','metal','rubber'): raise ValueError('Invalid shape or finish')
            vec(part['size'],.0003,5); vec(part['position']); vec(part['rotation'],-360,360)
            if part['shape']=='tube':
                if not 2<=len(part['points'])<=96:raise ValueError('Tube needs 2–96 points')
                for point in part['points']:vec(point)
                for a,b in zip(part['points'],part['points'][1:]):
                    if sum((x-y)**2 for x,y in zip(a,b))<1e-12:raise ValueError('Tube points must differ')
            if not re.fullmatch(r'#[0-9a-fA-F]{6}',part['color']):raise ValueError('Invalid color')
        if not 1<=len(obj['keys'])<=40 or obj['keys'][0]['time']!=0:raise ValueError('Keys must begin at zero')
        previous=-1
        for key in obj['keys']:
            num(key['time'],0,duration)
            if key['time']<=previous:raise ValueError('Increasing key times required')
            previous=key['time']; vec(key['position']); vec(key['rotation'],-360,360)
        for a,b in obj['visible']:
            num(a,0,duration); num(b,a+.0001,duration)
        if 'reveal' in obj:
            r=obj['reveal']
            num(r['start'],0,duration); num(r['end'],r['start']+.001,duration)
            if r['axis'] not in (0,2) or r['direction'] not in (-1,1) or len(obj['parts'])!=1 or obj['parts'][0]['shape']!='box':
                raise ValueError('Surface reveal needs one box and X or Z axis')
    return duration


def generate(url,output,model='gemini-3.5-flash'):
    from google import genai
    from google.genai import types
    from ori.config import load_settings
    from .video import plan_path
    plan_path(url)
    output.mkdir(parents=True,exist_ok=True)
    prompt=PROMPT+'\nSource URL: '+url
    with genai.Client(api_key=load_settings().gemini_api_key,http_options=types.HttpOptions(
            timeout=240000,retry_options=types.HttpRetryOptions(attempts=1))) as client:
        for attempt in range(2):
            save(output/f'generation-{attempt+1}.request.json',dict(model=model,url=url,prompt=prompt))
            response=client.models.generate_content(model=model,contents=[
                types.Part(file_data=types.FileData(file_uri=url,mime_type='video/mp4')),
                types.Part.from_text(text=prompt)],config=types.GenerateContentConfig(
                    response_mime_type='application/json',max_output_tokens=26000))
            (output/f'generation-{attempt+1}.response.json').write_text(response.model_dump_json(exclude_none=True))
            try:
                plan=json.loads(response.text or '')
                validate(plan)
                if plan['source_url']!=url:raise ValueError('Source URL changed')
                save(output/'plan.json',plan)
                return plan
            except (ValueError,KeyError,TypeError) as error:
                prompt=PROMPT+'\nSource URL: '+url+'\nCorrect the full previous JSON:\n'+str(response.text)+'\nValidation error: '+str(error)
                save(output/f'generation-{attempt+1}.error.json',dict(error=str(error)))
    raise ValueError('Generated plan failed validation; responses saved')


def render(plan,output,fps=18,preview=False):
    import numpy as np
    import trimesh
    from scipy.spatial.transform import Rotation,Slerp
    import genesis as gs
    import imageio.v2 as imageio
    from PIL import Image,ImageDraw
    duration=validate(plan)
    output.mkdir(parents=True,exist_ok=True); (output/'meshes').mkdir(exist_ok=True)
    gs.init(backend=gs.metal,seed=7,logging_level='warning')
    scene=gs.Scene(show_viewer=False,vis_options=gs.options.VisOptions(
        ambient_light=(.3,.3,.3),segmentation_level='entity',
        lights=[dict(type='directional',dir=(.7,1,-1.4),color=(1.,.95,.88),intensity=2.5),
                dict(type='directional',dir=(-1,-.2,-.5),color=(.8,.88,1.),intensity=1.)]),
        sim_options=gs.options.SimOptions(dt=1/fps,substeps=1),
        rigid_options=gs.options.RigidOptions(enable_collision=False))
    camera_distance=max(np.linalg.norm(np.array(v['position'])-v['target']) for v in plan['views'].values())
    table_depth=camera_distance*.4
    floor=scene.add_entity(morph=gs.morphs.Box(size=(camera_distance*3,camera_distance*3,table_depth),
        pos=(0,0,-table_depth/2),fixed=True,collision=False),surface=gs.surfaces.Rough(color=(.73,.74,.75)))
    entities={}; motion={}; bounds={}
    render_objects=[]
    for original in plan['objects']:
        if 'reveal' not in original:
            render_objects.append(original);continue
        reveal=original['reveal'];axis=reveal['axis'];part=original['parts'][0];count=16
        for i in range(count):
            obj=copy.deepcopy(original);obj.pop('reveal');obj['semantic_id']=original['id'];obj['id']=f'{original["id"]}_strip_{i:02d}'
            obj['parts'][0]['size'][axis]/=count
            obj['parts'][0]['position'][axis]+=((i+.5)/count-.5)*part['size'][axis]
            order=i if reveal['direction']==1 else count-1-i
            appear=reveal['start']+(order/count)*(reveal['end']-reveal['start'])
            obj['visible']=[[max(a,appear),b] for a,b in original['visible'] if b>appear]
            render_objects.append(obj)
    for obj in render_objects:
        assembly=trimesh.Scene()
        for i,part in enumerate(obj['parts']):
            size=np.array(part['size'])
            if part['shape']=='box':
                bevel=min(float(size.min())*.15,.012)
                corners=np.array([[x,y,z] for x in (-1,1) for y in (-1,1) for z in (-1,1)])*(size/2-bevel)
                orb=trimesh.creation.icosphere(subdivisions=1,radius=bevel)
                geom=trimesh.Trimesh(vertices=np.concatenate([orb.vertices+c for c in corners]),process=False).convex_hull
            elif part['shape']=='sphere':
                geom=trimesh.creation.icosphere(subdivisions=3,radius=1)
                geom.apply_scale(size/2)
            elif part['shape']=='tube':
                pieces=[];radius=float(size[0])/2
                for a,b in zip(part['points'],part['points'][1:]):
                    a=np.array(a);b=np.array(b);delta=b-a
                    segment=trimesh.creation.cylinder(radius=radius,height=np.linalg.norm(delta),sections=12)
                    transform=trimesh.geometry.align_vectors([0,0,1],delta)
                    transform[:3,3]=(a+b)/2;segment.apply_transform(transform);pieces.append(segment)
                for point in part['points']:
                    joint=trimesh.creation.icosphere(subdivisions=1,radius=radius)
                    joint.apply_translation(point);pieces.append(joint)
                geom=trimesh.util.concatenate(pieces)
            else:
                geom=trimesh.creation.cylinder(radius=1,height=1,sections=32)
                geom.apply_scale([size[0]/2,size[1]/2,size[2]])
            matrix=np.eye(4); matrix[:3,:3]=Rotation.from_euler('xyz',part['rotation'],degrees=True).as_matrix(); matrix[:3,3]=part['position']
            geom.apply_transform(matrix)
            color=[int(part['color'][j:j+2],16) for j in (1,3,5)]+[255]
            rng=np.random.default_rng(sum(map(ord,obj['id']))+i)
            noise=rng.normal(0,.012,(256,256))
            if any(word in obj['id'] for word in ('wood','furring','backing','clothespin_top','clothespin_bottom')):
                xx=np.arange(256)[None,:]
                noise+=.035*np.sin(xx*.32+np.cumsum(rng.normal(0,.015,(256,1)),axis=0))
            texture=Image.fromarray(np.clip(np.array(color[:3])[None,None,:]*(1+noise[:,:,None]),0,255).astype(np.uint8))
            spans=np.ptp(geom.vertices,axis=0); axes=np.argsort(spans)[-2:]
            uv=(geom.vertices[:,axes]-geom.vertices[:,axes].min(axis=0))/np.maximum(spans[axes],1e-6)
            material=trimesh.visual.material.PBRMaterial(baseColorFactor=[255,255,255,255],baseColorTexture=texture,
                metallicFactor=.75 if part['finish']=='metal' else 0,
                roughnessFactor=.3 if part['finish']=='metal' else .72)
            geom.visual=trimesh.visual.TextureVisuals(uv=uv,material=material)
            assembly.add_geometry(geom,geom_name=f'part_{i}')
        path=output/'meshes'/f'{obj["id"]}.glb'; assembly.export(path)
        bounds[obj['id']]=assembly.bounds.tolist()
        key=obj['keys'][0]
        entity=scene.add_entity(morph=gs.morphs.Mesh(file=str(path.resolve()),
            pos=tuple(key['position']),euler=tuple(key['rotation']),fixed=True,align=False,batch_fixed_verts=True,
            file_meshes_are_zup=True,collision=False,convexify=False,decimate=False),surface=gs.surfaces.Default())
        entities[obj['id']]=entity
        times=np.array([k['time'] for k in obj['keys']])
        rotations=Rotation.from_euler('xyz',[k['rotation'] for k in obj['keys']],degrees=True)
        motion[obj['id']]=(times,np.array([k['position'] for k in obj['keys']]),rotations,
                           Slerp(times,rotations) if len(times)>1 else None)
    cameras={name:scene.add_camera(res=(960,720),pos=tuple(view['position']),
        lookat=tuple(view['target']),fov=38,GUI=False) for name,view in plan['views'].items()}
    print('Building Genesis visual scene...',flush=True); scene.build()
    previous_poses={}
    def pose(t):
        states=[]
        for obj in render_objects:
            times,positions,rotations,slerp=motion[obj['id']]
            index=max(0,min(len(times)-2,int(np.searchsorted(times,t,side='right')-1)))
            if len(times)==1:
                p=positions[0]; q=rotations[0].as_quat()
            else:
                u=float(np.clip((t-times[index])/(times[index+1]-times[index]),0,1)); u=u*u*(3-2*u)
                p=(1-u)*positions[index]+u*positions[index+1]
                qt=times[index]+u*(times[index+1]-times[index])
                q=slerp(qt).as_quat()
            visible=any(a<=t<b or abs(t-duration)<1e-6 and b==duration for a,b in obj['visible'])
            hidden_z=-table_depth-float(np.linalg.norm(bounds[obj['id']],axis=1).max())-.01
            position=np.asarray(p if visible else [0,0,hidden_z])
            previous=previous_poses.get(obj['id'])
            if previous is None or not np.allclose(previous[0],position,atol=1e-7,rtol=0):
                entities[obj['id']].set_pos(position)
            if previous is None or not np.allclose(previous[1],q,atol=1e-7,rtol=0):
                entities[obj['id']].set_quat(q[[3,0,1,2]])
            previous_poses[obj['id']]=(position.copy(),q.copy())
            states.append(dict(id=obj.get('semantic_id',obj['id']),render_id=obj['id'],visible=visible,position=p.tolist(),quaternion_xyzw=q.tolist()))
        return states
    comparison=dict(title=plan['title'],source_url=plan['source_url'],engine='Genesis',
        purpose='Scripted visual comparison; not a physical reconstruction',
        views={name:{**view,'vertical_fov_degrees':38,'resolution':[960,720]} for name,view in plan['views'].items()},object_bounds_local=bounds,
        mask_labels={str(floor.idx+1):'studio_floor',**{str(entities[o['id']].idx+1):o.get('semantic_id',o['id']) for o in render_objects}},
        steps=[],approximation_notes=plan['approximation_notes'])
    timeline=[]; elapsed=0
    for step in plan['steps']:
        timeline.append((elapsed,elapsed+step['duration'],step)); elapsed+=step['duration']
    if not preview:
        print('Rendering animation...',flush=True)
        with imageio.get_writer(str(output/'animation.mp4'),fps=fps) as movie:
            for frame in range(round(duration*fps)):
                t=frame/fps; pose(t)
                rgb,*_=cameras['hero'].render(force_render=True)
                img=Image.fromarray(rgb); draw=ImageDraw.Draw(img)
                active=next((s for a,b,s in timeline if a<=t<b),timeline[-1][2])
                draw.rectangle((0,0,960,76),fill='#18212b')
                draw.text((24,13),plan['title'][:64],fill='white',font_size=25)
                draw.text((24,46),active['title'][:90],fill='#eec78a',font_size=18)
                movie.append_data(np.asarray(img))
                if frame%(fps*3)==0:print(f'  Movie {t:.1f}/{duration:.1f}s',flush=True)
    print('Exporting clean comparison frames...',flush=True)
    contact=[]
    for begin,end,step in timeline:
        directory=output/'steps'/step['id']; directory.mkdir(parents=True,exist_ok=True)
        item={**step,'animation_start':begin,'animation_end':end,'samples':[]}
        for phase,fraction in [('before',0),('during',.5),('after',.97)]:
            t=max(0,begin-1e-5) if phase=='before' else begin+fraction*(end-begin)
            states=pose(t)
            for view,camera in cameras.items():
                rgb,depth,seg,*_=camera.render(segmentation=True,depth=True,force_render=True)
                name=f'{phase}.{view}'; rgb_path=directory/f'{name}.png'
                Image.fromarray(rgb).save(rgb_path)
                np.save(directory/f'{name}.depth.npy',depth)
                # Genesis returns compact segmentation IDs, with zero background.
                # Resolve them through its map rather than assuming entity ordering.
                mask=np.zeros(seg.shape,dtype=np.uint16)
                for compact,entity_idx in scene.visualizer.segmentation_idx_dict.items():
                    if entity_idx>=0:mask[seg==compact]=entity_idx+1
                Image.fromarray(mask).save(directory/f'{name}.mask.png')
                item['samples'].append(dict(phase=phase,view=view,time=t,
                    rgb=str(rgb_path.relative_to(output)),mask=str((directory/f'{name}.mask.png').relative_to(output)),
                    depth=str((directory/f'{name}.depth.npy').relative_to(output)),objects=states))
                if view=='hero' and phase=='after':contact.append((step['title'],Image.fromarray(rgb)))
        comparison['steps'].append(item)
        print(f'  Exported {step["id"]}: {step["title"]}',flush=True)
        save(output/'comparison.json',comparison)
    if contact:
        sheet=Image.new('RGB',(960,math.ceil(len(contact)/3)*264),'#eef0f2')
        draw=ImageDraw.Draw(sheet)
        for i,(title,img) in enumerate(contact):
            x=(i%3)*320;y=(i//3)*264
            sheet.paste(img.resize((320,240)),(x,y));draw.text((x+8,y+242),title[:42],fill='#18212b',font_size=13)
        sheet.save(output/'contact-sheet.png')
    save(output/'plan.json',plan)
    save(output/'report.json',dict(status='rendered',engine='Genesis',scripted=True,
        duration=duration,steps=len(plan['steps']),objects=len(plan['objects']),
        comparison_images=sum(len(s['samples']) for s in comparison['steps']),
        physical_material_parameters_inferred=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--url');source.add_argument('--render-plan',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',default='gemini-3.5-flash')
    parser.add_argument('--preview',action='store_true',help='Export comparison images only')
    parser.add_argument('--generate-only',action='store_true')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    if args.render_plan:
        render(json.loads(args.render_plan.read_text()),args.output,preview=args.preview)
    else:
        generate(args.url,args.output,args.model)
        if not args.generate_only:
            command=[str(ROOT/'.local/genesis-venv/bin/python'),str(Path(__file__).resolve()),
                     '--render-plan',str((args.output/'plan.json').resolve()),'--output',str(args.output.resolve())]
            if args.preview:command.append('--preview')
            subprocess.run(command,check=True)


if __name__=='__main__':
    main()
