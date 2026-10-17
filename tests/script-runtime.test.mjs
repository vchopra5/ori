import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {compileScript} from '../src/ori/reconstruction/simulator/script-runtime.mjs';
const root=new URL('../src/ori/reconstruction/simulator/vendor/orisim3d/',import.meta.url);
for(const name of ['square-base','petal-fold','reverse-fold'])test(`upstream ${name} compiles with recorded motion and bounded segment strain`,()=>{
 const r=compileScript(readFileSync(new URL(`templates/${name}.txt`,root),'utf8'));
 assert.ok(r.command.paths.some(p=>p?.frames.length>2));
 assert.ok(r.model.points.every(p=>[p.x,p.y,p.z].every(Number.isFinite)));
 assert.ok(r.maxStrain<.03,`Strain ${r.maxStrain}`);
 const end=r.model.snapshotPositions();r.command.goTo(r.command.first);assert.notDeepEqual(end,r.model.snapshotPositions());
 r.command.goTo(r.command.instructions.length);assert.deepEqual(end,r.model.snapshotPositions());
});
test('model scripts cannot execute file/network commands or unknown commands',()=>{
 for(const script of ['define 200 200\nread https://example.com','define 200 200\nmagicFold','define 200 200\nby2d p0 p999'])assert.throws(()=>compileScript(script));
});
test('no-op rotations expose construction IDs for model correction',()=>{
 assert.throws(()=>compileScript('define 200 200\nby2d p0 p2\nt 1500 r s4 0 p1'),error=>{
  assert.match(error.message,/no motion/);assert.equal(error.constructionStates[0].state.segments.length,5);return true;
 });
});

const {expandRecipe}=await import('../src/ori/reconstruction/simulator/recipes.mjs');
const initial='define 200 200\niad\n';
test('native recipes compose square base and petal without resetting the sheet',()=>{
 const base=expandRecipe(initial,{name:'square_base'});
 assert.doesNotMatch(base,/\b(define|d)\b/);
 const petal=expandRecipe(initial+base,{name:'petal_fold',duration_ms:2200,angle_degrees:-170});
 const durations=[...petal.matchAll(/^t ([\d.]+)/gm)].map(m=>Number(m[1]));
 assert.ok(Math.abs(durations.reduce((a,b)=>a+b,0)-2200)<1e-5);
 const executed=compileScript(initial+base+'\n'+petal);
 assert.ok(executed.maxStrain<.03);
});
test('recipes reuse existing base creases and tolerate whole-paper orientation',()=>{
 const prefix=initial+'by2d p0 p2\nby2d p1 p3\nc2d p0 p1\nc2d p1 p2\ntz 45\n';
 const base=expandRecipe(prefix,{name:'square_base'});
 assert.equal(compileScript(prefix+base).model.points.length,9);
 const petal=expandRecipe(prefix+base,{name:'petal_fold'});
 assert.ok(compileScript(prefix+base+'\n'+petal).maxStrain<.03);
});
test('recipes reject incompatible paper and unsupported parameters',()=>{
 assert.throws(()=>expandRecipe(initial,{name:'petal_fold'}),/starting pose/);
 assert.throws(()=>expandRecipe(initial,{name:'square_base',duration_ms:-1}),/duration/);
 const folded=initial+'by2d p0 p2\nt 1500 r s4 -180 p1\n';
 assert.throws(()=>expandRecipe(folded,{name:'square_base'}),/pose/);
});
