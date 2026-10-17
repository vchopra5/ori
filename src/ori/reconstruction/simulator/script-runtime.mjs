// Execute OriSim3D's native language. Geometry and animation belong to the vendor.
import {Model,State} from './vendor/orisim3d/js/Model.js';
import {Command} from './vendor/orisim3d/js/Command.js';
const allowed=new Set('d define t time by by3d by2d c3d across3d c2d across2d p2d perpendicular2d p3d perpendicular3d parallel2d parallel3d bisector2d b2d bisector3d b3d bisector2dPoints bisector3dPoints split splitSegment2d r rotate m move mop moveOnPoint mos moveOnSegment a adjust check o offset order mountain mv valley tx ty tz z zoom fit labels textures lines snap il iad sp ss sf selectPoints selectSegments selectFaces ib io ia iao iso isb igb'.split(' '));
// Compilation uses fixed integration times; playback uses the recorded paths.
// Wall-clock sampling made repeated geometry probes produce different positions.
function sampleAnimation(command, frame) {
 const begin=command.iToken,tn=Math.min(1,frame/60);
 if(frame===1){command.freezeRotateAxes(begin);command.path={duration:command.duration,frames:[{tn:0,coords:command.model.snapshotPositions()}]};}
 const target=command.interpolator(tn),start=command.tpi;
 const count=Math.max(1,Math.ceil(Math.abs(target-start)/.005));
 for(let i=1;i<=count;i++){
  command.tni=start+(target-start)*i/count;command.iToken=begin;
  while(command.iToken<command.tokenTodo.length&&command.peek()!=='\n')command.execute(command.iToken);
  command.tpi=command.tni;
 }
 command.path.frames.push({tn,coords:command.model.snapshotPositions()});
 if(tn===1){
  if(command.model.snap)command.model.snapPoints();
  command.path.frames.at(-1).coords=command.model.snapshotPositions();
  command.record(command.idxBefore,command.iToken,command.path);
  command.path=null;command.tpi=0;command.tni=1;command.frozenAxes.clear();command.model.state=State.run;
 }else command.iToken=begin;
}
export function compileScript(script){
  if(typeof script!=='string'||script.length>150000)throw Error('Expected an OriSim3D script under 150 KB.');
  const model=new Model().init(),command=new Command(model);
  const tokens=command.tokenize(script);
  if(!['d','define'].includes(tokens[0]))throw Error('Script must start with define.');
  for(const token of tokens)if(token!=='\n'&&!allowed.has(token)&&!/^([psf]\d+|-?\d+(\.\d+)?([eE][+-]?\d+)?)$/.test(token))throw Error(`Unsupported command or token: ${token}`);
  command.skipUnexpected=function(){throw Error(`Unexpected token near ${this.tokenTodo.slice(this.iToken-1,this.iToken+3).join(' ')}`);};
  command.command(script);
  command.commandArea={addLine(line){if(line.startsWith('//')&&!line.startsWith('// Fit:'))throw Error(line.slice(3));}};
  const warnings=[],strainByInstruction=[];let count=0,frames=0,maxStrain=0;
  while(command.busy){
    if(++count>100000||model.points.length>2000)throw Error('Script exceeds execution limits.');
    try{if(model.state===State.anim)sampleAnimation(command,++frames);else{frames=0;command.anim();}}catch(error){error.message=`Instruction ${command.instructions.length+1}: ${error.message}`;error.state=registry(model);throw error;}
    if(model.points.some(p=>![p.x,p.y,p.z,p.xf,p.yf].every(Number.isFinite)))throw Error('Script produced non-finite coordinates.');
    let strain=0;
    for(const s of model.segments){const a=s.p1,b=s.p2,l=Math.hypot(a.xf-b.xf,a.yf-b.yf)*model.scale;if(l>1e-6)strain=Math.max(strain,Math.abs(Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z)/l-1));}
    maxStrain=Math.max(maxStrain,strain);
    const instruction=command.cursor+(model.state===State.anim?1:0);
    strainByInstruction[instruction]=Math.max(strainByInstruction[instruction]||0,strain);
  }
  const empty=command.paths.map((path,i)=>({path,i})).filter(({path})=>path&&path.frames.every(f=>f.coords.every((v,j)=>Math.abs(v-path.frames[0].coords[j])<1e-5)));
  if(empty.length){const error=Error(`Timed instructions ${empty.map(x=>x.i).join(', ')} produce no motion. Check the axis ID and moving vertices; rotation angles are incremental deltas.`);error.state=registry(model);error.constructionStates=command.instructions.flatMap((line,i)=>/^(by|c2d|c3d|b2d|b3d|bisector|split|perpendicular)/.test(line)?[{instruction:line,state:registry(Model.deserialize(command.snapshots[i+1]))}]:[]);throw error;};
  if(maxStrain>.1){const error=Error(`Paper stretches by ${(maxStrain*100).toFixed(1)}% during the proposed motion. List ALL moving vertices on the intended layers; keep hinge vertices fixed and use adjust for coordinated collapses.`);error.state=registry(model);error.constructionStates=command.instructions.flatMap((line,i)=>/^(by|c2d|c3d|b2d|b3d|bisector|split|perpendicular)/.test(line)?[{instruction:line,state:registry(Model.deserialize(command.snapshots[i+1]))}]:[]);throw error;}
  if(maxStrain>.03)warnings.push(`Maximum segment length deviation during playback: ${(100*maxStrain).toFixed(1)}%.`);
  return {model,command,warnings,maxStrain,strainByInstruction};
}
export function registry(model){
  const index=p=>model.points.indexOf(p),round=n=>Math.round(n*10000)/10000;
  return {points:model.points.map((p,i)=>({id:`p${i}`,material:[p.xf,p.yf].map(round),position:[p.x,p.y,p.z].map(round)})),segments:model.segments.map((s,i)=>({id:`s${i}`,points:[index(s.p1),index(s.p2)]})),faces:model.faces.map((f,i)=>({id:`f${i}`,points:f.points.map(index),edges:f.points.map((p,j)=>{const q=f.points[(j+1)%f.points.length];const k=model.segments.findIndex(s=>(s.p1===p&&s.p2===q)||(s.p1===q&&s.p2===p));return k<0?null:`s${k}`;})}))};
}
