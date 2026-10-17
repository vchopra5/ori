// Resample the browser's microphone to mono 16 kHz PCM, in 100 ms packets.
class OriMicrophone extends AudioWorkletProcessor {
  constructor(){
    super();this.ratio=sampleRate/16000;this.remaining=this.ratio;this.sum=0;
    this.packet=new ArrayBuffer(3200);this.view=new DataView(this.packet);this.offset=0;
  }
  process(inputs){
    const channel=inputs[0]?.[0];if(!channel)return true;
    for(const sample of channel){
      let available=1;
      while(available>1e-8){
        const weight=Math.min(available,this.remaining);
        this.sum+=sample*weight;this.remaining-=weight;available-=weight;
        if(this.remaining<1e-8){
          const value=Math.max(-1,Math.min(1,this.sum/this.ratio));
          this.view.setInt16(this.offset,Math.round(value*(value<0?32768:32767)),true);this.offset+=2;
          this.remaining=this.ratio;this.sum=0;
          if(this.offset===this.packet.byteLength){
            this.port.postMessage(this.packet,[this.packet]);
            this.packet=new ArrayBuffer(3200);this.view=new DataView(this.packet);this.offset=0;
          }
        }
      }
    }
    // Output stays silent: never feed the microphone back into the speakers.
    return true;
  }
}
registerProcessor('ori-microphone',OriMicrophone);
