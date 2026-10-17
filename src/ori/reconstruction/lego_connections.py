"""Catalog connector frames and rigid assembly transforms, in stud-length units.

These are simplified engineering proxies, not manufacturing CAD. LDraw unit
ratios and hinge pivots: https://www.ldraw.org/article/218.html and
https://library.ldraw.org/parts/10943 (6134), parts/3937.dat.
"""
from collections import Counter
import math
import numpy as np


def rotation(axis, degrees):
    t = math.radians(degrees); c, s = math.cos(t), math.sin(t)
    if axis == 'x': return np.array([[1,0,0],[0,c,-s],[0,s,c]])
    if axis == 'y': return np.array([[c,0,s],[0,1,0],[-s,0,c]])
    return np.array([[c,-s,0],[s,c,0],[0,0,1]])


def box(lo, hi):
    vertices = [[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])]
    return dict(vertices=vertices, faces=[[0,1,3,2],[4,6,7,5],[0,4,5,1],[2,3,7,6],[0,2,6,4],[1,5,7,3]])


def prism(width, profile):
    n=len(profile)
    return dict(vertices=[[x,y,z] for x in (0,width) for y,z in profile],
                faces=[list(range(n-1,-1,-1)),list(range(n,2*n))]+[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)])


def connector(kind, point, frame=None):
    return dict(kind=kind, point=point, frame=(np.eye(3) if frame is None else frame).tolist())


def rectangular(w,d,h,kind='brick',part_id=None):
    cs={}
    for x in range(w):
        for y in range(d):
            cs[f'socket:{x}:{y}']=connector('socket',[x+.5,y+.5,0],rotation('x',180))
            if kind != 'tile': cs[f'stud:{x}:{y}']=connector('stud',[x+.5,y+.5,h])
    return dict(size=[w,d,h/.4], connectors=cs, solids=[box([0,0,0],[w,d,h])], part_id=part_id)


CATALOG={}
for kind,h in [('brick',1.2),('plate',.4),('tile',.4)]:
    sizes=[(1,1),(1,2),(1,3),(1,4),(1,6),(1,8),(2,2),(2,3),(2,4),(2,6),(2,8)]
    if kind=='plate': sizes += [(4,4),(4,6),(4,8),(6,6),(6,8),(6,10),(6,12),(8,8)]
    if kind=='tile': sizes += [(4,4)]
    for w,d in sizes: CATALOG[f'{kind}_{w}x{d}']=rectangular(w,d,h,kind)
for name,part_id in {'plate_6x8':'3036','plate_4x6':'3032','tile_1x6':'6636',
                      'brick_2x4':'3001','plate_2x4':'3020','brick_1x2':'3004'}.items():
    CATALOG[name]['part_id']=part_id
# Slopes expose studs only on the high, flat row; curved 47457 has two studs.
for name,d,h,pid,curved in [('slope_2x2',2,1.2,'3039',False),('slope_2x3',3,1.2,'3298',False),
                           ('slope_2x4',4,1.2,'3037',False),('curved_slope_2x2',2,.8,'47457',True)]:
    item=rectangular(2,d,h,part_id=pid)
    item['connectors']={k:v for k,v in item['connectors'].items() if k.startswith('socket:') or k.endswith(':0')}
    if curved:
        # Convex, faceted approximation to the curved forward surface.
        profile=[(0,0),(d,0),(d,.2)]+[(1+math.sin(t),.2+.6*math.cos(t)) for t in np.linspace(math.pi/2,0,9)[1:]]+[(0,h)]
    else: profile=[(0,0),(d,0),(d,.2),(1,h),(0,h)]
    item['solids']=[prism(2,profile)];CATALOG[name]=item
# Classic friction hinge. Axis is local x, .7 studs above the base underside.
base=rectangular(2,1,1.2,kind='tile',part_id='3937')
base['connectors']['hinge']=connector('hinge_base',[1,.5,.7])
wall=prism(.18,[(0,.35),(1,.35)]+[(.5+.4*math.cos(t),.7+.4*math.sin(t)) for t in np.linspace(0,math.pi,13)])
right=dict(vertices=[[x+1.82,y,z] for x,y,z in wall['vertices']],faces=wall['faces'])
base['solids']=[box([0,0,0],[2,1,.35]),wall,right]
CATALOG['hinge_base_1x2']=base
for d,pid in [(1,'3938'),(2,'6134')]:
    top=rectangular(2,d,.1,part_id=pid)
    # Hinge top undersides are hinge hardware, not a standard socket grid.
    top['connectors']={k:v for k,v in top['connectors'].items() if k.startswith('stud:')}
    top['connectors']['hinge']=connector('hinge_top',[1,.5,-.4])
    top['solids'] += [box([.9,.25,-.4],[1.1,.75,0])]
    CATALOG[f'hinge_top_{"1x2" if d==1 else "2x2"}']=top
side=rectangular(1,1,1.2,part_id='87087')
side['connectors']['side_stud']=connector('stud',[.5,0,.7],rotation('x',90))
CATALOG['brick_side_stud_1x1']=side
ALIASES={p['part_id']:name for name,p in CATALOG.items() if p['part_id']}


def canonical(name):
    return ALIASES.get(name,name)


def finite(value,lo,hi,label):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
        raise ValueError(f'{label} must be finite in [{lo}, {hi}]')
    return value


def frame(piece, key):
    try: c=CATALOG[piece['part']]['connectors'][key]
    except KeyError: raise ValueError(f"{piece['id']} has no connector {key}") from None
    r=np.array(piece['matrix']);t=np.array(piece['origin'])
    return c, r@np.array(c['point'])+t, r@np.array(c['frame'])


def world_shapes(piece):
    r=np.array(piece['matrix']);t=np.array(piece['origin'])
    return [(np.array(shape['vertices'])@r.T+t,shape['faces']) for shape in CATALOG[piece['part']]['solids']]


def intersects(a,b):
    """Separating-axis test for convex polyhedra, including tilted plates."""
    av,af=a;bv,bf=b
    if np.any(np.max(av,axis=0)<=np.min(bv,axis=0)+1e-7) or np.any(np.max(bv,axis=0)<=np.min(av,axis=0)+1e-7): return False
    def axes(v,faces):
        normals=[];edges=[]
        for face in faces:
            pts=v[face];normals.append(np.cross(pts[1]-pts[0],pts[2]-pts[0]))
            edges.extend(pts[(i+1)%len(pts)]-pts[i] for i in range(len(pts)))
        return normals,edges
    an,ae=axes(av,af);bn,be=axes(bv,bf)
    for axis in an+bn+[np.cross(x,y) for x in ae for y in be]:
        length=np.linalg.norm(axis)
        if length<1e-9: continue
        axis=axis/length;ap=av@axis;bp=bv@axis
        if min(max(ap),max(bp))-max(min(ap),min(bp))<=1e-7: return False
    return True


def verify(placed,hinges):
    occupied=set();connections=[];items=list(placed.values())
    shapes={p['id']:world_shapes(p) for p in items}
    for p in items:
        if min(v[:,2].min() for v,_ in shapes[p['id']]) < -1e-7:
            raise ValueError(f"{p['id']} extends below the ground")
    for i,a in enumerate(items):
        for b in items[i+1:]:
            pair=frozenset((a['id'],b['id']))
            # Only the matched hinge pin proxy may interlock. Even a mated
            # hinge's top plate must not pass through the base body.
            for ai,x in enumerate(shapes[a['id']]):
                for bi,y in enumerate(shapes[b['id']]):
                    hardware = pair in hinges and ((a['part'].startswith('hinge_top_') and ai>0) or (b['part'].startswith('hinge_top_') and bi>0))
                    if not hardware and intersects(x,y):
                        raise ValueError(f"{a['id']} overlaps {b['id']}")
            matches=[]
            for ak,ac in CATALOG[a['part']]['connectors'].items():
                if ac['kind'] not in ('stud','socket'): continue
                _,ap,ar=frame(a,ak)
                for bk,bc in CATALOG[b['part']]['connectors'].items():
                    if {ac['kind'],bc['kind']} != {'stud','socket'}: continue
                    _,bp,br=frame(b,bk)
                    if np.linalg.norm(ap-bp)<1e-6 and np.dot(ar[:,2],br[:,2])<-.999999:
                        for token in ((a['id'],ak),(b['id'],bk)):
                            if token in occupied: raise ValueError(f'Connector already occupied: {token}')
                            occupied.add(token)
                        matches.append([ak,bk])
            if matches: connections.append(dict(a=a['id'],b=b['id'],kind='stud',studs=len(matches),connectors=matches))
            if pair in hinges: connections.append(dict(a=a['id'],b=b['id'],kind='hinge',studs=0))
    return connections


def compile_assembly(plan,colors):
    pieces=plan.get('pieces');steps=plan.get('steps')
    if not isinstance(pieces,list) or not 1<=len(pieces)<=128 or not isinstance(steps,list) or not 1<=len(steps)<=256:
        raise ValueError('Require 1–128 pieces and 1–256 assembly steps')
    import re
    inventory={}
    for source in pieces:
        if not isinstance(source,dict) or not isinstance(source.get('id'),str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',source['id']) or source['id'] in inventory:
            raise ValueError('Each piece needs a unique safe id')
        part=canonical(source.get('part'))
        if part not in CATALOG or source.get('color') not in colors: raise ValueError('Unknown catalog part or color')
        inventory[source['id']]=dict(id=source['id'],part=part,color=source['color'])
    placed={};parents={};hinges=set();hinge_angles={};states=[];instructions=[];connections=[]
    for i,step in enumerate(steps):
        if not isinstance(step,dict) or not isinstance(step.get('instruction'),str) or not step['instruction'].strip(): raise ValueError('Every step needs an instruction')
        identifier=step.get('piece');action=step.get('action','place');motion=None;target=None
        if identifier not in inventory: raise ValueError('Unknown inventory piece')
        if action=='rotate_hinge':
            if identifier not in hinge_angles: raise ValueError('Only a connected hinge top can rotate')
            angle=finite(step.get('angle'),-90,90,'Hinge angle');old=hinge_angles[identifier]
            parent=placed[parents[identifier]];_,pivot,_=frame(parent,'hinge')
            pr=np.array(parent['matrix']);motion=dict(pivot=pivot.tolist(),axis=pr[:,0].tolist(),degrees=angle-old,affected=[]);target=pivot.tolist();delta=pr@rotation('x',angle-old)@pr.T
            for key,p in placed.items():
                ancestor=key
                while ancestor in parents and ancestor!=identifier: ancestor=parents[ancestor]
                if ancestor==identifier:
                    motion['affected'].append(key)
                    p['origin']=(pivot+delta@(np.array(p['origin'])-pivot)).tolist()
                    p['matrix']=(delta@np.array(p['matrix'])).tolist()
            hinge_angles[identifier]=angle
        elif action=='place':
            if identifier in placed: raise ValueError('Place each inventory piece exactly once')
            p=dict(inventory[identifier]);part=CATALOG[p['part']]
            if not placed:
                pos=step.get('position',[0,0,0]);turn=step.get('rotation',0)
                if not isinstance(pos,list) or len(pos)!=3 or any(type(v) is not int or abs(v)>128 for v in pos) or pos[2]!=0: raise ValueError('Root position must be an integer grid point at ground level')
                if type(turn) is not int or turn not in (0,90,180,270): raise ValueError('Root rotation must be a quarter turn')
                r=rotation('z',turn);t=np.array([pos[0],pos[1],0.])
            else:
                attach=step.get('attach',{});parent_id=attach.get('to')
                if parent_id not in placed: raise ValueError('Attach to a previously placed piece')
                parent=placed[parent_id];pk=attach.get('connector');ck=attach.get('self')
                pc,point,pframe=frame(parent,pk);target=point.tolist()
                try: cc=part['connectors'][ck]
                except KeyError: raise ValueError(f'{identifier} has no connector {ck}') from None
                if pc['kind']=='hinge_base' and cc['kind']=='hinge_top':
                    if any(parent_id in h for h in hinges): raise ValueError('Hinge base already occupied')
                    angle=finite(attach.get('angle',0),-90,90,'Hinge angle')
                    r=np.array(parent['matrix'])@rotation('x',angle)
                    motion=dict(pivot=point.tolist(),axis=np.array(parent['matrix'])[:,0].tolist(),degrees=angle,affected=[identifier])
                    hinges.add(frozenset((parent_id,identifier)));hinge_angles[identifier]=angle
                elif {pc['kind'],cc['kind']}=={'stud','socket'}:
                    turn=attach.get('turn',0)
                    if type(turn) is not int or turn not in (0,90,180,270): raise ValueError('Snap turn must be a quarter turn')
                    r=pframe@rotation('z',turn)@rotation('x',180)@np.array(cc['frame']).T
                else: raise ValueError('Incompatible connector types')
                t=point-r@np.array(cc['point']);parents[identifier]=parent_id
            p.update(matrix=r.tolist(),origin=t.tolist(),size=part['size'],hex=colors[p['color']],
                     instruction=step['instruction'],solids=part['solids'],part_id=part['part_id'],
                     studs=[c['point'] for c in part['connectors'].values() if c['kind']=='stud'],
                     stud_frames=[c['frame'] for c in part['connectors'].values() if c['kind']=='stud'])
            placed[identifier]=p
        else: raise ValueError(f'Unknown assembly action: {action}')
        connections=verify(placed,hinges)
        if len(placed)>1:
            connected={next(iter(placed))}
            for _ in placed:
                for c in connections:
                    if c['a'] in connected or c['b'] in connected: connected.update((c['a'],c['b']))
            if len(connected)!=len(placed): raise ValueError('Assembly has disconnected pieces')
        # A second connection to another branch must remain satisfied after motion.
        if action=='rotate_hinge':
            old_edges={(c['a'],c['b'],c['kind'],str(c.get('connectors'))) for c in states[-1]['connections']}
            new_edges={(c['a'],c['b'],c['kind'],str(c.get('connectors'))) for c in connections}
            if not old_edges<=new_edges: raise ValueError('Hinge rotation would break an existing connection')
        states.append(dict(poses={k:dict(origin=p['origin'],matrix=p['matrix']) for k,p in placed.items()},connections=connections))
        targets=[]
        for connection in connections:
            if connection['kind']=='stud' and identifier in (connection['a'],connection['b']):
                side=0 if connection['a']==identifier else 1
                for keys in connection['connectors']:
                    targets.append(frame(placed[identifier],keys[side])[1].tolist())
        if motion: targets=[motion['pivot']]
        instructions.append(dict(piece=identifier,instruction=step['instruction'],action=action,attachment=step.get('attach'),motion=motion,target=target,targets=targets))
    if len(placed)!=len(inventory): raise ValueError('Every inventory piece must be placed')
    counts=Counter((p['part'],p['color']) for p in placed.values())
    return dict(version=2,title=plan['title'],pieces=list(placed.values()),connections=connections,states=states,
                steps=instructions,seconds_per_step=5.5,uncertainties=plan['uncertainties'],hinge_angles=hinge_angles,
                inventory=[dict(part=p,color=c,count=n,part_id=CATALOG[p]['part_id']) for (p,c),n in sorted(counts.items())])
