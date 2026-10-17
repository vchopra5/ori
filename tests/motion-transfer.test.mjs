import test from 'node:test';
import assert from 'node:assert/strict';
import {compileScript} from '../src/ori/reconstruction/simulator/script-runtime.mjs';
import {expandRecipe,recipes} from '../src/ori/reconstruction/simulator/recipes.mjs';
const base=recipes.petal_fold.prefix;
const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z);

test('native mechanism compilation is deterministic, including intermediate poses',()=>{
 const script=base+recipes.petal_fold.body;
 const a=compileScript(script),b=compileScript(script);
 assert.deepEqual(a.model.snapshotPositions(),b.model.snapshotPositions());
 assert.deepEqual(a.command.paths,b.command.paths);
});

test('petal motion survives subdivision of both stationary and moving edges',()=>{
 const plain=compileScript(base+expandRecipe(base,{name:'petal_fold'}));
 for(const edge of ['s0','s2']){
  const input=base+`split ${edge} 0.5\n`,before=compileScript(input).model;
  const commands=expandRecipe(input,{name:'petal_fold'}),result=compileScript(input+commands);
  assert.ok(result.maxStrain<.03);
  for(let i=0;i<9;i++)assert.ok(distance(plain.model.points[i],result.model.points[i])<1e-5);
  const p=result.model.points[9];assert.equal(p.xf,before.points[9].xf);assert.equal(p.yf,before.points[9].yf);
  if(edge==='s2'){
   const a=result.model.points[2],b=result.model.points[5];
   assert.ok(Math.hypot(p.x-(a.x+b.x)/2,p.y-(a.y+b.y)/2,p.z-(a.z+b.z)/2)<1e-5);
   assert.ok(distance(p,before.points[9])>10);
  }
 }
});

test('flat extra creases remain and their vertices follow the material patch',()=>{
 const input=base+'by2d p5 p7\n',before=compileScript(input).model;
 const result=compileScript(input+expandRecipe(input,{name:'petal_fold'}));
 assert.ok(result.maxStrain<.03);
 assert.ok(result.model.points.length>=before.points.length);
 for(let i=0;i<before.points.length;i++)assert.deepEqual([result.model.points[i].xf,result.model.points[i].yf],[before.points[i].xf,before.points[i].yf]);
 // Every original segment is still covered by collinear material segments.
 for(const old of before.segments){
  const a=old.p1,b=old.p2,dx=b.xf-a.xf,dy=b.yf-a.yf,len=Math.hypot(dx,dy);
  const on=p=>Math.abs((p.xf-a.xf)*dy-(p.yf-a.yf)*dx)<1e-3&&((p.xf-a.xf)*dx+(p.yf-a.yf)*dy)>=-1e-3&&((p.xf-b.xf)*dx+(p.yf-b.yf)*dy)<=1e-3;
  const pieces=result.model.segments.filter(s=>on(s.p1)&&on(s.p2));
  assert.ok(Math.abs(pieces.reduce((sum,s)=>sum+Math.hypot(s.p1.xf-s.p2.xf,s.p1.yf-s.p2.yf),0)-len)<.05);
 }
});

test('second petal preserves the first petal and tolerates turning the paper',()=>{
 const front=expandRecipe(base,{name:'petal_fold'}),first=base+front+'\n';
 const before=compileScript(first).model;
 const back=expandRecipe(first,{name:'petal_fold',material_rotation:180});
 const both=compileScript(first+back);
 for(const i of [2,5,7])assert.ok(distance(before.points[i],both.model.points[i])<1e-5);
 assert.ok(distance(before.points[0],both.model.points[0])>100);
 assert.ok(both.maxStrain<.03);
 const turned=first+'t 1500 ty 180\n';
 const afterTurn=compileScript(turned+expandRecipe(turned,{name:'petal_fold',material_rotation:180}));
 for(let i=0;i<both.model.points.length;i++){
  const a=both.model.points[i],b=afterTurn.model.points[i];
  assert.ok(Math.hypot(a.x+b.x,a.y-b.y,a.z+b.z)<.1);
 }
});

test('already raised flap is rejected instead of resetting or flattening it',()=>{
 const folded=base+expandRecipe(base,{name:'petal_fold'});
 assert.throws(()=>expandRecipe(folded,{name:'petal_fold'}),/starting pose/);
});

test('a recovered historical strain warning is not attributed to the new mechanism',()=>{
 const initial='define 200 200\niad\n';
 const recovered=initial+'t 1000 m 14 0 0 p0\nt 1000 m -14 0 0 p0\n'+base.slice(initial.length);
 const prior=compileScript(recovered);
 assert.ok(prior.maxStrain>.03);
 const result=compileScript(recovered+expandRecipe(recovered,{name:'petal_fold'}));
 assert.ok(Math.max(...result.strainByInstruction.slice(prior.command.instructions.length+1))<.03);
});
