"""Opt-in Gemini evaluation: uploads synthetic cameras and saved harness references.
Run: PYTHONPATH=src .venv/bin/python tests/manual/fold_verification_benchmark.py
Requires GEMINI_API_KEY. Never accesses the webcam. Normal test discovery does not run this.
"""
import asyncio,io,json,time,random,os,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from google import genai
from ori.config import load_settings
from ori.coaching.server import library,paper_source,replay,read_json
from ori.coaching.gemini_coach import snapshot_check,reference_images

def camera(pixels,busy=False,fingers=False):
 im=Image.open(io.BytesIO(pixels)).convert('RGB');rgb=np.asarray(im).astype(float)
 mask=(rgb[:,:,0]>rgb[:,:,1]*1.12)&(rgb[:,:,1]>rgb[:,:,2]*1.12)
 mask[:60]=False  # Remove all simulation captions from the synthetic camera.
 out=Image.new('RGB',im.size,(68,89,79));d=ImageDraw.Draw(out)
 if busy:
  rng=random.Random(23)
  for _ in range(70):
   x=rng.randrange(im.width);y=rng.randrange(im.height)
   d.rectangle((x,y,x+rng.randrange(15,180),y+rng.randrange(10,90)),fill=rng.choice(['#344758','#a88361','#c5b09d','#778c76','#dedbd5','#3b3431']))
  for y in range(150,im.height,85):d.line((0,y,im.width,y-35),fill='#494e50',width=7)
 bg=np.array(out);shade=np.where(rgb[:,:,1]<130,235,212);shade=np.where(rgb[:,:,0]<180,135,shade)
 for c,offset in enumerate([0,3,9]):bg[:,:,c][mask]=(shade-offset)[mask].astype('uint8')
 out=Image.fromarray(bg)
 if fingers:
  ys,xs=np.where(mask);x=int(np.quantile(xs,.12));y=int(np.quantile(ys,.75));d=ImageDraw.Draw(out)
  d.rounded_rectangle((x-30,y-65,x+25,y+130),radius=24,fill='#be896b',outline='#976448',width=3)
  d.rounded_rectangle((x+12,y+18,x+68,y+160),radius=24,fill='#cf9a78',outline='#976448',width=3)
 out.thumbnail((640,480));return out

def jpg(im):
 b=io.BytesIO();im.save(b,format='JPEG');return b.getvalue()

async def main():
 item=next(i for i in library() if i['kind']=='paper');base=paper_source(item['id'])[0];p=replay(base)
 c=read_json(base/'commands.json');commands=c.get('commands',[]) if isinstance(c,dict) else c
 print('MODEL',os.getenv('ORI_STEP_CHECK_MODEL','gemini-3.5-flash'),'ACTIONS',json.dumps([c.get('name') for c in commands[:2]]),flush=True)
 stage=len(p['states'])-1;refs={i:list(reference_images(p,i)) for i in range(stage+1)}
 pixels={i:next(pix for label,pix in refs[i] if label=='TARGET front') for i in refs}
 for i in range(1,stage+1):
  if i>1:refs[i].insert(0,('UNFOLDED flat sheet',pixels[0]))
 wrong=Image.new('RGB',Image.open(io.BytesIO(pixels[0])).size,'white');d=ImageDraw.Draw(wrong);d.polygon([(190,470),(360,170),(530,470)],fill='#ed9e43',outline='#8b5524',width=4);b=io.BytesIO();wrong.save(b,format='PNG');pixels[-1]=b.getvalue()
 skew=Image.new('RGB',Image.open(io.BytesIO(pixels[0])).size,'white');ImageDraw.Draw(skew).polygon([(230,180),(510,100),(560,430),(150,500)],fill='#ed9e43',outline='#8b5524',width=4);b=io.BytesIO();skew.save(b,format='PNG');pixels[-2]=b.getvalue()
 cases=[('SKEWED_FLAT_SHEET',1,-2,True,True,False),('WRONG_TRIANGLE',1,-1,True,True,False),('PLAIN_FLAT',1,0,False,False,False),('BUSY_FLAT_FINGERS',1,0,True,True,False),('BUSY_TARGET_1',1,1,True,True,True)]
 cases += [('ROTATED_FLAT',1,0,True,True,False),('ROTATED_TARGET_1',1,1,True,True,True)]
 for i in range(2,stage+1):
  cases += [(f'BUSY_FLAT_AT_FOLD_{i}',i,0,True,True,False),(f'BUSY_PREVIOUS_FOLD_{i}',i,i-1,True,True,False),(f'BUSY_TARGET_{i}',i,i,True,i<3,True)]
 client=genai.Client(api_key=load_settings().gemini_api_key);sem=asyncio.Semaphore(3);results=[]
 async def check(case):
  label,step,state,busy,fingers,expected=case;image=camera(pixels[state],busy,fingers)
  if label.startswith('ROTATED'):image=image.rotate(23,resample=Image.Resampling.BICUBIC,fillcolor='#344758')
  image.save('/private/tmp/ori-eval-'+label+'.png')
  async with sem:
   start=time.monotonic()
   try:
    result=await snapshot_check(client,p,commands,step,jpg(image),refs[step]);row=dict(case=label,seconds=round(time.monotonic()-start,2),expected_match=expected,correct=(result['verdict']=='match')==expected,result=result)
   except Exception as e:row=dict(case=label,error=type(e).__name__+': '+str(e)[:200])
   results.append(row);print(json.dumps(row),flush=True)
 try:await asyncio.gather(*(check(case) for case in cases))
 finally:await client.aio.aclose()
 false_approvals=sum(r.get('expected_match') is False and r.get('result',{}).get('verdict')=='match' for r in results)
 false_rejections=sum(r.get('expected_match') is True and r.get('result',{}).get('verdict')!='match' for r in results)
 print('SUMMARY',sum(r.get('correct',False) for r in results),'/',len(results),'FALSE_APPROVALS',false_approvals,'FALSE_REJECTIONS',false_rejections,flush=True)
 report=Path('output/verification-eval');report.mkdir(parents=True,exist_ok=True)
 (report/'latest.json').write_text(json.dumps(dict(model=os.getenv('ORI_STEP_CHECK_MODEL','gemini-3.5-flash'),run_id=item['id'],false_approvals=false_approvals,false_rejections=false_rejections,results=results),indent=2))
 return all(r.get('correct',False) for r in results)
if __name__=='__main__':sys.exit(0 if asyncio.run(main()) else 1)
