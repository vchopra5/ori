import test from 'node:test';
import assert from 'node:assert/strict';
import {nextMatchCount,motionScore} from '../src/ori/coaching/coach-state.mjs';
const match={provider:'local-dinov2',verdict:'match',advance_allowed:true,similarity:.95,margin:.08,shape_agreement:.94};
test('requires repeated local shape matches, not a confidence percentage',()=>{
  assert.equal(nextMatchCount(nextMatchCount(0,match),match),2);
  for(const changes of [{verdict:'unclear'},{verdict:'before_fold'},{advance_allowed:false},{provider:'gemini'},{similarity:.87},{similarity:NaN}])assert.equal(nextMatchCount(1,{...match,...changes}),0);
  assert.equal(nextMatchCount(1,{verdict:'match',confidence:.99}),0);
  assert.equal(nextMatchCount(1,{...match,margin:0}),2);
});
test('motion gate waits for stable frames',()=>{
  const a=new Uint8ClampedArray([10,10,10,255,20,20,20,255]);
  assert.equal(motionScore(null,a),Infinity);assert.equal(motionScore(a,a),0);
  assert.equal(motionScore(a,new Uint8ClampedArray([30,30,30,255,40,40,40,255])),20);
});
test('a Gemini pass advances immediately without local similarity or depth gates',()=>{
  assert.equal(nextMatchCount(0,{provider:'gemini-assisted',verdict:'match',advance_allowed:true}),2);
  for(const verdict of ['unclear','before_fold','mistake'])assert.equal(nextMatchCount(1,{provider:'gemini-assisted',verdict,advance_allowed:false}),0);
  assert.equal(nextMatchCount(1,{provider:'gemini-assisted',verdict:'match',advance_allowed:false}),0);
});
