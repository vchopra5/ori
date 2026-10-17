// Compatibility adapter for previously generated point-to-point action plans.
const EPS=1e-7;
export function pointFold(action) {
  const valid=p=>Array.isArray(p)&&p.length===2&&p.every(v=>Number.isFinite(v)&&v>=0&&v<=1);
  const a=action.moving_point_uv,b=action.target_point_uv;
  if(!valid(a)||!valid(b)||Math.hypot(a[0]-b[0],a[1]-b[1])<EPS||!Number.isFinite(action.angle_degrees)||action.angle_degrees<=0||action.angle_degrees>180||!['toward_front','toward_back'].includes(action.fold_direction))throw Error('Missing point-fold geometry.');
  const mid=a.map((v,i)=>(v+b[i])/2),normal=b.map((v,i)=>v-a[i]);
  const distance=p=>(p[0]-mid[0])*normal[0]+(p[1]-mid[1])*normal[1];
  const square=[[0,0],[1,0],[1,1],[0,1]];
  function clip(sign){const out=[];square.forEach((p,i)=>{const q=square[(i+1)%4],dp=sign*distance(p),dq=sign*distance(q);if(dp>=-EPS)out.push(p);if(dp>EPS&&dq<-EPS||dp<-EPS&&dq>EPS){const t=dp/(dp-dq);out.push(p.map((v,j)=>v+t*(q[j]-v)));}});return out;}
  const vertices=[],edges=[],edgeMap=new Map();
  const vertex=p=>{let i=vertices.findIndex(v=>Math.hypot(v[0]-p[0],v[1]-p[1])<EPS);if(i<0){i=vertices.length;vertices.push([...p]);}return i;};
  const faces=[clip(1),clip(-1)].map(poly=>poly.map(vertex));
  for(const face of faces)face.forEach((a,i)=>{const b=face[(i+1)%face.length],key=[a,b].sort((x,y)=>x-y).join(',');if(!edgeMap.has(key)){edgeMap.set(key,edges.length);edges.push([a,b]);}});
  const angle=(action.fold_direction==='toward_front'?1:-1)*action.angle_degrees;
  const assignments=edges.map(([a,b])=>Math.abs(distance(vertices[a]))<EPS&&Math.abs(distance(vertices[b]))<EPS?(angle>0?'V':'M'):'B');
  return {file_spec:1.2,file_creator:'Ori point-alignment adapter',file_title:action.description||'Point fold',frame_classes:['creasePattern'],frame_attributes:['2D'],vertices_coords:vertices,edges_vertices:edges,faces_vertices:faces,edges_assignment:assignments,edges_foldAngle:assignments.map(a=>a==='V'||a==='M'?angle:0),'ori:provenance':'Derived locally from extracted alignment; video correspondence unverified.'};
}

export function planStages(actions,template){
  let flat=true,open=null,complex=false;
  const sources=new Map();
  return actions.map((action,index)=>{
    const stage={description:action?.description||`Action ${index+1}`,kind:action?.kind,index};
    if(action?.kind==='fold'&&(action.template==='square_base_collapse'||(!Object.hasOwn(action,'template')&&/collaps/i.test(stage.description)&&/square base/i.test(stage.description)))){
      complex=true;flat=false;
      return {...stage,fold:structuredClone(template),from:0,to:1,template:true,note:`${action.template?'Explicit template selected by the instruction.':'Legacy description matched to a template.'} Canonical square-base geometry comes from the template, not Gemini. Orientation and layer correspondence to the video require review.`};
    }
    if(!complex&&action?.kind==='fold'&&flat){
      try{const fold=pointFold(action);sources.set(index+1,fold);flat=false;open=index+1;return {...stage,fold,from:0,to:1,note:'FOLD crease mesh derived from the extracted point alignment.'};}catch{}
    }
    if(!complex&&action?.kind==='unfold'&&action.reverse_step===open&&sources.has(open)){
      const fold=structuredClone(sources.get(open));flat=true;open=null;return {...stage,fold,from:1,to:0,note:'Reverses the referenced crease targets; the crease remains in the mesh.'};
    }
    if(!['rotate','turn_over'].includes(action?.kind)){complex=true;flat=false;}
    return {...stage,note:'No supported geometry for this action yet. Select the square-base template or another supported action to inspect it.'};
  });
}

export function validateFold(value){
  if(!value||!Array.isArray(value.vertices_coords)||!Array.isArray(value.edges_vertices)||!Array.isArray(value.faces_vertices))throw Error('Expected a FOLD mesh with vertices_coords, edges_vertices, and faces_vertices.');
  if(value.vertices_coords.length>2000||value.faces_vertices.length>4000)throw Error('This prototype supports up to 2,000 vertices / 4,000 faces.');
  const fold=structuredClone(value),n=fold.vertices_coords.length;
  const dimension=fold.vertices_coords[0]?.length;
  if(n<3||![2,3].includes(dimension)||fold.vertices_coords.some(p=>!Array.isArray(p)||p.length!==dimension||!p.every(Number.isFinite)))throw Error('Expected finite, consistently 2D or 3D FOLD vertices.');
  const valid=i=>Number.isInteger(i)&&i>=0&&i<n;
  if(fold.edges_vertices.some(e=>!Array.isArray(e)||e.length!==2||!e.every(valid)||e[0]===e[1])||fold.faces_vertices.some(f=>!Array.isArray(f)||f.length<3||!f.every(valid)))throw Error('Invalid FOLD edge or face indices.');
  if(fold.edges_assignment?.length!==fold.edges_vertices.length||fold.edges_assignment.some(a=>!['B','M','V','F','U'].includes(a)))throw Error('Supply an assignment (B/M/V/F/U) for every edge.');
  fold.edges_foldAngle??=fold.edges_assignment.map(a=>a==='M'?-180:a==='V'?180:0);
  if(fold.edges_foldAngle.length!==fold.edges_vertices.length||fold.edges_foldAngle.some(a=>!Number.isFinite(a)||Math.abs(a)>180))throw Error('Supply finite fold angles between -180 and 180 degrees.');
  return fold;
}

// FOLD key frame is frame 0; file_frames contains frames 1 onward.
export function foldStages(document){
  const {file_frames=[],...root}=document;
  if(!Array.isArray(file_frames))throw Error('file_frames must be an array.');
  const frames=[root,...file_frames],resolved=[];
  return frames.map((raw,index)=>{
    let frame=raw;
    try{
      if(!raw||typeof raw!=='object')throw Error('Invalid frame.');
      if(raw.frame_inherit){const parent=raw.frame_parent??0;if(!Number.isInteger(parent)||parent<0||parent>=index||!resolved[parent])throw Error('Unsupported or invalid parent frame.');frame={...resolved[parent],...raw};}
      resolved.push(frame);
      const fold=validateFold(frame);delete fold.frame_parent;delete fold.frame_inherit;
      const state=fold.vertices_coords[0].length===3||fold.frame_classes?.includes('foldedForm');
      return {description:fold.frame_title||fold.file_title||`Frame ${index}`,kind:state?'Folded state':'Crease pattern',fold,state,from:0,to:1,note:state?'Geometry supplied by the file. State preview only; physical reachability and layer order are not verified.':'Crease geometry supplied by the file; GPU simulation applies its target angles.',uncertainties:raw['ori:uncertainties']};
    }catch(error){if(resolved.length<=index)resolved.push(null);return {description:raw?.frame_title||`Frame ${index}`,kind:'Unresolved state',note:error.message,uncertainties:raw?.['ori:uncertainties']};}
  });
}
