// Endpoint constraints are constructed independently of a motion recipe.
// This initial experiment supports the nine-vertex preliminary/square base.
// It certifies material metric, not layer ordering or collision freedom.
const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
export function metricError(state,positions=state.points.map(p=>p.position)){
 let error=0;
 for(const face of state.faces)for(let a=0;a<face.points.length;a++)for(let b=0;b<a;b++){
  const i=face.points[a],j=face.points[b],length=distance(state.points[i].material,state.points[j].material);
  if(length>1e-8)error=Math.max(error,Math.abs(distance(positions[i],positions[j])/length-1));
 }
 return error;
}
export function flatStateError(state){
 // All material pairs, not just mesh edges: a folded sheet is also edge-isometric.
 let error=0;
 for(let i=0;i<state.points.length;i++)for(let j=0;j<i;j++){
  const a=state.points[i],b=state.points[j];
  error=Math.max(error,Math.abs(distance(a.material,b.material)-distance(a.position,b.position)));
 }
 return error;
}
export function endpointError(state,target){
 if(state.points.length!==target.points.length)return Infinity;
 let error=0;
 for(const p of target.points){
  const actual=state.points.find(q=>q.id===p.id&&distance(q.material,p.material)<1e-6);
  if(!actual)return Infinity;
  error=Math.max(error,distance(actual.position,p.position));
 }
 return error;
}
export function squareBaseTargets(state,spec){
 if(spec.state_family!=='square_base'||!spec.flat_at_end||!spec.center_becomes_closed_tip||!spec.original_corners_meet_at_open_tip)
  throw Error('Observation does not establish the supported flat square-base endpoint.');
 const direction={top:[0,1],right:[1,0],bottom:[0,-1],left:[-1,0]}[spec.closed_direction];
 const opposite={top:'bottom',bottom:'top',left:'right',right:'left'};
 if(!direction||spec.open_direction!==opposite[spec.closed_direction])throw Error('Endpoint orientation is uncertain or inconsistent.');
 if(flatStateError(state)>.1)throw Error('Starting sheet is not flat: material-pair distances disagree.');
 const xs=state.points.map(p=>p.material[0]),ys=state.points.map(p=>p.material[1]);
 const lo=[Math.min(...xs),Math.min(...ys)],hi=[Math.max(...xs),Math.max(...ys)];
 const width=hi[0]-lo[0],center=lo.map((v,i)=>(v+hi[i])/2);
 if(Math.abs(width-(hi[1]-lo[1]))>1e-6||state.points.length!==9||state.faces.length!==8||state.faces.some(f=>f.points.length!==3))
  throw Error('This endpoint family requires a square with eight triangular sectors and nine material vertices.');
 const corner=[],middle=[];let centerIndex;
 state.points.forEach((p,i)=>{
  const [x,y]=p.material.map((v,k)=>(v-center[k])/(width/2));
  if(Math.abs(x)<1e-6&&Math.abs(y)<1e-6)centerIndex=i;
  else if(Math.abs(Math.abs(x)-1)<1e-6&&Math.abs(Math.abs(y)-1)<1e-6)corner.push(i);
  else if((Math.abs(x)<1e-6&&Math.abs(Math.abs(y)-1)<1e-6)||(Math.abs(y)<1e-6&&Math.abs(Math.abs(x)-1)<1e-6))middle.push(i);
 });
 if(centerIndex===undefined||corner.length!==4||middle.length!==4)throw Error('Required center, corners and edge midpoints are missing.');
 const height=width/Math.sqrt(2),right=[direction[1],-direction[0]],origin=state.points[centerIndex].position;
 const point=(side,along)=>[origin[0]+side*right[0]+along*direction[0],origin[1]+side*right[1]+along*direction[1],origin[2]];
 const targets=[];
 // The video may not reveal which material edge occupies which side.
 // Enumerate rather than silently deciding this hidden correspondence.
 for(let a=0;a<4;a++)for(let b=a+1;b<4;b++){
  const left=[middle[a],middle[b]],positions=state.points.map((_,i)=>i===centerIndex?point(0,0):corner.includes(i)?point(0,-height):point(left.includes(i)?-height/2:height/2,-height/2));
  const error=metricError(state,positions);
  if(error>1e-8)continue;
  targets.push({id:`target-${a}-${b}`,points:state.points.map((p,i)=>({...p,position:positions[i]})),faces:state.faces,segments:state.segments,
   constraints:{closed_tip:state.points[centerIndex].id,open_corners:corner.map(i=>state.points[i].id),left_midpoints:left.map(i=>state.points[i].id),closed_direction:spec.closed_direction},
   metric_error:error,unresolved:['front/back layer order','collision-free reachability','hidden material correspondence']});
 }
 return targets;
}
export function planarRegistration(state,target){
 // Rigid rotation about the persistent center. No vertex morph or shape reset.
 const c=state.points.find(p=>p.id===target.constraints.closed_tip).position;
 const tc=target.points.find(p=>p.id===target.constraints.closed_tip).position;
 if(distance(c,tc)>.1)throw Error('This trial only registers poses around an unchanged sheet center.');
 let dot=0,cross=0;
 state.points.forEach((p,i)=>{
  if(p.id!==target.points[i].id)throw Error('Material correspondence changed.');
  const [x,y]=[p.position[0]-c[0],p.position[1]-c[1]],q=target.points[i].position;
  dot+=x*(q[0]-c[0])+y*(q[1]-c[1]);cross+=x*(q[1]-c[1])-y*(q[0]-c[0]);
 });
 const angle=Math.atan2(cross,dot),co=Math.cos(angle),si=Math.sin(angle);
 const fitted={...state,points:state.points.map(p=>{const x=p.position[0]-c[0],y=p.position[1]-c[1];return {...p,position:[c[0]+co*x-si*y,c[1]+si*x+co*y,p.position[2]]};})};
 return {angle_degrees:angle*180/Math.PI,error:endpointError(fitted,target)};
}
