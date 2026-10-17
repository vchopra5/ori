import test from 'node:test';
import assert from 'node:assert/strict';
import {rotate,poseAt,frameAt,layerOffsets,foldGuide,foldProgress} from '../src/ori/coaching/paper-motion.mjs';
const distance=(a,b)=>Math.hypot(...a.map((x,i)=>x-b[i]));
const motion={crease:[[-1,0,0],[1,0,0]],angle_degrees:180,moving:['flap'],panels:[
 {id:'flap',vertices:[[-1,0,0],[1,0,0],[0,1,0]],contacts:{base:[0,0,1]},end_contacts:{base:[0,0,-1]}},
 {id:'base',vertices:[[-1,0,0],[0,-1,0],[1,0,0]],contacts:{flap:[0,0,-1]},end_contacts:{flap:[0,0,1]}}
]};
test('intermediate browser poses preserve distances instead of shrinking the sheet',()=>{
 for(let i=0;i<=30;i++){const [flap,base]=poseAt(motion,i/30);
  assert.ok(Math.abs(distance(flap.vertices[0],flap.vertices[2])-Math.SQRT2)<1e-12);
  assert.deepEqual(base.vertices,motion.panels[1].vertices);
  assert.deepEqual(flap.vertices[0],[-1,0,0]);
 }
 assert.ok(poseAt(motion,.5)[0].vertices[2][2]>.999);
});
test('layer display follows contact order and packet turnover without editing vertices',()=>{
 const before=JSON.stringify(motion.panels),start=layerOffsets(motion.panels),end=layerOffsets(motion.panels,true);
 assert.ok(start.get('flap')[2]>start.get('base')[2]);
 assert.ok(end.get('flap')[2]<end.get('base')[2]);
 assert.equal(JSON.stringify(motion.panels),before);
});
test('timeline boundaries retain the initial and completed final pose',()=>{
 const replay={states:[motion.panels],motions:[motion],seconds_per_step:2.6};
 assert.equal(frameAt(replay,0).index,0);
 assert.equal(frameAt(replay,2.59).motion,null);
 const final=frameAt(replay,5.2);assert.equal(final.fraction,1);
 assert.ok(Math.abs(final.panels[0].vertices[2][1]+1)<1e-12);
 assert.ok(distance(rotate([0,0,1],motion.crease,Math.PI,true),[0,0,-1])<1e-12);
});

test('the active crease is clipped to real moving-paper edges, not command endpoints',()=>{
 const input={...motion,crease:[[-100,0,0],[100,0,0]]};
 const guide=foldGuide(input);
 assert.deepEqual(guide.segments,[[[-1,0,0],[1,0,0]]]);
 assert.ok(guide.arrow.some(p=>p[2]>.1));
 const reverse=foldGuide({...input,angle_degrees:-180});
 assert.ok(reverse.arrow.some(p=>p[2]<-.1));
});
test('separate hinge intervals are not joined across missing paper',()=>{
 const panel=(id,x)=>({id,vertices:[[x,0,0],[x+.25,0,0],[x+.1,1,0]]});
 const input={...motion,moving:['a','b'],panels:[panel('a',-1),panel('b',.5)]};
 assert.equal(foldGuide(input).segments.length,2);
});
test('instructional timing holds the starting crease and finished pose',()=>{
 assert.equal(foldProgress(0),0);assert.equal(foldProgress(.19),0);
 assert.equal(foldProgress(.81),1);assert.equal(foldProgress(1),1);
 assert.ok(Math.abs(foldProgress(.5)-.5)<1e-12);
 assert.deepEqual(poseAt(motion,.19)[0].vertices,motion.panels[0].vertices);
});

test('an asymmetric flap arrow follows the departure of a real interior point',()=>{
 const input={...motion,panels:[{id:'flap',vertices:[[0,0,0],[2,0,0],[2,.12,0]]}]};
 const guide=foldGuide(input),start=[4/3,.04,0];
 assert.ok(distance(guide.arrow[0],start)<1e-12);
 assert.ok(distance(guide.arrow.at(-1),rotate(start,input.crease,Math.PI/3))<1e-12);
 for(const p of guide.arrow)assert.ok(Math.abs(Math.hypot(p[1],p[2])-.04)<1e-12);
 assert.ok(guide.arcLength<.13,'small flaps must not get oversized arrows');
});
test('signed folds about an oblique hinge have the correct endpoint and tangent',()=>{
 const crease=[[0,0,0],[1,1,1]];
 for(const angle_degrees of [-135,45,180]){
  const input={...motion,crease,angle_degrees,panels:[{id:'flap',vertices:[[0,0,0],[1,1,1],[0,1,0]]}]};
  const guide=foldGuide(input),angle=Math.sign(angle_degrees)*Math.min(Math.abs(angle_degrees),60)*Math.PI/180,start=guide.arrow[0];
  assert.ok(distance(guide.arrow.at(-1),rotate(start,crease,angle))<1e-12);
  const prior=rotate(start,crease,angle-Math.sign(angle)*1e-6);
  const delta=guide.arrow.at(-1).map((x,i)=>x-prior[i]),length=Math.hypot(...delta);
  assert.ok(distance(guide.tangent,delta.map(x=>x/length))<1e-6);
 }
});
test('zero-angle and degenerate hinges do not produce misleading arrows',()=>{
 assert.deepEqual(foldGuide({...motion,angle_degrees:0}).arrow,[]);
 assert.deepEqual(foldGuide({...motion,crease:[[0,0,0],[0,0,0]]}).arrow,[]);
});

test('backward direction cues keep pointing into the sheet instead of returning out',()=>{
 for(const degrees of [-180,-135,-90,-30,30,90,135,180]){
  const guide=foldGuide({...motion,angle_degrees:degrees}),sign=Math.sign(degrees);
  for(let i=1;i<guide.arrow.length;i++)assert.ok(sign*(guide.arrow[i][2]-guide.arrow[i-1][2])>0);
  assert.ok(sign*guide.tangent[2]>0,'head must keep the departure direction');
  assert.ok(Math.abs(guide.angle)<=Math.abs(degrees*Math.PI/180),'cue must not exceed the fold');
 }
});
