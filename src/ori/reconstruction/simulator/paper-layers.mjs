import {Model} from './vendor/orisim3d/js/Model.js';
const xyz=p=>[p.x,p.y,p.z],sub=(a,b)=>a.map((x,i)=>x-b[i]),dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0);
const key=(a,b)=>a<b?`${a}:${b}`:`${b}:${a}`;
const center=points=>[0,1,2].map(k=>points.reduce((s,p)=>s+p[k],0)/points.length);
export function faceGeometry(model){
 return model.faces.map(f=>({points:f.points.map(xyz),normal:Model.normal(f),center:center(f.points.map(xyz))}));
}
function area(poly){return Math.abs(poly.reduce((s,p,i)=>{const q=poly[(i+1)%poly.length];return s+p[0]*q[1]-p[1]*q[0];},0))/2;}
function cross(a,b,c){return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);}
function overlap(a,b,n){
 const drop=n.map(Math.abs).indexOf(Math.max(...n.map(Math.abs))),project=p=>p.filter((_,k)=>k!==drop);
 let poly=a.map(project),clip=b.map(project);
 const signed=clip.reduce((s,p,i)=>{const q=clip[(i+1)%clip.length];return s+p[0]*q[1]-p[1]*q[0];},0);
 if(signed<0)clip.reverse();
 for(let i=0;i<clip.length&&poly.length;i++){
  const c=clip[i],d=clip[(i+1)%clip.length],next=[];
  for(let j=0;j<poly.length;j++){
   const p=poly[j],q=poly[(j+1)%poly.length],x=cross(c,d,p),y=cross(c,d,q);
   if(x>=-1e-8)next.push(p);
   if((x>0&&y<0)||(x<0&&y>0)){const t=x/(x-y);next.push(p.map((v,k)=>v+t*(q[k]-v)));}
  }poly=next;
 }
 return poly.length>2?area(poly):0;
}
function contains(poly,p){
 let sign=0;
 for(let i=0;i<poly.length;i++){const v=cross(poly[i],poly[(i+1)%poly.length],p);if(Math.abs(v)<1e-5)continue;if(sign&&Math.sign(v)!==sign)return false;sign=Math.sign(v);}
 return true;
}
export function edgeFaces(model){
 const ids=new Map(model.points.map((p,i)=>[p,i])),edges=new Map();
 model.faces.forEach((face,f)=>face.points.forEach((p,i)=>{
  const a=ids.get(p),b=ids.get(face.points[(i+1)%face.points.length]),k=key(a,b);
  if(!edges.has(k))edges.set(k,{a,b,faces:[]});edges.get(k).faces.push(f);
 }));return edges;
}
function updateOrder(model,orders){
 const faces=faceGeometry(model),epsilon=.05*model.scale;
 for(let i=0;i<faces.length;i++)for(let j=i+1;j<faces.length;j++){
  const a=faces[i],b=faces[j];if(Math.abs(dot(a.normal,b.normal))<.985)continue;
  const distance=dot(sub(b.center,a.center),a.normal);
  if(Math.abs(distance)<epsilon||overlap(a.points,b.points,a.normal)<.01*model.scale**2)continue;
  orders.set(key(i,j),Math.sign(distance));
 }
}
// Save contact ordering from the approach to a flat pose, not GPU draw order.
// The result is indexed by recorded instruction, so backward scrubbing is stable.
export function layerHistory(command){
 const history=[];let previous=null,orders=new Map();
 for(let k=0;k<command.snapshots.length;k++){
  if(!command.snapshots[k])continue;
  const model=Model.deserialize(command.snapshots[k]);
  const uv=model.faces.map(f=>f.points.map(p=>[p.xf,p.yf]));
  if(previous&&JSON.stringify(uv)!==JSON.stringify(previous)){
   const parents=uv.map(poly=>{const p=[0,1].map(k=>poly.reduce((s,q)=>s+q[k],0)/poly.length);return previous.findIndex(old=>contains(old,p));});
   const inherited=new Map();
   for(let i=0;i<parents.length;i++)for(let j=i+1;j<parents.length;j++){
    const a=parents[i],b=parents[j],order=orders.get(key(a,b));
    if(a>=0&&b>=0&&a!==b&&order)inherited.set(key(i,j),order*(a<b?1:-1));
   }orders=inherited;
  }
  const path=command.paths[k];
  if(path&&path.frames[0].coords.length===model.points.length*3){
   for(let f=0;f<path.frames.length;f+=3){model.restorePositions(path.frames[f].coords);updateOrder(model,orders);}
   model.restorePositions(path.frames.at(-1).coords);
  }
  updateOrder(model,orders);history[k]=new Map(orders);previous=uv;
 }
 return history;
}
function unionFind(n){const p=Array.from({length:n},(_,i)=>i);const root=i=>p[i]===i?i:p[i]=root(p[i]);return {root,join(a,b){p[root(b)]=root(a);}};}
export function layerLayout(model,orders=new Map(),spacing=.9){
 const faces=faceGeometry(model),edges=edgeFaces(model),panels=unionFind(faces.length),scale=model.scale||1;
 for(const e of edges.values())if(e.faces.length===2){
  const [a,b]=e.faces.map(i=>faces[i]);
  if(dot(a.normal,b.normal)>.99999&&Math.abs(dot(sub(a.center,b.center),a.normal))<.02*scale)panels.join(...e.faces);
 }
 const groups=[...new Set(faces.map((_,i)=>panels.root(i)))],contacts=unionFind(faces.length),links=[];
 for(let i=0;i<faces.length;i++)for(let j=i+1;j<faces.length;j++){
  const a=faces[i],b=faces[j],pa=panels.root(i),pb=panels.root(j);
  if(pa===pb||Math.abs(dot(a.normal,b.normal))<.995)continue;
  const distance=Math.max(...b.points.map(p=>Math.abs(dot(sub(p,a.center),a.normal))));
  if(distance>3*scale||overlap(a.points,b.points,a.normal)<.01*scale**2)continue;
  contacts.join(pa,pb);links.push({i,j,pa,pb,distance});
 }
 const offsets=faces.map(()=>[0,0,0]);let unresolved=0;
 for(const cluster of new Set(groups.map(contacts.root))){
  const members=groups.filter(g=>contacts.root(g)===cluster);if(members.length<2)continue;
  const normal=faces[members[0]].normal,adj=new Map(members.map(i=>[i,new Set()])),indegree=new Map(members.map(i=>[i,0]));
  let fade=0;
  for(const link of links.filter(l=>contacts.root(l.pa)===cluster)){
   const order=orders.get(key(link.i,link.j));if(!order)unresolved++;
   const above=(order??(link.i<link.j?1:-1))*dot(faces[link.i].normal,normal)>0;
   const [lo,hi]=above?[link.pa,link.pb]:[link.pb,link.pa];
   if(!adj.get(lo).has(hi)){adj.get(lo).add(hi);indegree.set(hi,indegree.get(hi)+1);}
   const t=1-link.distance/(3*scale);fade=Math.max(fade,t*t*(3-2*t));
  }
  const pending=members.slice(),rank=new Map();let level=0;
  while(pending.length){
   const index=pending.findIndex(i=>indegree.get(i)===0);
   if(index<0)unresolved++;
   const id=pending.splice(Math.max(0,index),1)[0];rank.set(id,level++);
   for(const j of adj.get(id))indegree.set(j,indegree.get(j)-1);
  }
  faces.forEach((_,i)=>{const p=panels.root(i);if(rank.has(p))offsets[i]=normal.map(v=>v*(rank.get(p)-(members.length-1)/2)*spacing*scale*fade);});
 }
 return {offsets,panels:faces.map((_,i)=>panels.root(i)),edges,unresolved};
}
export function motionHinges(model,path){
 const result=new Set();if(!path||path.frames[0].coords.length!==model.points.length*3)return result;
 const initial=path.frames[0].coords;
 const moving=model.points.map((_,i)=>path.frames.some(f=>Math.hypot(...[0,1,2].map(k=>f.coords[3*i+k]-initial[3*i+k]))>.02));
 const ids=new Map(model.points.map((p,i)=>[p,i]));
 for(const [key,e]of edgeFaces(model))if(e.faces.length===2&&!moving[e.a]&&!moving[e.b]&&e.faces.some(i=>model.faces[i].points.some(p=>moving[ids.get(p)])))result.add(key);
 return result;
}
