import test from 'node:test';
import assert from 'node:assert/strict';
import {rendererFor} from '../src/ori/reconstruction/simulator/renderer-routing.mjs';
test('one player routes supported instruction formats and rejects unknown engines',()=>{
 assert.equal(rendererFor({engine:'orisim3d',steps:[]}),'orisim3d');
 assert.equal(rendererFor('define 200 200'),'orisim3d');
 assert.equal(rendererFor({vertices_coords:[]}),'fold');
 assert.equal(rendererFor({file_frames:[]}),'fold');
 assert.equal(rendererFor([]),'fold');
 assert.throws(()=>rendererFor({engine:'unknown',steps:[]}));
 assert.throws(()=>rendererFor({hello:'world'}));
});
