import test from 'node:test';
import assert from 'node:assert/strict';
import {paperShell} from '../src/ori/reconstruction/simulator/paper-view.mjs';
import {compileScript} from '../src/ori/reconstruction/simulator/script-runtime.mjs';
import {View3d} from '../src/ori/reconstruction/simulator/vendor/orisim3d/js/View3d.js';
test('thin shell adds two surfaces and edges without changing engine geometry',()=>{
 const {model}=compileScript('define 200 200');const before=JSON.stringify(model);
 const mesh=paperShell(model,p=>View3d.prototype.normal(p),.45);
 assert.equal(mesh.positions.length/3,36);
 assert.ok(mesh.positions.every(Number.isFinite));
 assert.deepEqual([...new Set(mesh.positions.filter((_,i)=>i%3===2))].sort(),[-.225,.225]);
 assert.equal(JSON.stringify(model),before);
 assert.ok(mesh.lines.every(i=>Number.isInteger(i)&&i<36));
});
import {pausablePlayback} from '../src/ori/reconstruction/simulator/playback-clock.mjs';
test('pausing a recorded motion freezes time and resumes without jumping',()=>{
 let time=100,calls=0;const command={transition:{start:0},pause(){},play(){},anim(){calls++;return true;},goTo(){}};
 pausablePlayback(command,()=>time);command.pause();time=700;
 assert.equal(command.anim(),false);assert.equal(calls,0);
 command.play();assert.equal(command.transition.start,600);assert.equal(command.anim(),true);
 command.pause();command.goTo(1);assert.equal(command.anim(),true);
});
