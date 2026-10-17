import test from 'node:test';
import assert from 'node:assert/strict';
import {legoFrame,turnPose} from '../src/ori/coaching/lego-motion.mjs';
const eye=[[1,0,0],[0,1,0],[0,0,1]],pose={origin:[1,2,3],matrix:eye};
const close=(a,b)=>a.forEach((x,i)=>assert.ok(Math.abs(x-b[i])<1e-9));
test('hinge interpolation rotates around the pin without stretching',()=>{
 const result=turnPose(pose,[1,1,1],[1,0,0],90);
 close(result.origin,[1,-1,2]);
 close(result.matrix[0],[1,0,0]);
 const back=turnPose(result,[1,1,1],[1,0,0],-90);
 close(back.origin,pose.origin);
});
test('animated placement converges to the accepted pose and is seekable',()=>{
 const replay={seconds_per_step:5.5,states:[{poses:{a:pose}}],steps:[{piece:'a',action:'place'}]};
 const start=legoFrame(replay,0),end=legoFrame(replay,5.5);
 assert.ok(start.poses.a.origin[2]>pose.origin[2]);close(end.poses.a.origin,pose.origin);
 assert.deepEqual(legoFrame(replay,1),legoFrame(replay,1));assert.deepEqual(pose.origin,[1,2,3]);
});
test('hinge motion preserves descendants as one rigid assembly',()=>{
 const child={origin:[1,3,3],matrix:eye};
 const replay={seconds_per_step:5.5,states:[{poses:{a:pose,b:child}}],steps:[{piece:'a',action:'rotate_hinge',motion:{pivot:[1,1,1],axis:[1,0,0],degrees:60,affected:['a','b']}}]};
 for(const t of [0,1,2,3,5.5]){
  const f=legoFrame(replay,t),a=f.poses.a.origin,b=f.poses.b.origin;
  assert.ok(Math.abs(Math.hypot(...a.map((v,i)=>v-b[i]))-1)<1e-9);
 }
 close(legoFrame(replay,5.5).poses.b.origin,child.origin);
});
