import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {compileScript} from '../src/ori/reconstruction/simulator/script-runtime.mjs';
import {rotateFlap} from '../src/ori/reconstruction/simulator/hinge-rotation.mjs';
const base=readFileSync(new URL('./fixtures/bird-base-history.txt',import.meta.url),'utf8')+readFileSync(new URL('./fixtures/bird-base-narrowing.txt',import.meta.url),'utf8');
test('book fold collects subdivided material without moving other layers or hinge vertices',()=>{
 const before=compileScript(base).model;
 const op={name:'rotate_flap',hinge:'s8',seed_points:['p10'],angle_degrees:180};
 const fold=rotateFlap(base,op),after=compileScript(base+'\n'+fold.commands).model;
 assert.deepEqual(fold.selection.moving_points,['p10','p19','p20','p21','p24','p26']);
 assert.ok(fold.selection.max_strain<.03);
 for(let i=0;i<before.points.length;i++)if(!fold.selection.moving_points.includes('p'+i))
  assert.ok(Math.hypot(...['x','y','z'].map(k=>before.points[i][k]-after.points[i][k]))<1e-8);
 const undone=rotateFlap(base+'\n'+fold.commands,{...op,angle_degrees:-180});
 const result=compileScript(base+'\n'+fold.commands+'\n'+undone.commands).model;
 for(let i=0;i<before.points.length;i++)assert.ok(Math.hypot(...['x','y','z'].map(k=>before.points[i][k]-result.points[i][k]))<1e-7);
});
test('multiple layer seeds are combined, and hinge/seed errors are explicit',()=>{
 const op={name:'rotate_flap',hinge:'s8',seed_points:['p10','p17'],angle_degrees:-180};
 const fold=rotateFlap(base,op);
 assert.equal(fold.selection.moving_points.length,11);
 assert.throws(()=>rotateFlap(base,{...op,seed_points:['p0']}),/lies on the hinge/);
 assert.throws(()=>rotateFlap(base,{...op,seed_points:['p999']}),/Unknown seed/);
 assert.throws(()=>rotateFlap(base,{...op,angle_degrees:0}),/nonzero/);
});
