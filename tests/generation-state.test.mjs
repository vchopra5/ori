import test from 'node:test';
import assert from 'node:assert/strict';
import {generationState} from '../src/ori/coaching/generation-state.mjs';
test('working animation never invents a verdict',()=>{
 assert.equal(generationState({status:'running',events:[{kind:'working'}]}).verdict,'pending');
 assert.equal(generationState({status:'running',events:[{kind:'proposal'}]}).phase,'checking');
});
test('real acceptance, rejection and probes drive the cloud',()=>{
 const events=[{kind:'accepted',step:1},{kind:'rejected'},{kind:'working'}];
 assert.equal(generationState({status:'running',events}).verdict,'fail');
 events.push({kind:'tested',ok:true});assert.equal(generationState({status:'running',events}).verdict,'pass');
 events.push({kind:'tested',ok:false});assert.equal(generationState({status:'running',events}).verdict,'fail');
 assert.equal(generationState({status:'partial',events}).phase,'paused');
 assert.equal(generationState({status:'model_claimed_done',events:[]}).verdict,'pending');
});
test('undo clears the old verdict without pretending physics failed',()=>{
 const state=generationState({status:'running',accepted:0,events:[{kind:'accepted',step:1},{kind:'undone',count:1},{kind:'working'}]});
 assert.equal(state.verdict,'pending');assert.equal(state.detail,'↶ Restored the earlier paper');
});
