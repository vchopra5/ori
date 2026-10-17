// One-parameter coordinated preliminary-base mechanism on eight rigid triangles.
// The two stationary sectors meet at (-h,-h). The opposite rigid panel rotates
// by alpha about the diagonal axis (1,-1,0). The lateral corners follow beta,
// with tan(beta/2)=sqrt(2)*tan(alpha/2), derived from their fixed edge lengths.
// This is a reusable mechanism, not a video-specific sequence of point guesses.
import {compileScript,registry} from './script-runtime.mjs';
import {flatStateError,metricError} from './endpoint-target.mjs';

export function squareBasePosition(uv,h,alpha){
 const [x,y]=uv.map(v=>Math.round(v/h)),c=Math.cos(alpha),s=Math.sin(alpha);
 const beta=2*Math.atan2(Math.SQRT2*Math.sin(alpha/2),Math.cos(alpha/2));
 const cb=Math.cos(beta),sb=Math.sin(beta);
 const positions={
  '0,0':[0,0,0],'-1,-1':[-h,-h,0],
  '1,-1':[h*cb,-h,h*sb],'-1,1':[-h,h*cb,h*sb],
  '1,1':[h*c,h*c,Math.SQRT2*h*s],
  '0,-1':[0,-h,0],'-1,0':[-h,0,0],
  '0,1':[h*(c-1)/2,h*(c+1)/2,h*s/Math.SQRT2],
  '1,0':[h*(c+1)/2,h*(c-1)/2,h*s/Math.SQRT2],
 };
 if(!positions[`${x},${y}`]||Math.hypot(uv[0]-x*h,uv[1]-y*h)>.001)throw Error('Mechanism requires the nine base vertices.');
 return positions[`${x},${y}`];
}

export function coordinatedSquareBase(script,{duration=4000,samples=60}={}){
 if(!Number.isFinite(duration)||duration<300||duration>10000||!Number.isInteger(samples)||samples<20||samples>120)throw Error('Invalid mechanism sampling parameters.');
 const model=compileScript(script).model,state=registry(model);
 if(state.points.length!==9||flatStateError(state)>.01)throw Error('Mechanism requires a verified flat nine-vertex square.');
 const h=Math.max(...state.points.flatMap(p=>p.material.map(Math.abs)));
 const origin=state.points.find(p=>Math.hypot(...p.material)<.001)?.position;
 const east=state.points.find(p=>Math.hypot(p.material[0]-h,p.material[1])<.001)?.position;
 if(!origin||!east)throw Error('Missing mechanism anchors.');
 // Registry positions are rounded; normalize the frame so rounding cannot
 // introduce scale into an otherwise rigid registration.
 const length=Math.hypot(east[0]-origin[0],east[1]-origin[1]);
 const co=(east[0]-origin[0])/length,si=(east[1]-origin[1])/length;
 const transform=p=>[origin[0]+co*p[0]-si*p[1],origin[1]+si*p[0]+co*p[1],origin[2]+p[2]];
 const initial=state.points.map(p=>transform(squareBasePosition(p.material,h,0)));
 if(initial.some((p,i)=>Math.hypot(...p.map((v,k)=>v-state.points[i].position[k]))>.01))throw Error('Mechanism supports only a flat in-plane rigid starting pose.');
 let previous=initial,exactMetric=0;const lines=[...(model.snap?['snap']:[]),'il'];
 const number=v=>String(Number(v.toFixed(9)));
 for(let frame=1;frame<=samples;frame++){
  const positions=state.points.map(p=>transform(squareBasePosition(p.material,h,Math.PI*frame/samples)));
  exactMetric=Math.max(exactMetric,metricError(state,positions));
  const moves=positions.flatMap((p,i)=>{
   const delta=p.map((v,k)=>v-previous[i][k]);
   return Math.hypot(...delta)>1e-8?[`m ${delta.map(number).join(' ')} ${state.points[i].id}`]:[];
  });
  lines.push(`t ${number(duration/samples)} ${moves.join(' ')}`);previous=positions;
 }
 lines.push('iad',...(model.snap?['snap']:[]));
 if(exactMetric>1e-8)throw Error('Analytic mechanism did not preserve the face metric.');
 const commands=lines.join('\n');compileScript(script+'\n'+commands);
 return {commands,exact_metric_error:exactMetric};
}
