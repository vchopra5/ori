"""Opt-in real API comparison; isolated outputs, identical video/task/call budget.
Run each level in a separate process to preserve individual logs and timings.
"""
import argparse,json,time
from pathlib import Path
from google import genai
from google.genai import types
from ori.config import load_settings
from ori.coaching.jobs import Progress,run_paper
from ori.reconstruction.fold_commands import FoldHarness
from ori.reconstruction.fold_render import render
from ori.reconstruction.batching import atomic_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level',choices=['medium','high'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-calls',type=int,default=12)
    parser.add_argument('--timeout-seconds',type=int,default=600)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    url='https://www.youtube.com/watch?v=10KurnMH_6o'
    route=dict(kind='origami',title='origami fox face',summary='A square red sheet of paper is folded into a fox face and decorated with a black marker.')
    progress=Progress(args.output,url);progress.data['route']=route
    started=time.monotonic()
    with genai.Client(api_key=load_settings().gemini_api_key,http_options=types.HttpOptions(timeout=args.timeout_seconds*1000,retry_options=types.HttpRetryOptions(attempts=1))) as client:
        report=run_paper(client,url,args.output,progress,route,max_calls=args.max_calls,thinking_level=args.level)
    wall=time.monotonic()-started
    h=FoldHarness();h.execute(progress.data['commands'])
    render(h.panels,f'{args.level.upper()} final').save(args.output/'final.png')
    render(h.panels,f'{args.level.upper()} final',True).save(args.output/'final-oblique.png')
    rows=[]
    for folder in sorted((args.output/'debug').glob('call-*')):
        request=folder/'direct-api-request.json';response=folder/'response.json';feedback=folder/'harness-feedback.json'
        if not response.exists():continue
        r=json.loads(response.read_text());f=json.loads(feedback.read_text()) if feedback.exists() else {}
        rows.append(dict(call=folder.name,api_seconds=response.stat().st_mtime-request.stat().st_mtime,
            usage=r.get('usage_metadata',{}),finish_reasons=[c.get('finish_reason') for c in r.get('candidates',[])],
            ok=f.get('ok'),error=f.get('error'),undo=f.get('undo_count',0),accepted=len(f.get('accepted_commands',[]))))
    summary=dict(level=args.level,timeout_seconds=args.timeout_seconds,wall_seconds=wall,report=report,calls=rows)
    atomic_json(args.output/'benchmark.json',summary)
    print('BENCHMARK',json.dumps(dict(level=args.level,seconds=round(wall,1),status=report['status'],accepted=report['accepted_folds'])),flush=True)

if __name__=='__main__':main()
