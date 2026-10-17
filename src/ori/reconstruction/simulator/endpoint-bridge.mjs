import {readFileSync} from 'node:fs';
import {compileScript,registry} from './script-runtime.mjs';
import {expandRecipe} from './recipes.mjs';
import {squareBaseTargets,planarRegistration,endpointError,metricError,flatStateError} from './endpoint-target.mjs';
import {coordinatedSquareBase} from './square-base-path.mjs';

const {spec}=JSON.parse(readFileSync(0,'utf8'));
const initial='define 200 200\niad\n';
const preparation='by2d p0 p2\nby2d p1 p3\nc2d p0 p1\nc2d p1 p2';
const prefix=initial+preparation+'\n',start=registry(compileScript(prefix).model);
const targets=squareBaseTargets(start,spec);
// Only now do we ask a motion library to reach these independently built states.
const native=expandRecipe(prefix,{name:'square_base'});
const unaligned=registry(compileScript(prefix+native).model);
const fits=targets.map(target=>({target,...planarRegistration(unaligned,target)})).sort((a,b)=>a.error-b.error);
const candidates=[];
for(const fit of fits.filter(f=>f.error<.25)){
 const orientation=`t 1000 tz ${fit.angle_degrees.toFixed(8)}`;
 for(const mechanism of ['coordinated','upstream']){
 const commands=mechanism==='coordinated'?coordinatedSquareBase(prefix+orientation+'\n').commands:expandRecipe(prefix+orientation+'\n',{name:'square_base'});
 const compiled=compileScript(prefix+orientation+'\n'+commands),end=registry(compiled.model);
 let faceError=0,maxFrameTravel=0,maxRadius=0;
 for(const path of compiled.command.paths)if(path){
  for(let i=0;i<path.frames.length;i++){
   const coords=path.frames[i].coords,positions=start.points.map((_,j)=>coords.slice(3*j,3*j+3));
   faceError=Math.max(faceError,metricError(start,positions));
   positions.forEach((p,j)=>{maxRadius=Math.max(maxRadius,Math.hypot(...p));if(i)maxFrameTravel=Math.max(maxFrameTravel,Math.hypot(...p.map((v,k)=>v-path.frames[i-1].coords[3*j+k])));});
  }
 }
 const error=endpointError(end,fit.target);
 const checks={endpoint_max_distance:error,max_face_metric_error:faceError,max_frame_vertex_travel:maxFrameTravel,max_radius:maxRadius,segment_strain:compiled.maxStrain};
 if(error>.25||faceError>.03||maxFrameTravel>40)continue;
 candidates.push({id:`${mechanism}-${fit.target.id}`,mechanism,target_id:fit.target.id,checks,orientation_degrees:fit.angle_degrees,
  steps:[{description:'Verified flat sheet with both diagonals and center creases',commands:preparation},
   {description:'Orient the flat sheet for the observed diamond-shaped endpoint',commands:orientation},
   {description:'Collapse along existing creases into the target square base',commands}],
  endpoint:end,unresolved:['Layer order and global self-collision are not certified.','The motion library supplies the mechanism; Gemini did not invent this solver.']});
 }
}
console.log(JSON.stringify({start,flat_error:flatStateError(start),targets,candidates,
 rejected_fits:fits.filter(f=>f.error>=.25).map(f=>({id:f.target.id,error:f.error})),
 unaligned_endpoint_errors:targets.map(t=>({id:t.id,error:endpointError(unaligned,t)}))}));
