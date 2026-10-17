// Similarity is not a probability. Only the local checker's explicit gates advance.
export function nextMatchCount(previous, result){
  if(result.provider==='gemini-assisted')return result.verdict==='match'&&result.advance_allowed===true?2:0;
  return result.provider==='local-dinov2'&&result.verdict==='match'&&result.advance_allowed===true&&
    Number.isFinite(result.similarity)&&result.similarity>=.88?previous+1:0;
}
export function motionScore(previous,current){
  if(!previous||previous.length!==current.length)return Infinity;
  let delta=0;for(let i=0;i<current.length;i+=4)delta+=(Math.abs(current[i]-previous[i])+Math.abs(current[i+1]-previous[i+1])+Math.abs(current[i+2]-previous[i+2]))/3;
  return delta/(current.length/4);
}
