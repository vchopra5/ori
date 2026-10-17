import test from 'node:test';
import assert from 'node:assert/strict';
import {compileScript} from '../src/ori/reconstruction/simulator/script-runtime.mjs';
import {Model} from '../src/ori/reconstruction/simulator/vendor/orisim3d/js/Model.js';
import {layerHistory,layerLayout,motionHinges} from '../src/ori/reconstruction/simulator/paper-layers.mjs';
import {paperShell} from '../src/ori/reconstruction/simulator/paper-view.mjs';
const normal=pts=>Model.normal(pts);
const base='define 200 200\nby2d p0 p2\n';
test('a closed fold uses its approach to put the moving layer above or below the stationary layer',()=>{
 for(const angle of [180,-180]){
  const {command,model}=compileScript(base+`t 1000 r s4 ${angle} p1`);
  const history=layerHistory(command),layout=layerLayout(model,history.at(-1));
  const moving=model.faces.findIndex(f=>f.points.includes(model.points[1])),fixed=1-moving;
  // The engine orients s4 from p2 to p0; positive rotation lifts p1 above z=0.
  assert.equal(Math.sign(layout.offsets[moving][2]-layout.offsets[fixed][2]),Math.sign(angle));
  assert.ok(Math.abs(layout.offsets[moving][2]-layout.offsets[fixed][2])>.5);
  assert.equal(layout.unresolved,0);
  assert.deepEqual([...motionHinges(model,command.paths.at(-1))],['0:2']);
 }
});
test('coplanar mesh subdivisions do not become separate paper layers or visible construction lines',()=>{
 const {model}=compileScript(base),layout=layerLayout(model);
 assert.equal(new Set(layout.panels).size,1);
 assert.ok(layout.offsets.flat().every(x=>x===0));
 const mesh=paperShell(model,normal),withCreases=paperShell(model,normal,.35,{showCreases:true});
 assert.equal(mesh.creases.length,0);
 assert.ok(withCreases.creases.length>0);
 assert.equal(mesh.lines.length,16); // four outside edges, two surfaces
});
test('front, back, and rim triangles have outward winding and keep fixed material-side labels',()=>{
 const {model}=compileScript('define 200 200');const mesh=paperShell(model,normal);
 for(let i=0;i<mesh.positions.length;i+=9){
  const p=mesh.positions.slice(i,i+3),a=mesh.positions.slice(i+3,i+6).map((v,k)=>v-p[k]),b=mesh.positions.slice(i+6,i+9).map((v,k)=>v-p[k]);
  const n=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  assert.ok(n.reduce((sum,v,k)=>sum+v*mesh.normals[i+k],0)>0);
 }
 assert.deepEqual([...new Set(mesh.sides)],[0,1,2]);
});
test('layer ordering rotates with the sheet and is deterministic when revisiting a frame',()=>{
 const {command}=compileScript(base+'t 1000 r s4 180 p1\nt 1000 ty 180');
 const history=layerHistory(command),k=command.paths.findIndex(p=>p),folded=Model.deserialize(command.snapshots[k]),turned=Model.deserialize(command.snapshots.at(-1));
 const a=layerLayout(folded,history[k]),b=layerLayout(turned,history.at(-1));
 for(let i=0;i<a.offsets.length;i++)assert.ok(Math.abs(a.offsets[i][2]+b.offsets[i][2])<1e-6);
 const before=JSON.stringify(folded),first=paperShell(folded,normal,.35,{orders:history[k]});
 paperShell(turned,normal,.35,{orders:history.at(-1)});
 assert.deepEqual(paperShell(folded,normal,.35,{orders:history[k]}),first);
 assert.equal(JSON.stringify(folded),before);
});
