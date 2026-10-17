import {planStages,validateFold,foldStages} from './fold-model.mjs';
const $=id=>document.getElementById(id),frame=$('solver');
let api,template,stages=[],selected=0,active=null,animation=null;
const ready=new Promise((resolve,reject)=>{
  function check(){if(frame.contentWindow?.foldSolver){api=frame.contentWindow.foldSolver;resolve();}}
  window.addEventListener('message',event=>{if(event.origin!==location.origin||event.source!==frame.contentWindow)return;if(event.data.type==='ori-fold-ready')check();if(event.data.type==='ori-fold-error')reject(Error(event.data.message));});
  frame.addEventListener('load',check);check();
});
function percent(value){value=Math.min(.98,value);api.setProgress(value);$('progress').value=value*100;$('amount').textContent=`${Math.round(value*100)}%`;}
function stop(){animation=null;$('play').textContent='Animate';}
function pattern(fold){
  $('pattern').replaceChildren();
  const coords=fold['vertices_ori:uv']||fold.vertices_coords,min=coords.reduce((a,p)=>a.map((v,i)=>Math.min(v,p[i])),[Infinity,Infinity]),max=coords.reduce((a,p)=>a.map((v,i)=>Math.max(v,p[i])),[-Infinity,-Infinity]);
  const size=Math.max(max[0]-min[0],max[1]-min[1])||1;
  fold.edges_vertices.forEach(([a,b],i)=>{const line=document.createElementNS('http://www.w3.org/2000/svg','line');const p=coords[a],q=coords[b];for(const [key,value] of Object.entries({x1:(p[0]-min[0])/size,y1:1-(p[1]-min[1])/size,x2:(q[0]-min[0])/size,y2:1-(q[1]-min[1])/size,stroke:{M:'#b94a48',V:'#347fa3',F:'#a0a6a0',B:'#2b4038',U:'#aaa'}[fold.edges_assignment[i]],'stroke-width':.008}))line.setAttribute(key,value);if(fold.edges_assignment[i]==='F')line.setAttribute('stroke-dasharray','.025 .025');$('pattern').append(line);});
  $('mesh-count').textContent=`${coords.length} VERTICES · ${fold.faces_vertices.length} FACES`;
}
function choose(index){
  stop();selected=index;const stage=stages[index];
  [...$('steps').children].forEach((el,i)=>el.classList.toggle('selected',index===i));
  $('title').textContent=stage.template?'Square-base collapse':stage.kind||'FOLD pattern';$('description').textContent=stage.description;$('source').textContent=stage.note;
  $('warning').textContent=[stage.fold?'':'No geometry for this state; the viewer retains the last supported mesh.',...(Array.isArray(stage.uncertainties)?stage.uncertainties:[])].filter(Boolean).join(' ');
  $('play').disabled=!stage.fold||stage.state;$('progress').disabled=!stage.fold||stage.state;$('export').disabled=!stage.fold;
  if(!stage.fold)return;
  active=validateFold(stage.fold);api.load(active,stage.state);if(!stage.state)percent(stage.from||0);else $('amount').textContent='State';pattern(active);
  $('mode').textContent=stage.state?'FOLD STATE · FILE GEOMETRY':stage.template?'TEMPLATE GEOMETRY · GPU SOLVER':'FOLD GEOMETRY · GPU SOLVER';
  $('status').textContent=`Loaded ${active.file_title||'FOLD pattern'}. ${stage.template?'Template selected from the instruction description; verify its orientation against the video.':stage.state?'Displaying supplied coordinates. No simulated motion between states.':'Use Animate or the fold-amount slider.'}`;
}
function show(newStages){stages=newStages;$('steps').replaceChildren();$('count').textContent=`${stages.length} ACTIONS`;stages.forEach((stage,i)=>{const b=document.createElement('button');b.className='op'+(stage.fold?'':' muted');b.textContent=`${i+1}. ${stage.description}${stage.fold?'':' · unsupported'}`;b.onclick=()=>choose(i);$('steps').append(b);});choose(Math.max(0,stages.findIndex(s=>s.template)));}
function showTemplate(){show([{kind:'collapse',description:'Collapse the precreased square into a square base.',fold:template,from:0,to:1,template:true,note:'Adapted from Origami Simulator’s squareBase.svg. Four mountain and two valley segments move together; the other diagonal stays flat.'}]);}
async function loadPlan(url){try{const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw Error('Could not load saved instructions.');const data=await response.json();show(Array.isArray(data)?planStages(data,template):foldStages(data));}catch(e){$('status').textContent=e.message;}}
$('latest').onclick=()=>loadPlan('./latest-plan.json');
$('template').onclick=()=>showTemplate();
$('file').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>2_000_000)throw Error('Please select a file smaller than 2 MB.');const data=JSON.parse(await file.text());if(Array.isArray(data)){if(!data.length)throw Error('The action list is empty.');show(Array.isArray(data)?planStages(data,template):foldStages(data));}else{show(foldStages(data));}}catch(error){$('status').textContent=error.message;}finally{e.target.value='';}};
$('progress').oninput=e=>{stop();percent(+e.target.value/100);};
$('reset').onclick=()=>{if(!api||!active)return;stop();if(stages[selected]?.state){api.load(active,true);return;}api.reset();percent(0);};
$('play').onclick=()=>{if(animation){stop();return;}const stage=stages[selected];const from=stage.from||0,to=stage.to??1;api.reset();percent(from);animation={start:performance.now()+400,from,to};$('play').textContent='Pause';};
$('export').onclick=()=>{if(!active)return;const blob=new Blob([JSON.stringify(active,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=active.ori_template?`${active.ori_template}.fold`:'ori-pattern.fold';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
function tick(now){if(animation){const t=Math.max(0,Math.min(1,(now-animation.start)/4500));percent(animation.from+(animation.to-animation.from)*(t*t*(3-2*t)));if(t===1)stop();}if(api){const snapshot=api.snapshot();$('solver-warning').textContent=snapshot.error||(!snapshot.finite?'Solver became unstable. Reset to the flat pattern.':'');}requestAnimationFrame(tick);}
const embedded=new URLSearchParams(location.search).has('embedded');
if(embedded){const style=document.createElement('style');style.textContent='header,.toolbar,.input-panel{display:none!important}';document.head.append(style);}
window.oriGeometryReady=(async()=>{try{template=validateFold(await (await fetch('./templates/square-base.fold')).json());await ready;window.oriLoadGeometry=data=>show(Array.isArray(data)?planStages(data,template):foldStages(data));if(!embedded){showTemplate();await loadPlan('./latest-plan.json');}requestAnimationFrame(tick);}catch(e){$('status').textContent=`Could not start solver: ${e.message}`;}})();
