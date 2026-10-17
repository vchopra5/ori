import {readAPIJSON} from './api.mjs';
// Camera JPEGs and opt-in microphone PCM. Credentials stay in the local relay.
export class LiveCoach {
  constructor({context,frame,event,state}){
    Object.assign(this,{context,frame,event,state});this.generation=0;this.socket=null;
    this.ready=false;this.timer=null;this.abort=null;this.audio=null;this.sources=new Set();this.speaking=false;
    this.micStream=null;this.micNode=null;this.micSource=null;this.micGeneration=0;this.micPending=false;this.workletLoaded=false;
    this.connectionEpoch=0;this.clientId=crypto.randomUUID();this.reconnectTimer=null;this.connectTimeout=null;this.retryCount=0;this.readyAt=0;this.lastMessageAt=0;
    this.pendingMatch=null;this.pendingIntro=null;this.introduced=false;this.replyComplete=true;this.frameSequence=0;this.stageBoundary=0;
  }
  get running(){return Boolean(this.abort||this.socket||this.reconnectTimer);}
  async start(){this.stop();this.introduced=false;this.retryCount=0;await this.connect(this.generation);}
  async connect(generation){
    if(generation!==this.generation)return;
    const connection=++this.connectionEpoch;
    this.abort=new AbortController();this.state(this.retryCount?'reconnecting':'connecting');
    this.connectTimeout=setTimeout(()=>{if(generation===this.generation&&connection===this.connectionEpoch&&!this.ready)this.recover(generation,'The live connection timed out.');},20000);
    try{
      const healthResponse=await fetch('/api/health',{cache:'no-store',signal:this.abort.signal});
      const health=await readAPIJSON(healthResponse);if(generation!==this.generation||connection!==this.connectionEpoch)return;
      if(!healthResponse.ok||health.service!=='ori-coaching'||health.live_protocol!==4)throw Error('This Ori backend is an older version. Restart the demo server on this port, then refresh this page.');
      const response=await fetch('/api/live/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:this.context().runId,client_id:this.clientId}),signal:this.abort.signal});
      const info=await readAPIJSON(response);if(generation!==this.generation||connection!==this.connectionEpoch)return;
      if(!response.ok){const error=Error(info.error||'Live coaching could not start.');error.retryable=response.status>=500;throw error;}
      this.abort=null;const socket=this.socket=new WebSocket(info.url);
      const current=()=>generation===this.generation&&this.socket===socket;
      socket.onmessage=({data})=>{
        if(!current())return;
        let msg;try{msg=JSON.parse(data);}catch{return;}
        this.lastMessageAt=Date.now();
        if(msg.type==='ready'){
          clearTimeout(this.connectTimeout);this.connectTimeout=null;this.ready=true;this.readyAt=Date.now();this.stage();this.state('ready');
          // Existing AudioWorklet and tracks survive transport recovery.
          if(this.micStream){this.send({type:'microphone',enabled:true});this.event({type:'microphone',enabled:true,pending:false});}
          this.timer=setInterval(()=>{
            if(!current()||!this.ready)return;
            if(Date.now()-this.lastMessageAt>20000){this.recover(generation,'The live connection stopped responding.');return;}
            if(this.pendingMatch&&Date.now()-this.pendingMatch.at>30000&&!this.sources.size){this.recover(generation,'The step check stopped responding.');return;}
            if(socket.readyState!==WebSocket.OPEN||socket.bufferedAmount>100000)return;
            this.send({type:'ping'});
            const data=this.introduced?this.frame():null;if(data){const {step,epoch}=this.context();this.send({type:'frame',data,step,epoch,frame_id:++this.frameSequence});}
          },1000);
        }else if(msg.type==='intro_pending'){
          if(msg.epoch===this.context().epoch){this.pendingIntro={epoch:msg.epoch};this.replyComplete=false;}
        }else if(msg.type==='progress'&&msg.status==='matched'){
          const context=this.context();if(msg.epoch!==context.epoch||msg.step!==context.step||msg.verified!==true||!Number.isSafeInteger(msg.frame_id)||msg.frame_id<=this.stageBoundary||msg.frame_id>this.frameSequence)return;
          if(!this.pendingMatch){this.pendingMatch={message:msg,at:Date.now()};this.replyComplete=false;this.event({...msg,type:'match_pending'});}
        }else if(msg.type==='response_complete'||msg.type==='turn_complete'){
          if(msg.epoch!==undefined&&msg.epoch!==this.context().epoch)return;
          this.replyComplete=true;this.event(msg);this.finishIntro();this.finishMatch();
        }else if(msg.type==='heartbeat'){/* A quiet coach is healthy while heartbeats arrive. */}
        else if(msg.type==='error'){
          if(msg.retryable)this.recover(generation,msg.message);else this.fail(msg.message);
        }else if(msg.type==='interrupted'){this.cancelMatch(true);this.clearAudio();}
        else if(msg.type==='audio'){if(msg.epoch===this.context().epoch){this.replyComplete=false;this.playAudio(msg.data);}}
        else if(msg.type==='user_caption'){this.cancelMatch(true);this.event(msg);}
        else if(msg.type==='caption'){this.replyComplete=false;this.event(msg);}
        else this.event(msg);
      };
      socket.onclose=()=>{if(current())this.recover(generation,'The live connection closed.');};
      socket.onerror=()=>{if(current())this.recover(generation,'The live connection was interrupted.');};
    }catch(error){
      if(generation!==this.generation||connection!==this.connectionEpoch||error.name==='AbortError')return;
      if(error.retryable||error instanceof TypeError)this.recover(generation,error.message);else this.fail(error.message);
    }
  }
  disconnectTransport(){
    this.cancelMatch();this.pendingIntro=null;
    this.connectionEpoch++;this.ready=false;this.abort?.abort();this.abort=null;
    clearInterval(this.timer);this.timer=null;clearTimeout(this.connectTimeout);this.connectTimeout=null;
    const socket=this.socket;this.socket=null;socket?.close();this.clearAudio();
  }
  recover(generation,message){
    if(generation!==this.generation||this.reconnectTimer)return;
    if(this.readyAt&&Date.now()-this.readyAt>30000)this.retryCount=0;
    this.readyAt=0;this.disconnectTransport();
    if(this.retryCount>=3){this.fail(message+' Turn the camera on again to retry.');return;}
    const delay=Math.min(4000,1000*2**this.retryCount++);
    this.state('reconnecting');
    this.reconnectTimer=setTimeout(()=>{this.reconnectTimer=null;this.connect(generation);},delay);
  }
  fail(message){this.stop();this.state('error',message);}
  send(msg){if(this.ready&&this.socket?.readyState===WebSocket.OPEN)this.socket.send(JSON.stringify(msg));}
  stage(){this.cancelMatch();this.pendingIntro=null;this.clearAudio();this.stageBoundary=this.frameSequence;const {step,epoch}=this.context();if(this.ready&&!this.introduced)this.event({type:'intro_start',epoch});this.send({type:'stage',step,epoch,after_frame_id:this.stageBoundary,intro:!this.introduced});}
  finishIntro(){
    if(!this.pendingIntro||!this.replyComplete||this.sources.size)return;
    const {epoch}=this.pendingIntro;this.pendingIntro=null;
    if(epoch!==this.context().epoch)return;
    this.introduced=true;this.stageBoundary=this.frameSequence;
    this.event({type:'intro_complete',epoch});
    this.send({type:'intro_done',epoch});
  }
  ask(text){this.cancelMatch(true);this.send({type:'ask',text});}
  cancelMatch(recheck=false){
    if(recheck&&this.pendingMatch){const {step,epoch}=this.context();this.send({type:'recheck',step,epoch});}
    this.pendingMatch=null;
  }
  finishMatch(){
    if(!this.pendingMatch||!this.replyComplete||this.sources.size)return;
    const msg=this.pendingMatch.message,{step,epoch}=this.context();this.pendingMatch=null;
    if(msg.step===step&&msg.epoch===epoch)this.event(msg);
  }
  async ensureAudio(){this.audio??=new AudioContext();await this.audio.resume();}
  async toggleVoice(){
    this.speaking=!this.speaking;
    if(this.speaking){
      try{await this.ensureAudio();}
      catch{this.speaking=false;}
    }else this.clearAudio();
    return this.speaking;
  }
  async enableMicrophone(inputStream=null){
    if(!this.ready)throw Error('Start your camera before enabling the microphone.');
    if(this.micStream||this.micPending)return;
    const generation=++this.micGeneration,session=this.generation;
    this.micPending=true;this.event({type:'microphone',enabled:false,pending:true});
    try{
      await this.ensureAudio();
      const stream=inputStream||await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
      if(generation!==this.micGeneration||session!==this.generation){stream.getTracks().forEach(t=>t.stop());return;}
      this.micStream=stream;
      if(!this.workletLoaded){await this.audio.audioWorklet.addModule(new URL('./mic-processor.js',import.meta.url));this.workletLoaded=true;}
      if(generation!==this.micGeneration||session!==this.generation){stream.getTracks().forEach(t=>t.stop());return;}
      this.micSource=this.audio.createMediaStreamSource(stream);
      this.micNode=new AudioWorkletNode(this.audio,'ori-microphone',{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[1]});
      this.micNode.port.onmessage=({data})=>{
        if(generation!==this.micGeneration||!this.ready||this.socket?.bufferedAmount>64000)return;
        const bytes=new Uint8Array(data);let raw='';for(const byte of bytes)raw+=String.fromCharCode(byte);
        this.send({type:'audio',data:btoa(raw)});
      };
      this.micSource.connect(this.micNode);this.micNode.connect(this.audio.destination);
      this.send({type:'microphone',enabled:true});this.speaking=true;
      this.event({type:'voice',enabled:true});
      this.micPending=false;this.event({type:'microphone',enabled:true,pending:false});
      stream.getAudioTracks()[0]?.addEventListener('ended',()=>{if(this.micStream===stream){this.stopMicrophone();this.event({type:'microphone_ended'});}});
    }catch(error){
      if(generation!==this.micGeneration||session!==this.generation)return;
      this.stopMicrophone();
      throw Error(error.name==='NotAllowedError'?'Microphone access was denied. Allow it in your browser, then turn the camera on again.':'Could not start the microphone. Check your browser’s microphone settings and try again.');
    }
  }
  stopMicrophone(){
    this.micGeneration++;this.micPending=false;
    if(this.micNode){this.micNode.port.onmessage=null;this.micNode.disconnect();this.micNode.port.close();this.micNode=null;}
    this.micSource?.disconnect();this.micSource=null;
    this.micStream?.getTracks().forEach(t=>t.stop());this.micStream=null;
    this.send({type:'microphone',enabled:false});this.event({type:'microphone',enabled:false,pending:false});
  }
  playAudio(encoded){
    if(!this.speaking||!this.audio||this.audio.state!=='running')return;
    const raw=atob(encoded),bytes=Uint8Array.from(raw,char=>char.charCodeAt(0));
    const samples=new DataView(bytes.buffer),buffer=this.audio.createBuffer(1,bytes.length/2,24000),channel=buffer.getChannelData(0);
    for(let i=0;i<channel.length;i++)channel[i]=samples.getInt16(i*2,true)/32768;
    // Generated audio can arrive faster than it plays. Never truncate a reply
    // just because its queued duration exceeds a fixed number of seconds.
    const source=this.audio.createBufferSource();source.buffer=buffer;source.connect(this.audio.destination);
    this.audioAt=Math.max(this.audio.currentTime,this.audioAt||0);source.start(this.audioAt);this.audioAt+=buffer.duration;
    if(!this.sources.size)this.send({type:'playback',playing:true,...this.contextForWire()});
    this.sources.add(source);source.onended=()=>{
      const removed=this.sources.delete(source);
      if(removed&&!this.sources.size)this.send({type:'playback',playing:false,...this.contextForWire()});
      this.finishIntro();this.finishMatch();
    };
  }
  contextForWire(){const {step,epoch}=this.context();return {step,epoch};}
  clearAudio(){const playing=this.sources.size>0;for(const source of this.sources){try{source.stop();}catch{/* Already ended. */}}this.sources.clear();this.audioAt=0;if(playing)this.send({type:'playback',playing:false,...this.contextForWire()});}
  stop(){
    this.stopMicrophone();this.generation++;clearTimeout(this.reconnectTimer);this.reconnectTimer=null;
    this.disconnectTransport();this.state('stopped');
  }
}
