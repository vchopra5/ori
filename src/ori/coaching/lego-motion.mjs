// Display motion only: accepted end poses remain authoritative. Paths are illustrative.
const clamp=x=>Math.max(0,Math.min(1,x));
export const ease=x=>{x=clamp(x);return x*x*(3-2*x);};
const mul=(a,v)=>a.map(row=>row.reduce((sum,x,j)=>sum+x*v[j],0));
const mm=(a,b)=>a.map(row=>[0,1,2].map(j=>row.reduce((sum,x,k)=>sum+x*b[k][j],0)));
export function turnPose(pose,pivot,axis,degrees){
  const [x,y,z]=axis,t=degrees*Math.PI/180,c=Math.cos(t),s=Math.sin(t),k=1-c;
  const r=[[c+x*x*k,x*y*k-z*s,x*z*k+y*s],[y*x*k+z*s,c+y*y*k,y*z*k-x*s],[z*x*k-y*s,z*y*k+x*s,c+z*z*k]];
  const offset=mul(r,pose.origin.map((v,i)=>v-pivot[i]));
  return {origin:offset.map((v,i)=>v+pivot[i]),matrix:mm(r,pose.matrix)};
}
export function legoFrame(replay,time){
  const seconds=replay.seconds_per_step,index=Math.min(replay.states.length-1,Math.max(0,Math.floor(time/seconds))),u=clamp(time/seconds-index);
  const step=replay.steps[index],poses={},motion=step.motion;
  const moving=motion?.affected||[step.piece];
  let phase=u<.2?'Align the piece':u<.7?'Press into place':'Connected';
  for(const [id,final] of Object.entries(replay.states[index].poses)){
    let pose={origin:[...final.origin],matrix:final.matrix.map(row=>[...row])};
    if(moving.includes(id)&&motion){
      const progress=ease((u-(step.action==='rotate_hinge' ? .12 : .5))/(step.action==='rotate_hinge' ? .65 : .3));
      pose=turnPose(pose,motion.pivot,motion.axis,-motion.degrees*(1-progress));
      phase=u<.5&&step.action!=='rotate_hinge'?'Align the hinge':progress<1?'Tilt around the hinge':'Hinge set';
    }
    if(step.action!=='rotate_hinge'&&id===step.piece){
      const progress=ease((u-.15)/(motion ? .35 : .55));
      // Approach along the mating face normal, including tilted roof plates.
      const normal=pose.matrix.map(row=>row[2]);
      pose.origin=pose.origin.map((v,i)=>v+normal[i]*2*(1-progress));
    }
    poses[id]=pose;
  }
  return {index,u,poses,active:step.piece,moving,phase,target:step.target};
}
