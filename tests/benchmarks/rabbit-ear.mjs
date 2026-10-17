// Run after: npm install --prefix .local/rabbit-ear-benchmark --ignore-scripts rabbit-ear@0.9.4
// Isolated benchmark: no app dependency change, no Gemini calls, no publishing.
import assert from 'node:assert/strict';
import ear from '../../.local/rabbit-ear-benchmark/node_modules/rabbit-ear/module/index.js';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {compileScript} from '../../src/ori/reconstruction/simulator/script-runtime.mjs';
import {alignEdge} from '../../src/ori/reconstruction/simulator/edge-alignment.mjs';
import {View3d} from '../../src/ori/reconstruction/simulator/vendor/orisim3d/js/View3d.js';
const out=new URL('../../.local/rabbit-ear-benchmark/results/',import.meta.url);mkdirSync(out,{recursive:true});
const clone=x=>JSON.parse(JSON.stringify(x)),sub=(a,b)=>a.map((x,i)=>x-b[i]),dist=(a,b)=>Math.hypot(...sub(a,b));
function graphOf(model){
 const index=p=>model.points.indexOf(p),normals=model.faces.map(f=>View3d.prototype.normal(f.points));
 const g={file_spec:1.2,vertices_coords:model.points.map(p=>[(p.xf+200)/400,(p.yf+200)/400]),edges_vertices:model.segments.map(s=>[index(s.p1),index(s.p2)]),faces_vertices:model.faces.map(f=>f.points.map(index))};
 ear.graph.populate(g);
 g.edges_assignment=g.edges_faces.map(fs=>fs.length<2?'B':normals[fs[0]].reduce((s,v,i)=>s+v*normals[fs[1]][i],0)<0?'V':'F');
 g.edges_foldAngle=g.edges_assignment.map(a=>a==='V'?180:0);
 return g;
}
function error(a,b,count=Math.min(a.length,b.length)){
 let max=0;for(let i=0;i<count;i++)for(let j=0;j<i;j++)max=Math.max(max,Math.abs(dist(a[i],a[j])-dist(b[i],b[j])));return max;
}
function strain(g,coords){return Math.max(...g.edges_vertices.map(([a,b])=>Math.abs(dist(coords[a],coords[b])/dist(g.vertices_coords[a],g.vertices_coords[b])-1)));}
const nativeCoords=m=>m.points.map(p=>[p.x,p.y,p.z].map(v=>v/(400*m.scale)));
const line=(m,s)=>({origin:[s.p1.x,s.p1.y].map(v=>v/(400*m.scale)),vector:[s.p2.x-s.p1.x,s.p2.y-s.p1.y]});
function exported(name,g,coords){writeFileSync(new URL(name+'.fold',out),JSON.stringify({...g,vertices_coords:coords},null,2));}
const baseScript=readFileSync(new URL('../fixtures/square-base-history.txt',import.meta.url),'utf8');
const base=compileScript(baseScript).model,baseGraph=graphOf(base),baseline=ear.graph.makeVerticesCoordsFolded(baseGraph);
const report={library:'rabbit-ear@0.9.4',units:'sheet side = 1; pairwise errors are invariant to global rigid pose',scope:'Tests native foldLine, not every possible custom layer-aware implementation.',base:{reconstruction_pairwise_error:error(baseline,nativeCoords(base)),strain:strain(baseGraph,baseline)},flaps:[]};
let history=baseScript;
for(const [label,operation]of [['right',{name:'align_edge',moving_edge:'s1',target_edge:'s5',seed_face:'f6',direction:'mountain'}],['left',{name:'align_edge',moving_edge:'s2',target_edge:'s6',seed_face:'f1',direction:'mountain'}]]){
 const before=compileScript(history).model,reference=alignEdge(history,operation),after=compileScript(history+'\n'+reference.commands).model;
 const source=before.segments[+operation.moving_edge.slice(1)],target=before.segments[+operation.target_edge.slice(1)];
 const candidates=ear.axiom.axiom3(line(before,source),line(before,target));
 const g0=graphOf(before),folded=nativeCoords(before).map(p=>p.slice(0,2)),desired=nativeCoords(after);
 const trials=candidates.map((crease,i)=>{
  try{
   const g=clone(g0),event=ear.graph.foldLine(g,crease,'V',180,folded,1e-4),coords=ear.graph.makeVerticesCoordsFolded(g);
   exported(`flap-${label}-solution-${i}`,g,coords);
   // Give the compiler a correct layer mask, independent of LLM selection.
   // These are the two faces adjoining the flap corner in this fixture.
   const selectedBefore=label==='right'?[2,6]:[1,5];
   const selectedAfter=new Set(selectedBefore.flatMap(f=>event.faces.map[f]??[]));
   const masked=clone(g);
   for(const e of event.edges.new)if(!masked.edges_faces[e].some(f=>selectedAfter.has(f))){masked.edges_assignment[e]='F';masked.edges_foldAngle[e]=0;}
   const maskedCoords=ear.graph.makeVerticesCoordsFolded(masked);
   exported(`flap-${label}-solution-${i}-masked`,masked,maskedCoords);
   const samples=[0,.25,.5,.75,1].map(progress=>{
    const frame=clone(masked);
    for(const e of event.edges.new)frame.edges_foldAngle[e]*=progress;
    const coords=ear.graph.makeVerticesCoordsFolded(frame);
    return {progress,strain:strain(frame,coords),finite:coords.flat().every(Number.isFinite)};
   });
   const maskedResult={supplied_face_mask:selectedBefore,strain:strain(masked,maskedCoords),pairwise_error:error(maskedCoords,desired,before.points.length),motion_samples:samples};
   return {solution:i,crease,masked:maskedResult,vertices:g.vertices_coords.length,new_edges:event.edges.new,new_faces:event.faces.new,strain:strain(g,coords),pairwise_error_vs_selected_layer:error(coords,desired,before.points.length),coincident_layer_separation:dist(coords[5],coords[7])};
  }catch(e){return {solution:i,error:e.message};}
 });
 report.flaps.push({label,operation,native_commands:reference.commands,native_max_strain:reference.selection.max_strain,expected_layer_separation:dist(desired[5],desired[7]),trials});
 history+='\n'+reference.commands;
}
// Isolate the petal action using the known-good upstream precreased square base.
const template=readFileSync(new URL('../../src/ori/reconstruction/simulator/vendor/orisim3d/templates/petal-fold.txt',import.meta.url),'utf8');
const prefix=template.split('// Petal fold\n')[0],petalBefore=compileScript(prefix).model,petalAfter=compileScript(prefix+'\nt 2000 r s31 -178 p2 a p5 p7').model;
const petalGraph=graphOf(petalBefore),hinge=line(petalBefore,petalBefore.segments[31]);
report.petal={starting_reconstruction_error:error(ear.graph.makeVerticesCoordsFolded(petalGraph),nativeCoords(petalBefore)),native_max_strain:compileScript(prefix+'\nt 2000 r s31 -178 p2 a p5 p7').maxStrain,trials:[]};
for(const degrees of [0,45,90,135,178]){
 try{
  const g=clone(petalGraph),event=ear.graph.foldLine(g,hinge,'V',degrees,nativeCoords(petalBefore).map(p=>p.slice(0,2)),1e-4),coords=ear.graph.makeVerticesCoordsFolded(g);
  exported(`petal-${degrees}`,g,coords);
  report.petal.trials.push({degrees,strain:strain(g,coords),finite:coords.flat().every(Number.isFinite),new_edges:event.edges.new,reassigned_edges:event.edges.reassigned,shape_change:error(coords,nativeCoords(petalBefore),petalBefore.points.length),final_pairwise_error:degrees===178?error(coords,nativeCoords(petalAfter),petalBefore.points.length):undefined});
 }catch(e){report.petal.trials.push({degrees,error:e.message});}
}
report.limitations=[
 'Layer masks were supplied by the benchmark, not selected autonomously by Gemini.',
 'Base M/V signs were reduced to folded-versus-flat for pose reconstruction; full layer ordering and collision freedom were not validated.',
 'Flap tests are independent compiler comparisons against native states, not a fully autonomous Rabbit Ear reconstruction of the whole video.',
 'The petal trial tests direct foldLine angle control; it does not rule out a custom coordinated Rabbit Ear implementation.'
];
assert.ok(report.base.reconstruction_pairwise_error<1e-3,'Base conversion must be accurate before judging the compiler.');
assert.ok(report.petal.starting_reconstruction_error<1e-3,'Petal starting state must reconstruct accurately.');
for(const flap of report.flaps){
 const best=flap.trials.filter(t=>t.masked).sort((a,b)=>a.masked.pairwise_error-b.masked.pairwise_error)[0];
 assert.ok(best?.masked.pairwise_error<1e-3,`${flap.label}: selected-layer endpoint mismatch`);
 assert.ok(best.masked.motion_samples.every(s=>s.finite&&s.strain<1e-3),`${flap.label}: sampled motion strain`);
}
writeFileSync(new URL('report.json',out),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
