// Native motions adapted from OriSim3D templates at the revision in vendor/SOURCE.md.
// Petals transfer the reference surface motion onto material subdivisions.
// All exported commands and their playback are executed by OriSim3D.
import {compileScript} from './script-runtime.mjs';
import {transferMotion} from './motion-transfer.mjs';
const sheet='define 200 200\niad\n';
const creases='by2d p0 p2\nby2d p1 p3\nc2d p0 p1\nc2d p1 p2\n';
const collapse='t 1500 r s11 -180 p1 r s15 -180 p3 a p5 p2 p7\nt 1500 r s6 -90 p7 r s7 -90 p5 a p2\n';
const petalCreases='b3d s2 s4\nb3d s0 s4\nby3d p9 p11\n';
export const recipes={
 square_base:{description:'Flat square to square base, including existing or new base creases.',prefix:sheet,body:creases+collapse},
 petal_fold:{description:'Square base to one raised petal. Creates the native petal creases and closes flat by default.',prefix:sheet+creases+collapse,body:'t 1500 fit\ntz 45\nz 0.71\n'+petalCreases+'t 2000 r s31 -178 p2 a p5 p7\n'},
};
function mapping(reference,current){
 const ids=reference.points.map(p=>current.points.findIndex(q=>Math.hypot(p.xf-q.xf,p.yf-q.yf)<.05));
 if(ids.some(i=>i<0))throw Error('Recipe starting topology does not match: required material points are missing.');
 // Pairwise distances are invariant under whole-sheet camera/orientation changes.
 for(let i=0;i<ids.length;i++)for(let j=0;j<i;j++){
  const a=reference.points[i],b=reference.points[j],c=current.points[ids[i]],d=current.points[ids[j]];
  if(Math.abs(Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z)/reference.scale-Math.hypot(c.x-d.x,c.y-d.y,c.z-d.z)/current.scale)>2)
   throw Error('Recipe starting pose does not match. Restore/unfold the affected flaps first, or use a different operation.');
 }
 return ids;
}
export function expandRecipe(script,spec){
 if(!spec||typeof spec!=='object'||!recipes[spec.name])throw Error('Unknown recipe. Available: '+Object.keys(recipes).join(', '));
 if(Object.keys(spec).some(k=>!['name','duration_ms','angle_degrees','material_rotation'].includes(k)))throw Error('Unsupported recipe parameter.');
 const recipe=recipes[spec.name],duration=spec.duration_ms??1500,angle=spec.angle_degrees??-180;
 if(!Number.isFinite(duration)||duration<300||duration>10000)throw Error('duration_ms must be 300..10000.');
 if(!Number.isFinite(angle)||angle> -90||angle< -180)throw Error('Petal angle_degrees must be -180..-90.');
 if(spec.name!=='petal_fold'&&spec.angle_degrees!==undefined)throw Error('angle_degrees is only supported for petal_fold.');
 if(spec.name==='petal_fold'){
  const rotation=spec.material_rotation??0;
  if(![0,90,180,270].includes(rotation))throw Error('petal_fold material_rotation must be 0, 90, 180, or 270.');
  const reference=recipe.prefix+recipe.body.replace('r s31 -178','r s31 '+angle);
  return transferMotion(script,reference,{duration,rotation}).commands;
 }
 if(spec.material_rotation!==undefined)throw Error('material_rotation is only supported for petal_fold.');
 let referenceScript=recipe.prefix,commands='';
 for(let line of recipe.body.trim().split('\n')){
  const reference=compileScript(referenceScript).model,current=compileScript(script+'\n'+commands).model;
  const ids=mapping(reference,current);
  if(line.startsWith('t ')&&current.points.length!==reference.points.length)throw Error('Additional crease vertices need a custom moving-layer selection; this recipe cannot safely move them yet. Existing paper is unchanged.');
  let tokens=line.split(' ');
  for(let i=0;i<tokens.length;i++){
   if(/^p\d+$/.test(tokens[i]))tokens[i]='p'+ids[Number(tokens[i].slice(1))];
   else if(/^s\d+$/.test(tokens[i])){
    const edge=reference.segments[Number(tokens[i].slice(1))];
    const a=ids[reference.points.indexOf(edge.p1)],b=ids[reference.points.indexOf(edge.p2)];
    const n=current.segments.findIndex(s=>(s.p1===current.points[a]&&s.p2===current.points[b])||(s.p1===current.points[b]&&s.p2===current.points[a]));
    if(n<0)throw Error('Recipe hinge is subdivided differently; use a custom operation for this topology.');
    tokens[i]='s'+n;
    if(tokens[i-1]==='r'&&current.segments[n].p1!==current.points[a])tokens[i+1]=String(-Number(tokens[i+1]));
   }
  }
  if(tokens[0]==='t')tokens[1]=String(duration);
  commands+=tokens.join(' ')+'\n';referenceScript+=line+'\n';
 }
 compileScript(script+'\n'+commands);
 return commands.trim();
}
