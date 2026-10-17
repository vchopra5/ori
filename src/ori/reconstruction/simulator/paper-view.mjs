import {View3d} from './vendor/orisim3d/js/View3d.js';
import {layerLayout} from './paper-layers.mjs';

// Display thickness and contact offsets never feed back into engine coordinates.
export function paperShell(model,normal,thickness=.35,options={}){
 const mesh={positions:[],normals:[],front:[],back:[],sides:[],lines:[],creases:[],active:[]};
 const layout=layerLayout(model,options.orders,options.spacing??.9),ids=new Map(model.points.map((p,i)=>[p,i]));
 const key=(a,b)=>a<b?`${a}:${b}`:`${b}:${a}`;
 const vertex=(p,n,offset,side)=>{
  const id=mesh.positions.length/3;
  mesh.positions.push(p.x+offset[0],p.y+offset[1],p.z+offset[2]);mesh.normals.push(...n);
  mesh.front.push(p.xf,p.yf);mesh.back.push(p.xf,p.yf);mesh.sides.push(side);return id;
 };
 model.faces.forEach((face,f)=>{
  const pts=face.points,n=normal(pts),half=thickness*(model.scale||1)/2;
  const shift=layout.offsets[f].map((v,k)=>v+(face.offset||0)*n[k]);
  const add=(p,side)=>vertex(p,n.map(v=>v*side),shift.map((v,k)=>v+side*half*n[k]),side===1?0:1);
  for(const side of [1,-1]){
   const indices=new Map();
   for(let i=1;i<pts.length-1;i++)for(const p of side===1?[pts[0],pts[i],pts[i+1]]:[pts[0],pts[i+1],pts[i]]){
    const id=add(p,side);if(!indices.has(p))indices.set(p,id);
   }
   for(let i=0;i<pts.length;i++){
    const p=pts[i],q=pts[(i+1)%pts.length],edgeKey=key(ids.get(p),ids.get(q)),edge=layout.edges.get(edgeKey);
    const pair=[indices.get(p),indices.get(q)];
    const boundary=edge.faces.length===1||edge.faces.some(g=>layout.panels[g]!==layout.panels[f]);
    if(options.activeHinges?.has(edgeKey))mesh.active.push(...pair);
    else if(boundary)mesh.lines.push(...pair);
    else if(options.showCreases)mesh.creases.push(...pair);
   }
  }
  for(let i=0;i<pts.length;i++){
   const a=pts[i],b=pts[(i+1)%pts.length],edge=layout.edges.get(key(ids.get(a),ids.get(b)));
   if(edge.faces.length===2&&edge.faces.every(g=>layout.panels[g]===layout.panels[f]))continue;
   const at=(p,d)=>({x:p.x+n[0]*d,y:p.y+n[1]*d,z:p.z+n[2]*d,xf:p.xf,yf:p.yf});
   const ap=at(a,half),am=at(a,-half),bp=at(b,half),bm=at(b,-half),en=normal([ap,am,bp]);
   for(const p of [ap,am,bp,bp,am,bm])vertex(p,en,shift,2);
  }
 });
 mesh.unresolved=layout.unresolved;return mesh;
}
export class PaperView extends View3d{
 initShaders(){
  this.VERTEX_SHADER=`#version 300 es
  precision highp float;
  in vec4 aVertexPosition;
  in vec3 aVertexNormal;
  in vec2 aTexCoordsFront;
  in vec2 aTexCoordsBack;
  in float aPaperSide;
  uniform mat4 uModelViewMatrix;
  uniform mat4 uProjectionMatrix;
  out vec2 vFront;
  out vec2 vBack;
  out float vSide;
  out float vLight;
  void main(){
   gl_Position=uProjectionMatrix*uModelViewMatrix*aVertexPosition;
   vFront=aTexCoordsFront;vBack=aTexCoordsBack;vSide=aPaperSide;
   vec3 n=normalize((uModelViewMatrix*vec4(aVertexNormal,0.)).xyz);
   vLight=.82+.18*max(0.,dot(n,normalize(vec3(-.3,.5,1.))));
  }`;
  this.FRAGMENT_SHADER=`#version 300 es
  precision highp float;
  in vec2 vFront;
  in vec2 vBack;
  in float vSide;
  in float vLight;
  uniform sampler2D uSamplerFront;
  uniform sampler2D uSamplerBack;
  uniform bool uLine;
  uniform vec4 uInk;
  out vec4 outColor;
  void main(){
   if(uLine){outColor=uInk;return;}
   vec4 color=vSide<.5?texture(uSamplerFront,vFront):vSide<1.5?texture(uSamplerBack,vBack):vec4(.82,.79,.73,1.);
   outColor=vec4(color.rgb*vLight,1.);
  }`;
  super.initShaders();this.uniforms.uInk=this.gl.getUniformLocation(this.gl.program,'uInk');
 }
 syncCanvasSize(){
  const ratio=Math.min(globalThis.devicePixelRatio||1,2),width=Math.round((this.canvas3d.clientWidth||1)*ratio),height=Math.round((this.canvas3d.clientHeight||1)*ratio);
  this.canvas3d.width=width;this.canvas3d.height=height;
  if(this.overlay){this.overlay.width=width;this.overlay.height=height;}return {width,height};
 }
 initPerspective(){super.initPerspective();this.gl.clearColor(.95,.96,.93,1);}
 initBuffers(){
  const gl=this.gl,m=paperShell(this.model,pts=>this.normal(pts),.35,{
   orders:this.layerOrders,spacing:this.separateLayers?7:.9,showCreases:this.showCreases,activeHinges:this.activeHinges,
  });
  this.vao??=gl.createVertexArray();gl.bindVertexArray(this.vao);
  this.vtx=m.positions;this.fnr=m.normals;this.lin=m.lines;this.layerAmbiguities=m.unresolved;
  this.vtxBuffer=this.attribute(this.vtxBuffer,'aVertexPosition',m.positions,3);
  this.fnrBuffer=this.attribute(this.fnrBuffer,'aVertexNormal',m.normals,3);
  this.ftxBuffer=this.attribute(this.ftxBuffer,'aTexCoordsFront',m.front,2);
  this.btxBuffer=this.attribute(this.btxBuffer,'aTexCoordsBack',m.back,2);
  this.sideBuffer=this.attribute(this.sideBuffer,'aPaperSide',m.sides,1);
  this.linePasses=[['outline',[.25,.30,.28,1],m.lines],['crease',[.49,.51,.47,.38],m.creases],['active',[.90,.40,.12,1],m.active]].map(([name,color,indices])=>{
   this[name+'Buffer']??=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,this[name+'Buffer']);
   gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(indices),gl.DYNAMIC_DRAW);return {buffer:this[name+'Buffer'],color,count:indices.length};
  });gl.bindVertexArray(null);
 }
 render(){
  const gl=this.gl;if(!this.vao)return;
  gl.useProgram(gl.program);gl.bindVertexArray(this.vao);gl.enable(gl.DEPTH_TEST);gl.enable(gl.CULL_FACE);gl.cullFace(gl.BACK);
  gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,this.texPlaceholderFront);
  gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,this.texPlaceholderBack);
  gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.uniform1i(this.uniforms.uLine,0);
  gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(1,1);
  gl.drawArrays(gl.TRIANGLES,0,this.vtx.length/3);gl.disable(gl.POLYGON_OFFSET_FILL);
  gl.disable(gl.CULL_FACE);
  if(this.model.lines){
   gl.uniform1i(this.uniforms.uLine,1);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
   for(const pass of this.linePasses){gl.uniform4fv(this.uniforms.uInk,pass.color);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,pass.buffer);gl.drawElements(gl.LINES,pass.count,gl.UNSIGNED_INT,0);}
   gl.disable(gl.BLEND);gl.uniform1i(this.uniforms.uLine,0);
  }
  gl.bindVertexArray(null);this.context2d?.clearRect(0,0,this.overlay.width,this.overlay.height);
 }
}
