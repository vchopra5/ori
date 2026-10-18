import test from 'node:test';
import assert from 'node:assert/strict';
import {paperRevision,animatePaperUndo} from '../src/ori/coaching/paper-undo.mjs';
import {poseAt} from '../src/ori/coaching/paper-motion.mjs';

const a={name:'base'},wrong={name:'inward ear'},right={name:'correct ear'};
test('detects undo even when the replacement arrives in the same poll',()=>{
  assert.deepEqual(paperRevision([a,wrong],[a,right],2.6,7.8),{shared:1,from:7.8,to:5.2,hasReplacement:true});
  assert.equal(paperRevision([a],[a,right],2.6,5.2),null);
  assert.equal(paperRevision([a,wrong],[a],2.6,7.8).hasReplacement,false);
  assert.equal(paperRevision([a,wrong],[a],2.6,6).from,6);
});
test('undo reverses monotonically and preserves rigid paper geometry',async()=>{
  let callback;const values=[];
  const motion={crease:[[0,0,0],[1,0,0]],angle_degrees:180,moving:['ear'],panels:[{id:'ear',vertices:[[0,0,0],[1,0,0],[0,1,0]]}]};
  const done=animatePaperUndo({from:7.8,to:5.2},{valid:()=>true,frame:fn=>callback=fn,draw:time=>{
    values.push(time);const vertices=poseAt(motion,(time-5.2)/2.6)[0].vertices;
    assert.ok(Math.abs(Math.hypot(...vertices[2])-1)<1e-10);
  }});
  for(const time of [0,400,800,1200,1601])callback(time);
  assert.equal(await done,true);assert.equal(values[0],7.8);assert.equal(values.at(-1),5.2);
  assert.ok(values.every((value,i)=>i===0||value<values[i-1]));
});
test('navigating away cancels undo without drawing into the new lesson',async()=>{
  let callback,valid=true,draws=0;
  const done=animatePaperUndo({from:7.8,to:5.2},{valid:()=>valid,frame:fn=>callback=fn,draw:()=>draws++});
  callback(0);valid=false;callback(100);
  assert.equal(await done,false);assert.equal(draws,1);
});
