// Presentation follows recorded events; animation never invents a physics verdict.
export function generationState(job){
  const events=(job.events||[]).filter(event=>event.kind!=='demo_pause'),last=events.at(-1)||{};
  const result=[...events].reverse().find(e=>e.kind==='undone'||e.kind==='accepted'||e.kind==='rejected'||e.kind==='tested'&&typeof e.ok==='boolean');
  const complete=['model_claimed_done','completed'].includes(job.status);
  const running=['queued','classifying','running'].includes(job.status);
  const phase=complete?'done':!running?'paused':last.kind==='proposal'?'checking':'working';
  const verdict=result?.kind==='undone'?'pending':result?(result.kind==='rejected'||result.ok===false?'fail':'pass'):'pending';
  return {phase,verdict,label:complete?'Your tutorial is ready.':!running?'Tutorial paused.':phase==='checking'?'Checking this step…':job.status==='classifying'?'Watching your video…':'Creating your tutorial…',
    detail:result?.kind==='undone'?'↶ Restored the earlier paper':result?`${verdict==='pass'?'✓':'×'} ${result.kind==='tested'?'Fold checked':result.kind==='accepted'?'Step added':'Fold needs another try'}${result.step?` · ${result.step}`:''}`:'Preparing the first step',
    count:`${job.accepted||0} folds made`};
}
