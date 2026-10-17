// Presentation follows recorded events; animation never invents a physics verdict.
export function generationState(job){
  const events=job.events||[],last=events.at(-1)||{};
  const result=[...events].reverse().find(e=>e.kind==='undone'||e.kind==='accepted'||e.kind==='rejected'||e.kind==='tested'&&typeof e.ok==='boolean');
  const complete=['model_claimed_done','completed'].includes(job.status);
  const running=['queued','classifying','running'].includes(job.status);
  const phase=complete?'done':!running?'paused':last.kind==='proposal'?'checking':'working';
  const verdict=result?.kind==='undone'?'pending':result?(result.kind==='rejected'||result.ok===false?'fail':'pass'):'pending';
  return {phase,verdict,label:complete?'Ready for your hands.':!running?'Taking a little pause.':phase==='checking'?'A little check with physics…':job.status==='classifying'?'Watching. Wondering. Planning.':'One little fold at a time.',
    detail:result?.kind==='undone'?'↶ Restored the earlier paper':result?`${verdict==='pass'?'✓':'×'} ${result.kind==='tested'?'Candidate test':result.kind==='accepted'?'Fold accepted':'Fold needs another try'}${result.step?` · ${result.step}`:''}`:'Waiting for the first physics check',
    count:`${job.accepted||0} folds made`};
}
