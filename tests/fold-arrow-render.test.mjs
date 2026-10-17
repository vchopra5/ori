import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {foldGuide} from '../src/ori/coaching/paper-motion.mjs';

// Exercise the actual renderer orientation with its vendored Three.js math.
const context={};
vm.runInNewContext(readFileSync(new URL('../src/ori/reconstruction/simulator/vendor/origami-simulator/dependencies/three.min.js',import.meta.url),'utf8'),context);
const T=context.THREE;
globalThis.window={THREE:T};
const {StudioScene}=await import('../src/ori/coaching/scene.mjs');
delete globalThis.window;
const convert=p=>new T.Vector3(p[0]*1.8,.24+p[2]*1.8,-p[1]*1.8);

test('curved 3D heads join the shaft, end at the departure cue, and stay fixed while orbiting',()=>{
 for(const degrees of [-180,-90,90,180]){
  const motion={crease:[[-1,0,0],[1,0,0]],angle_degrees:degrees,moving:['flap'],panels:[{id:'flap',vertices:[[-1,0,0],[1,0,0],[0,1,0]]}]};
  const guide=foldGuide(motion),end=convert(guide.arrow.at(-1));
  const studio=Object.create(StudioScene.prototype);
  studio.foldGuides=new T.Group();studio.camera=new T.PerspectiveCamera(31,1,.01,300);
  studio.renderer={render(){}};
  studio.buildFoldGuide(motion);
  for(const name of ['fold-arrowhead','fold-arrowhead-hidden']){
    const head=studio.foldGuides.getObjectByName(name);
    const vertices=head.geometry.vertices,tip=vertices.at(-2),base=vertices.at(-1);
    const shaft=studio.foldGuides.getObjectByName('fold-arrow-shaft');
    assert.ok(base.distanceTo(shaft.geometry.parameters.path.getPoint(1))<1e-10,'shaft must end at the head base');
    assert.ok(tip.distanceTo(end)<1e-10,'tip must meet the direction cue endpoint');
    for(let ring=0;ring<12;ring++){
      const center=vertices.slice(ring*16,(ring+1)*16).reduce((sum,v)=>sum.add(v),new T.Vector3()).multiplyScalar(1/16);
      assert.ok(Math.abs(Math.hypot(center.y-.24,center.z)-.6)<1e-10,`head centerline must stay on the fold arc: ${center.toArray()} ring ${ring}`);
    }
    assert.ok(head.material.depthTest);
    const quaternion=head.quaternion.clone(),position=head.position.clone();
    for(const elevation of [.4,1.06,1.56])for(const azimuth of [-.8,0,.8]){
      studio.camera.position.set(Math.sin(azimuth)*9,Math.sin(elevation)*9,Math.cos(azimuth)*Math.cos(elevation)*9);
      studio.camera.lookAt(new T.Vector3(0,.24,-.25));studio.render();
      assert.ok(head.quaternion.equals(quaternion),'orbit must not rotate the arrowhead');
      assert.ok(head.position.equals(position),'orbit must not move the arrowhead');

    }
  }
  studio.clear(studio.foldGuides);
 }
});
