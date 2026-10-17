import {legoFrame,turnPose} from './lego-motion.mjs';
import {frameAt, layerOffsets, rotate, foldGuide, foldProgress} from './paper-motion.mjs';
/* Rendering only. Sample motion is illustrative, never a physics validation. */
const T = window.THREE;
export class StudioScene {
  constructor(canvas) {
    if (!T) throw new Error('The local 3D renderer could not be loaded.');
    this.canvas = canvas;
    this.renderer = new T.WebGLRenderer({canvas, antialias:true, alpha:true, preserveDrawingBuffer:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.gammaInput = true;this.renderer.gammaOutput = true;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = T.PCFSoftShadowMap;
    this.scene = new T.Scene();
    this.scene.add(new T.HemisphereLight(0xffffff, 0xc9c7e3, .88));
    const light = new T.DirectionalLight(0xffffff, .45);
    light.position.set(-3, 7, 4); light.castShadow = true;
    light.shadow.mapSize.width = light.shadow.mapSize.height = 2048;
    Object.assign(light.shadow.camera, {left:-6,right:6,top:6,bottom:-6});
    light.shadow.bias = -.001; light.shadow.radius = 4; this.scene.add(light);
    const floor = new T.Mesh(new T.PlaneGeometry(200,200), new T.ShadowMaterial({opacity:.06,depthWrite:false}));
    floor.rotation.x = -Math.PI/2;floor.position.y=-.04;floor.receiveShadow=true;this.scene.add(floor);
    this.camera = new T.PerspectiveCamera(31,1,.01,300);
    this.angle = -.12; this.elevation=.43; this.distance=10.5;
    this.target = new T.Vector3(0,.65,0);this.setCamera();
    this.root = new T.Group();this.scene.add(this.root);
    this.markers = new T.Group();this.scene.add(this.markers);
    this.foldGuides=new T.Group();this.scene.add(this.foldGuides);this.guideVisible=true;
    this.mode='toy'; this.time=0; this.contactVisible=true; this.paperColor='apricot';
    this.paperTexture=this.makePaperTexture();
    this.buildToy();
    this.resizeObserver = new ResizeObserver(()=>this.resize());this.resizeObserver.observe(canvas.parentElement);
    let pointer = null;
    canvas.addEventListener('pointerdown', e=>{pointer={x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId);});
    canvas.addEventListener('pointermove', e=>{if(!pointer)return;this.angle-=(e.clientX-pointer.x)*.006;this.elevation=Math.max(.12,Math.min(1.5,this.elevation+(e.clientY-pointer.y)*.004));pointer={x:e.clientX,y:e.clientY};this.setCamera();this.render();});
    const release=()=>{pointer=null;};canvas.addEventListener('pointerup',release);canvas.addEventListener('pointercancel',release);canvas.addEventListener('lostpointercapture',release);
    canvas.addEventListener('wheel',e=>{e.preventDefault();this.distance=Math.max(5,Math.min(18,this.distance+e.deltaY*.008));this.setCamera();this.render();},{passive:false});
  }
  material(color){return new T.MeshStandardMaterial({color,roughness:.65,metalness:0});}
  mesh(geometry,color,parent=this.root){const mesh=new T.Mesh(geometry,this.material(color));mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;}
  clear(group){while(group.children.length){const child=group.children[0];group.remove(child);child.traverse(node=>{node.geometry?.dispose();if(node.material){for(const material of Array.isArray(node.material)?node.material:[node.material])material.dispose();}});}}
  buildToy(){
    this.clear(this.root);this.clear(this.markers);this.clear(this.foldGuides);this.mode='toy';this.angle=-.12;this.elevation=.43;this.distance=10.5;this.target.set(0,.65,0);this.setCamera();
    const shape=new T.Shape();shape.moveTo(-.38,0);shape.lineTo(.38,0);shape.lineTo(.04,.83);shape.lineTo(-.04,.83);shape.closePath();
    const pivot=this.mesh(new T.ExtrudeGeometry(shape,{depth:.52,amount:.52,bevelEnabled:true,bevelSegments:3,steps:1,bevelSize:.055,bevelThickness:.055}),0xe6dfcf);pivot.position.z=-.26;
    this.beam=new T.Group();this.beam.position.y=.9;this.root.add(this.beam);
    this.mesh(new T.BoxGeometry(4.8,.16,.62),0xa6bdf0,this.beam);
    this.ball=this.mesh(new T.SphereGeometry(.245,40,30),0xf1a99c,this.beam);
    this.block=this.mesh(new T.BoxGeometry(.36,.42,.36),0xf0df9b,this.beam);this.block.position.set(1.7,.29,0);
    const hub=this.mesh(new T.CylinderGeometry(.1,.1,.67,32),0xc0c5cf);hub.rotation.x=Math.PI/2;hub.position.y=.86;
    this.contact=this.mesh(new T.SphereGeometry(.035,16,12),0x5278ec,this.markers);
    const path=new T.Geometry();for(let i=0;i<=48;i++){const x=-1.65+i/48*3.35;path.vertices.push(new T.Vector3(x,1.42+Math.sin(i/48*Math.PI)*.4,0));}
    this.trajectory=new T.Line(path,new T.LineDashedMaterial({color:0x7e9deb,dashSize:.075,gapSize:.075,transparent:true,opacity:.65}));path.computeLineDistances();this.markers.add(this.trajectory);
    this.setTime(0);
  }
  setLego(replay){
    if(replay.version===2)return this.setLegoAssembly(replay);
    this.mode='lego';this.replay=replay;this.legoGuideStep=-1;this.clear(this.root);this.clear(this.markers);this.clear(this.foldGuides);
    const pieces=replay.pieces, xs=pieces.flatMap(p=>[p.position[0],p.position[0]+p.size[0]]), zs=pieces.flatMap(p=>[p.position[1],p.position[1]+p.size[1]]);
    const cx=(Math.min(...xs)+Math.max(...xs))/2,cz=(Math.min(...zs)+Math.max(...zs))/2;
    const height=Math.max(...pieces.map(p=>(p.position[2]+p.size[2])*.4));
    const scale=3.5/Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...zs)-Math.min(...zs),height,4);
    this.legoNodes=pieces.map(p=>{
      const group=new T.Group();this.root.add(group);const [w,d,h]=p.size;
      this.mesh(new T.BoxGeometry(w-.025,h*.4,d-.025),p.hex,group);
      for(let x=0;x<w;x++)for(let y=0;y<d;y++){
        const stud=this.mesh(new T.CylinderGeometry(.3,.3,.2,20),p.hex,group);
        stud.position.set(x+.5-w/2,h*.2+.1,y+.5-d/2);
      }
      group.scale.setScalar(scale);group.position.set((p.position[0]+w/2-cx)*scale,(p.position[2]*.4+h*.2)*scale+.02,(p.position[1]+d/2-cz)*scale);
      return group;
    });
    this.angle=-.5;this.elevation=.65;this.distance=10;this.target.set(0,height*scale/2,0);this.setCamera();this.setTime(0);
  }
  setLegoAssembly(replay){
    this.mode='lego';this.replay=replay;this.legoGuideStep=-1;this.clear(this.root);this.clear(this.markers);this.clear(this.foldGuides);
    const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
    for(const state of replay.states)for(const p of replay.pieces){
      const pose=state.poses[p.id];if(!pose)continue;
      for(const shape of p.solids)for(const v of shape.vertices)pose.origin.forEach((x,i)=>{const value=x+pose.matrix[i].reduce((sum,r,j)=>sum+r*v[j],0);lo[i]=Math.min(lo[i],value);hi[i]=Math.max(hi[i],value);});
    }
    this.legoCenter=[(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,0];this.legoScale=3.5/Math.max(...hi.map((x,i)=>x-lo[i]),4);
    this.legoNodes=replay.pieces.map(p=>{
      const group=new T.Group();group.matrixAutoUpdate=false;this.root.add(group);
      for(const solid of p.solids){
        const geometry=new T.Geometry();geometry.vertices=solid.vertices.map(v=>new T.Vector3(...v));
        for(const face of solid.faces)for(let i=1;i<face.length-1;i++)geometry.faces.push(new T.Face3(face[0],face[i],face[i+1]));
        geometry.computeFaceNormals();const mesh=this.mesh(geometry,p.hex,group);mesh.material.side=T.DoubleSide;
      }
      this.addLegoHinge(p,group);
      p.studs.forEach((point,i)=>{const frame=p.stud_frames[i],normal=new T.Vector3(frame[0][2],frame[1][2],frame[2][2]);const stud=this.mesh(new T.CylinderGeometry(.3,.3,.2,20),p.hex,group);stud.position.set(...point).addScaledVector(normal,.1);stud.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),normal);});
      return group;
    });
    this.angle=-.5;this.elevation=.65;this.distance=10;this.target.set(0,hi[2]*this.legoScale/2,0);this.setCamera();this.setTime(0);
  }
  addLegoHinge(piece,group){
    if(!piece.part.startsWith('hinge_'))return;
    const base=piece.part.startsWith('hinge_base'),z=base ? .7 : -.4;
    // Visible plastic knuckles and pin bores. These details do not change colliders.
    const xs=base?[.12,1.88]:[.4,.8,1.2,1.6];
    for(const x of xs){
      const ring=this.mesh(new T.TorusGeometry(base ? .23 : .21,.065,12,28),piece.hex,group);ring.rotation.y=Math.PI/2;ring.position.set(x,.5,z);
      const sleeve=this.mesh(new T.CylinderGeometry(.24,.24,.16,28,1,true),piece.hex,group);sleeve.rotation.z=Math.PI/2;sleeve.position.set(x,.5,z);
      if(!base){const arm=this.mesh(new T.BoxGeometry(.12,.16,.32),piece.hex,group);arm.position.set(x,.5,-.16);}
    }
  }
  legoMatrix(pose){
    const s=this.legoScale,c=this.legoCenter,r=pose.matrix,t=pose.origin;
    return new T.Matrix4().set(s*r[0][0],s*r[0][1],s*r[0][2],s*(t[0]-c[0]),s*r[2][0],s*r[2][1],s*r[2][2],s*t[2]+.02,-s*r[1][0],-s*r[1][1],-s*r[1][2],-s*(t[1]-c[1]),0,0,0,1);
  }
  focusLego(){
    const frame=legoFrame(this.replay,this.time),point=frame.target||this.replay.states[frame.index].poses[frame.active].origin,s=this.legoScale,c=this.legoCenter;
    this.target.set((point[0]-c[0])*s,point[2]*s+.2,-(point[1]-c[1])*s);this.distance=5;this.elevation=.55;this.setCamera();this.render();
  }
  drawLego(time){
    const frame=legoFrame(this.replay,time);this.legoFrame=frame;
    this.legoNodes.forEach((node,i)=>{const id=this.replay.pieces[i].id,pose=frame.poses[id];node.visible=Boolean(pose);if(!pose)return;
      node.matrix.copy(this.legoMatrix(pose));node.matrixWorldNeedsUpdate=true;
      node.traverse(mesh=>{if(!mesh.material)return;const active=frame.moving.includes(id);mesh.material.transparent=Boolean(this.legoXray&&!active);mesh.material.opacity=this.legoXray&&!active ? .22 : 1;mesh.material.depthWrite=!this.legoXray||active;if(mesh.material.emissive)mesh.material.emissive.setHex(active&&frame.u<.8?0x151a25:0);});
    });
    const guidePhase=frame.u>=.8?'done':this.replay.steps[frame.index].motion&&frame.u>=.5?'turn':'place';
    const guideKey=`${frame.index}:${guidePhase}`;
    if(this.legoGuideStep!==guideKey){
      this.clear(this.foldGuides);this.legoGuideStep=guideKey;
      this.buildLegoGuide(frame,guidePhase);
    }
    this.foldGuides.visible=this.guideVisible;
  }
  buildLegoGuide(frame,phase){
    if(!frame.target)return;
    const step=this.replay.steps[frame.index],motion=step.motion,s=this.legoScale,c=this.legoCenter;
    const world=p=>new T.Vector3((p[0]-c[0])*s,p[2]*s+.02,-(p[1]-c[1])*s);
    const direction=p=>new T.Vector3(p[0],p[2],-p[1]).normalize();
    const color=phase==='done'?0x15856b:0x365de3;
    const material=hex=>new T.MeshBasicMaterial({color:hex,depthTest:false,depthWrite:false});
    const add=(geometry,hex,order)=>{const mesh=new T.Mesh(geometry,material(hex));mesh.renderOrder=order;this.foldGuides.add(mesh);return mesh;};
    const tube=(points,radius,hex,order)=>add(new T.TubeGeometry(new T.CatmullRomCurve3(points),48,radius,8,false),hex,order);
    const arrow=points=>{
      // White casing keeps the direction readable against any brick color.
      tube(points,.032,0xffffff,30);tube(points,.017,color,31);
      const end=points[points.length-1],dir=end.clone().sub(points[points.length-2]).normalize();
      for(const [r,h,hex,order] of [[.085,.18,0xffffff,32],[.062,.15,color,33]]){
        const head=add(new T.ConeGeometry(r,h,24),hex,order);
        head.position.copy(end).addScaledVector(dir,-h/2);head.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),dir);
      }
    };
    let pose=this.replay.states[frame.index].poses[frame.active];
    if(motion&&phase==='place')pose=turnPose(pose,motion.pivot,motion.axis,-motion.degrees);
    const normal=direction(pose.matrix.map(row=>row[2]));
    const points=step.targets?.length?step.targets:[frame.target];
    // Outline the mating sites instead of hiding their geometry with solid dots.
    for(const p of points){
      for(const [radius,width,hex,order] of [[.105,.022,0xffffff,24],[.105,.011,color,25]]){
        const ring=add(new T.TorusGeometry(radius,width,8,32),hex,order);
        ring.position.copy(world(p));ring.quaternion.setFromUnitVectors(new T.Vector3(0,0,1),motion?direction(motion.axis):normal);
      }
    }
    if(phase==='done')return;
    const center=world(frame.target);
    if(motion&&(phase==='turn'||step.action==='rotate_hinge')){
      const axis=direction(motion.axis),finalNormal=direction(this.replay.states[frame.index].poses[frame.active].matrix.map(row=>row[2]));
      const start=finalNormal.clone().applyAxisAngle(axis,-motion.degrees*Math.PI/180);
      const arc=[];
      for(let i=0;i<=32;i++)arc.push(center.clone().addScaledVector(start.clone().applyAxisAngle(axis,motion.degrees*Math.PI/180*i/32),.65));
      if(Math.abs(motion.degrees)>.1)arrow(arc);
    }else{
      // One arrow into the center of the connection pattern; rings mark each socket.
      const centerTarget=points.reduce((sum,p)=>sum.add(world(p)),new T.Vector3()).multiplyScalar(1/points.length);
      arrow([centerTarget.clone().addScaledVector(normal,.85),centerTarget.clone().addScaledVector(normal,.48),centerTarget.clone().addScaledVector(normal,.14)]);
    }
  }

  makePaperTexture(){
    const canvas=document.createElement('canvas');canvas.width=canvas.height=256;
    const ctx=canvas.getContext('2d'), pixels=ctx.createImageData(256,256);let seed=19;
    for(let i=0;i<pixels.data.length;i+=4){seed=(seed*1664525+1013904223)>>>0;const n=248+(seed%6);pixels.data.set([n,n,n,255],i);}
    ctx.putImageData(pixels,0,0);ctx.strokeStyle='rgba(120,120,120,.035)';
    for(let i=0;i<90;i++){ctx.beginPath();ctx.moveTo((i*73)%256,(i*37)%256);ctx.lineTo((i*73)%256+12,(i*37)%256+3);ctx.stroke();}
    const texture=new T.CanvasTexture(canvas);texture.wrapS=texture.wrapT=T.RepeatWrapping;texture.repeat.set(2,2);return texture;
  }
  setPaper(replay){
    this.mode='paper';this.replay=replay;this.lastPaperStep=-1;this.paperNodes=[];
    this.clear(this.root);this.clear(this.markers);this.setPaperView('perspective');this.setTime(0);
  }
  setPaperView(view){
    this.angle=view==='top'?0:-.24;this.elevation=view==='top'?1.56:1.06;this.distance=9.4;
    this.target.set(0,.24,-.25);this.setCamera();this.render();
  }
  setFoldGuide(value){
    this.guideVisible=value;if(this.mode==='paper'){this.lastPaperStep=-1;this.setTime(this.time);}
  }
  buildFoldGuide(motion){
    this.clear(this.foldGuides);const guide=foldGuide(motion);if(!guide)return;
    const convert=p=>new T.Vector3(p[0]*1.8,.24+p[2]*1.8,-p[1]*1.8);
    const stroke=(a,b,radius,color,order)=>{
      const delta=new T.Vector3().subVectors(b,a),length=delta.length();if(length<1e-8)return;
      const mesh=new T.Mesh(new T.CylinderGeometry(radius,radius,length,8),new T.MeshBasicMaterial({color:new T.Color(color).convertGammaToLinear(),depthTest:false,depthWrite:false,transparent:true,opacity:.95}));
      mesh.position.copy(a).add(b).multiplyScalar(.5);mesh.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),delta.normalize());mesh.renderOrder=order;this.foldGuides.add(mesh);
    };
    for(const [start,end]of guide.segments){
      const a=convert(start),b=convert(end),length=a.distanceTo(b),direction=new T.Vector3().subVectors(b,a).normalize();
      for(let t=0;t<length;t+=.12){const from=a.clone().addScaledVector(direction,t),to=a.clone().addScaledVector(direction,Math.min(length,t+.075));stroke(from,to,.017,0xffffff,100);stroke(from,to,.009,0x3152c4,101);}
    }
    if(guide.arrow.length){
      const points=guide.arrow.map(convert),curve=new T.Curve();
      curve.getPoint=t=>convert(rotate(guide.arrow[0],motion.crease,guide.angle*t));
      const size=Math.min(1,guide.arcLength*1.8/.5);
      const blue=new T.Color(0x3152c4).convertGammaToLinear();
      const material=(color,hidden=false)=>hidden
        ?new T.MeshBasicMaterial({color,depthTest:true,depthWrite:false,depthFunc:T.GreaterDepth,transparent:true,opacity:.36})
        :new T.MeshStandardMaterial({color,roughness:.55,metalness:0,depthTest:true,depthWrite:false,transparent:true});
      const addTube=(path,radius,color,hidden,order)=>{
        const mesh=new T.Mesh(new T.TubeGeometry(path,48,radius,6,false),material(color,hidden));
        mesh.renderOrder=order;this.foldGuides.add(mesh);return mesh;
      };
      // Sweep the head along the same arc as the shaft, with one shared join.
      const headStart=1-Math.min(.28,.11*size/curve.getLength());
      const shaft=new T.Curve();shaft.getPoint=t=>curve.getPointAt(t*headStart);
      addTube(shaft,.015*size,0xffffff,false,104);
      addTube(shaft,.008*size,blue,false,105).name='fold-arrow-shaft';
      const dashCount=Math.max(4,Math.ceil(curve.getLength()*headStart/.09));
      for(let i=0;i<dashCount;i++){
        // End with a dash touching the head, rather than a floating gap.
        const dash=new T.Curve();
        dash.getPoint=t=>shaft.getPoint((i+.45+t*.55)/dashCount);
        addTube(dash,.007*size,blue,true,106);
      }
      const geometry=new T.Geometry(),rings=12,sides=16;
      const axis=convert(motion.crease[1]).sub(convert(motion.crease[0])).normalize();
      for(let i=0;i<rings;i++){
        const fraction=i/rings,t=headStart+(1-headStart)*fraction;
        const center=curve.getPointAt(t),tangent=curve.getTangentAt(t);
        const lateral=new T.Vector3().crossVectors(tangent,axis).normalize();
        for(let j=0;j<sides;j++){
          const angle=j/sides*Math.PI*2,radius=.037*size*(1-fraction);
          geometry.vertices.push(center.clone().addScaledVector(axis,Math.cos(angle)*radius).addScaledVector(lateral,Math.sin(angle)*radius));
        }
      }
      const tip=geometry.vertices.length;geometry.vertices.push(points.at(-1).clone());
      const base=geometry.vertices.length;geometry.vertices.push(curve.getPointAt(headStart));
      for(let i=0;i<rings;i++)for(let j=0;j<sides;j++){
        const a=i*sides+j,b=i*sides+(j+1)%sides;
        if(i<rings-1){const c=a+sides,d=b+sides;geometry.faces.push(new T.Face3(a,b,c),new T.Face3(b,d,c));}
        else geometry.faces.push(new T.Face3(a,b,tip));
        if(i===0)geometry.faces.push(new T.Face3(base,b,a));
      }
      geometry.computeFaceNormals();geometry.computeVertexNormals();
      for(const hidden of [false,true]){
        const head=new T.Mesh(geometry.clone(),material(blue,hidden));
        head.name=hidden?'fold-arrowhead-hidden':'fold-arrowhead';
        head.renderOrder=107;this.foldGuides.add(head);
      }
      geometry.dispose();
    }
  }
  setPaperColor(color){this.paperColor=color;if(this.mode==='paper'){this.lastPaperStep=-1;this.setTime(this.time);}}
  drawPaper(time){
    const frame=frameAt(this.replay,time);
    const coordinates=frame.panels.flatMap(p=>p.vertices),span=Math.max(...[0,1,2].map(k=>Math.max(...coordinates.map(p=>p[k]))-Math.min(...coordinates.map(p=>p[k]))));
    this.paperFit=Math.max(.6,Math.min(1.25,span/1.9));this.setCamera();
    if(frame.index!==this.lastPaperStep){
      this.lastPaperStep=frame.index;this.buildFoldGuide(frame.motion);this.clear(this.root);this.clear(this.markers);this.paperNodes=[];
      const palette={lilac:[0x8974bd,0xf5e9cf],apricot:[0xd96950,0xf5e9cf],ivory:[0x65977f,0xf5e9cf]}[this.paperColor];
      this.startOffsets=layerOffsets(frame.motion?.panels||frame.panels);
      this.endOffsets=frame.motion?layerOffsets(frame.motion.panels,true):this.startOffsets;
      for(const panel of frame.panels){
        const geometry=new T.Geometry();
        panel.vertices.forEach(()=>geometry.vertices.push(new T.Vector3()));
        for(let j=1;j<panel.vertices.length-1;j++){
          geometry.faces.push(new T.Face3(0,j,j+1));
          geometry.faceVertexUvs[0].push([0,j,j+1].map(i=>new T.Vector2(...panel.material[i])));
        }
        const group=new T.Group();this.root.add(group);
        for(const [color,side]of [[palette[0],T.FrontSide],[palette[1],T.BackSide]]){
          const tint=new T.Color(color).convertGammaToLinear();
          // Contact-order depth adds a subtle tonal cue to lower paper layers.
          const depth=this.startOffsets.get(panel.id)?.[2]||0;
          tint.multiplyScalar(1-Math.min(.12,Math.max(0,-depth)*5));
          const material=new T.MeshStandardMaterial({color:tint,side,roughness:.92,metalness:0,map:this.paperTexture,
            bumpMap:this.paperTexture,bumpScale:.001,polygonOffset:true,polygonOffsetFactor:1,polygonOffsetUnits:1});
          const mesh=new T.Mesh(geometry,material);mesh.castShadow=true;mesh.receiveShadow=true;mesh.frustumCulled=false;group.add(mesh);
        }
        const edgeGeometry=new T.Geometry();panel.vertices.forEach(()=>edgeGeometry.vertices.push(new T.Vector3(),new T.Vector3()));
        const edge=new T.LineSegments(edgeGeometry,new T.LineBasicMaterial({color:0x806c68,transparent:true,opacity:.4}));group.add(edge);
        const creaseGeometry=edgeGeometry.clone(),crease=new T.LineSegments(creaseGeometry,new T.LineBasicMaterial({color:0x6376a7,transparent:true,opacity:.48}));this.markers.add(crease);
        this.paperNodes.push({geometry,edgeGeometry,creaseGeometry,group,crease,panel});
      }
    }
    this.foldGuides.visible=this.guideVisible&&!!frame.motion;
    const moving=new Set(frame.motion?.moving||[]),t=frame.fraction,eased=foldProgress(t),angle=(frame.motion?.angle_degrees||0)*Math.PI/180*eased;
    for(let i=0;i<frame.panels.length;i++){
      const panel=frame.panels[i],node=this.paperNodes[i];let offset=this.startOffsets.get(panel.id)||[0,0,0];
      if(frame.motion&&frame.motion.type!=='compound'&&moving.has(panel.id))offset=rotate(offset,frame.motion.crease,angle,true);
      const blend=Math.max(0,(eased-.84)/.16),end=this.endOffsets.get(panel.id)||offset;
      offset=offset.map((x,k)=>x*(1-blend)+end[k]*blend);
      const convert=p=>new T.Vector3(p[0]*1.8,.24+p[2]*1.8,-p[1]*1.8);
      panel.vertices.forEach((p,j)=>node.geometry.vertices[j].copy(convert(p)));
      node.geometry.computeFaceNormals();node.geometry.verticesNeedUpdate=true;node.geometry.normalsNeedUpdate=true;
      panel.vertices.forEach((p,j)=>{node.edgeGeometry.vertices[j*2].copy(convert(p));node.edgeGeometry.vertices[j*2+1].copy(convert(panel.vertices[(j+1)%panel.vertices.length]));});
      node.edgeGeometry.verticesNeedUpdate=true;
      node.edgeGeometry.vertices.forEach((v,j)=>node.creaseGeometry.vertices[j].copy(v));node.creaseGeometry.verticesNeedUpdate=true;
      node.group.position.set(offset[0]*1.8,offset[2]*1.8,-offset[1]*1.8);node.crease.position.copy(node.group.position);
    }
  }
  setTime(time){this.time=time;if(this.mode==='lego'&&this.replay.version===2){this.drawLego(time);}else if(this.mode==='lego'){const step=Math.floor(time/this.replay.seconds_per_step);this.legoNodes.forEach((node,i)=>{node.visible=i<=step;});}else if(this.mode==='paper'){this.drawPaper(time);}else{const t=Math.max(0,Math.min(1,time/12));this.beam.rotation.z=.085-Math.sin(t*Math.PI/2)*.21;this.ball.position.set(-1.65+Math.min(1,t*1.12)*3.03,.325,0);this.ball.rotation.z=-t*12;this.block.position.x=1.7+Math.max(0,t-.86)*1.1;this.beam.updateMatrixWorld(true);this.contact.position.copy(this.beam.localToWorld(new T.Vector3(this.ball.position.x,.08,0)));}this.markers.visible=this.contactVisible;this.render();}
  setContacts(value){this.contactVisible=value;this.markers.visible=value;this.render();}
  setCamera(){const distance=this.distance*(this.mode==='paper'?(this.paperFit||1):1)*Math.max(1,1.15/this.camera.aspect);this.camera.position.set(Math.sin(this.angle)*distance,Math.sin(this.elevation)*distance,Math.cos(this.angle)*Math.cos(this.elevation)*distance);const focus=this.target.clone();if(this.mode==='paper'&&this.camera.aspect<1)focus.z-=.6;this.camera.lookAt(focus);}
  resize(){const {width,height}=this.canvas.parentElement.getBoundingClientRect();if(!width||!height)return;this.renderer.setSize(width,height,false);this.camera.aspect=width/height;this.camera.updateProjectionMatrix();this.setCamera();this.render();}
  render(){this.renderer.render(this.scene,this.camera);}
  thumbnail(time){const old=this.time,guide=this.guideVisible;this.guideVisible=false;this.lastPaperStep=-1;this.setTime(time);const capture=document.createElement('canvas');capture.width=300;capture.height=150;const ctx=capture.getContext('2d');ctx.drawImage(this.canvas,0,this.canvas.height*.18,this.canvas.width,this.canvas.height*.65,0,0,300,150);const url=capture.toDataURL();this.guideVisible=guide;this.lastPaperStep=-1;this.setTime(old);return url;}
}
