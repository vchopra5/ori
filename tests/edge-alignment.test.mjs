import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {alignEdge} from '../src/ori/reconstruction/simulator/edge-alignment.mjs';
import {compileScript} from '../src/ori/reconstruction/simulator/script-runtime.mjs';
const base=readFileSync(new URL('./fixtures/square-base-history.txt',import.meta.url),'utf8');
const first={name:'align_edge',moving_edge:'s1',target_edge:'s5',seed_face:'f6',direction:'mountain'};
test('saved failure: two sequential edge folds discover different hinge IDs and preserve other layers',()=>{
 const before=compileScript(base).model;
 const right=alignEdge(base,first);assert.deepEqual(right.selection.moving_points,['p7']);
 const script=base+'\n'+right.commands;
 const left=alignEdge(script,{...first,moving_edge:'s2',target_edge:'s6',seed_face:'f1'});
 assert.deepEqual(left.selection.moving_points,['p6']);assert.notEqual(left.selection.hinge,right.selection.hinge);
 const result=compileScript(script+'\n'+left.commands);
 assert.ok(result.maxStrain<.001);
 for(const i of [0,1,3,4,5,8])assert.ok(Math.hypot(...['x','y','z'].map(k=>result.model.points[i][k]-before.points[i][k]))<.1);
});
test('same operation aligns parallel edges on a plain square',()=>{
 const r=alignEdge('define 200 200',{...first,moving_edge:'s0',target_edge:'s2',seed_face:'f0'});
 const m=compileScript('define 200 200\n'+r.commands).model;
 assert.ok(Math.abs(m.points[0].y-200)<.1);assert.ok(Math.abs(m.points[1].y-200)<.1);
 assert.equal(r.selection.moving_points.length,2);
});
test('invalid references, layer selections, and already aligned edges return errors',()=>{
 assert.throws(()=>alignEdge(base,{...first,moving_edge:'s99'}),/Unknown current/);
 assert.throws(()=>alignEdge(base,{...first,seed_face:'f0'}),/must border/);
 assert.throws(()=>alignEdge(base,{...first,target_edge:'s1'}),/already aligned/);
 assert.throws(()=>alignEdge(base,{...first,direction:'left'}),/valley/);
});
test('connectivity includes extra vertices along the moving boundary',()=>{
 const r=alignEdge('define 200 200\nsplit s0 0.5',{...first,moving_edge:'s0',target_edge:'s2',seed_face:'f0'});
 assert.deepEqual(r.selection.moving_points,['p0','p1','p4']);
});
test('an omitted redundant operation name is accepted, but an unknown name is rejected',()=>{
 const op={moving_edge:'s0',target_edge:'s2',seed_face:'f0',direction:'valley'};
 assert.deepEqual(alignEdge('define 200 200',op),alignEdge('define 200 200',{...op,name:'align_edge'}));
 assert.throws(()=>alignEdge('define 200 200',{...op,name:'invented_fold'}),/Available: align_edge/);
});
test('bird-base edge fold survives rounding at a shared endpoint and preserves other layers',()=>{
 const script=readFileSync(new URL('./fixtures/bird-base-history.txt',import.meta.url),'utf8');
 const before=compileScript(script).model;
 const result=alignEdge(script,{name:'align_edge',moving_edge:'s23',target_edge:'s5',seed_face:'f19',direction:'valley'});
 const after=compileScript(script+'\n'+result.commands);
 assert.deepEqual(result.selection.moving_points,['p11']);
 assert.ok(after.maxStrain<.03);
 for(let i=0;i<before.points.length;i++)if(i!==11)
  assert.ok(Math.hypot(...['x','y','z'].map(k=>after.model.points[i][k]-before.points[i][k]))<.01);
});
