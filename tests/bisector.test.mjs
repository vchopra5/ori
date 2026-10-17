import test from 'node:test';
import assert from 'node:assert/strict';
import {Model} from '../src/ori/reconstruction/simulator/vendor/orisim3d/js/Model.js';
const p=(x,y,z=0)=>({x,y,z});
test('bisector uses supporting lines when finite segments stop short of their intersection',()=>{
 const model=new Model().init();let actual;
 model.bisector3dPoints=(a,intersection,c)=>{actual={a,intersection,c};};
 model.bisector3d(p(1,0),p(2,0),p(0,1),p(0,2));
 assert.ok(actual);
 assert.ok(Math.hypot(actual.intersection.x,actual.intersection.y,actual.intersection.z)<1e-9);
});
test('parallel displaced segments produce a plane midway between their supporting lines',()=>{
 const model=new Model().init();
 model.bisector3d(p(-200,0),p(-100,0),p(100,100),p(200,100));
 const interior=model.segments.filter(s=>Math.abs(s.p1.y-50)<1e-6&&Math.abs(s.p2.y-50)<1e-6);
 assert.ok(interior.length);
});
