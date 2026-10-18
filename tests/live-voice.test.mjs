import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {readAPIJSON} from '../src/ori/coaching/api.mjs';
import {LiveCoach} from '../src/ori/coaching/live-coach.mjs';

test('HTML API failures become useful server errors instead of JSON syntax errors',async()=>{
  const response=new Response('<!DOCTYPE html><h1>Not found</h1>',{status:404});
  await assert.rejects(readAPIJSON(response),/coaching server returned a web page.*HTTP 404/);
  assert.deepEqual(await readAPIJSON(new Response('{"error":"Unavailable"}',{status:503})),{error:'Unavailable'});
});

test('microphone resampling preserves duration and PCM amplitude across audio packets',async()=>{
  const source=await readFile(new URL('../src/ori/coaching/mic-processor.js',import.meta.url),'utf8');
  for(const rate of [44100,48000]){
    const packets=[];let Processor;
    vm.runInNewContext(source,{sampleRate:rate,AudioWorkletProcessor:class{constructor(){this.port={postMessage:data=>packets.push(data)};}},
      registerProcessor:(_name,Type)=>{Processor=Type;}});
    const processor=new Processor();
    // Supply one second over arbitrary render blocks; packet boundaries must not drift.
    for(let count=0;count<rate;count+=128)processor.process([[new Float32Array(Math.min(128,rate-count)).fill(.5)]]);
    assert.equal(packets.length,10,`one second at ${rate} Hz`);
    assert.equal(packets.reduce((n,p)=>n+p.byteLength,0),32000);
    for(const packet of packets){const view=new DataView(packet);assert.equal(view.getInt16(0,true),16384);}
  }
});

test('stopping during microphone permission releases any track that opens late',async()=>{
  let resolve;const original=globalThis.navigator;
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia:()=>new Promise(r=>{resolve=r;})}}});
  try{
    const events=[];const coach=new LiveCoach({context:()=>({step:0,epoch:1}),event:msg=>events.push(msg),state:()=>{}});
    coach.ready=true;coach.ensureAudio=async()=>{};
    const pending=coach.enableMicrophone();await Promise.resolve();
    coach.stop();let stopped=false;
    resolve({getTracks:()=>[{stop:()=>{stopped=true;}}]});await pending;
    assert.equal(stopped,true);assert.equal(coach.micStream,null);
    assert.equal(events.some(msg=>msg.type==='microphone'&&msg.enabled),false);
  }finally{Object.defineProperty(globalThis,'navigator',{configurable:true,value:original});}
});

test('connection recovery keeps mic tracks, restores the current step and ignores the old socket',async t=>{
  t.mock.timers.enable({apis:['setTimeout','setInterval','Date']});
  const sockets=[],requests=[],events=[];let stopped=0;
  class Socket {
    static OPEN=1;
    constructor(){this.readyState=1;this.bufferedAmount=0;this.sent=[];sockets.push(this);}
    emit(msg){this.onmessage?.({data:JSON.stringify(msg)});}
    send(raw){this.sent.push(JSON.parse(raw));}
    close(){this.readyState=3;this.onclose?.();}
  }
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    if(url==='/api/health')return new Response(JSON.stringify({service:'ori-coaching',live_protocol:4}));
    requests.push(JSON.parse(options.body));return new Response(JSON.stringify({url:'ws://127.0.0.1:12345/test'}));
  });
  const originalSocket=globalThis.WebSocket;globalThis.WebSocket=Socket;t.after(()=>{globalThis.WebSocket=originalSocket;});
  let step=1;const coach=new LiveCoach({context:()=>({runId:'lesson',step,epoch:step+1}),frame:()=>null,event:msg=>events.push(msg),state:()=>{}});
  t.after(()=>coach.stop());
  await coach.start();coach.micStream={getTracks:()=>[{stop:()=>stopped++}]};sockets[0].emit({type:'ready'});
  sockets[0].emit({type:'intro_pending',epoch:2});sockets[0].emit({type:'response_complete',epoch:2});
  sockets[0].close();assert.equal(stopped,0);assert.equal(coach.ready,false);
  step=2;t.mock.timers.tick(1000);
  for(let i=0;i<20;i++)await Promise.resolve();
  assert.equal(sockets.length,2);sockets[1].emit({type:'ready'});
  assert.equal(stopped,0);assert.ok(coach.ready);
  assert.deepEqual(sockets[1].sent[0],{type:'stage',step:2,epoch:3,after_frame_id:0,intro:false});
  assert.ok(sockets[1].sent.some(msg=>msg.type==='microphone'&&msg.enabled));
  assert.equal(requests[0].client_id,requests[1].client_id);
  sockets[0].emit({type:'progress',status:'matched'});assert.equal(events.some(msg=>msg.type==='progress'),false);
  sockets[1].close();coach.stop();assert.equal(stopped,1);
  t.mock.timers.tick(10000);for(let i=0;i<10;i++)await Promise.resolve();assert.equal(requests.length,2);
});

test('an old backend is rejected before opening a live session',async t=>{
  const requests=[];t.mock.method(globalThis,'fetch',async url=>{requests.push(url);return new Response('{}');});
  const states=[];const coach=new LiveCoach({context:()=>({runId:'lesson',step:0,epoch:1}),frame:()=>null,event:()=>{},state:(...state)=>states.push(state)});
  await coach.start();assert.deepEqual(requests,['/api/health']);assert.equal(coach.running,false);
  assert.match(states.at(-1)[1],/older version/);
});

test('matched steps wait for generation AND actual playback; long replies are not truncated',async t=>{
  let socket;const sources=[],events=[];
  class Socket {
    static OPEN=1;
    constructor(){this.readyState=1;this.bufferedAmount=0;this.sent=[];socket=this;}
    emit(msg){this.onmessage?.({data:JSON.stringify(msg)});}
    send(raw){this.sent.push(JSON.parse(raw));}
    close(){this.readyState=3;this.onclose?.();}
  }
  const original=globalThis.WebSocket;globalThis.WebSocket=Socket;t.after(()=>{globalThis.WebSocket=original;});
  t.mock.method(globalThis,'fetch',async url=>new Response(JSON.stringify(url==='/api/health'?{service:'ori-coaching',live_protocol:4}:{url:'ws://127.0.0.1:12345/test'})));
  let context={runId:'lesson',step:1,epoch:3};
  const coach=new LiveCoach({context:()=>context,frame:()=>null,event:msg=>events.push(msg),state:()=>{}});t.after(()=>coach.stop());
  await coach.start();socket.emit({type:'ready'});coach.speaking=true;coach.frameSequence=1;
  // Live claims and previous-stage frames cannot complete the step.
  for(const msg of [{},{verified:true,frame_id:0},{verified:true,frame_id:2}])socket.emit({type:'progress',step:1,epoch:3,status:'matched',...msg});
  assert.equal(coach.pendingMatch,null);
  coach.audio={state:'running',currentTime:0,destination:{},
    createBuffer:(_channels,count,rate)=>({duration:count/rate,getChannelData:()=>new Float32Array(count)}),
    createBufferSource:()=>{const source={connect(){},start(){},stop(){this.stopped=true;}};sources.push(source);return source;}};
  socket.emit({type:'intro_pending',epoch:3});
  socket.emit({type:'audio',epoch:3,data:btoa('\x00\x00'.repeat(24000))});
  socket.emit({type:'response_complete',epoch:3});
  assert.equal(coach.introduced,false,'intro generation is not the end of playback');
  sources[0].onended();
  assert.equal(coach.introduced,true);
  assert.equal(events.filter(e=>e.type==='intro_complete').length,1);
  assert.ok(socket.sent.some(m=>m.type==='intro_done'&&m.epoch===3));
  sources.length=0;
  // The intro boundary excludes old camera evidence.
  coach.frameSequence=2;
  // A generated 14-second reply used to clear the first 12 seconds from the queue.
  const second=btoa('\x00\x00'.repeat(24000));
  for(let i=0;i<14;i++)socket.emit({type:'audio',epoch:3,data:second});
  assert.equal(sources.some(s=>s.stopped),false);assert.equal(coach.sources.size,14);
  socket.emit({type:'progress',step:1,epoch:3,status:'matched',verified:true,frame_id:2});
  assert.equal(events.some(e=>e.status==='matched'&&e.type==='progress'),false);
  socket.emit({type:'response_complete',epoch:3});
  for(const source of sources.slice(0,-1))source.onended();
  assert.equal(events.some(e=>e.status==='matched'&&e.type==='progress'),false);
  sources.at(-1).onended();
  assert.equal(events.filter(e=>e.status==='matched'&&e.type==='progress').length,1);
  socket.emit({type:'turn_complete',epoch:3});assert.equal(events.filter(e=>e.type==='progress').length,1);
  // An interruption cancels the pending handoff and requests a fresh check.
  socket.emit({type:'progress',step:1,epoch:3,status:'matched',verified:true,frame_id:2});
  socket.emit({type:'interrupted'});socket.emit({type:'response_complete',epoch:3});
  assert.equal(events.filter(e=>e.type==='progress').length,1);
  assert.ok(socket.sent.some(msg=>msg.type==='recheck'&&msg.step===1&&msg.epoch===3));
  context={runId:'lesson',step:2,epoch:4};coach.stage();
  socket.emit({type:'progress',step:2,epoch:4,status:'matched',verified:true,frame_id:2});
  socket.emit({type:'response_complete',epoch:4});
  assert.equal(events.filter(e=>e.type==='progress').length,1,'previous frame cannot pass a newly selected step');
  coach.frameSequence=3;
  socket.emit({type:'progress',step:2,epoch:4,status:'matched',verified:true,frame_id:3});
  socket.emit({type:'response_complete',epoch:4});
  assert.equal(events.filter(e=>e.type==='progress').length,2);

});


test('suspended audio is scheduled rather than discarded and requests resume',async()=>{
  const events=[],starts=[];
  const coach=new LiveCoach({context:()=>({step:1,epoch:2}),event:event=>events.push(event),state:()=>{}});
  coach.speaking=true;
  coach.audio={state:'suspended',currentTime:0,destination:{},
    resume:async()=>{coach.audio.state='running';},
    createBuffer:()=>({duration:.1,getChannelData:()=>new Float32Array(2)}),
    createBufferSource:()=>({connect(){},start(at){starts.push(at);},stop(){}})};
  coach.playAudio(btoa(String.fromCharCode(0,0,0,0)));
  assert.equal(starts.length,1);
  assert.equal(coach.sources.size,1);
  await Promise.resolve();
  assert.ok(events.some(event=>event.type==='audio_blocked'));
  assert.ok(events.some(event=>event.type==='audio_resumed'));
});
