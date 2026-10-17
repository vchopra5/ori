import {readAPIJSON} from './api.mjs';
import {LiveCoach} from './live-coach.mjs';
import {StudioScene} from './scene.mjs';
import {createHomeScene} from './home-scene.mjs';

const $ = id => document.getElementById(id);
const toySteps = [
  ['A moment of balance','Set the scene: a beam rests on its pivot, with a ball on the left and a block on the right.'],
  ['A little nudge','Notice the slope of the beam. Which way would you expect the ball to move?'],
  ['Following the contact','Watch where the ball touches the beam. The blue marker follows that contact.'],
  ['A change in balance','As the ball changes position, the beam tilts. Explore the scene from another angle.'],
  ['One motion meets another','Follow the ball as it approaches the block. Think about what happens at contact.'],
  ['The whole picture','Replay the sequence and trace the chain of movement from start to finish.'],
];
const toy = {id:'toy',title:'A study in balance',kind:'toy',engine:'Toy simulation',duration:12,steps:toySteps};
let scene, current=toy, steps=toySteps, duration=12, time=0, playing=false, active=-1, library=[], stream=null, cameraSession=0;
let lessonScene=null,lessonDemoTime=null;
let paperPoint=null;
let toastTimeout, loadSession=0, stopAt=null, liveJob=null, liveSession=0;
let coachEpoch=0,coachFinished=false;
function stepTime(i){return i*duration/steps.length;}
function thumbnailTime(i){return current.kind==='lego'?Math.min(duration,(i+.94)*duration/steps.length):current.kind==='paper'&&i>0?Math.min(duration,(i+1)*duration/steps.length-.00001):stepTime(i);}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>$('toast').hidden=true,5000);}
function clock(seconds){return `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;}
function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');const use=document.createElementNS(svg.namespaceURI,'use');use.setAttribute('href',`#i-${name}`);svg.append(use);return svg;}
function setPlaying(value){if(!value)stopAt=null;playing=value;$('play').querySelector('use').setAttribute('href',value?'#i-pause':'#i-play');$('play').querySelector('span').textContent=value?'Pause':'Play';$('play').setAttribute('aria-label',value?'Pause simulation':'Play simulation');if(current.kind==='recording'){if(value)$('recording').play().catch(()=>{setPlaying(false);toast('Playback could not start. Try pressing Play again.');});else $('recording').pause();}}
function statusRow(title,description,state){const li=document.createElement('li');li.className=state;const dot=document.createElement('span');dot.className='event-dot';dot.textContent=state==='complete'?'✓':state==='rejected'?'×':'';dot.setAttribute('aria-label',state);const copy=document.createElement('div');copy.className='event-copy';const strong=document.createElement('strong');strong.textContent=title;const p=document.createElement('p');p.textContent=description;copy.append(strong,p);li.append(dot,copy);return li;}
function renderActivity(){
  const list=$('activity-list');list.replaceChildren();list.classList.toggle('lego-inventory',current.kind==='lego');
  if(liveJob&&!(current.kind==='lego'&&liveJob.status==='completed')){
    const events=liveJob.events.slice(-8);
    for(const [index,event] of events.entries()){
      const titles={classifying:'Watching your video',routed:'Simulator selected',working:'Argon is working',proposal:'Proposed · checking physics',tested:'Testing a fold mechanism',accepted:'Harness accepted',rejected:'Harness rejected',planning:'Planning a simple approach',recovering:'Replanning this fold',compacted:'Context refreshed',resuming:'Continuing saved folds',incomplete:'Incomplete preview',finished:'Ready to explore',error:'Run stopped'};
      const incompleteEnd=event.kind==='finished'&&!['model_claimed_done','completed'].includes(liveJob.status);
      const message=incompleteEnd?'This run could not complete the video. Its accepted steps remain available as a preview.':event.message;
      list.append(statusRow(incompleteEnd?'Incomplete preview':titles[event.kind]||event.kind,[message,...(event.names||[])].join(' · '),incompleteEnd||event.kind==='rejected'||event.kind==='error'||event.kind==='incomplete'?'rejected':index===events.length-1&&['queued','classifying','running'].includes(liveJob.status)?'active':'complete'));
    }
    return;
  }
  if(current.kind==='toy'){
    const progress=Math.max(0,active);
    [['Meet the system','A beam, a pivot, and two objects.',0],['Follow the motion','Explore the illustrated trajectory.',1],['Look a little closer','Inspect the contact markers.',2],['Connect the steps','See the whole sequence unfold.',5]].forEach(([title,description,step])=>list.append(statusRow(title,description,progress>step?'complete':progress===step?'active':'pending')));
  }else{
    const report=current.report||{};
    if(current.kind==='lego'){
      list.append(statusRow('Assembly validated',`${report.pieces} pieces · ${report.connections} connections · no body overlaps.`, 'complete'));
      for(const p of report.inventory||[])list.append(statusRow(`${p.count} × ${p.color.replaceAll('_',' ')} ${p.part.replaceAll('_',' ')}`,'Required pieces','complete'));
      for(const text of report.uncertainties||[])list.append(statusRow(report.origin==='original_design'?'Design limitation':'Video uncertainty',text,'pending'));
      if(report.origin==='original_design'){
        list.append(statusRow('Original Gemini design',`${report.step_validation?.checks?.length||steps.length} steps checked · hinge motion sampled every 2°.`, 'complete'));
      }else list.append(statusRow('Video match not verified','Geometry checks do not confirm every piece matches the source.','pending'));
    }else if(current.kind==='paper'){
      list.append(statusRow('Harness run saved',`${report.commands_executed??report.accepted_folds??steps.length-1} accepted folding actions.`, 'complete'));
      list.append(statusRow('Material preserved','The sheet keeps its original dimensions.',report.ok?'complete':'pending'));
      list.append(statusRow('Seams checked','Connected paper stays connected through each fold.',report.ok?'complete':'pending'));
      list.append(statusRow(current.audit?.passed?'Feedback independently replayed':'Layer order recorded',current.audit?.passed?'Every model response and render was checked against the harness.':'Explore the front, reverse, and overlapping layers.', 'complete'));
    }else{
      const passed=report.passed===true;
      list.append(statusRow('MuJoCo recording','Playback of a real dynamics run.','complete'));
      list.append(statusRow('Dynamics evaluated',report.mujoco_version?`MuJoCo ${report.mujoco_version}`:'See the report for engine details.','complete'));
      list.append(statusRow('Validation report',passed?'Saved run passed its checks.':'Open the report for validation results.',passed?'complete':'pending'));
    }
    const link=document.createElement('a');link.className='report-link';link.href=current.report_url;link.target='_blank';link.rel='noopener';link.textContent='Open the full harness report ↗';list.append(link);
  }
}
function updateStep(){
  const next=Math.min(steps.length-1,Math.floor(time/(duration/steps.length)));
  if(next===active)return;active=next;resetCoachStep(false);
  document.querySelectorAll('.step-button').forEach((button,i)=>button.setAttribute('aria-current',String(i===active)));
  $('replay-fold').disabled=current.kind!=='paper'||active===0;
  $('event-step').textContent=`STEP ${active+1} / ${steps.length}`;
  if(current.kind==='lego'){$('lego-step-number').textContent=`STEP ${active+1} OF ${steps.length}`;$('lego-back').disabled=active===0;$('lego-next').disabled=active===steps.length-1;}
  $('event-title').textContent=steps[active][0];$('event-description').textContent=steps[active][1];
  $('progress-label').textContent=`${String(active+1).padStart(2,'0')} / ${String(steps.length).padStart(2,'0')}`;
  $('event-status').lastChild.textContent=current.kind==='toy'?'Illustrative sample motion':current.kind==='paper'?'Recorded fold · drag to explore':'Saved harness result';
  const card=$('steps').children[active];if(card&&$('steps').dataset.long==='true')$('steps').scrollTo({left:Math.max(0,card.offsetLeft-$('steps').offsetLeft-80),behavior:'instant'});
  $('lesson-step').textContent=current.kind==='paper'?(active===0?'STARTING SHEET':`FOLD ${active} OF ${steps.length-1}`):`STEP ${active+1} OF ${steps.length}`;$('lesson-title').textContent=steps[active][0];$('lesson-instruction').textContent=steps[active][1];
  $('lesson-back').disabled=active===0;$('lesson-next').textContent=active===steps.length-1?'Finish lesson ✓':'Next step →';
  startLessonDemo();
  liveCoach.stage();
  renderActivity();
}
function seek(value){time=Math.max(0,Math.min(duration,value));if(current.kind==='recording'){if(Math.abs($('recording').currentTime-time)>.15)$('recording').currentTime=time;}else scene?.setTime(time);if(current.kind==='lego'&&scene?.legoFrame)$('lego-phase').textContent=scene.legoFrame.phase;$('scrubber').value=time;$('timecode').textContent=`${clock(time)} / ${clock(duration)}`;updateStep();}
function playLegoStep(index){
  if(current.kind!=='lego')return;setPlaying(false);seek(stepTime(Math.max(0,Math.min(steps.length-1,index))));setPlaying(true);stopAt=Math.min(duration,stepTime(active+1))-.00001;
}
$('lego-replay').onclick=()=>playLegoStep(active);
$('lego-back').onclick=()=>playLegoStep(active-1);
$('lego-next').onclick=()=>playLegoStep(active+1);
$('lego-focus').onclick=()=>scene?.focusLego();
$('lego-xray').onclick=()=>{scene.legoXray=!scene.legoXray;$('lego-xray').setAttribute('aria-pressed',String(scene.legoXray));scene.setTime(time);};
function renderSteps(){
  $('steps').replaceChildren();$('steps').style.setProperty('--step-columns',steps.length);$('steps').dataset.long=String(steps.length>7);
  steps.forEach(([title],i)=>{const button=document.createElement('button');button.className='step-button';button.setAttribute('aria-label',`Step ${i+1}: ${title}`);const image=document.createElement('div');image.className='step-image';
    if(scene&&current.kind!=='recording'){const img=document.createElement('img');img.alt='';img.src=scene.thumbnail(thumbnailTime(i));image.append(img);}else{image.append(icon('play'));image.style.display='grid';image.style.placeItems='center';}
    const number=document.createElement('span');number.className='step-number';number.textContent=i+1;image.append(number);
    const label=document.createElement('span');label.className='step-label';label.textContent=title;label.title=title;const timestamp=document.createElement('span');timestamp.className='step-time';timestamp.textContent=clock(i*duration/steps.length);button.append(image,label,timestamp);button.onclick=()=>{if(current.kind==='lego'){playLegoStep(i);}else{setPlaying(false);seek(stepTime(i));}};$('steps').append(button);
  });
  active=-1;seek(0);
}
async function loadItem(item, options={}){
  if(!options.live){liveSession++;liveJob=null;$('activity-list').classList.remove('live-events');}
  $('home-view').hidden=true;$('studio-view').hidden=false;$('retry-run').hidden=true;$('teach').disabled=false;
  const session=++loadSession;setPlaying(false);let replay=options.replay;
  if(['paper','lego'].includes(item.kind)&&!replay){
    $('paper-loading').hidden=false;$('paper-loading-text').textContent='Unfolding the saved motion…';
    try{const response=await fetch(item.replay_url);if(!response.ok)throw Error();replay=await readAPIJSON(response);}
    catch{if(session===loadSession){$('paper-loading').hidden=true;toast('This saved replay could not be prepared. Check the run artifacts.');}return;}
  }
  if(session!==loadSession)return;$('paper-loading').hidden=true;
  stopCamera();$('teaching').hidden=true;current=item;active=-1;time=0;
  $('lego-tools').hidden=item.kind!=='lego'||replay?.version!==2;document.querySelector('.studio-grid').classList.toggle('lego-mode',item.kind==='lego');$('lego-xray').setAttribute('aria-pressed','false');if(scene)scene.legoXray=false;
  $('paper-tools').hidden=item.kind!=='paper';document.querySelector('.simulation').classList.toggle('is-paper',item.kind==='paper');
  $('scene').setAttribute('aria-label',item.kind==='paper'?'Interactive folded paper. Drag to orbit; scroll to zoom.':'Interactive three dimensional seesaw. Drag to rotate; scroll to zoom.');
  $('contacts-label').textContent=item.kind==='paper'?'Fold guide':'Contacts';
  $('contacts').setAttribute('aria-pressed','true');scene?.setContacts(item.kind!=='paper');scene?.setFoldGuide(true);$('fold-guide-key').hidden=false;
  document.querySelectorAll('[data-paper-view]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.paperView==='perspective')));
  $('source-link').hidden=!item.source_url;if(item.source_url)$('source-link').href=item.source_url;
  $('final-view').hidden=item.kind!=='paper';
  history.replaceState(null,'',`?run=${encodeURIComponent(item.id)}`);
  const video=$('recording');video.pause();video.removeAttribute('src');video.load();video.hidden=item.kind!=='recording';$('scene').hidden=item.kind==='recording';
  $('contacts').hidden=item.kind==='recording';$('orbit-hint').hidden=item.kind==='recording';
  $('session-name').textContent=item.title;$('sample-badge').textContent=item.kind==='toy'?'Interactive sample':item.id.startsWith('trial-')?'Argon approximation':'Saved harness run';
  $('engine-badge').replaceChildren(icon('cube'),document.createTextNode(` ${item.engine}`));
  $('canvas-title').textContent=item.kind==='toy'?'Learning how it moves.':item.title;
  $('canvas-eyebrow').textContent=item.kind==='toy'?'SMALL ACTIONS. INTERESTING PHYSICS.':'FROM THE PHYSICS HARNESS';
  $('canvas-subtitle').textContent=item.kind==='toy'?'A little motion. A whole chain of possibilities.':item.kind==='paper'?'One sheet. Every crease, a little possibility.':'Real dynamics, recorded directly from MuJoCo.';
  $('activity-tag').textContent=item.kind==='toy'?'SAMPLE':'RECORDED';$('activity-title').textContent=item.kind==='toy'?'A world in the making.':'Grounded in a harness.';
  $('activity-description').textContent=item.kind==='toy'?'Explore the motions that make this little system work.':'Validation from the saved run. These checks are not running live.';
  $('footer-note').textContent=item.kind==='toy'?'Toy playback · illustrative motion, not a MuJoCo solve':item.kind==='paper'?'Rigid paper · recorded hinge motion · display layer spacing':'Recorded MuJoCo run · inspect the report for assumptions';
  if(item.kind==='toy'){steps=toySteps;duration=12;scene?.buildToy();}
  else if(item.kind==='lego'){steps=replay.version===2?replay.steps.map((step,i)=>[`${step.action==='rotate_hinge'?'Adjust':'Place'} ${replay.pieces.find(p=>p.id===step.piece)?.part.replaceAll('_',' ')||'piece'}`,step.instruction]):replay.pieces.map((p,i)=>[`Place piece ${i+1}: ${p.color} ${p.part.replaceAll('_',' ')}`,p.instruction]);duration=steps.length*replay.seconds_per_step;scene?.setLego(replay);$('teach').disabled=true;$('contacts').hidden=true;$('fold-guide-key').hidden=true;$('scene').setAttribute('aria-label','LEGO assembly. Drag to orbit; scroll to zoom.');$('canvas-subtitle').textContent=`${replay.pieces.length} pieces · validated snap connections`;$('footer-note').textContent='Illustrative assembly motion · validated end positions · simplified hinge geometry';}
  else if(item.kind==='paper'){steps=[['The starting sheet','Begin with the flat sheet, ready for its first fold.'],...item.commands.map(command=>[command.name||'Accepted fold',`Follow this accepted harness action: ${(command.name||'Fold').toLowerCase()}.`])];if(steps.length!==replay.states.length)steps=replay.states.map((_,i)=>[i===0?'The starting sheet':`Accepted fold ${i}`,i===0?'Start with the flat sheet.':item.commands[i-1]?.name||'Inspect this saved state.']);duration=steps.length*(replay.seconds_per_step||2.6);scene?.setPaper(replay);}
  else{duration=Number(item.report.simulation_seconds)||14;steps=[['The starting state','Observe the mechanism before the actuators move.'],['The motion begins','Watch the pre-existing joints start to move.'],['Following the motion','Compare the changing shape and contact.'],['The final state','Inspect the final state and the saved validation report.']];video.src=item.video;video.onerror=()=>toast('This recording could not be loaded. Try another library item.');video.onloadedmetadata=()=>{if(current.id!==item.id)return;duration=video.duration;$('scrubber').max=duration;$('duration').textContent=clock(duration);$('step-count').textContent=`${steps.length} steps · ${Math.round(duration)} seconds`;renderSteps();};}
  $('scrubber').max=duration;$('duration').textContent=clock(duration);$('step-count').textContent=`${steps.length} steps · ${Math.round(duration)} seconds`;scene?.resize();renderSteps();seek(0);
}
function makeLibraryItem(item){const row=document.createElement('div');row.className='library-row';row.dataset.token=item.delete_token||'';const button=document.createElement('button');button.className='library-item';if(item.thumbnail){const thumbnail=document.createElement('img');thumbnail.className='library-thumbnail';thumbnail.src=item.thumbnail;thumbnail.alt='';thumbnail.onerror=()=>thumbnail.remove();button.append(thumbnail);}else button.append(icon(item.kind==='recording'?'play':'cube'));const copy=document.createElement('div');const title=document.createElement('strong');title.textContent=item.title;const description=document.createElement('p');description.textContent=item.kind==='toy'?'Interactive sample · 6 moments to explore':`${item.engine} · saved ${item.kind==='recording'?'recording and validation':item.kind==='lego'?'assembly and inventory':'folding motion and validation'}`;if(item.saved_at)description.textContent+=` · ${new Date(item.saved_at*1000).toLocaleString()}`;copy.append(title,description);const arrow=icon('arrow');arrow.classList.add('item-arrow');button.append(copy,arrow);button.onclick=()=>{$('library-dialog').close();loadItem(item).catch(()=>toast('This saved run could not be opened.'));};row.append(button);if(item.delete_token){const remove=document.createElement('button');remove.className='delete-run-button';remove.textContent='Delete';remove.setAttribute('aria-label',`Delete ${item.title}`);remove.onclick=()=>confirmDeleteRun(item);row.append(remove);}return row;}
let pendingDelete=null;
function confirmDeleteRun(item){pendingDelete=item;$('delete-run-title').textContent=`Delete “${item.title}”?`;$('delete-run-error').hidden=true;$('delete-run-confirm').disabled=false;$('delete-run-dialog').showModal();}
$('delete-run-cancel').onclick=()=>$('delete-run-dialog').close();
$('delete-run-dialog').addEventListener('close',()=>{pendingDelete=null;});
$('delete-run-confirm').onclick=async()=>{
  if(!pendingDelete)return;const item=pendingDelete,button=$('delete-run-confirm');button.disabled=true;$('delete-run-error').hidden=true;
  try{
    const response=await fetch('/api/library/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:item.delete_token})});
    const result=await readAPIJSON(response);if(!response.ok)throw Error(result.error||'This run could not be deleted.');
    library=library.filter(run=>run.delete_token!==item.delete_token);
    document.querySelectorAll('.library-row').forEach(row=>{if(row.dataset.token===item.delete_token)row.remove();});
    if(current.delete_token===item.delete_token){setPlaying(false);stopCamera();$('teaching').hidden=true;showHome();history.replaceState(null,'',location.pathname+'#home-library');}
    else if(!$('home-view').hidden)showHome();
    $('delete-run-dialog').close();toast('Run deleted.');
  }catch(error){$('delete-run-error').textContent=error.message;$('delete-run-error').hidden=false;}
  finally{button.disabled=false;}
};

async function openLibrary(){
  const items=$('library-items');items.replaceChildren(makeLibraryItem(toy));$('library-dialog').showModal();
  try{const response=await fetch('/api/library',{cache:'no-store'});if(!response.ok)throw Error();library=await readAPIJSON(response);for(const item of library)items.append(makeLibraryItem(item));if(!library.length){const p=document.createElement('p');p.className='library-empty';p.textContent='No saved harness runs yet. Generated runs will appear here when available.';items.append(p);}}
  catch{const p=document.createElement('p');p.className='library-empty';p.textContent='Start the coaching Python server to browse local harness runs.';items.append(p);}
  try{const drafts=JSON.parse(localStorage.getItem('ori-video-drafts')||'[]');if(drafts.length){const heading=document.createElement('p');heading.className='draft-label';heading.textContent='VIDEO DRAFTS · NOT YET RECONSTRUCTED';items.append(heading);for(const draft of drafts.slice(-3).reverse()){const p=document.createElement('p');p.className='import-url';p.textContent=draft.url;items.append(p);}}}catch{/* Browsing remains available when storage is disabled. */}
}
function stopCamera(){setIntroVisible(false);liveCoach.stop();cameraSession++;resetCoachStep();$('stop-camera').hidden=true;$('camera-guide').hidden=true;paperPoint=null;$('paper-point').hidden=true;stream?.getTracks().forEach(track=>track.stop());stream=null;$('webcam').srcObject=null;$('webcam').hidden=true;$('camera-placeholder').hidden=false;$('camera-label').hidden=true;$('enable-camera').disabled=false;$('enable-camera').textContent='Turn on camera';$('use-desk-view').disabled=false;$('camera-source').disabled=false;}
function setIntroVisible(intro){
  for(const id of ['lesson-step','lesson-title','lesson-instruction'])$(id).hidden=intro;
  $('lesson-demo-wrap').hidden=intro||current.kind!=='paper'||!lessonScene;
  $('lesson-back').disabled=intro||active===0;$('lesson-next').disabled=intro;
  if(intro){lessonDemoTime=null;coachMessage('Ori is introducing your lesson…');}
}
function startLessonDemo(){
  const hasFold=current.kind==='paper'&&active>0;
  $('lesson-autoloop').disabled=!hasFold;$('lesson-replay').disabled=!hasFold;
  $('lesson-replay').title=hasFold?'Replay the current fold':'Choose Next step to see the first fold.';
  if(!lessonScene||$('teaching').hidden)return;
  lessonDemoTime=hasFold?stepTime(active):null;
  lessonScene.setTime(hasFold?lessonDemoTime:0);
}
function playLessonStep(index){
  setPlaying(false);
  if(current.kind==='paper'&&lessonScene&&!$('teaching').hidden){
    // Keep the target and camera checks stable while the side demo repeats.
    seek(thumbnailTime(index));
    startLessonDemo();
  }else{seek(stepTime(index));if(current.kind==='paper'&&index>0){setPlaying(true);stopAt=Math.min(duration,(index+1)*duration/steps.length-.00001);}}
}
function coachMessage(message){$('coach-status').textContent=message;}
function resetCoachStep(notify=true){
  coachEpoch++;if(notify)liveCoach.stage();coachFinished=false;
  $('coach-caption-live').textContent='';$('coach-heard').textContent='';$('coach-heard').hidden=true;liveCaptionNew=true;
  $('coach-observation').hidden=true;$('coach-instruction').hidden=true;$('perception-previews').hidden=true;$('paper-mask-preview').removeAttribute('src');$('paper-depth-preview').removeAttribute('src');
  coachMessage(current.kind==='paper'?'Show your shape to the camera.':'Automatic checks are available for paper lessons.');
}
function cameraJPEG(full=false){
  const video=$('webcam'),canvas=document.createElement('canvas');
  if(full){
    if(video.readyState<2||!video.videoWidth)return null;
    const scale=Math.min(1,768/video.videoWidth,768/video.videoHeight);canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
    canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);return canvas.toDataURL('image/jpeg',.8).split(',')[1];
  }
  const side=Math.min(video.videoWidth,video.videoHeight)*.8;
  canvas.width=canvas.height=Math.min(640,Math.round(side));
  canvas.getContext('2d').drawImage(video,(video.videoWidth-side)/2,(video.videoHeight-side)/2,side,side,0,0,canvas.width,canvas.height);
  return canvas.toDataURL('image/jpeg',.85).split(',')[1];
}
function updateCameraGuide(){
  const video=$('webcam');if(!video.videoWidth)return;
  const size=Math.min(video.clientWidth/video.videoWidth,video.clientHeight/video.videoHeight)*Math.min(video.videoWidth,video.videoHeight)*.8;
  $('camera-guide').style.width=`${size}px`;$('camera-guide').style.height=`${size}px`;
  if(paperPoint){$('paper-point').style.left=`${paperPoint[0]*100}%`;$('paper-point').style.top=`${paperPoint[1]*100}%`;}
}
$('webcam').addEventListener('loadedmetadata',updateCameraGuide);
new ResizeObserver(updateCameraGuide).observe($('webcam'));
let liveCaptionNew=true;
const liveCoach=new LiveCoach({
  context:()=>({runId:current.id,step:active,epoch:coachEpoch}),
  frame:()=>stream&&!$('teaching').hidden&&!coachFinished?cameraJPEG(true):null,
  state:(state,message)=>{
    $('coach-question-text').disabled=state!=='ready';
    $('camera-guide').hidden=true;
    if(state==='ready'){
      startLessonDemo();
      coachMessage('Connecting voice…');
      const audioTracks=stream?.getAudioTracks()||[];
      const session=cameraSession;liveCoach.enableMicrophone(audioTracks.length?new MediaStream(audioTracks):null).catch(error=>{if(session===cameraSession){stopCamera();coachMessage(error.message);toast(error.message);}});
    }
    if(state==='connecting')coachMessage('Connecting your live coach…');
    if(state==='reconnecting')coachMessage('Reconnecting Ori… keep working at your own pace.');
    if(state==='error'){stopCamera();coachMessage(message);toast(message);}
  },
  event:msg=>{
    if(msg.type==='microphone'){if(msg.enabled&&liveCoach.ready)coachMessage(liveCoach.introduced?'Ori is listening · fold naturally and ask anything.':'Ori is introducing your lesson…');return;}
    if(msg.type==='voice')return;
    if(msg.type==='intro_start'){setIntroVisible(true);return;}
    if(msg.type==='intro_complete'){setIntroVisible(false);startLessonDemo();coachMessage(`Fold ${active} · Ori is listening. Watch the demo, then show your result.`);return;}
    if(msg.type==='microphone_ended'){stopCamera();coachMessage('Microphone disconnected. Turn on the camera to reconnect.');return;}
    if(msg.type==='turn_complete'){liveCaptionNew=true;return;}
    if(!stream||$('teaching').hidden||msg.epoch!==coachEpoch)return;
    if(msg.type==='match_pending'){coachMessage('Step matched · Ori is finishing the explanation.');return;}
    if(msg.type==='user_caption'){const caption=$('coach-heard');if(msg.new_turn)caption.textContent='You: ';caption.textContent=(caption.textContent+msg.text).slice(-650);caption.hidden=false;return;}
    if(msg.type==='caption'){
      const caption=$('coach-caption-live');if(liveCaptionNew)caption.textContent='';liveCaptionNew=false;caption.textContent=(caption.textContent+msg.text).slice(-650);caption.hidden=false;return;
    }
    if(msg.type!=='progress'||msg.step!==active||coachFinished)return;
    $('coach-observation').textContent=[msg.fold_location,msg.observation].filter(Boolean).join(' · ');$('coach-observation').hidden=false;
    $('coach-instruction').textContent=msg.status==='out_of_view'?'Work on your desk; hold it up whenever you’re ready.':msg.instruction;$('coach-instruction').hidden=!$('coach-instruction').textContent;
    const labels={working:'Following your fold…',out_of_view:'Paper out of view · take your time.',need_view:'One more angle would help.',mistake:'A small adjustment to try.',check_in:'Want a hand with this step?',matched:'That shape matches.'};
    coachMessage(labels[msg.status]||'Watching your folds…');
    if(msg.status==='matched'){
      if(active===steps.length-1){coachFinished=true;coachMessage('Finished! Your paper matches the final stage.');}
      else if($('auto-coach').checked){playLessonStep(active+1);coachMessage('Step matched. Watch the next fold, then try it.');}
      else coachMessage('Step matched. Choose Next step when you’re ready.');
    }
  }
});
function startCoach(){
  resetCoachStep();$('stop-camera').hidden=false;
  if(current.kind==='paper')liveCoach.start();
}
$('coach-question').onsubmit=event=>{event.preventDefault();const input=$('coach-question-text'),text=input.value.trim();if(text&&liveCoach.ready){liveCoach.ask(text);input.value='';$('coach-caption-live').textContent='';}};
$('stop-camera').onclick=stopCamera;
$('auto-coach').onchange=()=>{resetCoachStep();coachMessage($('auto-coach').checked?'Automatic advance enabled.':'Automatic advance paused. Your live coach can still help.');};
$('library-button').onclick=openLibrary;
document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>button.closest('dialog').close());
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}}));
$('link-form').onsubmit=async e=>{e.preventDefault();const input=$('video-link');let url;try{url=new URL(input.value);if(!['http:','https:'].includes(url.protocol))throw Error();}catch{input.setCustomValidity('Use a complete http or https video URL.');input.reportValidity();return;}input.setCustomValidity('');
  const videoId=value=>{try{const u=new URL(value);if(u.hostname==='youtu.be')return u.pathname.slice(1);if(!['youtube.com','www.youtube.com','m.youtube.com'].includes(u.hostname))return null;return u.searchParams.get('v')||u.pathname.split('/').filter(Boolean).pop();}catch{return null;}};
  try{const response=await fetch('/api/library');if(response.ok){const savedRuns=await readAPIJSON(response);const matching=savedRuns.find(item=>item.source_url&&videoId(url.href)&&videoId(item.source_url)===videoId(url.href));if(matching){await loadItem(matching);toast('Opened the saved tutorial.');return;}}}catch{/* Unsaved links can still be stored as drafts. */}
  try{
    const response=await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:url.href})});
    const job=await readAPIJSON(response);if(!response.ok)throw Error(job.error||'Could not start this video.');
    followJob(job.id);
  }catch(error){toast(error.message);}
};
async function followJob(id){
  $('home-view').hidden=true;$('studio-view').hidden=false;scene?.resize();
  const session=++liveSession;let accepted=-1,attempt=-1,revision=-1,failures=0;
  liveJob={events:[]};setPlaying(false);$('paper-loading').hidden=false;$('paper-loading-text').textContent='Argon is watching your video…';
  history.replaceState(null,'',`?job=${encodeURIComponent(id)}`);
  while(session===liveSession){
    try{
      const response=await fetch(`/api/jobs/${encodeURIComponent(id)}`,{cache:'no-store'});
      if(!response.ok)throw Error('Could not read the live run');
      const job=await readAPIJSON(response);if(session!==liveSession)return;liveJob=job;failures=0;
      if(job.route?.kind==='lego'&&job.status==='running')$('paper-loading-text').textContent='Identifying pieces and checking snap connections…';
      if(job.route?.kind==='mujoco'&&job.status==='running')$('paper-loading-text').textContent='Building and validating the MuJoCo scene…';
      if(job.route?.kind==='origami'&&(job.accepted!==accepted||(job.attempt||0)!==attempt)){
        const result=await fetch(`/api/jobs/${encodeURIComponent(id)}/playback`,{cache:'no-store'});
        if(!result.ok)throw Error('Paper state is not ready');
        const replay=await readAPIJSON(result);if(session!==liveSession)return;
        // Each atomic snapshot can be newer than the status poll. Wait until they agree.
        if(replay.states.length!==job.commands.length+1||(replay.attempt||0)!==(job.attempt||0)||(job.command_hash&&replay.command_hash!==job.command_hash)){await new Promise(resolve=>setTimeout(resolve,1200));continue;}
        await loadItem({id:job.id,title:job.route.title||'Paper, imagined by Argon',kind:'paper',engine:'Argon · paper harness',
          commands:job.commands,source_url:job.url,report:{...replay.metrics,ok:true,accepted_folds:job.accepted},
          report_url:`/api/jobs/${id}`,replay_url:`/api/jobs/${id}/playback`},{live:true,replay});
        history.replaceState(null,'',`?job=${encodeURIComponent(id)}`);
        accepted=job.accepted;attempt=job.attempt||0;seek(stepTime(steps.length-1));setPlaying(job.accepted>0);
      }
      if(job.revision!==revision){
        revision=job.revision;$('sample-badge').textContent=['queued','classifying','running'].includes(job.status)?'Live Argon run':['model_claimed_done','completed'].includes(job.status)?'Ready to explore':'Incomplete preview';$('activity-tag').textContent=['queued','classifying','running'].includes(job.status)?'LIVE':['model_claimed_done','completed'].includes(job.status)?'READY':'INCOMPLETE';
        $('activity-title').textContent=job.route?.title||'Choosing the right physics.';
        $('activity-list').classList.add('live-events');
        $('activity-description').textContent='Argon proposals and harness results · only accepted folds enter the paper view.';
        renderActivity();
      }
      if(!['queued','classifying','running'].includes(job.status)){
        $('paper-loading').hidden=true;
        if(['mujoco','lego'].includes(job.route?.kind)&&job.status==='completed'){
          const items=await readAPIJSON(await fetch('/api/library'));const item=items.find(value=>value.id===job.id);if(item)await loadItem(item,{live:true});
        }
        const complete=['model_claimed_done','completed'].includes(job.status);
        const message=job.message||(complete?'Your approximation is ready.':'This run could not complete the video. Any saved steps are an incomplete preview.');
        $('activity-description').textContent=message;
        $('retry-run').hidden=complete;$('retry-run').textContent=job.resumable?'Continue this run →':'Try another approach ↻';$('teach').disabled=!complete||job.route?.kind==='lego';
        toast(message);return;
      }
    }catch(error){if(++failures>=5){$('paper-loading').hidden=true;toast('Live updates disconnected. Reload this page to reconnect to the saved job.');return;}}
    await new Promise(resolve=>setTimeout(resolve,1200));
  }
}

$('retry-run').onclick=async()=>{
  if(!liveJob?.url)return;
  const button=$('retry-run');button.disabled=true;
  try{const response=await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(liveJob.resumable?{resume_id:liveJob.id}:{url:liveJob.url})});
    const job=await readAPIJSON(response);if(!response.ok)throw Error(job.error||'Could not restart the run.');
    button.hidden=true;followJob(job.id);
  }catch(error){toast(error.message);}finally{button.disabled=false;}
};
$('video-link').addEventListener('input',()=>$('video-link').setCustomValidity(''));
$('import-explore').onclick=()=>{$('import-dialog').close();loadItem(toy);};
$('play').onclick=()=>{if(time>=duration)seek(0);setPlaying(!playing);};$('reset').onclick=()=>{setPlaying(false);seek(0);};
$('contacts').onclick=()=>{const value=$('contacts').getAttribute('aria-pressed')!=='true';$('contacts').setAttribute('aria-pressed',String(value));if(current.kind==='paper'){scene?.setFoldGuide(value);$('fold-guide-key').hidden=!value;}else scene?.setContacts(value);};
$('scrubber').oninput=e=>{setPlaying(false);seek(Number(e.target.value));};
$('teach').onclick=()=>{setPlaying(false);seek(0);$('teaching').hidden=false;resetCoachStep();updateStep();
  $('lesson-demo-wrap').hidden=current.kind!=='paper';
  if(current.kind==='paper'&&scene){try{if(!lessonScene)lessonScene=new StudioScene($('lesson-demo'));lessonScene.resize();lessonScene.setPaper(scene.replay);lessonScene.distance=6;startLessonDemo();}catch{$('lesson-demo-wrap').hidden=true;}if(steps.length>1)playLessonStep(1);}
$('teaching').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});};
$('exit-teaching').onclick=()=>{stopCamera();$('teaching').hidden=true;$('teach').focus();};
$('lesson-back').onclick=()=>playLessonStep(Math.max(0,active-1));
$('lesson-replay').onclick=()=>playLessonStep(active);
$('lesson-autoloop').onchange=()=>{
  if($('lesson-autoloop').checked&&current.kind==='paper'&&active>0&&lessonScene){
    setPlaying(false);startLessonDemo();
  }
};
$('lesson-next').onclick=()=>{if(active===steps.length-1){stopCamera();$('teaching').hidden=true;toast('A little more understood. Nicely explored.');$('teach').focus();}else playLessonStep(active+1);};
async function refreshCameraSources(){
  if(!navigator.mediaDevices?.enumerateDevices)return;
  try{
    const devices=(await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='videoinput');
    const selected=stream?.getVideoTracks()[0]?.getSettings?.().deviceId||$('camera-source').value;
    $('camera-source').replaceChildren();
    const fallback=new Option('System default camera','');$('camera-source').add(fallback);
    devices.forEach((device,i)=>$('camera-source').add(new Option(device.label||`Camera ${i+1}`,device.deviceId)));
    if([...$('camera-source').options].some(option=>option.value===selected))$('camera-source').value=selected;
    $('camera-source').disabled=false;
  }catch{ /* Default-camera capture still works if enumeration is restricted. */ }
}
async function startCapture(kind='camera',deviceId=''){
  const method=kind==='desk'?'getDisplayMedia':'getUserMedia';
  if(!navigator.mediaDevices?.[method]){
    toast(kind==='desk'?'Window sharing is unavailable here. Open Ori in Chrome or Safari, or choose a Desk View camera if it appears in the camera list.':'Camera access needs localhost or HTTPS and a supported browser.');return;
  }
  stopCamera();
  const session=++cameraSession;
  if(current.kind==='paper'){liveCoach.speaking=true;liveCoach.ensureAudio().catch(()=>{});}
  $('enable-camera').disabled=true;$('use-desk-view').disabled=true;$('camera-source').disabled=true;
  $('enable-camera').textContent=kind==='desk'?'Choose the Desk View window…':'Opening camera…';
  try{
    // Keep the window picker directly in the user's click gesture.
    const result=kind==='desk'
      ?await navigator.mediaDevices.getDisplayMedia({video:{displaySurface:'window'},audio:false})
      :await navigator.mediaDevices.getUserMedia({video:deviceId?{deviceId:{exact:deviceId}}:{facingMode:'user'},audio:current.kind==='paper'?{echoCancellation:true,noiseSuppression:true,autoGainControl:true}:false});
    if(session!==cameraSession){result.getTracks().forEach(track=>track.stop());return;}
    if(kind==='desk'&&current.kind==='paper'){
      try{const mic=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
        mic.getAudioTracks().forEach(track=>result.addTrack(track));
      }catch(error){result.getTracks().forEach(track=>track.stop());throw error;}
      if(session!==cameraSession){result.getTracks().forEach(track=>track.stop());return;}
    }
    stream=result;$('webcam').srcObject=stream;$('webcam').hidden=false;
    $('camera-placeholder').hidden=true;$('camera-label').hidden=false;$('camera-guide').hidden=true;
    updateCameraGuide();
    $('camera-label').textContent=kind==='desk'?'DESK VIEW WINDOW · GEMINI COACH':current.kind==='paper'?'YOUR WORKSPACE · GEMINI COACH':'YOUR WORKSPACE · LOCAL CAMERA';
    result.getVideoTracks()[0]?.addEventListener('ended',()=>{if(stream===result){stopCamera();toast(kind==='desk'?'Desk View sharing ended.':'Camera disconnected.');}});
    startCoach();await refreshCameraSources();
  }catch(error){
    if(session!==cameraSession)return;
    const message=kind==='desk'
      ?'Desk View was not shared. Open Desk View from the macOS Video menu, then choose its window in the picker.'
      :error.name==='NotAllowedError'?'Allow camera and microphone access in your browser, then turn the camera on again.':'That camera is unavailable. Choose another camera or use Desk View.';
    $('camera-message').textContent=message;toast(message);
  }finally{
    if(session===cameraSession){$('enable-camera').disabled=false;$('use-desk-view').disabled=false;$('camera-source').disabled=false;$('enable-camera').textContent='Turn on camera';}
  }
}
$('enable-camera').onclick=()=>startCapture('camera',$('camera-source').value);
$('camera-source').onchange=()=>startCapture('camera',$('camera-source').value);
$('use-desk-view').onclick=()=>startCapture('desk');
navigator.mediaDevices?.addEventListener?.('devicechange',refreshCameraSources);
window.addEventListener('pagehide',stopCamera);
try{scene=new StudioScene($('scene'));scene.resize();}catch(error){$('scene-error').hidden=false;$('scene-error').textContent='The 3D view needs WebGL. Try another browser, or open a recorded MuJoCo run from the library.';$('play').disabled=true;$('contacts').disabled=true;console.error(error);}
createHomeScene($('home-canvas'),$('home-animation-pause'),$('home-animation-replay'),$('home-animation-caption'));
const params=new URLSearchParams(location.search),requestedJob=params.get('job'),requestedRun=params.get('run');
let libraryAvailable=false;
try{const response=await fetch('/api/library');if(response.ok){library=await readAPIJSON(response);libraryAvailable=true;}}catch{/* The sample remains available offline. */}
if(requestedJob){await loadItem(toy);followJob(requestedJob);}
else if(requestedRun){
  const initial=requestedRun==='toy'?toy:library.find(item=>item.id===requestedRun||item.legacy_id===requestedRun);
  if(initial)await loadItem(initial);
  else{showHome();toast('That tutorial is unavailable. Choose one from your library.');}
}else showHome();
function showHome(){
  $('home-view').hidden=false;$('studio-view').hidden=true;
  $('home-items').replaceChildren(...library.map(makeLibraryItem));
  $('home-status').hidden=libraryAvailable&&library.length>0;
  $('home-status').textContent=libraryAvailable?'No saved tutorials yet. Try the motion sample, or add a video link above.':'Your tutorials could not be loaded. Refresh to try again, or explore the motion sample.';
  $('footer-note').textContent='Watch a fold. Understand the motion. Make it your own.';
}
$('replay-fold').onclick=()=>{if(current.kind!=='paper'||active<1)return;const index=active;setPlaying(false);seek(stepTime(index));setPlaying(true);stopAt=Math.min(duration,(index+1)*duration/steps.length-.00001);};
$('final-view').onclick=()=>{setPlaying(false);seek(duration);};
document.querySelectorAll('[data-paper-view]').forEach(button=>button.onclick=()=>{scene?.setPaperView(button.dataset.paperView);document.querySelectorAll('[data-paper-view]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));});
document.querySelectorAll('[data-paper-color]').forEach(button=>button.onclick=()=>{scene?.setPaperColor(button.dataset.paperColor);document.querySelectorAll('[data-paper-color]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));});
let last=performance.now();function animate(now){const dt=Math.min((now-last)/1000,.1);last=now;if(playing){if(current.kind==='recording')seek($('recording').currentTime);else seek(Math.min(time+dt,stopAt??duration));if(time>=duration||stopAt!==null&&time>=stopAt||current.kind==='recording'&&$('recording').ended)setPlaying(false);}if(lessonDemoTime!==null&&lessonScene&&!$('teaching').hidden&&!document.hidden&&current.kind==='paper'){
  const end=Math.min(duration,stepTime(active+1))-.00001;
  lessonDemoTime+=dt;lessonScene.setTime(Math.min(lessonDemoTime,end));
  if(lessonDemoTime>=end+.8)lessonDemoTime=$('lesson-autoloop').checked&&active>0?stepTime(active):null;
}requestAnimationFrame(animate);}requestAnimationFrame(animate);
