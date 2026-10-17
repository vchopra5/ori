"""Direct Gemini FOLD-frame extraction and non-destructive geometry checks."""
import json
import math


def initial_state():
    return {
        'file_spec': 1.2, 'file_creator': 'Ori', 'file_title': 'Video reconstruction',
        'frame_title': 'Initial square', 'frame_classes': ['creasePattern'],
        'frame_attributes': ['2D'],
        'vertices_coords': [[0, 0], [1, 0], [1, 1], [0, 1]],
        'edges_vertices': [[0, 1], [1, 2], [2, 3], [3, 0]],
        'edges_assignment': ['B'] * 4, 'edges_foldAngle': [0] * 4,
        'faces_vertices': [[0, 1, 2, 3]], 'file_frames': [],
    }


def build_fold_request(url, model, frames, start, end, boundary, fps):
    previous = frames[-1] if frames else {k:v for k,v in initial_state().items() if not k.startswith('file_')}
    titles = [frame.get('frame_title', '') if isinstance(frame,dict) else 'Unresolved frame' for frame in frames]
    prompt = f'''Reconstruct this origami demonstration as FOLD 1.2 geometry.
This clip spans {start:g}–{end:g} seconds. Video before {boundary:g}s has already
been processed. Leading overlap is context, not new steps. Include each new
completed action, including unfolds and paper reorientations. Defer unfinished
actions to the next clip. Never duplicate actions completed in earlier clips.

Return one JSON object with file_spec:1.2 and file_frames:[...]. Each entry is a
complete, self-contained FOLD frame describing the resulting paper state after
one action. Use frame_inherit:false and omit frame_parent. No template IDs or
point-to-point action objects: YOU supply the geometry, not a template lookup.
Use these FOLD fields:
- frame_title: a short instruction describing the action just completed.
- frame_classes:["foldedForm"], frame_attributes:["3D"].
- vertices_coords: numeric [x,y,z] positions in the original unit-square frame.
- vertices_ori:uv: matching [u,v] material coordinates on the original sheet.
- edges_vertices: zero-based vertex pairs; split edges where creases intersect.
- faces_vertices: consistently wound vertex cycles for planar material panels.
- edges_assignment: one B, M, V, F, or U per edge.
- edges_foldAngle: one signed angle per edge in [-180,180]; positive valley,
negative mountain, zero flat/boundary. These describe the RESULTING state.
- faceOrders: [faceA,faceB,sign] for known overlapping face order. +1 means A is
above B along B's oriented normal, -1 below; omit unknown relationships.
- ori:uncertainties: short notes where geometry or correspondence is uncertain.

Initial sheet corners are (0,0,0),(1,0,0),(1,1,0),(0,1,0), front normal +z.
Material UV remains fixed to the original paper. Retain vertex IDs when possible;
add vertices and subdivide faces when new creases require it. Preserve paper
edge lengths and total material area. Track which layers actually move. A collapse
may move several faces simultaneously. Do not replace it with a one-hinge fold.
An unfold restores the relevant pose but retains crease topology. Coordinates
must describe the folded state, not just the flat crease pattern. Do not insert
fake layer thickness to separate faces. No cut edges, duplicate faces, or geometry
invented merely to fill a field. If a state cannot be reconstructed, keep a frame
with its frame_title and ori:uncertainties explaining the missing geometry rather
than dropping the action or copying the previous geometry as if it were new.
Return file_frames:[] if there are no new completed actions in this clip.

Already extracted actions: {json.dumps(titles)}
Previous state (may have missing or uncertain geometry): {json.dumps(previous)}
'''
    return {
        'model': model,
        'input': [{'type':'video','uri':url,'processing':{'type':'static','start_offset':f'{start:g}s','end_offset':f'{end:g}s','fps':fps}}, {'type':'text','text':prompt}],
        'response_format': {'type':'text','mime_type':'application/json'},
        'generation_config': {'max_output_tokens':16384}, 'store':False,
    }


def geometry_issues(frame):
    """Report issues without throwing away model output; not a foldability proof."""
    if not isinstance(frame, dict):
        return ['Frame must be an object.']
    points, edges, faces = (frame.get(k) for k in ('vertices_coords','edges_vertices','faces_vertices'))
    if not all(isinstance(x,list) and x for x in (points,edges,faces)):
        return ['Missing mesh geometry.']
    if any(not isinstance(p,list) or len(p)!=3 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in p) for p in points):
        return ['Expected finite 3D coordinates.']
    valid=lambda i:isinstance(i,int) and not isinstance(i,bool) and 0<=i<len(points)
    if any(not isinstance(e,list) or len(e)!=2 or not all(valid(i) for i in e) or e[0]==e[1] for e in edges):
        return ['Invalid edge indices.']
    if any(not isinstance(f,list) or len(f)<3 or not all(valid(i) for i in f) for f in faces):
        return ['Invalid face indices.']
    issues=[]
    for key in ('edges_assignment','edges_foldAngle'):
        if not isinstance(frame.get(key),list) or len(frame[key])!=len(edges):issues.append(f'{key} must match the edge count.')
    uv=frame.get('vertices_ori:uv')
    if not isinstance(uv,list) or len(uv)!=len(points) or any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in p) for p in uv):
        issues.append('Missing/invalid material coordinates; length preservation cannot be checked.')
    else:
        if any(abs(math.dist(points[a],points[b])-math.dist(uv[a],uv[b]))>.01 for a,b in edges):
            issues.append('Some edges differ from material lengths by more than 0.01 sheet widths.')
        area=sum(abs(sum(uv[a][0]*uv[f[(i+1)%len(f)]][1]-uv[f[(i+1)%len(f)]][0]*uv[a][1] for i,a in enumerate(f)))/2 for f in faces)
        if abs(area-1)>.01:issues.append('Total material face area differs from one square sheet.')
    return issues


def fold_document(frames):
    document=initial_state()
    document['file_frames']=frames
    return document
