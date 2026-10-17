import {pausablePlayback} from './playback-clock.mjs';
import {rendererFor} from './renderer-routing.mjs';
import {compileScript} from './script-runtime.mjs';
import {PaperView as View3d} from './paper-view.mjs';
import {layerHistory,motionHinges} from './paper-layers.mjs';
import {View2d} from './vendor/orisim3d/js/View2d.js';
const $=id=>document.getElementById(id);
let model,command,view,flat,currentScript='',lastCursor=-1,stepEnds=[],layerOrders=[],hinges=new Map(),entries=[];
function redraw(){
 view.layerOrders=layerOrders[command.cursor];
 if(!hinges.has(command.cursor))hinges.set(command.cursor,motionHinges(model,command.paths[command.cursor]));
 view.activeHinges=hinges.get(command.cursor);
 view.initBuffers();view.initModelView();view.render();if(document.querySelector('details').open){flat.fit();flat.drawModel();}
 $('layer-status').textContent=view.layerAmbiguities?'Layer order is approximate in this view.':'';
}
document.querySelector('details').addEventListener('toggle',()=>{if(flat){flat.fit();flat.drawModel();}});
function load(data,label){
 const renderer=rendererFor(data),legacy=$('geometry-player');
 command?.pause();
 if(renderer==='fold'){
  document.querySelector('.view-tools').hidden=true;
  legacy.hidden=false;document.querySelector('.player').hidden=true;
  document.querySelector('details').hidden=true;$('download').hidden=true;
  $('provenance').textContent=label;
  return new Promise((resolve,reject)=>{
   legacy.onload=async()=>{try{await legacy.contentWindow.oriGeometryReady;legacy.contentWindow.oriLoadGeometry(data);resolve();}catch(e){$('provenance').textContent=e.message;reject(e);}};
   legacy.src='geometry.html?embedded=1';
  });
 }
 legacy.hidden=true;legacy.removeAttribute('src');document.querySelector('.player').hidden=false;
 document.querySelector('.view-tools').hidden=false;
 document.querySelector('details').hidden=false;$('download').hidden=false;
 const steps=typeof data==='object'?data.steps:null;
 const script=typeof data==='string'?data:'define 200 200\niad\n'+steps.map(s=>`// ${s.description}\n${s.commands}`).join('\n');
 const result=compileScript(script);
 layerOrders=layerHistory(result.command);hinges=new Map();
 if(!view){model=result.model;view=new View3d(model,$('canvas3d'));flat=new View2d(model,$('canvas2d'));view.gl.deleteTexture(view.texPlaceholderFront);view.gl.deleteTexture(view.texPlaceholderBack);view.texPlaceholderFront=view.createTexture([223,161,166,255]);view.texPlaceholderBack=view.createTexture([255,240,211,255]);}
 else Object.assign(model,result.model);
 command=pausablePlayback(result.command);command.model=model;currentScript=script;lastCursor=-1;
 $('script').textContent=script;$('provenance').textContent=label+(data.processed_seconds?` · first ${data.processed_seconds}s of video`:'');$('warning').textContent=result.warnings.join(' ');
 entries=steps||command.instructions.map(commands=>({description:commands,commands}));
 stepEnds=[];
 if(steps){let cursor=2;for(const step of steps){let remaining=command.tokenize(step.commands).filter(t=>t!=='\n').length;while(remaining>0&&cursor<command.instructions.length){remaining-=command.tokenize(command.instructions[cursor++]).filter(t=>t!=='\n').length;}stepEnds.push(cursor);}}
 else stepEnds=command.instructions.map((_,i)=>i+1);
 $('timeline').min=0;$('timeline').max=stepEnds.length;$('timeline').value=0;
 $('steps').replaceChildren(...entries.map((s,i)=>{const li=document.createElement('li'),b=document.createElement('button');b.textContent=s.description;b.onclick=()=>{command.goTo(i?stepEnds[i-1]:command.first);command.play();};li.append(b);return li;}));
 const candidate=data?.source==='engine_candidate',test=data?.source==='mechanism_test';
 $('title').textContent=candidate?'Motion candidate':test?'Mechanism test':steps?'Video instructions':'Engine reference sequence';
 $('status').textContent=candidate?'Candidate preview; not accepted into the extraction.':test?'Reference mechanism test; not extracted from the video.':steps?`${steps.length} extracted steps. Press Play.`:'Reference script supplied with OriSim3D; not extracted from your video.';
 let radius=Math.max(1,...model.points.map(p=>Math.hypot(p.x,p.y,p.z)));
 for(const path of command.paths)if(path)for(const frame of path.frames)for(let i=0;i<frame.coords.length;i+=3)radius=Math.max(radius,Math.hypot(...frame.coords.slice(i,i+3)));
 command.goTo(command.first);view.angleX=-18;view.angleY=15;view.angleZ=0;view.scale=Math.min(.8,200/radius);redraw();
 window.oriPlayback={get command(){return command;},get model(){return model;},get view(){return view;},get stepEnds(){return stepEnds;},load};
}
async function fetchLoad(url,label){const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw Error('No native animation extraction saved yet.');const text=await r.text();await load(text.trim().startsWith('{')||text.trim().startsWith('[')?JSON.parse(text):text,label);}
$('latest').onclick=()=>fetchLoad('latest-animation.json','Gemini extraction · native OriSim3D commands').catch(e=>$('status').textContent=e.message);
$('file').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>150000)throw Error('Please use a file smaller than 150 KB.');const text=await f.text();await load(text.trim().startsWith('{')||text.trim().startsWith('[')?JSON.parse(text):text,`Imported: ${f.name}`);}catch(error){$('status').textContent=error.message;}finally{e.target.value='';}};
$('play').onclick=()=>command&&(command.playing?command.pause():command.play());
$('reset').onclick=()=>{command?.goTo(command.first);};
$('timeline').oninput=e=>{const step=+e.target.value;command?.goTo(step?stepEnds[step-1]:command.first);};
$('show-creases').onchange=e=>{if(view){view.showCreases=e.target.checked;redraw();}};
$('separate-layers').onchange=e=>{if(view){view.separateLayers=e.target.checked;$('layer-note').hidden=!e.target.checked;redraw();}};
for(const [id,x,y] of [['view-front',0,0],['view-back',0,180],['view-3d',-25,30]])$(id).onclick=()=>{if(view){view.angleX=x;view.angleY=y;view.angleZ=0;view.initModelView();}};
$('download').onclick=()=>{const u=URL.createObjectURL(new Blob([currentScript],{type:'text/plain'}));const a=document.createElement('a');a.href=u;a.download='ori-folding.txt';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};
let drag;
$('canvas3d').onpointerdown=e=>{drag=[e.clientX,e.clientY];e.target.setPointerCapture(e.pointerId);};
$('canvas3d').onpointermove=e=>{if(!drag||!view)return;view.angleY+=(e.clientX-drag[0])*.4;view.angleX+=(e.clientY-drag[1])*.4;drag=[e.clientX,e.clientY];view.initModelView();};
$('canvas3d').onpointerup=()=>drag=null;$('canvas3d').onpointercancel=()=>drag=null;
$('canvas3d').addEventListener('wheel',e=>{e.preventDefault();if(view){view.scale=Math.min(3,Math.max(.2,view.scale*Math.exp(-e.deltaY*.001)));view.initModelView();}},{passive:false});
function tick(){try{if(command){if(command.anim())redraw();else view.render();$('play').textContent=command.playing?'Pause':'Play';
 const idx=stepEnds.findIndex(n=>n>=command.cursor),step=command.cursor===command.first?0:idx+1;
 $('timeline').min=0;$('timeline').max=stepEnds.length;$('timeline').value=step;$('position').textContent=`${step} / ${stepEnds.length} steps`;
 $('current-action').textContent=step?entries[idx]?.description:'Ready to fold';
 if(lastCursor!==command.cursor){
  [...$('steps').children].forEach((el,i)=>el.classList.toggle('active',step>0&&i===idx));
  const selected=step>0?$('steps').children[idx]:null,aside=document.querySelector('aside');
  if(selected){const row=selected.getBoundingClientRect(),panel=aside.getBoundingClientRect();if(row.top<panel.top||row.bottom>panel.bottom)aside.scrollTop+=row.top-panel.top-(panel.height-row.height)/2;}
  lastCursor=command.cursor;
 }}}catch(e){command?.pause();$('status').textContent=e.message;}requestAnimationFrame(tick);}
try{await fetchLoad('latest-animation.json','Gemini extraction · native OriSim3D commands');}catch(e){$('provenance').textContent='No animation loaded.';$('status').textContent=e.message;}requestAnimationFrame(tick);
