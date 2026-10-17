"""Gemini proposes OriSim3D commands; the existing engine executes the geometry."""
import base64
import json
import subprocess
from pathlib import Path

SIMULATOR = Path(__file__).parent / 'simulator'
INITIAL = 'define 200 200\niad\n'


def script_for(steps):
    return INITIAL + '\n'.join(step['commands'] for step in steps) + '\n'


def simulate(steps):
    result = subprocess.run(['node', str(SIMULATOR/'check-script.mjs')], input=script_for(steps), text=True, capture_output=True, timeout=30)
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise RuntimeError(f'OriSim3D did not return a result: {result.stderr[:500]}')


def resolve_steps(steps, proposed):
    result = subprocess.run(['node', str(SIMULATOR/'resolve-recipes.mjs')],
        input=json.dumps({'script':script_for(steps),'steps':proposed}),
        text=True, capture_output=True, timeout=60)
    return json.loads(result.stdout)


def motion_candidates(steps):
    result = subprocess.run(['node', str(SIMULATOR/'enumerate-motions.mjs')],
        input=json.dumps({'script':script_for(steps)}), text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError('Could not enumerate motions: '+result.stderr[-500:])
    return json.loads(result.stdout)


def parse_observation(text):
    content=json.loads(text)
    if isinstance(content,list):content={'actions':content}
    if not isinstance(content,dict) or not isinstance(content.get('actions'),list):
        raise ValueError('Video observation did not contain actions; raw response saved.')
    return content


def observation_request(url,model,start,end,boundary,fps):
    return {'model':model,'input':[{'type':'video','uri':url,'processing':{'type':'static','start_offset':f'{start:g}s','end_offset':f'{end:g}s','fps':fps}},
        {'type':'text','text':f'''Observe the physical origami actions in this video clip, independently of any simulator or command language.
The clip is {start:g}–{end:g} seconds in the original video. Actions through {boundary:g} seconds were already processed.
Return JSON with actions [{{"start_seconds":number,"end_seconds":number,"description":string,"moving_part":string,"destination":string,"crease_reference":string,"layer":string,"completed":boolean}}] and final_shape.
Report only actions visible in this clip, in order. Distinguish narrowing an edge to a centerline, turning a flap like a page, lifting a bottom tip upward, and an inside reverse fold. Do not assume any occurs.
Use absolute video timestamps. Mark actions unfinished at the clip end as completed:false; mention occlusion or uncertainty. Do not write geometry, coordinates, simulator commands or suggested implementations.'''}],
        'response_format':{'type':'text','mime_type':'application/json'},'generation_config':{'max_output_tokens':3000},'store':False}


def build_request(url, model, steps, start, end, boundary, fps, feedback=None, observation=None):
    if feedback and feedback.get('mode')=='visual_review':
        request=observation_request(url,model,start,end,boundary,fps)
        request['input'][1]['text']='''You are performing visual_review of a proposed origami animation against the video.
Return only {"approved":true} or {"approved":false,"reason":"Specific missing action or visible mismatch"}.
Check EVERY completed action after the processed boundary against the independent observation below, not just whether the final silhouette seems plausible. In particular, narrowing an edge does not substitute for lifting a bottom tip. Check the actual moving material, front AND back layers, direction, symmetry, and intermediate motion. Reject missing actions and uncertain layer matches. The engine passing its geometric checks does not establish a match. Do not generate commands or probes in this review.
'''+f'Clip {start:g}–{end:g}s, already processed through {boundary:g}s.\nIndependent video observation: '+json.dumps(observation)+ '\nProposed actions: '+json.dumps([s['description'] for s in feedback['candidate']['steps']])
        for img in feedback.get('images',[]):
            request['input'].extend([{'type':'text','text':f"Simulator {img.get('phase','after')} step {img['step']}: {img['description']} ({img['view']})"},{'type':'image','mime_type':'image/png','data':base64.b64encode(Path(img['path']).read_bytes()).decode()}])
        return request
    execution = simulate(steps)
    examples = '\n\n'.join(f'{name}:\n'+(SIMULATOR/'vendor/orisim3d/templates'/f'{name}.txt').read_text() for name in ['square-base','petal-fold','reverse-fold'])
    prompt = f'''Watch this origami video and reconstruct its movements as an executable
OriSim3D script. The engine computes paper geometry and animates your commands.
Return JSON {{"steps":[{{"description":"Short instruction", "commands":"native script"}}]}}.
For a square-base collapse or petal fold, FIRST ask the engine for rendered choices:
{{"compare_motions":{{"after_steps":[]}}}}.
after_steps may contain the setup/unfold/turn steps needed BEFORE the compound fold;
they start from the accepted state and are temporary. The engine enumerates matching
mechanisms, constructs their creases, transfers motion to all material subdivisions,
and returns labeled previews. It can raise either opposing petal, including the
second one after the first has been raised. Do not infer front/back from the ID:
compare the actual images and material corner against the video.
Choose a matching preview with {{"select_motion":"candidate ID"}}. This proposes
its setup plus compound fold for the ordinary visual review; it commits nothing yet.
You may then extend the proposed steps to cover the rest of this clip. Never approve
a partial clip just because one candidate matches. If none matches, explain the
mismatch with {{"steps":[...]}} or request choices after corrected setup steps.
Before rotating around a NEW crease, inspect its actual IDs: you may reply
{{"probe":"native construction commands"}} instead of steps. The controller
executes this temporary script on the accepted state and returns the resulting
point/edge/face IDs. Probe as often as needed; probes do NOT commit any geometry.
Each probe replaces the previous probe and starts from the ACCEPTED state below.
Include all necessary probe construction commands again in your final steps.
Do not guess newly-created segment IDs. Use probes to discover them first.
For simple edge-to-edge folds, prefer this GEOMETRIC OPERATION over raw commands:
{{"steps":[{{"description":"Fold the selected edge to the centerline","operation":{{"name":"align_edge","moving_edge":"s1","target_edge":"s5","seed_face":"f6","direction":"valley","duration_ms":1500}}}}]}}
These IDs are illustrative: select actual CURRENT edges and a face bordering the
moving edge. seed_face identifies the paper layer and its oriented normal.
Valley moves toward that face normal; mountain moves away. The adapter constructs
the bisector with the native engine, discovers its actual ID, collects the connected
moving vertices, and verifies alignment and strain. Do not predict hinge IDs or
list moving vertices yourself. Supports a planar flap folded 180 degrees to a
stationary coplanar target line (intersecting or parallel edges); not compound folds.
Current faces include boundary edge IDs to make layer/edge selection easier.
For book folds or rigid rotations around an EXISTING hinge, use:
{{"steps":[{{"description":"Turn the selected flap like a page","operation":{{"name":"rotate_flap","hinge":"s8","seed_points":["p10"],"angle_degrees":180,"duration_ms":1500}}}}]}}.
IDs above are illustrative. The engine finds ALL connected material vertices on
each selected flap, stopping at the hinge. Choose one off-axis seed point per
intended moving material component; do not enumerate every moving vertex.
Multiple seeds can move several disconnected layers together. Angles are signed
incremental rotations about the segment's p1->p2 direction. Use separate operations
for flaps moving in opposite directions. Existing internal folds move rigidly with
the component. This is NOT a reverse-fold solver. Probe these operations and compare
renders to choose layers and sign; the engine checks strain but not self-collision.
To inspect an operation before proposing the complete clip, return
{{"probe_steps":[{{"description":"Temporary edge fold","operation":{{"name":"align_edge","moving_edge":"s1","target_edge":"s5","seed_face":"f6","direction":"valley"}}}}]}}.
This starts from accepted state and commits nothing. Include earlier proposed steps
in probe_steps when inspecting a sequence. It returns the executed state and actual
moving selection; use that state for later operations instead of guessing future IDs.
Repeat the intended operations in final steps. Choose exactly one of operation,
recipe, or commands in each proposed step. If no planar flap can be isolated, use a
compound recipe or request a corrected selection; do not bypass physical checks.

Prefer the tested upstream recipes below whenever their starting state matches.
A step may use {{"description":"Raise the front petal","recipe":{{"name":"petal_fold","duration_ms":2000}}}}
instead of commands. Available recipes:
- square_base: flat square -> collapsed square base, reusing/creating base creases.
- petal_fold: square base -> one raised petal, including crease construction.
Both accept duration_ms (300..10000); petal_fold also accepts angle_degrees (-180..-90).
Petals close flat at -180 degrees by default so subsequent edge folds are coplanar.
Use a partially open angle only if the video leaves that action unfinished.
petal_fold also accepts material_rotation=0,90,180,270; the engine filters which
material flaps match the starting pose. Prefer selecting its rendered candidates.
These are real callable operations, expanded against CURRENT material regions.
They never reset the sheet. Whole-sheet reorientations are supported. Different
layers/topology or already folded flaps may require unfolding/setup commands first.
Petal motion transfers to extra vertices and flat precreases on the same affected
regions. Other already-raised flaps stay in place. Incompatible starting poses are
rejected; no sheet reset or global layer-order/collision guarantee is implied.
Use recipe steps for supported actions; use custom native commands only for missing
operations or necessary setup. You may mix recipe and command steps in video order.
The controller renders recipe results for your review before committing, just like
custom commands. A recipe name does not prove a visual match to the video.
Each step is a completed video action. No mesh arrays or prose in commands.
This clip is {start:g}–{end:g}s; video through {boundary:g}s is already processed.
Overlap is context. Include actions completing after {boundary:g}s; defer unfinished
ones. Include unfolding, rotations and compound folds. Keep the demonstrated order.
The first new action is step {len(steps)+1}. Return only NEW steps.
Independent video-only observation (use this to identify the intended actions before
choosing geometry operations; do not substitute an easier operation for the observed
action). Completed actions after the boundary must all be covered, in order:
{json.dumps(observation)}

The engine already started with define 200 200 and iad. Do NOT redefine the sheet.
Initial p0=(-200,-200),p1=(200,-200),p2=(200,200),p3=(-200,200), z=0.
Original material coordinates never change; 3D coordinates change after each fold.
Points, segments and faces use IDs p0, s0, f0 etc. Construction commands append
new IDs; later subdivisions can alter existing segment endpoints. Use the actual
state below; do not assume example IDs apply to your current sheet.

Native command reference:
by2d pA pB: split all intersected faces along the material-space line through points.
by3d pA pB: split along the line through points in the current folded state.
c2d pA pB: material-space perpendicular bisector; c3d uses folded space.
b2d sA sB / b3d sA sB: bisect the two segment lines in material/folded space.
perpendicular2d sA pB / perpendicular3d sA pB: crease perpendicular to segment through point.
split sA ratio: insert point along segment, ratio 0..1.
r sA angle pA pB ...: rotate ONLY the listed vertices around the oriented
segment (p1->p2) by a signed right-hand INCREMENTAL rotation in degrees.
The angle is a DELTA, NOT a target. r s4 0 does NOTHING. To undo r s4 180 p2,
use r s4 -180 p2. A newly folded state does not reset the hinge angle to zero.
Explicitly list all
moving vertices/layers. An unfold rotates back about its existing crease.
a pA pB ...: adjust listed vertices to enforce segment lengths. Used during
compound folds alongside explicit driven rotations; never use it to invent a pose.
t 1500 r sA angle pA ... a pB ...: animate commands on this SAME LINE together
for 1500ms. Put topology construction on separate untimed lines BEFORE animation.
Multiple r commands on one timed line can coordinate a collapse; their axes are
frozen at the beginning. For all visible motion use t 1500 (or longer).
tx angle / ty angle / tz angle rotate the whole sheet about the named axis;
these also work after t. Whole-sheet motion must match the video's reorientation.
offset value fA ...: rendering-only layer offset, if needed to avoid z-fighting.
order fA fB ...: rendering-only face order, nearest first.
Do not use fit, zoom, move, read, write, pauses, JavaScript, or imaginary commands.
Use comments starting // for short notes only. Preserve one continuous sheet.

Actual executed state (point positions, material coordinates, segment/face IDs):
{json.dumps(execution.get('state'))}
Already accepted steps and native commands:
{json.dumps(steps)}

These are WORKING UPSTREAM EXAMPLES for understanding the command language.
They are not the video, and their IDs only apply when run from their own initial sheet:
{examples}
'''
    if feedback and feedback.get('mode')=='probe_result':
        prompt += '\nFor a successful operation probe, inspect the attached renders and preserve its useful steps. If it covers ALL remaining completed actions in this clip, return those steps as final steps now. Otherwise extend that sequence. Do not keep probing an already verified selection. For a failed sequence, engine_feedback.state is AFTER resolved_steps and BEFORE failed_step; repair that step using those IDs. All new proposals still start from the accepted state, so repeat the successful prefix. Do not repeat proposals listed in recent_attempts without a concrete correction. An already-aligned edge may indicate a redundant action or the wrong layer; compare the video before choosing.\n'
    if feedback and feedback.get('mode')=='visual_review':
        prompt += '\nYou now have actual engine renders after each proposed action. Compare these against the video, including silhouette, moving layers, front/back and orientation. Reply {"approved":true} ONLY if the proposed sequence matches. Otherwise return a corrected {"steps":[...]} for this clip, replacing the candidate. Do not approve merely because execution succeeded.\n'
    if feedback and feedback.get('mode')=='motion_options':
        prompt += '\nThese are engine-generated alternatives from one starting state. Each image is labeled with its candidate ID. Choose with select_motion only if the material flap and motion match the video; an engine-valid candidate can still be wrong. No candidate has been committed.\n'
    if feedback:
        prompt += '\nCandidate and simulator feedback (review/correct without dropping video actions):\n'+json.dumps({k:v for k,v in feedback.items() if k!='images'})
    request = {'model':model,'input':[{'type':'video','uri':url,'processing':{'type':'static','start_offset':f'{start:g}s','end_offset':f'{end:g}s','fps':fps}},{'type':'text','text':prompt}], 'response_format':{'type':'text','mime_type':'application/json'},'generation_config':{'max_output_tokens':8192},'store':False}
    for image in (feedback or {}).get('images',[]):
        request['input'].extend([{'type':'text','text':f"Simulator {image.get('phase','after')} step {image['step']}: {image['description']} ({image['view']} view)"}, {'type':'image','mime_type':'image/png','data':base64.b64encode(Path(image['path']).read_bytes()).decode()}])
    return request


def render(steps, url, model, start, path):
    doc=document(url,model,steps);doc['review_start']=start
    result=subprocess.run(['node',str(SIMULATOR/'render-script.mjs'),str(path)],input=json.dumps(doc),text=True,capture_output=True,timeout=90)
    if result.returncode:raise RuntimeError('Could not render simulator feedback. Run npm install and ensure Google Chrome is installed. '+result.stderr[-600:])
    return json.loads(result.stdout)['images']


def document(url, model, steps):
    return {'engine':'orisim3d','video_url':url,'model':model,'steps':steps}
