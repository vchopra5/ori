import test from 'node:test';
import assert from 'node:assert/strict';
import {compileScript,registry} from '../src/ori/reconstruction/simulator/script-runtime.mjs';
import {expandRecipe} from '../src/ori/reconstruction/simulator/recipes.mjs';
import {squareBaseTargets,flatStateError,metricError,endpointError,planarRegistration} from '../src/ori/reconstruction/simulator/endpoint-target.mjs';
import {squareBasePosition,coordinatedSquareBase} from '../src/ori/reconstruction/simulator/square-base-path.mjs';
const script='define 200 200\niad\nby2d p0 p2\nby2d p1 p3\nc2d p0 p1\nc2d p1 p2\n';
const spec={state_family:'square_base',flat_at_end:true,center_becomes_closed_tip:true,original_corners_meet_at_open_tip:true,closed_direction:'top',open_direction:'bottom'};
test('endpoint constraints preserve every face metric and retain ambiguous material correspondences',()=>{
 const state=registry(compileScript(script).model),targets=squareBaseTargets(state,spec);
 assert.equal(targets.length,6);
 for(const t of targets){assert.ok(metricError(t)<1e-12);assert.equal(t.constraints.open_corners.length,4);assert.ok(t.unresolved.includes('front/back layer order'));}
 assert.throws(()=>squareBaseTargets(state,{...spec,open_direction:'left'}),/orientation/);
});
test('flat endpoint check rejects a folded sheet even when its segment metric passes',()=>{
 const folded=registry(compileScript(script+'snap\nt 1500 r s11 -180 p1 p2 p7\nsnap').model);
 assert.ok(metricError(folded)<1e-8);
 assert.ok(flatStateError(folded)>300);
 assert.throws(()=>squareBaseTargets(folded,spec),/not flat/);
});
test('independent endpoint distinguishes wrong orientation from matching motion and rejects swapped identities',()=>{
 const start=registry(compileScript(script).model),targets=squareBaseTargets(start,spec);
 const end=registry(compileScript(script+expandRecipe(script,{name:'square_base'})).model);
 assert.ok(Math.min(...targets.map(t=>endpointError(end,t)))>200);
 const fits=targets.map(t=>({t,...planarRegistration(end,t)})).filter(f=>f.error<.25);
 assert.equal(fits.length,1);assert.ok(Math.abs(fits[0].angle_degrees-45)<.01);
 const oriented=script+`t 1000 tz ${fits[0].angle_degrees}\n`;
 const actual=registry(compileScript(oriented+expandRecipe(oriented,{name:'square_base'})).model);
 assert.ok(endpointError(actual,fits[0].t)<.03);
 actual.points[0].id='wrong-material';assert.equal(endpointError(actual,fits[0].t),Infinity);
});
test('coordinated collapse preserves all triangle lengths analytically and moves both lateral corners together',()=>{
 const state=registry(compileScript(script).model);
 for(let i=0;i<=100;i++){
  const positions=state.points.map(p=>squareBasePosition(p.material,200,Math.PI*i/100));
  assert.ok(metricError(state,positions)<1e-12);
  if(i>0&&i<100){assert.ok(positions[1][2]>0);assert.ok(positions[3][2]>0);assert.ok(Math.abs(positions[1][2]-positions[3][2])<1e-8);}
 }
 const prefix=script+'t 1000 tz 45\n',motion=coordinatedSquareBase(prefix);
 const result=compileScript(prefix+motion.commands);
 assert.ok(result.maxStrain<.001);assert.ok(motion.exact_metric_error<1e-12);
 const targets=squareBaseTargets(state,spec),end=registry(result.model);
 // Native whole-sheet turns snap to hundredths; the mechanism preserves that
 // input discrepancy instead of teleporting vertices to its analytic start.
 assert.ok(Math.min(...targets.map(t=>endpointError(end,t)))<.01);
 assert.throws(()=>coordinatedSquareBase(prefix,{samples:0}),/sampling/);
});
