// A living origami sculpture: a single square folds along a coordinated linkage.
export function createHomeScene(canvas, pauseButton, replayButton, caption) {
  const T=window.THREE;
  if(!T)return;
  let renderer;
  try{renderer=new T.WebGLRenderer({canvas,alpha:true,antialias:true});}catch{return;}
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
  renderer.setClearColor(0x000000,0);renderer.gammaInput=true;renderer.gammaOutput=true;
  const scene=new T.Scene(),camera=new T.PerspectiveCamera(34,1,.1,100);
  camera.position.set(2.7,4.5,7.8);camera.lookAt(new T.Vector3(0,.1,0));
  scene.add(new T.HemisphereLight(0xffffff,0x8e94bc,.95));
  const key=new T.DirectionalLight(0xffffff,.85);key.position.set(-3,6,5);scene.add(key);
  const rim=new T.DirectionalLight(0xc5d8ff,.55);rim.position.set(4,2,-4);scene.add(rim);
  const sculpture=new T.Group();sculpture.scale.setScalar(1.12);scene.add(sculpture);
  // Eight rigid triangular sectors of ONE square. The lateral hinges follow
  // the closed-form square-base linkage, so the paper never stretches or
  // breaks into floating parts as it folds.
  const materialPoints=[[0,0],[-1,-1],[0,-1],[1,-1],[1,0],[1,1],[0,1],[-1,1],[-1,0]];
  const geometry=new T.Geometry();
  materialPoints.forEach(()=>geometry.vertices.push(new T.Vector3()));
  for(let i=1;i<=8;i++)geometry.faces.push(new T.Face3(0,i,i===8?1:i+1));
  const front=new T.MeshStandardMaterial({color:new T.Color(0x8c9fe6).convertGammaToLinear(),roughness:.88,metalness:0,side:T.FrontSide});
  const back=new T.MeshStandardMaterial({color:new T.Color(0xf6e6ce).convertGammaToLinear(),roughness:.95,metalness:0,side:T.BackSide});
  sculpture.add(new T.Mesh(geometry,front),new T.Mesh(geometry,back));
  const seams=new T.Geometry();
  for(let i=1;i<=8;i++)seams.vertices.push(new T.Vector3(),new T.Vector3());
  sculpture.add(new T.LineSegments(seams,new T.LineBasicMaterial({color:0x5369ac,transparent:true,opacity:.22})));
  const border=new T.Geometry();
  for(let i=0;i<=8;i++)border.vertices.push(new T.Vector3());
  sculpture.add(new T.Line(border,new T.LineBasicMaterial({color:0xffffff,transparent:true,opacity:.65})));
  // A soft pool of light grounds the floating paper without a mechanical stand.
  const shadowCanvas=document.createElement('canvas');shadowCanvas.width=shadowCanvas.height=128;
  const ctx=shadowCanvas.getContext('2d'),gradient=ctx.createRadialGradient(64,64,0,64,64,64);
  gradient.addColorStop(0,'rgba(75,83,139,.16)');gradient.addColorStop(1,'rgba(75,83,139,0)');
  ctx.fillStyle=gradient;ctx.fillRect(0,0,128,128);
  const shadow=new T.Mesh(new T.PlaneGeometry(5.8,5.8),new T.MeshBasicMaterial({map:new T.CanvasTexture(shadowCanvas),transparent:true,depthWrite:false}));
  shadow.rotation.x=-Math.PI/2;shadow.position.y=-1.1;scene.add(shadow);
  function fold(alpha){
    const c=Math.cos(alpha),s=Math.sin(alpha);
    const beta=2*Math.atan2(Math.SQRT2*Math.sin(alpha/2),Math.cos(alpha/2));
    const cb=Math.cos(beta),sb=Math.sin(beta);
    const points=[[0,0,0],[-1,-1,0],[0,-1,0],[cb,-1,sb],
      [(c+1)/2,(c-1)/2,s/Math.SQRT2],[c,c,Math.SQRT2*s],
      [(c-1)/2,(c+1)/2,s/Math.SQRT2],[-1,cb,sb],[-1,0,0]];
    // Material XY is rotated 45 degrees into a diamond and laid in world XZ.
    const center=new T.Vector3();
    points.forEach(([x,y,z],i)=>{geometry.vertices[i].set((x-y)*Math.SQRT2*.8,z*1.6,-(x+y)*Math.SQRT2*.8);center.add(geometry.vertices[i]);});
    center.multiplyScalar(1/points.length);
    geometry.vertices.forEach(v=>v.sub(center));
    geometry.computeFaceNormals();geometry.verticesNeedUpdate=true;geometry.normalsNeedUpdate=true;
    for(let i=1;i<=8;i++){seams.vertices[(i-1)*2].copy(geometry.vertices[0]);seams.vertices[(i-1)*2+1].copy(geometry.vertices[i]);}
    for(let i=0;i<=8;i++)border.vertices[i].copy(geometry.vertices[i%8+1]);
    seams.verticesNeedUpdate=true;border.verticesNeedUpdate=true;
  }
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let paused=reduced.matches,visible=false,frame=null,last=0,time=paused?7:2.5,pointer={x:0,y:0};
  const smooth=t=>{t=Math.max(0,Math.min(1,t));return t*t*(3-2*t);};
  function draw(){
    const cycle=time%18;
    const closed=smooth((cycle-1)/5)*(1-smooth((cycle-12)/5));
    // Hold an open sculptural fold long enough to read the paper's facets.
    const alpha=closed*Math.PI*.54;
    fold(alpha);
    sculpture.position.y=.15+Math.sin(time*.65)*.09;
    sculpture.rotation.set(.18+pointer.y*.12,Math.sin(time*.22)*.48+pointer.x*.22,-.12);
    shadow.scale.setScalar(1-.12*closed);
    const label=closed>.98?'A single sheet. A little wonder.':cycle<9?'Every possibility begins with one fold.':'Unfold your curiosity. Make something new.';
    if(caption.textContent!==label)caption.textContent=label;
    renderer.render(scene,camera);
  }
  function tick(now){frame=null;if(!visible||paused||document.hidden)return;time+=Math.min((now-last)/1000,.05);last=now;draw();frame=requestAnimationFrame(tick);}
  function sync(){
    if(frame!==null){cancelAnimationFrame(frame);frame=null;}
    pauseButton.textContent=paused?'Play animation':'Pause animation';
    if(visible){draw();if(!paused&&!document.hidden){last=performance.now();frame=requestAnimationFrame(tick);}}
  }
  const observer=new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;sync();});observer.observe(canvas);
  const resize=new ResizeObserver(()=>{const {width,height}=canvas.getBoundingClientRect();if(!width||!height)return;renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();draw();});resize.observe(canvas);
  canvas.addEventListener('pointermove',event=>{const rect=canvas.getBoundingClientRect();pointer={x:(event.clientX-rect.left)/rect.width*2-1,y:(event.clientY-rect.top)/rect.height*2-1};if(paused)draw();});
  canvas.addEventListener('pointerleave',()=>{pointer={x:0,y:0};if(paused)draw();});
  pauseButton.onclick=()=>{paused=!paused;sync();};
  replayButton.onclick=()=>{time=0;paused=false;sync();};
  document.addEventListener('visibilitychange',sync);
  reduced.addEventListener('change',()=>{paused=reduced.matches;if(paused)time=7;sync();});
  pauseButton.hidden=false;replayButton.hidden=false;
  draw();
}
