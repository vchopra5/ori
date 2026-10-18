// Compare histories, not just their lengths: an undo and correction may arrive
// in the same poll with an unchanged fold count.
export function paperRevision(previous, next, secondsPerStep, visibleTime) {
  let shared=0;
  while(shared<Math.min(previous.length,next.length)&&JSON.stringify(previous[shared])===JSON.stringify(next[shared]))shared++;
  if(shared===previous.length)return null;
  const end=(shared+1)*secondsPerStep;
  return {shared,from:Math.max(end,Math.min(visibleTime,(previous.length+1)*secondsPerStep)),to:end,
    hasReplacement:next.length>shared};
}

// Reuse the original rigid hinge trajectory backwards; never interpolate meshes.
export function animatePaperUndo(transition, {draw, valid, frame=requestAnimationFrame}) {
  return new Promise(resolve=>{
    let start;
    const duration=Math.max(350,(transition.from-transition.to)/2.6*1600);
    function tick(now){
      if(!valid()){resolve(false);return;}
      start??=now;
      const progress=Math.min(1,(now-start)/duration);
      draw(transition.from+(transition.to-transition.from)*progress);
      if(progress===1)resolve(true);else frame(tick);
    }
    if(transition.from===transition.to){resolve(valid());return;}
    frame(tick);
  });
}
