"""Extract a full video in bounded static clips, saving progress after each clip."""
import argparse
import json
import math
import re
import httpx
from pathlib import Path
from time import monotonic
from ori.reconstruction.batching import atomic_json
from ori.reconstruction.video import VIDEO_URL, plan_path
from ori.reconstruction.outputs import new_run, clip_directory, resolve_checkpoint, save_request
from ori.reconstruction.animation import build_request as build_animation_request, observation_request, parse_observation, document as animation_document, simulate, script_for, render, resolve_steps, motion_candidates

MODEL = "gemini-3.5-flash"

def video_duration(url):
    """Read public YouTube metadata, without downloading media or calling Gemini."""
    response = httpx.get(url, follow_redirects=True, timeout=20)
    response.raise_for_status()
    html = response.text
    for match in re.finditer(r"(?:var\s+)?ytInitialPlayerResponse\s*=\s*", html):
        try:
            player, _ = json.JSONDecoder().raw_decode(html[match.end():])
            value = float(player["videoDetails"]["lengthSeconds"])
            if math.isfinite(value) and value > 0:
                return value
        except (ValueError, KeyError, TypeError):
            continue
    raise ValueError("Could not read video duration from YouTube. Use --duration SECONDS to override.")



def windows(duration, size=30, overlap=5, completed=0):
    end = completed
    while end < duration:
        boundary = end
        end = min(duration, boundary + size)
        yield max(0, boundary-overlap), end, boundary


def publish_preview(document):
    preview=Path(__file__).parent/'simulator'/'latest-animation.json'
    if preview.parent.exists():atomic_json(preview,document)


def save_feedback(state, feedback, checkpoint):
    previous=state.get('pending_feedback',{})
    recent=list(previous.get('recent_attempts',[]))
    if previous:
        result=previous.get('engine_feedback',{})
        recent.append({'proposal':previous.get('candidate',previous.get('probe_steps',previous.get('probe_commands'))),
            'ok':result.get('ok'),'error':result.get('error'),'failed_step':result.get('failed_step')})
    feedback['recent_attempts']=recent[-8:]
    state['pending_feedback']=feedback
    atomic_json(checkpoint,state)


def compare_motions(steps, setup, url, model, path):
    if not isinstance(setup,list) or any(not isinstance(step,dict) for step in setup):
        raise ValueError('compare_motions.after_steps must be a list of setup steps.')
    resolved=resolve_steps(steps,setup)
    if not resolved['ok']:
        return {'mode':'engine_error','candidate':{'steps':setup},'engine_feedback':resolved}
    prefix=steps+resolved['steps']
    choices=motion_candidates(prefix)
    atomic_json(Path(str(path)+'.motions.json'),choices)
    options=[];images=[]
    for option in choices['candidates']:
        preview=render(prefix+[option['resolved_step']],url,model,len(prefix),Path(str(path)+'.'+option['id']))
        images.extend([{**image,'description':f"Candidate {option['id']}: {image['description']}"} for image in preview])
        options.append({'id':option['id'],'description':option['description'],
            'steps':setup+[option['step']],'max_strain':option['max_strain']})
    return {'mode':'motion_options','candidates':options,'images':images,
        'unavailable':choices['unavailable'],'validation':choices['validation'],
        'note':'All options start from the same accepted state plus after_steps. Select an ID or correct the setup. None is committed.'}


def main():
    parser=argparse.ArgumentParser(description='Reconstruct a video as an animated OriSim3D folding script.')
    parser.add_argument('--url', default=None)
    parser.add_argument('--model', default=None)
    parser.add_argument('--duration',type=float,help='Otherwise detected from the full video')
    parser.add_argument('--window',type=float,default=30)
    parser.add_argument('--overlap',type=float,default=5)
    parser.add_argument('--fps',type=float,default=1)
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    if args.resume:
        args.resume=resolve_checkpoint(args.resume)
    saved=json.loads(args.resume.read_text()) if args.resume else None
    if saved and saved.get('engine')!='orisim3d':parser.error('This checkpoint is from the older geometry extractor. Start a new extraction.')
    old=saved['config'] if saved else {}
    args.url=args.url or old.get('url',VIDEO_URL)
    args.model=args.model or old.get('model',MODEL)
    base=plan_path(args.url)
    url=f'https://www.youtube.com/watch?v={base.stem}'
    if args.duration is None:
        args.duration=old.get('duration')
        if args.duration is None:
            print('Detecting video duration…',flush=True)
            args.duration=video_duration(url)
    if not all(math.isfinite(v) for v in [args.duration,args.window,args.overlap,args.fps]) or min(args.duration,args.window,args.fps)<=0 or not 0<=args.overlap<args.window:
        parser.error('Require positive duration/window/fps and 0 <= overlap < window.')
    config={'url':url,'model':args.model,'duration':args.duration,'window':args.window,'overlap':args.overlap,'fps':args.fps}
    if args.dry_run:
        print(json.dumps(config,indent=2));return
    if saved and old!=config:parser.error('Resume with the same clip settings.')
    run_dir=args.resume.parent if saved else new_run(base,'animation')
    checkpoint=run_dir/'progress.checkpoint.json'
    state=saved or {'engine':'orisim3d','config':config,'completed_seconds':0,'steps':[],'clips':[]}
    atomic_json(checkpoint,state)
    if not saved and base.exists():atomic_json(run_dir/'debug/previous-plan.json',json.loads(base.read_text()))
    print(f'Model: {args.model}\nNative OriSim3D animation · {args.duration:g}s video\nCheckpoint: {checkpoint}\nOne independent observation per clip, then up to eight working turns and one reserved final review. No API-error retries.',flush=True)
    from google import genai
    from google.genai import types
    from ori.config import load_settings
    with genai.Client(api_key=load_settings().gemini_api_key,http_options=types.HttpOptions(timeout=300_000,retry_options=types.HttpRetryOptions(attempts=1))) as client:
        for start,end,boundary in windows(args.duration,args.window,args.overlap,state['completed_seconds']):
            print(f'Clip {start:g}–{end:g}s; {len(state["steps"])} steps saved',flush=True)
            clip_dir=clip_directory(run_dir,start,end)
            begun=monotonic()
            try:
                observed=state.get('clip_observation')
                if not observed or (observed['start'],observed['end'],observed['boundary'])!=(start,end,boundary):
                    print('  Observing video actions before choosing simulator operations…',flush=True)
                    request=observation_request(url,args.model,start,end,boundary,args.fps)
                    save_request(clip_dir/'observation.request.json',request,[])
                    observation=client.interactions.create(**request)
                    atomic_json(clip_dir/'observation.response.json',{'response':observation.model_dump(mode='json',exclude_none=True),'output_text':observation.output_text})
                    if observation.status!='completed' or not observation.output_text:raise ValueError('Incomplete video observation; raw response saved.')
                    content=parse_observation(observation.output_text)
                    observed={'start':start,'end':end,'boundary':boundary,'observations':content}
                    state['clip_observation']=observed
                    atomic_json(checkpoint,state)
                feedback=state.get('pending_feedback')
                if feedback and feedback.get('mode')=='probe_result' and feedback.get('engine_feedback',{}).get('ok') and feedback.get('resolved_steps') and not feedback.get('images'):
                    print('Rendering the successful saved probe before continuation…',flush=True)
                    feedback['images']=render(state['steps']+feedback['resolved_steps'],url,args.model,len(state['steps']),clip_dir/'saved-probe')
                    atomic_json(checkpoint,state)
                for attempt in range(9):
                    final_review = attempt == 8
                    if final_review and (not feedback or feedback.get('mode') != 'visual_review'):
                        raise ValueError('Working budget exhausted without a candidate ready for visual review; progress saved.')
                    request=build_animation_request(url,args.model,state['steps'],start,end,boundary,args.fps,feedback,observed['observations'])
                    if final_review:
                        print('  Using reserved final review for the rendered candidate…',flush=True)
                        request['input'].append({'type':'text','text':'This is the reserved FINAL REVIEW call, not a generation or probe call. Compare the saved candidate renders to the video. Reply {"approved":true} only if ALL completed actions in this clip are covered correctly, including layer selection and motion. Otherwise reply {"approved":false,"reason":"Specific mismatch or uncertainty"}. Do not generate replacement steps or probes in this call. Simulator success alone is insufficient.'})
                    attempt_stem=clip_dir/f'turn-{attempt+1:02d}'
                    save_request(Path(str(attempt_stem)+'.request.json'),request,(feedback or {}).get('images',[]))
                    interaction=client.interactions.create(**request)
                    result=interaction.model_dump(mode='json',exclude_none=True)
                    atomic_json(Path(str(attempt_stem)+'.response.json'),{'response':result,'output_text':interaction.output_text,'elapsed_seconds':monotonic()-begun})
                    if interaction.status!='completed' or not interaction.output_text:raise ValueError('Incomplete response; raw output saved.')
                    candidate=json.loads(interaction.output_text.lstrip('\ufeff'))
                    atomic_json(Path(str(attempt_stem)+'.proposal.json'),candidate)
                    if final_review and candidate.get('approved') is not True:
                        feedback={**feedback,'mode':'engine_error','review_response':candidate,'note':'Final visual review did not approve this candidate. Correct the identified mismatch before proposing it again.'}
                        save_feedback(state,feedback,checkpoint)
                        raise ValueError('Final visual review did not approve the candidate: '+str(candidate.get('reason','Unexpected review response; saved for correction.')))
                    if candidate.get('approved') is False and feedback and feedback.get('mode')=='visual_review':
                        feedback={**feedback,'mode':'engine_error','review_response':candidate,'note':'Independent visual review rejected this proposal. Correct the missing or mismatched observed actions.'}
                        save_feedback(state,feedback,checkpoint)
                        print('  Visual review rejected candidate: '+str(candidate.get('reason','Mismatch')),flush=True)
                        continue
                    if isinstance(candidate.get('compare_motions'),dict):
                        print('  Comparing engine-generated motions…',flush=True)
                        feedback=compare_motions(state['steps'],candidate['compare_motions'].get('after_steps',[]),url,args.model,attempt_stem)
                        save_feedback(state,feedback,checkpoint)
                        print(f"  {len(feedback.get('candidates',[]))} motion candidates rendered; accepted state unchanged.",flush=True)
                        if attempt==7:raise ValueError('Working budget reached; rendered choices saved for continuation.')
                        continue
                    if 'select_motion' in candidate:
                        choice=next((option for option in (feedback or {}).get('candidates',[]) if option['id']==candidate['select_motion']),None)
                        if not choice or feedback.get('mode')!='motion_options':
                            raise ValueError('Select an ID from the current rendered motion choices.')
                        candidate={'steps':choice['steps']}
                    if isinstance(candidate.get('probe_steps'),list):
                        resolved=resolve_steps(state['steps'],candidate['probe_steps'])
                        execution=simulate(state['steps']+resolved['steps']) if resolved['ok'] else resolved
                        atomic_json(Path(str(attempt_stem)+'.execution.json'),execution)
                        feedback={'mode':'probe_result','probe_steps':candidate['probe_steps'],'resolved_steps':resolved.get('steps',resolved.get('resolved_steps')),'engine_feedback':execution,'note':'Temporary operation preview. Accepted state is unchanged; repeat intended steps in final output.'}
                        if execution['ok'] and resolved['steps']:
                            feedback['images']=render(state['steps']+resolved['steps'],url,args.model,len(state['steps']),attempt_stem)
                            print(f'  Operation probe passed: {len(resolved["steps"])} steps; rendered preview ready ({attempt+1}/8 turns used).',flush=True)
                        else:
                            print(f'  Operation probe failed at step {execution.get("failed_step", "unknown")}: {execution.get("error", "No steps proposed")}',flush=True)
                        save_feedback(state,feedback,checkpoint)
                        if attempt==7:raise ValueError('Probe budget reached; progress and feedback saved.')
                        continue
                    if isinstance(candidate.get('probe'),str):
                        execution=simulate(state['steps']+[{'description':'Temporary geometry probe','commands':candidate['probe']}])
                        atomic_json(Path(str(attempt_stem)+'.execution.json'),execution)
                        feedback={'mode':'probe_result','probe_commands':candidate['probe'],'engine_feedback':execution,'note':'Probe was temporary. Repeat necessary constructions in final steps. Accepted state is unchanged.'}
                        if execution['ok'] and re.search(r'(?m)^\s*(?:t|time)\s',candidate['probe']):
                            feedback['resolved_steps']=[{'description':'Temporary motion probe','commands':candidate['probe']}]
                            feedback['images']=render(state['steps']+feedback['resolved_steps'],url,args.model,len(state['steps']),attempt_stem)
                        save_feedback(state,feedback,checkpoint)
                        print(f'  Geometry probe {"passed" if execution["ok"] else "failed: "+execution["error"]} ({attempt+1}/8 turns used).',flush=True)
                        if attempt==7:raise ValueError('Probe budget reached; progress and feedback saved.')
                        continue
                    if candidate.get('approved') is True:
                        if not feedback or feedback.get('mode')!='visual_review':raise ValueError('Approval without simulator preview.')
                        new=feedback['candidate']['steps'];execution=feedback['engine_feedback']
                        state.pop('pending_feedback',None)
                        break
                    new=candidate.get('steps')
                    if not isinstance(new,list) or any(not isinstance(s,dict) for s in new):
                        raise ValueError('Expected a list of steps; raw output saved.')
                    resolved=resolve_steps(state['steps'],new)
                    if not resolved['ok']:
                        feedback={'mode':'engine_error','candidate':candidate,'engine_feedback':resolved}
                        save_feedback(state,feedback,checkpoint)
                        print(f"  Operation / recipe feedback: {resolved['error']}",flush=True)
                        if attempt==7:raise ValueError('Recipe correction budget reached; progress saved.')
                        continue
                    new=resolved['steps'];candidate={'steps':new}
                    execution=simulate(state['steps']+new)
                    atomic_json(Path(str(attempt_stem)+'.execution.json'),execution)
                    if not new and feedback and feedback.get('candidate',{}).get('steps'):
                        raise ValueError('Correction dropped all proposed actions; candidate retained for review.')
                    if execution['ok'] and not new:
                        state.pop('pending_feedback',None);break
                    if execution['ok']:
                        print('  Rendering proposed motion for Gemini to compare with the video…',flush=True)
                        images=render(state['steps']+new,url,args.model,len(state['steps']),attempt_stem)
                        feedback={'mode':'visual_review','candidate':candidate,'engine_feedback':execution,'images':images}
                    else:
                        feedback={'mode':'engine_error','candidate':candidate,'engine_feedback':execution}
                        print(f'  Engine feedback: {execution["error"]}',flush=True)
                    save_feedback(state,feedback,checkpoint)
                    if attempt==7 and not execution['ok']:raise ValueError('Working budget exhausted with simulator errors; all candidates and feedback saved.')
                    print(f'  Sending simulator feedback to Gemini ({attempt+1}/8 turns used).',flush=True)
                state['steps'].extend(new);state['completed_seconds']=end
                state['clips'].append({'start':start,'end':end,'steps':len(new),'usage':result.get('usage',{})})
                atomic_json(checkpoint,state)
                doc=animation_document(url,args.model,state['steps'])
                doc['processed_seconds']=end
                atomic_json(run_dir/'plan.json',doc)
                atomic_json(base,doc)
                base.with_suffix('.txt').write_text(script_for(state['steps']))
                (run_dir/'animation.txt').write_text(script_for(state['steps']))
                publish_preview(doc)
                print(f'  +{len(new)} steps, {execution["animated"]} animated instructions. {monotonic()-begun:.1f}s. '+ ' '.join(execution['warnings']),flush=True)
            except Exception as error:
                parser.exit(1,f'Stopped: {error}\nSaved progress and raw responses remain at {run_dir}\nResume with --resume {checkpoint}\n')
    doc=animation_document(url,args.model,state['steps']);doc['processed_seconds']=state['completed_seconds']
    atomic_json(base,doc)
    base.with_suffix('.txt').write_text(script_for(state['steps']))
    print(f'Done: {base}\nAnimation script: {base.with_suffix(".txt")}',flush=True)


if __name__=='__main__':main()
