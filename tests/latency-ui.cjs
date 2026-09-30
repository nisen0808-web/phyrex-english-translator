const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8');
const onFrame=source.slice(source.indexOf('function onFrame('),source.indexOf('function flush('));
function run(pending,framesCount,quiet,chunkSeconds=12,latency){
  const context={running:true,frames:[],samples:0,quiet:0,uploads:[],lastState:{pending,latency},chunkSeconds,totalSamples:0,Int16Array,Math,Number,
    clock:x=>x,$:()=>({}),flush(){context.sent.push(context.samples/16000);context.samples=0;context.quiet=0;context.frames=[];},sent:[]};
  vm.createContext(context);vm.runInContext(onFrame,context);
  for(let i=0;i<framesCount;i++)context.onFrame(new Int16Array(320).fill(quiet?0:1000).buffer);
  return context;
}
assert.deepEqual(run(0,150,true).sent,[3],'Idle natural pause should flush after three seconds');
assert.deepEqual(run(2,150,true).sent,[],'AI backlog must not produce extra three-second requests');
assert.deepEqual(run(2,300,true).sent,[6],'Existing six-second pause boundary is retained under load');
assert.deepEqual(run(2,600,false).sent,[12],'Selected maximum must still apply during continuous speech');
assert.deepEqual(run(0,200,false,0).sent,[4],'Auto follows at four seconds when no backlog');
assert.deepEqual(run(2,200,false,0).sent,[],'Auto waits under backlog instead of multiplying requests');
assert.deepEqual(run(2,400,false,0).sent,[8],'Auto remains bounded at eight seconds under backlog');
assert.deepEqual(run(2,200,false,0,{queued:0,recognizing:1,translating:1,recommended_chunk_seconds:3}).sent,[4],'Normal parallel work must not force eight-second chunks');
assert.deepEqual(run(2,150,false,0,{queued:1,recommended_chunk_seconds:3}).sent,[],'Actual waiting still limits request bursts');
assert.deepEqual(run(0,200,false,0,{queued:0,recommended_chunk_seconds:1}).sent,[4],'Never force continuous speech into sub-four-second chunks');
const el={textContent:''},ctx={$:()=>el,Number,Math};vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function renderLatency(')),ctx);
ctx.renderLatency({pending:2,latency:{recognizing:1,translating:1,queued:0,oldest_processing_seconds:28.2}});
assert.match(el.textContent,/语音识别中.*AI 翻译中/);
assert.match(el.textContent,/28.2/);
assert.match(el.textContent,/不一定/);
ctx.renderLatency({pending:0,latency:{latest:{processing_seconds:9,asr_seconds:2,translation_seconds:5,recognition_wait_seconds:1,translation_wait_seconds:1}}});
assert.match(el.textContent,/排队 2.0 秒/);
assert.match(el.textContent,/不含收集音频/);
assert.ok(source.includes("waiting_translation:'已识别，等待翻译…'"));
console.log('PASS idle pause, loaded pause, selected chunk maximum, and measured-stage display');
