// Procedural Huzita–Hatori construction using Rabbit Ear (GPLv3).
// Exports discrete states, not a certified collision-free motion trajectory.
import ear from 'rabbit-ear';
const copy=x=>JSON.parse(JSON.stringify(x));
const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
const cross=(a,b)=>a[0]*b[1]-a[1]*b[0];
export class SymbolicCompiler {
 constructor(graph=ear.graph.square()){
  this.graph=copy(graph);delete this.graph.file_frames;delete this.graph.faceOrders;
  ear.graph.populate(this.graph);this.graph.edges_foldAngle??=ear.graph.makeEdgesFoldAngle(this.graph);
  this.edges=Object.fromEntries(this.graph.edges_vertices.map((_,i)=>['e'+i,[i]]));
  this.faces=Object.fromEntries(this.graph.faces_vertices.map((_,i)=>['f'+i,[i]]));
  this.folds={};this.ids=[];this.frames=[this.frame('Initial state')];
 }
 coords(){return ear.graph.makeVerticesCoordsFolded(this.graph).map(p=>[p[0],p[1],p[2]??0]);}
 frame(title){const g=this.graph;return {frame_title:title,frame_inherit:false,frame_classes:['foldedForm'],frame_attributes:['3D'],vertices_coords:this.coords(),'vertices_ori:uv':copy(g.vertices_coords),edges_vertices:copy(g.edges_vertices),edges_assignment:copy(g.edges_assignment),edges_foldAngle:copy(g.edges_foldAngle),faces_vertices:copy(g.faces_vertices),'ori:uncertainties':['Discrete compiled state; collision-free reachability and layer order have not been verified.']};}
 point(ref,coords){if(typeof ref!=='string'||!/^v\d+$/.test(ref)||!coords[+ref.slice(1)])throw Error(`Unknown point ${ref}`);const p=coords[+ref.slice(1)];if(Math.abs(p[2])>1e-6)throw Error('Axiom construction currently requires a flat XY state.');return p.slice(0,2);}
 line(ref,coords){
  const indices=this.edges[ref];if(!indices?.length)throw Error(`Unknown line ${ref}`);
  const pts=indices.flatMap(e=>this.graph.edges_vertices[e].map(i=>coords[i]));
  const b=pts.find(p=>distance(p,pts[0])>1e-7);if(!b)throw Error(`Line ${ref} is collapsed`);
  const vector=b.slice(0,2).map((v,i)=>v-pts[0][i]),norm=Math.hypot(...vector);
  if(pts.some(p=>Math.abs(p[2])>1e-6||Math.abs(cross(vector,p.slice(0,2).map((v,i)=>v-pts[0][i])))/norm>1e-6))throw Error(`Line ${ref} is no longer straight in this state. Select a current edge.`);
  return {origin:pts[0].slice(0,2),vector};
 }

 catalog(){const coords=this.coords();return {points:coords.map((position,i)=>({ref:'v'+i,material:this.graph.vertices_coords[i],position})),lines:Object.entries(this.edges).map(([ref,edges])=>({ref,edges:edges.map(e=>this.graph.edges_vertices[e].map(v=>'v'+v))})),layers:Object.entries(this.faces).map(([ref,faces])=>({ref,faces:faces.map(f=>this.graph.faces_vertices[f].map(v=>'v'+v))})),folds:Object.keys(this.folds)};}
 validate(){const coords=this.coords();if(coords.flat().some(v=>!Number.isFinite(v)))throw Error('Non-finite compiled coordinates.');let strain=0;for(const [a,b]of this.graph.edges_vertices){const rest=distance(this.graph.vertices_coords[a],this.graph.vertices_coords[b]);if(rest<1e-9)throw Error('Zero-length edge.');strain=Math.max(strain,Math.abs(distance(coords[a],coords[b])/rest-1));}if(strain>.01)throw Error(`Compiled state stretches paper by ${(strain*100).toFixed(2)}%.`);return {max_strain:strain};}
 apply(step){const snapshot=copy({graph:this.graph,edges:this.edges,faces:this.faces,folds:this.folds,ids:this.ids});try{return this.execute(step);}catch(e){Object.assign(this,snapshot);throw e;}}
 execute(step){
  if(!step||typeof step.id!=='string'||!step.id||this.ids.includes(step.id)||typeof step.description!=='string')throw Error('Each step needs a unique id and description.');
  if(step.action==='unfold'){
   const fold=this.folds[step.fold];if(!fold)throw Error('Unknown fold to unfold.');
   for(const change of fold)for(const edge of this.edges[change.ref]){this.graph.edges_foldAngle[edge]=change.before;this.graph.edges_assignment[edge]=change.before===0?'F':change.before>0?'V':'M';}
  }else if(step.action==='fold'||step.action==='crease'){
   const coords=this.coords(),points=(step.points||[]).map(r=>this.point(r,coords)),lines=(step.lines||[]).map(r=>this.line(r,coords));
   const counts={1:[2,0],2:[2,0],3:[0,2],4:[1,1],5:[2,1],6:[2,2],7:[1,2]};
   if(!counts[step.axiom]||points.length!==counts[step.axiom][0]||lines.length!==counts[step.axiom][1])throw Error('Incorrect point/line count for axiom.');
   const args={1:points,2:points,3:lines,4:[lines[0],points[0]],5:[lines[0],points[1],points[0]],6:[...lines,...points],7:[...lines,points[0]]};
   const solutions=ear.axiom['axiom'+step.axiom](...args[step.axiom]);
   const validSolutions=solutions.flatMap((line,i)=>line?[i]:[]);
   const solution=step.solution??(validSolutions.length===1?validSolutions[0]:undefined);
   if(!Number.isInteger(solution)||!solutions[solution])throw Error('Select solution index. Candidates: '+JSON.stringify(solutions));
   if(!['V','M'].includes(step.assignment))throw Error('assignment must be V or M.');
   if(step.layers!=='all'&&(!Array.isArray(step.layers)||!step.layers.length))throw Error('Select nonempty layer refs or all.');
   const selected=new Set(step.layers==='all'?this.graph.faces_vertices.map((_,i)=>i):step.layers.flatMap(ref=>{if(!this.faces[ref])throw Error('Unknown layer '+ref);return this.faces[ref];}));
   const previous=copy(this.graph.edges_foldAngle),oldAssignments=copy(this.graph.edges_assignment);
   const event=ear.graph.foldLine(this.graph,solutions[solution],step.assignment,step.action==='crease'?0:step.assignment==='V'?180:-180,coords.map(p=>p.slice(0,2)));
   const remap=(dict,map)=>{for(const ref of Object.keys(dict))dict[ref]=[...new Set(dict[ref].flatMap(i=>map[i]??[]))];};
   remap(this.edges,event.edges.map);remap(this.faces,event.faces.map);
   const selectedAfter=new Set([...selected].flatMap(i=>event.faces.map[i]??[]));
   const prior={};event.edges.map.forEach((mapped,i)=>{for(const e of mapped??[])prior[e]={angle:previous[i],assignment:oldAssignments[i]};});
   const touched=[...new Set([...event.edges.new,...event.edges.reassigned])],active=[];
   for(const e of touched){const allowed=this.graph.edges_faces[e].some(f=>selectedAfter.has(f));if(!allowed){this.graph.edges_foldAngle[e]=prior[e]?.angle??0;this.graph.edges_assignment[e]=prior[e]?.assignment??'F';}else if(this.graph.edges_assignment[e]!=='B'){active.push(e);}}
   if(!active.length)throw Error('This crease does not intersect the selected layers. Choose a different solution or layer.');
   this.folds[step.id]=active.map((e,i)=>{const ref=step.id+'.hinge'+i;this.edges[ref]=[e];return {ref,before:prior[e]?.angle??0};});
   this.edges[step.id+'.crease']=active;
   delete this.graph.faceOrders; // all-layer ordering from foldLine is not valid after masking.
   this.graph.edges_vertices.forEach((_,i)=>{this.edges[step.id+'.e'+i]=[i];});
   this.graph.faces_vertices.forEach((_,i)=>{this.faces[step.id+'.f'+i]=[i];});
  }else throw Error('Supported actions: fold, crease, unfold. No raw code or mesh arrays.');
  const check=this.validate();this.ids.push(step.id);this.frames.push(this.frame(step.description));return check;
 }
 export(){return {file_spec:1.2,file_creator:'ORI symbolic compiler / Rabbit Ear 0.9.4',file_title:'Symbolic video reconstruction',...this.frames[0],file_frames:this.frames.slice(1)};}
}
