import {StudioScene} from './scene.mjs';

// A separate renderer keeps library previews from changing the active lesson.
let previewScene, queue=Promise.resolve();
const previews=new Map();
function renderer(){
  if(!previewScene){
    const host=document.createElement('div');
    host.style.cssText='position:fixed;left:-10000px;top:0;width:400px;height:300px;pointer-events:none';
    host.setAttribute('aria-hidden','true');
    const canvas=document.createElement('canvas');host.append(canvas);document.body.append(host);
    previewScene=new StudioScene(canvas);previewScene.resize();previewScene.setContacts(false);
    previewScene.setFoldGuide(false);
  }
  return previewScene;
}
function videoPreview(url){
  return new Promise((resolve,reject)=>{
    const video=document.createElement('video');video.muted=true;video.preload='auto';
    const timeout=setTimeout(()=>finish(new Error('Preview timed out')),15000);
    function finish(error,result){clearTimeout(timeout);video.onloadedmetadata=video.onseeked=video.onerror=null;video.removeAttribute('src');video.load();error?reject(error):resolve(result);}
    video.onerror=()=>finish(new Error('Video unavailable'));
    video.onloadedmetadata=()=>{if(!Number.isFinite(video.duration))return finish(new Error('No final frame'));video.currentTime=Math.max(0,video.duration-.15);};
    video.onseeked=()=>{try{const canvas=document.createElement('canvas');canvas.width=400;canvas.height=300;const ctx=canvas.getContext('2d');const scale=Math.min(400/video.videoWidth,300/video.videoHeight);const w=video.videoWidth*scale,h=video.videoHeight*scale;ctx.drawImage(video,(400-w)/2,(300-h)/2,w,h);finish(null,canvas.toDataURL('image/png'));}catch(error){finish(error);}};
    video.src=url;
  });
}
export function finalStateThumbnail(item){
  if(!['paper','lego','recording'].includes(item.kind))return Promise.resolve(null);
  const key=JSON.stringify([item.replay_url||item.video,item.saved_at]);
  if(!previews.has(key)){
    const task=queue.then(async()=>{
      if(item.kind==='recording')return videoPreview(item.video);
      const response=await fetch(item.replay_url);if(!response.ok)throw Error('Replay unavailable');
      const replay=await response.json(),scene=renderer();
      if(item.kind==='paper')scene.setPaper(replay);else scene.setLego(replay);
      scene.setContacts(false);scene.setFoldGuide(false);
      const count=item.kind==='paper'?replay.states.length:(replay.steps?.length||replay.pieces.length);
      scene.setTime(count*(replay.seconds_per_step||2.6));
      return scene.canvas.toDataURL('image/png');
    });
    queue=task.catch(()=>{});previews.set(key,task.catch(()=>item.thumbnail||null));
  }
  return previews.get(key);
}
