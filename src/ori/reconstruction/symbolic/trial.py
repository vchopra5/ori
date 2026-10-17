"""Bounded trial of Gemini's axiom → Rabbit Ear → FOLD proposal."""
import base64
import json
import subprocess
from pathlib import Path
from google import genai
from google.genai import types
from ori.config import load_settings
from ori.reconstruction.batching import atomic_json
from ori.reconstruction.video import VIDEO_URL, plan_path
from ori.reconstruction.outputs import new_run, save_request

HERE=Path(__file__).parent

def compile_plan(initial,steps):
    r=subprocess.run(['node',str(HERE/'compile.mjs')],input=json.dumps({'initial':initial,'steps':steps}),text=True,capture_output=True,timeout=30)
    if r.returncode:raise RuntimeError(r.stderr[-1000:])
    return json.loads(r.stdout)

def render(fold,path):
    r=subprocess.run(['node',str(HERE/'render.mjs'),str(path)],input=json.dumps(fold),text=True,capture_output=True,timeout=60)
    if r.returncode:raise RuntimeError(r.stderr[-1000:])
    return json.loads(r.stdout)['images']

def main():
    initial=json.loads((HERE.parent/'simulator/templates/square-base.fold').read_text())
    base=plan_path(VIDEO_URL)
    out=new_run(base,'symbolic')
    steps=[];execution=compile_plan(initial,steps);history=[];status={'stopped_reason':'six-call budget exhausted','model_claimed_done':False}
    print(f'Symbolic trial: 85–150s, initialized from the sourced square-base template.\nModel: gemini-3.5-flash. At most 6 calls. Output: {out}',flush=True)
    with genai.Client(api_key=load_settings().gemini_api_key,http_options=types.HttpOptions(timeout=300000,retry_options=types.HttpRetryOptions(attempts=1))) as client:
        for turn in range(6):
            call=out/'debug'/f'call-{turn+1:02d}'
            call.mkdir(parents=True)
            images=render(execution['fold'],call/'state')
            prompt='''Reconstruct the video AFTER the square base is completed (about 90s), through 150s.
You are testing your proposed procedural symbolic architecture: Huzita–Hatori constructions compiled by Rabbit Ear into sequential FOLD states. Starting geometry is a standard square base, already folded. Do not repeat the collapse or replace the sheet. Infer the demonstrated folds and layers autonomously.
Return JSON {"steps":[...],"done":false}. New steps only. Set done:true only after all completed actions through 150s have been covered. You can return {"steps":[],"done":false,"blocked":"specific unsupported action"} if this representation cannot express the next action; do not pretend completion.
Each step has unique id, description, action (fold, crease, unfold).
For fold/crease: axiom 1..7, points:[named point refs], lines:[named edge refs], assignment:M or V, layers:"all" or [named face refs], solution:index if multiple mathematical solutions.
Axiom inputs: 1=2 points through line; 2=2 points brought together; 3=2 lines aligned; 4=1 point and 1 line (perpendicular through point); 5=2 points and 1 line (first point to line through second point); 6=2 points and 2 lines (point1 to line1, point2 to line2); 7=1 point and 2 lines (point to first line, perpendicular to second line).
For unfold: {"id":"u1","description":"...","action":"unfold","fold":"earlier step id"}. This restores that fold's previous angles while retaining crease topology.
Fold means completed 180-degree flat fold. Crease adds a flat crease. Compiler supports flat states, not arbitrary 3D motions. Compound actions must be described with valid operations if possible; report a limitation if not.
The compiler computes vertices/intersections. Never output coordinates, mesh arrays, arbitrary code, or native simulator commands. Use the supplied CURRENT reference catalog. Named references track descendants when edges/faces split. A face name selects all its descendants; new current faces/edges are available as stepId.fN / stepId.eN. Unfold references preserve crease identities after subdivision.
Propose one operation at a time if later choices depend on newly created geometry. Inspect compiler feedback and the actual current FOLD-state image. Failed proposals are transactional and do not alter accepted state. Do not confuse a valid file or low strain with the correct video action. Initial rendering orientation may differ from the video; reference material coordinates to identify corresponding corners.
'''
            prompt+='\nAccepted symbolic steps:\n'+json.dumps(steps)+'\nCurrent catalog:\n'+json.dumps(execution['state'])+'\nPrevious feedback:\n'+json.dumps(history[-3:])
            contents=[{'type':'video','uri':VIDEO_URL,'processing':{'type':'static','start_offset':'85s','end_offset':'150s','fps':1}},{'type':'text','text':prompt}]
            for image in images:contents.append({'type':'image','mime_type':'image/png','data':base64.b64encode(Path(image['path']).read_bytes()).decode()})
            request={'model':'gemini-3.5-flash','input':contents,'response_format':{'type':'text','mime_type':'application/json'},'generation_config':{'max_output_tokens':8192},'store':False}
            save_request(call/'model.request.json',request,images)
            reply=client.interactions.create(**request)
            atomic_json(call/'model.response.json',reply.model_dump(mode='json',exclude_none=True))
            proposal=json.loads((reply.output_text or '').lstrip('\ufeff'));atomic_json(call/'model.proposal.json',proposal)
            proposed=proposal.get('steps',[])
            if not isinstance(proposed,list):raise ValueError('Expected steps array')
            result=compile_plan(initial,steps+proposed)
            atomic_json(call/'compiler.json',result)
            print(f'Call {turn+1}: {len(proposed)} proposed; '+('compiled' if result['ok'] else result['error']),flush=True)
            history.append({'proposal':proposal,'ok':result['ok'],'error':result.get('error'),'failed_step':result.get('failed_step')})
            if result['ok']:
                steps+=proposed;execution=result
                atomic_json(out/'plan.json',{'initial':initial,'steps':steps,'video_url':VIDEO_URL,'scope_seconds':[90,150]})
                atomic_json(out/'compiled.fold',execution['fold'])
                atomic_json(base.with_suffix('.fold'),execution['fold'])
                if proposal.get('blocked') or proposal.get('done'):
                    status={'stopped_reason':'model finished or reported a limitation','model_claimed_done':proposal.get('done',False),'blocked':proposal.get('blocked')}
                    break
        atomic_json(out/'status.json',{**status,'calls':len(history),'compiled_steps':len(steps),'validated':'geometry only; sequence correspondence and collision-free motion not independently confirmed'})
        final_images=render(execution['fold'],out/'final')
        atomic_json(out/'debug/history.json',history)
        if steps:
            print(f'Saved {len(steps)} compiled steps. Import into simulator: {base.with_suffix(".fold")}\nRun details: {out}\nPreview: {final_images[0]["path"]}',flush=True)
        else:
            print(f'No folds compiled. Run details: {out}',flush=True)

if __name__=='__main__':main()
