class PCMProcessor extends AudioWorkletProcessor {
  constructor(){super();this.phase=0;this.sum=0;this.n=0;this.frame=new Int16Array(320);this.pos=0;}
  process(inputs,outputs){
    const channels=inputs[0];
    if(channels&&channels.length&&channels[0].length){
      for(let i=0;i<channels[0].length;i++){
        let value=0;for(let c=0;c<channels.length;c++)value+=channels[c][i];value/=channels.length;
        this.sum+=value;this.n++;this.phase+=16000;
        if(this.phase>=sampleRate){
          this.phase-=sampleRate;
          this.frame[this.pos++]=Math.max(-32768,Math.min(32767,Math.round(this.sum/this.n*32767)));
          this.sum=0;this.n=0;
          if(this.pos===320){const buffer=this.frame.buffer;this.port.postMessage(buffer,[buffer]);this.frame=new Int16Array(320);this.pos=0;}
        }
      }
    }
    for(const channel of outputs[0]||[])channel.fill(0);
    return true;
  }
}
registerProcessor('pcm-capture',PCMProcessor);
