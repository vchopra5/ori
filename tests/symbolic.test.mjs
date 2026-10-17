import test from 'node:test';import assert from 'node:assert/strict';
import {SymbolicCompiler} from '../src/ori/reconstruction/symbolic/compiler.mjs';
test('axiom point alignment and unfold preserve topology and sheet metric',()=>{
 const c=new SymbolicCompiler();const a={id:'half',description:'Fold in half',action:'fold',axiom:2,points:['v0','v1'],layers:'all',assignment:'V'};
 assert.ok(c.apply(a).max_strain<1e-10);assert.ok(Math.hypot(...c.coords()[0].map((v,i)=>v-c.coords()[1][i]))<1e-7);
 const count=c.graph.edges_vertices.length;c.apply({id:'open',description:'Unfold',action:'unfold',fold:'half'});
 assert.equal(c.graph.edges_vertices.length,count);assert.ok(Math.abs(Math.hypot(...c.coords()[0].map((v,i)=>v-c.coords()[1][i]))-1)<1e-7);
 assert.equal(c.export().file_frames.length,2);
});
test('failed actions are transactional and scripts cannot inject native commands',()=>{
 const c=new SymbolicCompiler(),before=JSON.stringify(c.export());
 assert.throws(()=>c.apply({id:'bad',description:'Invalid',action:'commands',commands:'anything'}));
 assert.equal(JSON.stringify(c.export()),before);
});
test('unfold keeps working after another construction subdivides the first crease',()=>{
 const c=new SymbolicCompiler();c.apply({id:'half',description:'Half',action:'fold',axiom:2,points:['v0','v1'],layers:'all',assignment:'V'});
 c.apply({id:'cross',description:'Cross crease',action:'crease',axiom:2,points:['v1','v2'],layers:'all',assignment:'V'});
 c.apply({id:'open',description:'Unfold half',action:'unfold',fold:'half'});
 assert.ok(c.validate().max_strain<1e-10);assert.equal(c.ids.length,3);
 assert.ok(Math.abs(Math.hypot(...c.coords()[0].map((v,i)=>v-c.coords()[1][i]))-1)<1e-7);
});
test('axiom 3 aligns parallel edges without supplied coordinates',()=>{
 const c=new SymbolicCompiler();c.apply({id:'align',description:'Align edges',action:'fold',axiom:3,lines:['e0','e2'],layers:['f0'],assignment:'V'});
 assert.ok(c.validate().max_strain<1e-10);assert.ok(c.graph.vertices_coords.length>4);
});
test('axiom 5 moves the first point onto a line through the second point',()=>{
 const c=new SymbolicCompiler();c.apply({id:'a5',description:'Point to edge through corner',action:'fold',axiom:5,points:['v0','v3'],lines:['e1'],layers:'all',assignment:'V'});
 const p=c.coords();
 // The moving corner coincides with the opposite corner; the through-corner stays on the hinge.
 assert.ok(Math.hypot(...p[0].map((v,i)=>v-p[2][i]))<1e-7);
});
