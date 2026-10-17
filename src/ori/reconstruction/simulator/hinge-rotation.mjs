import {compileScript} from './script-runtime.mjs';

// Cut the material connectivity at the hinge, then move complete components.
// Components may contain several folded faces: no planar-flap assumption.
export function rotateFlap(script,op){
 if(Object.keys(op).some(k=>!['name','hinge','seed_points','angle_degrees','duration_ms'].includes(k)))throw Error('Unsupported rotate_flap parameter.');
 const before=compileScript(script),model=before.model;
 if(typeof op.hinge!=='string'||!/^s\d+$/.test(op.hinge))throw Error('rotate_flap requires an actual hinge segment ID.');
 const edge=model.segments[Number(op.hinge.slice(1))];
 if(!edge)throw Error('Unknown hinge segment. Inspect the current geometry.');
 const duration=op.duration_ms??1500,angle=op.angle_degrees;
 if(!Number.isFinite(duration)||duration<300||duration>10000)throw Error('duration_ms must be 300..10000.');
 if(!Number.isFinite(angle)||Math.abs(angle)>180||Math.abs(angle)<.01)throw Error('angle_degrees must be a nonzero incremental rotation between -180 and 180.');
 if(!Array.isArray(op.seed_points)||!op.seed_points.length)throw Error('Supply seed_points: one point off the hinge in each intended moving material component.');
 const a=edge.p1,b=edge.p2,u=[b.x-a.x,b.y-a.y,b.z-a.z],length=Math.hypot(...u);
 if(length<1e-6)throw Error('Hinge has zero length.');
 u.forEach((v,i)=>u[i]/=length);
 const onAxis=new Set();
 model.points.forEach((p,i)=>{
  const d=[p.x-a.x,p.y-a.y,p.z-a.z],t=d.reduce((s,v,k)=>s+v*u[k],0);
  if(Math.hypot(...d.map((v,k)=>v-t*u[k]))<.1*model.scale)onAxis.add(i);
 });
 const adjacency=model.points.map(()=>[]);
 for(const segment of model.segments){
  const i=model.points.indexOf(segment.p1),j=model.points.indexOf(segment.p2);
  if(!onAxis.has(i)&&!onAxis.has(j)){adjacency[i].push(j);adjacency[j].push(i);}
 }
 const moving=new Set(),queue=[];
 for(const seed of op.seed_points){
  if(typeof seed!=='string'||!/^p\d+$/.test(seed)||!model.points[Number(seed.slice(1))])throw Error('Unknown seed point. Inspect the current geometry.');
  const i=Number(seed.slice(1));if(onAxis.has(i))throw Error(`${seed} lies on the hinge; choose a point on the intended moving flap.`);
  if(!moving.has(i)){moving.add(i);queue.push(i);}
 }
 for(let k=0;k<queue.length;k++)for(const j of adjacency[queue[k]])if(!moving.has(j)){moving.add(j);queue.push(j);}
 const ids=[...moving].sort((a,b)=>a-b),commands=(model.snap?'snap\n':'')+`t ${duration} r ${op.hinge} ${angle} ${ids.map(i=>'p'+i).join(' ')}`+(model.snap?'\nsnap':'');
 const result=compileScript(script+'\n'+commands);
 const strain=Math.max(0,...result.strainByInstruction.slice(before.command.instructions.length+1));
 if(strain>.03)throw Error(`Selected hinge components stretch by ${(100*strain).toFixed(2)}%; construct the complete hinge or select a different component.`);
 return {commands,selection:{hinge:op.hinge,moving_points:ids.map(i=>'p'+i),max_strain:strain,validation:'Material connectivity and segment strain checked. Layer ordering and collision require visual review.'}};
}
