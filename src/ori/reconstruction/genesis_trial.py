"""Bounded Gemini -> Genesis -> rendered feedback -> revised parameters loop."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT/'examples/genesis_compound/run.py'


def write(path, value):
    path.write_text(json.dumps(value,indent=2)+'\n')


def check(plan):
    spec = importlib.util.spec_from_file_location('genesis_compound', RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate(plan)


def assess(client, model, directory, plan):
    from google.genai import types
    report = json.loads((directory/'report.json').read_text())
    prompt = '''Inspect the actual Genesis simulation frames and particle metrics.
Goal: a putty knife physically SPREADS an elastoplastic lump into a thin smear
on a horizontal drywall test coupon. Judge the observed motion, not the title.
Do not approve a blob merely being pushed forward or particles exploding.
This is NOT calibrated real joint compound and NOT the full vertical-wall task.
You may revise material parameters and the guided blade path. The simulation
runner does not prescribe material particle positions. No visibility tricks.
Return JSON {"achieves_spreading":boolean,"assessment":string,
"visible_defects":[string],"revised_plan":null or FULL replacement plan}.
Replacement plan retains title, E in [1000,20000],nu in [.15,.4],rho in
[1000,2000], optional yield_stress in [10,5000] Pa (default100),duration in[2,4],
optional panel_coupling_friction[0,2] (default .1), blade_friction[0,2] (default .3),
optional blade_tilt_degrees[-60,60] about the y axis (default0, upright),
keys:[{time,position:[x,y,z]}], rationale and approximations. 4-10 keys,
start time0 and end time=duration, increasing times; x[-.2,.2], abs(y)<=.03,
blade center z[.088,.2] so bottom stays above panel top .052.
Panel .36x.24x.024 centered [0,0,.04]; initial lump .06x.06x.03 centered
[-.07,0,.075]. Blade .006x.12x.07. If successful use revised_plan:null.
Particle spacing is .004m; a coating much thinner than that cannot be resolved
reliably. Board-to-paste coupling friction is distinct from rigid-body friction;
increase panel_coupling_friction if paste slides wholesale instead of shearing.
Current plan:\n''' + json.dumps(plan) + '\nACTUAL metrics:\n' + json.dumps(report)
    images = sorted(directory.glob('frame-*.png'))
    write(directory/'review.request.json',dict(model=model,prompt=prompt,images=[str(p) for p in images]))
    parts=[types.Part.from_text(text=prompt)]
    for path in images:
        parts.extend([types.Part.from_text(text=path.name),
                      types.Part.from_bytes(data=path.read_bytes(),mime_type='image/png')])
    response = client.models.generate_content(model=model,contents=parts,
        config=types.GenerateContentConfig(response_mime_type='application/json',max_output_tokens=6000))
    (directory/'review.response.json').write_text(response.model_dump_json(exclude_none=True))
    result = json.loads(response.text or '')
    write(directory/'review.json',result)
    return result


def propose(client, model, url, directory):
    from google.genai import types
    from .video import plan_path
    plan_path(url)
    prompt = '''Watch the putty knife spreading joint compound in this tutorial.
Design a physical Genesis MPM experiment. The drywall sample is horizontal
to isolate spreading from vertical adhesion; acknowledge this approximation.
Panel size .36x.24x.024 m centered [0,0,.04], top z=.052. Compound starts as a
.06x.06x.03 m lump centered [-.07,0,.075]. A rigid blade .006x.12x.07 m follows
your center positions while contacting material particles. No particle position
edits or staged spreading. Choose material parameters and a slow sweep across
the lump, leaving a thin layer on the board, then lift. Allow .4s settling.
Return JSON {title,E,nu,rho,yield_stress,panel_coupling_friction,blade_friction,blade_tilt_degrees,
duration,keys:[{time,position:[x,y,z]}],
rationale,approximations:[string]}. E[1000,20000] Pa,nu[.15,.4],rho[1000,2000],
yield_stress[10,5000] Pa,duration[2,4] s. 4-10 keys start at t0 and end at duration,
strictly increasing. x[-.2,.2],abs(y)<=.03,z[.088,.2]. Start [-.15,0,.105];
blade bottom is center z minus .035. Use low plastic yield for a smear rather
than an elastic block. Choose panel_coupling_friction[.1,2] and blade_friction[0,2].
Particle spacing is .004m: leave a resolvable coating thickness under the blade.
Choose blade_tilt_degrees[-60,60] around y; 0 is upright. Tilt changes the gap.
This is uncalibrated surrogate paste, not real compound.
The runner returns actual frames and particle metrics for your revision.'''
    write(directory/'initial-plan.request.json',dict(model=model,url=url,prompt=prompt))
    response=client.models.generate_content(model=model,contents=[
        types.Part(file_data=types.FileData(file_uri=url,mime_type='video/mp4')),
        types.Part.from_text(text=prompt)],
        config=types.GenerateContentConfig(response_mime_type='application/json',max_output_tokens=4000))
    (directory/'initial-plan.response.json').write_text(response.model_dump_json(exclude_none=True))
    plan=check(json.loads(response.text or ''))
    write(directory/'initial-plan.json',plan)
    return plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    initial=parser.add_mutually_exclusive_group(required=True)
    initial.add_argument('--plan',type=Path,help='Initial Gemini-generated material/motion plan')
    initial.add_argument('--url',help='Have Gemini observe this tutorial and propose the initial plan')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--python',type=Path,default=ROOT/'.local/genesis-venv/bin/python')
    parser.add_argument('--backend',choices=['metal','cpu','cuda'],default='metal')
    parser.add_argument('--model',default='gemini-3.5-flash')
    parser.add_argument('--attempts',type=int,choices=[1,2,3],default=2)
    args=parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Use a new output directory to preserve prior trial evidence')
    args.output.mkdir(parents=True,exist_ok=True)
    write(args.output/'config.json',dict(source_plan=str(args.plan.resolve()) if args.plan else None,
        source_url=args.url,model=args.model,backend=args.backend,attempts=args.attempts,
        simulation_python=str(args.python),runner=str(RUNNER)))
    from google import genai
    from google.genai import types
    from ori.config import load_settings
    history=[]
    with genai.Client(api_key=load_settings().gemini_api_key,http_options=types.HttpOptions(
            timeout=180000,retry_options=types.HttpRetryOptions(attempts=1))) as client:
        plan=check(json.loads(args.plan.read_text())) if args.plan else propose(client,args.model,args.url,args.output)
        for attempt in range(args.attempts):
            directory=args.output/f'attempt-{attempt+1:02d}'
            directory.mkdir()
            write(directory/'plan.json',plan)
            print(f'Genesis attempt {attempt+1}/{args.attempts}: {directory}',flush=True)
            with (directory/'simulation.log').open('w') as log:
                result=subprocess.run([str(args.python),'-u',str(RUNNER),
                    '--plan',str((directory/'plan.json').resolve()),
                    '--output',str(directory.resolve()),'--backend',args.backend],
                    stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError(f'Genesis failed; inspect {directory}/simulation.log')
            feedback=assess(client,args.model,directory,plan)
            history.append(dict(directory=str(directory),review=feedback))
            write(args.output/'result.json',dict(history=history,
                status='model_observed_spreading' if feedback.get('achieves_spreading') is True else 'needs_improvement',
                latest_animation=str(directory/'animation.mp4'),
                limitation='Visual model assessment; material properties are uncalibrated.'))
            print(feedback['assessment'],flush=True)
            if feedback.get('achieves_spreading') is True or feedback.get('revised_plan') is None:
                break
            if attempt+1 < args.attempts:
                plan=check(feedback['revised_plan'])


if __name__ == '__main__':
    main()
