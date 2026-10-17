// Exact hinge kinematics. Display offsets are separate from material coordinates.
export function rotate(point, crease, angle, vector=false) {
  const origin=vector?[0,0,0]:crease[0], axis=crease[1].map((x,i)=>x-crease[0][i]);
  const length=Math.hypot(...axis), n=axis.map(x=>x/length), p=point.map((x,i)=>x-origin[i]);
  const c=Math.cos(angle),s=Math.sin(angle),dot=p.reduce((sum,x,i)=>sum+x*n[i],0);
  const cross=[n[1]*p[2]-n[2]*p[1],n[2]*p[0]-n[0]*p[2],n[0]*p[1]-n[1]*p[0]];
  return p.map((x,i)=>origin[i]+x*c+cross[i]*s+n[i]*dot*(1-c));
}
export function layerOffsets(panels, end=false) {
  const rank=new Map(panels.map(p=>[p.id,0])), pending=new Map(panels.map(p=>[p.id,new Set()]));
  for(const p of panels)for(const [other,normal]of Object.entries(end?p.end_contacts||{}:p.contacts||{}))
    if(rank.has(other)&&normal[2]>1e-8)pending.get(p.id).add(other);
  const result=new Map();
  while(pending.size){
    const ready=[...pending].filter(([,deps])=>!deps.size).map(([id])=>id);
    if(!ready.length)throw Error('Contradictory paper layer order');
    for(const id of ready){pending.delete(id);result.set(id,rank.get(id));
      for(const [next,deps]of pending)if(deps.delete(id))rank.set(next,Math.max(rank.get(next),rank.get(id)+1));}
  }
  const center=Math.max(0,...result.values())/2;
  return new Map([...result].map(([id,r])=>[id,[0,0,(r-center)*.0018]]));
}
export function evaluatePath(node,t) {
  if(typeof node==='number')return node;
  const [op,...rest]=node;if(op==='t')return t;
  const a=rest.map(x=>evaluatePath(x,t));
  switch(op){case '+':return a[0]+a[1];case '-':return a[0]-a[1];case '*':return a[0]*a[1];case '/':return a[0]/a[1];
    case 'sin':return Math.sin(a[0]);case 'cos':return Math.cos(a[0]);case 'sqrt':return Math.sqrt(a[0]);case 'atan2':return Math.atan2(a[0],a[1]);
    default:throw Error('Unknown path operation');}
}
export function poseAt(motion, fraction) {
  const t=Math.max(0,Math.min(1,fraction)), eased=foldProgress(t), angle=motion.angle_degrees*Math.PI/180*eased;
  if(motion.type==='compound')return motion.panels.map(p=>({...p,vertices:p.vertices.map((v,i)=>{
    const path=motion.paths.find(x=>Math.hypot(...x.material.map((a,k)=>a-p.material[i][k]))<1e-8);
    return path?path.position.map(x=>evaluatePath(x,eased)):v.slice();
  })}));
  const moving=new Set(motion.moving);
  return motion.panels.map(p=>({...p,vertices:p.vertices.map(v=>moving.has(p.id)?rotate(v,motion.crease,angle):v.slice())}));
}
export function frameAt(replay,time) {
  const step=replay.seconds_per_step||2.6, position=Math.max(0,time/step), index=Math.floor(position);
  if(index===0||!replay.motions?.length)return {index:0,panels:replay.states[0],motion:null,fraction:0};
  const number=Math.min(replay.motions.length-1,index-1),fraction=index>replay.motions.length?1:Math.min(1,position-index);
  const motion=replay.motions[number];
  return {index:number+1,panels:poseAt(motion,fraction),motion,fraction};
}

// A short pause to read the crease, then the rigid rotation, then its result.
export function foldProgress(fraction) {
  const t=Math.max(0,Math.min(1,(fraction-.2)/.6));
  return t*t*(3-2*t);
}
export function foldGuide(motion) {
  if(!motion||motion.type==='compound')return null;
  const origin=motion.crease[0],axis=motion.crease[1].map((x,i)=>x-origin[i]);
  const length=Math.hypot(...axis),n=axis.map(x=>x/length),moving=new Set(motion.moving),intervals=[];
  let anchor=null,score=0;
  if(length<1e-10)return {segments:[],arrow:[],moving:[...moving]};
  for(const panel of motion.panels){
    if(!moving.has(panel.id))continue;
    const hinge=[];
    for(const point of panel.vertices){
      const v=point.map((x,i)=>x-origin[i]),along=v.reduce((sum,x,i)=>sum+x*n[i],0);
      const radial=v.map((x,i)=>x-along*n[i]),distance=Math.hypot(...radial);
      if(distance<1e-7)hinge.push(along);

    }
    // Pick an interior point of a real moving triangle. Keeping its axial
    // position avoids inventing a trajectory over empty space beside a flap.
    for(let i=1;i<panel.vertices.length-1;i++){
      const [a,b,c]=[panel.vertices[0],panel.vertices[i],panel.vertices[i+1]];
      const u=b.map((x,k)=>x-a[k]),v=c.map((x,k)=>x-a[k]);
      const area=Math.hypot(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])/2;
      const candidate=a.map((x,k)=>(x+b[k]+c[k])/3),offset=candidate.map((x,k)=>x-origin[k]);
      const along=offset.reduce((sum,x,k)=>sum+x*n[k],0);
      const radius=Math.hypot(...offset.map((x,k)=>x-along*n[k]));
      if(area*radius>score){score=area*radius;anchor=candidate;}
    }
    if(hinge.length>=2){const min=Math.min(...hinge),max=Math.max(...hinge);if(max-min>1e-8)intervals.push([min,max]);}
  }
  intervals.sort((a,b)=>a[0]-b[0]);const merged=[];
  for(const interval of intervals){const last=merged.at(-1);if(last&&interval[0]<=last[1]+1e-7)last[1]=Math.max(last[1],interval[1]);else merged.push(interval.slice());}
  const point=t=>origin.map((x,i)=>x+n[i]*t),segments=merged.map(([a,b])=>[point(a),point(b)]);
  const fullAngle=motion.angle_degrees*Math.PI/180;
  // A direction cue shows departure, not the return toward the sheet at the
  // end of a 180-degree fold. Stop before the arc turns back on itself.
  const angle=Math.sign(fullAngle)*Math.min(Math.abs(fullAngle),Math.PI/3);
  if(!anchor||Math.abs(angle)<1e-8)return {segments,arrow:[],moving:[...moving]};
  // Trace the first part of the real material trajectory.
  const arrow=Array.from({length:49},(_,i)=>rotate(anchor,motion.crease,angle*i/48));
  const offset=anchor.map((x,k)=>x-origin[k]),along=offset.reduce((sum,x,k)=>sum+x*n[k],0);
  const radial=offset.map((x,k)=>x-along*n[k]),radius=Math.hypot(...radial);
  const endRadial=rotate(radial,motion.crease,angle,true);
  const tangent=[n[1]*endRadial[2]-n[2]*endRadial[1],n[2]*endRadial[0]-n[0]*endRadial[2],n[0]*endRadial[1]-n[1]*endRadial[0]].map(x=>x*Math.sign(angle)/radius);
  return {segments,arrow,tangent,angle,arcLength:radius*Math.abs(angle),moving:[...moving]};
}
