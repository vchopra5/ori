import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pointFold,planStages,validateFold} from '../src/ori/reconstruction/simulator/fold-model.mjs';
const template=JSON.parse(readFileSync(new URL('../src/ori/reconstruction/simulator/templates/square-base.fold',import.meta.url)));
const action={kind:'fold',description:'Fold diagonal.',moving_point_uv:[1,0],target_point_uv:[0,1],angle_degrees:180,fold_direction:'toward_front'};
test('square-base FOLD is connected, triangulated, and has the sourced six active hinge segments',()=>{
  const f=validateFold(template);
  assert.equal(f.vertices_coords.length,9);assert.equal(f.faces_vertices.length,8);
  assert.equal(f.edges_assignment.filter(a=>a==='M').length,4);assert.equal(f.edges_assignment.filter(a=>a==='V').length,2);
  f.edges_vertices.forEach(([a,b],i)=>{const adjacent=f.faces_vertices.filter(face=>face.includes(a)&&face.includes(b));assert.equal(adjacent.length,f.edges_assignment[i]==='B'?1:2);});
  const total=f.faces_vertices.reduce((sum,face)=>{const [a,b,c]=face.map(i=>f.vertices_coords[i]);return sum+Math.abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2;},0);
  assert.equal(total,1);
});
test('point alignment becomes FOLD hinge geometry, with no supplied crease',()=>{
  const f=validateFold(pointFold(action));
  const active=f.edges_vertices.filter((e,i)=>f.edges_assignment[i]==='V');
  assert.ok(active.length);for(const edge of active)for(const i of edge)assert.ok(Math.abs(f.vertices_coords[i][0]-f.vertices_coords[i][1])<1e-7);
});
test('unfold reverses its source and collapse selects provenance-labeled template',()=>{
  const s=planStages([action,{kind:'unfold',reverse_step:1},{kind:'fold',description:'Collapse the paper into a square base.'},{...action}],template);
  assert.deepEqual(s[0].fold,s[1].fold);assert.equal(s[1].from,1);assert.equal(s[1].to,0);assert.equal(s[2].template,true);assert.equal(s[2].fold.ori_template,'square_base_collapse');assert.equal(s[3].fold,undefined);
});
test('saved 3.8 instructions map the eight simple actions and the square-base collapse',()=>{
  const plan=JSON.parse(readFileSync(new URL('./fixtures/crane-3.8-flash.json',import.meta.url)));
  const s=planStages(plan,template);assert.equal(s.filter(x=>x.fold).length,9);assert.equal(s[9].template,true);
});
test('FOLD imports reject invalid references and default signed M/V angles',()=>{
  const f=structuredClone(template);delete f.edges_foldAngle;assert.equal(validateFold(f).edges_foldAngle[9],-180);
  f.edges_vertices[0]=[0,999];assert.throws(()=>validateFold(f),/indices/);
});
test('explicit template selection does not depend on wording and explicit null suppresses guessing',()=>{
  const explicit={kind:'fold',description:'Push the two sides inward.',template:'square_base_collapse'};
  assert.equal(planStages([explicit],template)[0].template,true);
  assert.equal(planStages([{kind:'fold',description:'Collapse into a square base.',template:null}],template)[0].fold,undefined);
  assert.equal(planStages([{...explicit,template:'unsupported_template'}],template)[0].fold,undefined);
});
test('direct 3D FOLD states and inherited frames import without template replacement',async()=>{
  const {foldStages}=await import('../src/ori/reconstruction/simulator/fold-model.mjs');
  const state=structuredClone(template);state.vertices_coords=state.vertices_coords.map(([x,y])=>[x,y,0]);state.frame_classes=['foldedForm'];state.frame_title='Model supplied state';
  state.file_frames=[{frame_title:'Next state',frame_parent:0,frame_inherit:true,vertices_coords:state.vertices_coords.map(([x,y,z])=>[x,y,z+.2])},{frame_title:'Unresolved', 'ori:uncertainties':['Hidden'],frame_inherit:false}];
  const stages=foldStages(state);assert.equal(stages.length,3);assert.equal(stages[0].state,true);assert.equal(stages[0].template,undefined);assert.equal(stages[1].fold.vertices_coords[0][2],.2);assert.equal(stages[2].fold,undefined);
});
