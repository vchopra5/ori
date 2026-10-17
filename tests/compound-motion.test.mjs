import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {poseAt,foldProgress,foldGuide} from '../src/ori/coaching/paper-motion.mjs';

test('coordinated browser playback preserves the same material metric at arbitrary times',()=>{
  const replay=JSON.parse(execFileSync('.venv/bin/python',['-c',`import json
from tests.test_fold_compound import base_commands,collapse
from ori.coaching.paper_playback import compile_playback
print(json.dumps(compile_playback(base_commands()+[collapse()])))`],{env:{...process.env,PYTHONPATH:'src'},encoding:'utf8'}));
  const motion=replay.motions.at(-1);
  for(const t of [.201,.271,.389,.507,.643,.729,.8,1]){
    const panels=poseAt(motion,t),shared=new Map();
    for(const p of panels)for(let i=0;i<p.material.length;i++){
      for(let j=0;j<i;j++){
        const distance=(a,b)=>Math.hypot(...a.map((x,k)=>x-b[k]));
        assert.ok(Math.abs(distance(p.vertices[i],p.vertices[j])-distance(p.material[i],p.material[j]))<1e-8);
      }
      const key=p.material[i].join(',');
      if(shared.has(key))assert.deepEqual(p.vertices[i],shared.get(key));
      shared.set(key,p.vertices[i]);
    }
    if(t===1)for(let i=0;i<panels.length;i++)assert.deepEqual(panels[i].vertices,replay.states.at(-1)[i].vertices);
  }
  assert.equal(foldGuide(motion),null); // Never draw a false single-hinge arrow.
});
