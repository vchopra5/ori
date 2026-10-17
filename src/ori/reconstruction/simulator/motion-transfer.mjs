// Transfer a sampled mechanism onto subdivisions of the same material regions.
// The engine supplies the reference motion; the model never supplies pose arrays.
import {compileScript} from './script-runtime.mjs';
import {Model} from './vendor/orisim3d/js/Model.js';
const xyz=p=>[p.x,p.y,p.z],uv=p=>[p.xf,p.yf];
const sub=(a,b)=>a.map((v,i)=>v-b[i]),dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const norm=a=>Math.hypot(...a),unit=a=>a.map(v=>v/norm(a));
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const number=x=>String(Number(x.toFixed(9)));

function triangles(model,faces=model.faces){
 return faces.flatMap(face=>{
  const ids=face.points.map(p=>model.points.indexOf(p)),result=[];
  for(let i=1;i<ids.length-1;i++)result.push([ids[0],ids[i],ids[i+1]]);
  return result;
 });
}
function weights(p,tri,model){
 const [a,b,c]=tri.map(i=>uv(model.points[i]));
 const v=sub(b,a),w=sub(c,a),q=sub(p,a),det=v[0]*w[1]-v[1]*w[0];
 if(Math.abs(det)<1e-7)return null;
 const y=(q[0]*w[1]-q[1]*w[0])/det,z=(v[0]*q[1]-v[1]*q[0])/det,x=1-y-z;
 return Math.min(x,y,z)>=-1e-5?[x,y,z]:null;
}
function binding(p,mesh,tris){
 for(const tri of tris){const w=weights(p,tri,mesh);if(w)return {tri,w};}
 return null;
}
function interpolate(bind,coords){return [0,1,2].map(axis=>bind.tri.reduce((s,id,i)=>s+bind.w[i]*coords[id*3+axis],0));}
function materialPosition(model,p){
 const bind=binding(p,model,triangles(model));
 if(!bind)throw Error('Mechanism material region is outside the current sheet.');
 return interpolate(bind,model.snapshotPositions());
}
function rigidAlignment(source,target,scale){
 let a=0,b=1,c=2,best=-1;
 for(let i=0;i<source.length;i++)for(let j=i+1;j<source.length;j++){
  const distance=norm(sub(source[i],source[j]));if(distance>best){best=distance;a=i;b=j;}
 }
 best=-1;
 for(let i=0;i<source.length;i++){
  const area=norm(cross(sub(source[b],source[a]),sub(source[i],source[a])));
  if(area>best){best=area;c=i;}
 }
 if(best<1e-4)throw Error('Mechanism anchors are degenerate.');
 function basis(points){const x=unit(sub(points[b],points[a])),z=unit(cross(x,sub(points[c],points[a])));return [x,cross(z,x),z];}
 const from=basis(source),to=basis(target);
 const apply=p=>{const d=sub(p,source[a]);return target[a].map((v,k)=>v+scale*from.reduce((s,axis,j)=>s+dot(d,axis)*to[j][k],0));};
 if(source.some((p,i)=>norm(sub(apply(p),target[i]))>1*scale))throw Error('Affected flap is not in the mechanism starting pose. Unfold its preparatory folds first, or backtrack.');
 return apply;
}

// Add only reference segments that bound moving material regions. Native split
// operations retain the original vertices, extra creases, and adjacent faces.
function overlay(model,reference,faces,mapUV){
 const commands=[],edges=new Set();
 for(const face of faces)for(let i=0;i<face.points.length;i++){
  const a=reference.points.indexOf(face.points[i]),b=reference.points.indexOf(face.points[(i+1)%face.points.length]);
  edges.add([Math.min(a,b),Math.max(a,b)].join(','));
 }
 function ensurePoint(p){
  let id=model.points.findIndex(q=>norm(sub(uv(q),p))<.02);
  if(id>=0)return id;
  for(let i=0;i<model.segments.length;i++){
   const edge=model.segments[i],a=uv(edge.p1),d=sub(uv(edge.p2),a),q=sub(p,a),len=dot(d,d),t=dot(q,d)/len;
   if(t>1e-7&&t<1-1e-7&&norm(sub(q,d.map(v=>v*t)))<.02){
    const ratio=Number(number(t));commands.push(`split s${i} ${ratio}`);model.splitSegmentByRatio2d(edge,ratio);
    return model.points.findIndex(q=>norm(sub(uv(q),p))<.03);
   }
  }
  return -1;
 }
 let pending=[...edges].map(e=>e.split(',').map(Number));
 for(let round=0;pending.length&&round<reference.points.length;round++){
  const next=[];let progress=false;
  for(const [a,b]of pending){
   const i=ensurePoint(mapUV(uv(reference.points[a]))),j=ensurePoint(mapUV(uv(reference.points[b])));
   if(i<0||j<0){next.push([a,b]);continue;}
   const before=model.faces.length;
   model.splitBy2d(model.points[i],model.points[j]);
   if(model.faces.length!==before)commands.push(`by2d p${i} p${j}`);
   progress=true;
  }
  pending=next;if(!progress)break;
 }
 if(pending.length)throw Error('Could not construct mechanism creases on this material patch.');
 return commands;
}

export function transferMotion(script,referenceScript,{duration=2000,rotation=0}={}){
 const reference=compileScript(referenceScript),indices=reference.command.paths.flatMap((p,i)=>p?[i]:[]),last=indices.at(-1);
 const path=reference.command.paths[last],start=Model.deserialize(reference.command.snapshots[last-1]);
 const active=new Set(start.points.flatMap((_,i)=>path.frames.some(f=>norm(sub(f.coords.slice(i*3,i*3+3),path.frames[0].coords.slice(i*3,i*3+3)))>.03)?[i]:[]));
 const faces=start.faces.filter(face=>face.points.some(p=>active.has(start.points.indexOf(p))));
 const patchTriangles=triangles(start,faces),support=[...new Set(patchTriangles.flat())];
 const radians=rotation*Math.PI/180;
 const rotate=(p,r)=>[p[0]*Math.cos(r)-p[1]*Math.sin(r),p[0]*Math.sin(r)+p[1]*Math.cos(r)];
 const mapUV=p=>rotate(p,radians),unmapUV=p=>rotate(p,-radians);
 const prior=compileScript(script),current=prior.model,scale=current.scale/start.scale;
 const fit=rigidAlignment(support.map(i=>xyz(start.points[i])),support.map(i=>materialPosition(current,mapUV(uv(start.points[i])))),scale);
 const commands=overlay(current,start,faces,mapUV);
 const prepared=compileScript(script+'\n'+commands.join('\n')).model;
 if(prepared.points.length!==current.points.length)throw Error('Mechanism crease construction was not reproducible.');
 const bindings=prepared.points.map(p=>binding(unmapUV(uv(p)),start,patchTriangles));
 const initial=prepared.snapshotPositions();
 for(let i=0;i<bindings.length;i++)if(bindings[i]&&norm(sub(fit(interpolate(bindings[i],path.frames[0].coords)),initial.slice(i*3,i*3+3)))>1*scale)
  throw Error('An extra crease changes the flap pose; the selected mechanism cannot be applied.');
 // Bake twenty short intervals into ordinary engine move commands. Subdivision
 // points use barycentric coordinates on the reference surface throughout.
 let previous=initial.slice(),tn=0;
 if(prepared.snap)commands.push('snap');
 commands.push('il');
 const sampled=path.frames.filter((_,i)=>i%3===0||i===path.frames.length-1).slice(1);
 for(const frame of sampled){
  const next=initial.slice(),moves=[];
  for(let i=0;i<bindings.length;i++)if(bindings[i]){
   const coords=fit(interpolate(bindings[i],frame.coords));
   // Preserve tiny initial discrepancies instead of snapping the input pose.
   const origin=fit(interpolate(bindings[i],path.frames[0].coords));
   for(let j=0;j<3;j++)next[i*3+j]=initial[i*3+j]+coords[j]-origin[j];
   const delta=next.slice(i*3,i*3+3).map((v,j)=>v-previous[i*3+j]);
   if(norm(delta)>1e-7)moves.push(`m ${delta.map(number).join(' ')} p${i}`);
  }
  if(moves.length)commands.push(`t ${number((frame.tn-tn)*duration)} ${moves.join(' ')}`);
  tn=frame.tn;previous=next;
 }
 commands.push('iad');if(prepared.snap)commands.push('snap');
 const output=commands.join('\n'),executed=compileScript(script+'\n'+output);
 const motionStrain=Math.max(0,...executed.strainByInstruction.slice(prior.command.instructions.length+1));
 if(motionStrain>.03)throw Error(`Mechanism transfer exceeds the 3% strain limit (${(motionStrain*100).toFixed(2)}%).`);
 return {commands:output,selection:{material_rotation:rotation,moving_points:bindings.flatMap((b,i)=>b&&norm(sub(previous.slice(i*3,i*3+3),initial.slice(i*3,i*3+3)))>.03?[`p${i}`]:[]),max_strain:motionStrain,validation:'Segment strain checked; global self-collision is not certified.'}};
}
