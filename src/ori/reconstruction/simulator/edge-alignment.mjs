import {compileScript} from './script-runtime.mjs';
const xyz=p=>[p.x,p.y,p.z],sub=(a,b)=>a.map((v,i)=>v-b[i]),dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0),length=a=>Math.hypot(...a),unit=a=>a.map(v=>v/length(a)),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const distance=(p,a,u)=>length(cross(sub(p,a),u));
function normal(face){
 const p=face.points.map(xyz);
 for(let i=1;i<p.length-1;i++){const n=cross(sub(p[i],p[0]),sub(p[i+1],p[0]));if(length(n)>1e-5)return unit(n);}
 throw Error('Selected face is degenerate.');
}
function reference(model,id,kind){
 if(typeof id!=='string'||!new RegExp(`^${kind}\\d+$`).test(id))throw Error(`Expected a current ${kind} reference.`);
 const item=(kind==='s'?model.segments:model.faces)[Number(id.slice(1))];
 if(!item)throw Error(`Unknown current reference ${id}. Inspect the returned state before selecting an edge or layer.`);
 return item;
}
export function alignEdge(script,op){
 // This adapter has one operation; its edge/face fields identify it unambiguously.
 if(op.name!==undefined&&op.name!=='align_edge')throw Error('Unknown geometric operation. Available: align_edge.');
 if(Object.keys(op).some(k=>!['name','moving_edge','target_edge','seed_face','direction','duration_ms'].includes(k)))throw Error('Unsupported align_edge parameter.');
 if(!['valley','mountain'].includes(op.direction))throw Error('Choose valley (toward the selected face normal) or mountain (away).');
 const duration=op.duration_ms??1500;
 if(!Number.isFinite(duration)||duration<300||duration>10000)throw Error('duration_ms must be 300..10000.');
 const before=compileScript(script).model,source=reference(before,op.moving_edge,'s'),target=reference(before,op.target_edge,'s'),face=reference(before,op.seed_face,'f');
 if(!face.points.includes(source.p1)||!face.points.includes(source.p2))throw Error('seed_face must border moving_edge and identify the intended layer.');
 const n=normal(face),origin=xyz(face.points[0]),a=xyz(target.p1),targetAxis=unit(sub(xyz(target.p2),a)),sourcePoints=[xyz(source.p1),xyz(source.p2)],tol=.1*(before.scale||1);
 if(!Number.isFinite(targetAxis[0]))throw Error('Target edge has zero length.');
 if([source.p1,source.p2,target.p1,target.p2].some(p=>Math.abs(dot(sub(xyz(p),origin),n))>tol))throw Error('Edges must lie in the selected flap plane; this requires a compound operation.');
 if(sourcePoints.every(p=>distance(p,a,targetAxis)<tol))throw Error('Edges are already aligned; no fold is required.');
 const construction=`b3d ${op.moving_edge} ${op.target_edge}`;
 const split=compileScript(script+'\n'+construction).model;
 // Find the actual generated hinge by its geometric action, not its numeric ID.
 const candidates=split.segments.map((s,i)=>{
  const p=xyz(s.p1),u=unit(sub(xyz(s.p2),p));
  if(!Number.isFinite(u[0])||Math.abs(dot(u,n))>.001||Math.abs(dot(sub(p,origin),n))>tol)return null;
  const reflected=sourcePoints.map(q=>{const d=sub(q,p);return p.map((v,j)=>v+2*dot(d,u)*u[j]-d[j]);});
  const error=Math.max(...reflected.map(q=>distance(q,a,targetAxis)));
  return error<tol?{s,i,p,u,error}:null;
 }).filter(Boolean).sort((a,b)=>a.error-b.error);
 if(!candidates.length)throw Error('The native crease construction did not produce a hinge that aligns these edges.');
 const hinge=candidates[0],onAxis=p=>distance(xyz(p),hinge.p,hinge.u)<tol;
 const sourceIndices=[before.points.indexOf(source.p1),before.points.indexOf(source.p2)];
 const seed=sourceIndices.find(i=>!onAxis(split.points[i]));
 if(seed===undefined)throw Error('Moving edge lies on the hinge.');
 const adjacency=split.points.map(()=>[]);
 for(const edge of split.segments){const i=split.points.indexOf(edge.p1),j=split.points.indexOf(edge.p2);if(!onAxis(edge.p1)&&!onAxis(edge.p2)){adjacency[i].push(j);adjacency[j].push(i);}}
 const moving=new Set([seed]),queue=[seed];
 for(let k=0;k<queue.length;k++)for(const j of adjacency[queue[k]])if(!moving.has(j)){moving.add(j);queue.push(j);}
 const side=dot(cross(hinge.u,sub(xyz(split.points[seed]),hinge.p)),n);
 for(const i of moving){const p=xyz(split.points[i]);if(Math.abs(dot(sub(p,origin),n))>tol||dot(cross(hinge.u,sub(p,hinge.p)),n)*side< -tol*tol)throw Error('Selected component is not a single planar flap on one side of the hinge; use a compound fold.');}
 if([before.points.indexOf(target.p1),before.points.indexOf(target.p2)].some(i=>moving.has(i)))throw Error('The target would move with this flap; select another layer or a compound operation.');
 const angle=(side>0?180:-180)*(op.direction==='valley'?1:-1),ids=[...moving].sort((a,b)=>a-b);
 // Native snapping moves nearby vertices on other layers too. Keep a local
 // rigid fold local; rendering thickness handles separation of coincident faces.
 const commands=construction+(split.snap?'\nsnap':'')+`\nt ${duration} r s${hinge.i} ${angle} ${ids.map(i=>'p'+i).join(' ')}`+(split.snap?'\nsnap':'');
 const result=compileScript(script+'\n'+commands);
 if(sourceIndices.some(i=>distance(xyz(result.model.points[i]),a,targetAxis)>tol))throw Error('Executed fold did not align the selected edge.');
 return {commands,selection:{hinge:`s${hinge.i}`,moving_points:ids.map(i=>'p'+i),max_strain:result.maxStrain}};
}
