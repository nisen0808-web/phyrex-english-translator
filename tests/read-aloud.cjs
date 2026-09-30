const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const script=fs.readFileSync(process.argv[2],'utf8');
const code=script.match(/\/\* BEGIN PHYREX READ ALOUD \*\/[\s\S]*?\/\* END PHYREX READ ALOUD \*\//)?.[0];
assert.ok(code,'Packaged read-aloud module missing');
const sandbox={setTimeout,clearTimeout};vm.createContext(sandbox);vm.runInContext(code,sandbox);
const Reader=vm.runInContext('PhyrexChineseReader',sandbox),Monitor=vm.runInContext('PhyrexOriginalAudio',sandbox);
const reports=[];
function test(name,run){run();reports.push(name);console.log('PASS '+name);}
function harness(voices=[{voiceURI:'local-cn',lang:'zh-CN',name:'中文',localService:true}]){
  const spoken=[],muted=[],timers=new Map();let timer=0;
  const synth={getVoices:()=>voices,speak:u=>spoken.push(u),cancel(){this.cancels=(this.cancels||0)+1;}};
  const r=new Reader({synth,Utterance:class{constructor(text){this.text=text;}},speaking:value=>muted.push(value),later:fn=>{timers.set(++timer,fn);return timer;},clear:id=>timers.delete(id)});
  const row=(seq,text='中文正文',status='done')=>({seq,text,status,note:'待核实说明不朗读',review:true,start:12,end:24});
  const observe=rows=>r.observe({id:'live',rows});
  return {r,spoken,muted,timers,row,observe};
}
test('Opt-in and historical-session isolation',()=>{const h=harness();h.r.begin('live');h.observe([h.row(0)]);assert.equal(h.spoken.length,0);h.r.enable(true);h.r.begin('live');h.r.observe({id:'history',rows:[h.row(0)]});assert.equal(h.spoken.length,0);});
test('Only local Chinese voices can be selected',()=>{const h=harness([{lang:'zh-CN',localService:false},{lang:'en-US',localService:true}]);assert.equal(h.r.enable(true),false);h.r.preview();assert.equal(h.spoken.length,0);});
test('Chinese body only, with notes and timestamps excluded',()=>{const h=harness();h.r.enable(true);h.r.begin('live');h.observe([h.row(0)]);assert.equal(h.spoken[0].text,'中文正文');assert.equal(h.muted.at(-1),true);h.spoken[0].onend();assert.equal(h.muted.at(-1),false);});
test('Repeated polls never repeat completed paragraphs',()=>{const h=harness();h.r.enable(true);h.r.begin('live');h.observe([h.row(0)]);h.spoken[0].onend();h.observe([h.row(0)]);assert.equal(h.spoken.length,1);});
test('Wait for earlier pending translation, then preserve order',()=>{const h=harness();h.r.enable(true);h.r.begin('live');h.observe([h.row(1,'第二'),h.row(0,'','translating')]);assert.equal(h.spoken.length,0);h.observe([h.row(1,'第二'),h.row(0,'第一')]);assert.equal(h.spoken[0].text,'第一');h.spoken[0].onend();assert.equal(h.spoken[1].text,'第二');});
test('Prepared audio still blocks out-of-order speech',()=>{const h=harness();h.r.enable(true);h.r.begin('live');h.observe([h.row(0,'','waiting_translation'),h.row(1,'第二')]);assert.equal(h.spoken.length,0);h.observe([h.row(0,'第一'),h.row(1,'第二')]);assert.equal(h.spoken[0].text,'第一');h.spoken[0].onend();assert.equal(h.spoken[1].text,'第二');});
test('Streaming preview is never spoken before validation',()=>{const h=harness();h.r.enable(true);h.r.begin('live');h.observe([{...h.row(0,'','translating'),preview:'正在形成的中文'}]);assert.equal(h.spoken.length,0);h.observe([h.row(0,'校验完成的中文')]);assert.equal(h.spoken[0].text,'校验完成的中文');});
test('Pause restores English and resume skips paused backlog',()=>{const h=harness();h.r.enable(true);h.r.begin('live');h.observe([h.row(0)]);const stale=h.spoken[0];h.r.pause();assert.equal(h.muted.at(-1),false);h.observe([h.row(0),h.row(1)]);h.r.pause();h.observe([h.row(0),h.row(1),h.row(2,'最新')]);assert.equal(h.spoken.at(-1).text,'最新');stale.onend();assert.equal(h.muted.at(-1),true);});
test('Bounded queue sheds older audio but never alters saved rows',()=>{const h=harness();h.r.enable(true);h.r.begin('live');const rows=Array.from({length:12},(_,i)=>h.row(i,'第'+i));h.observe(rows);assert.equal(h.r.skipped,6);assert.equal(h.spoken[0].text,'第6');assert.equal(rows.length,12);assert.equal(h.r.queue.length,5);});
test('Long paragraph is split without losing text',()=>{const h=harness();h.r.enable(true);h.r.begin('live');const text='劳动市场保持平稳。'.repeat(40);h.observe([h.row(0,text)]);while(h.r.current){assert.ok(h.r.current.text.length<=160);h.r.current.onend();}assert.equal(h.spoken.map(u=>u.text).join(''),text);});
test('Stop ends speaking and ignores all late speech callbacks',()=>{const h=harness();h.r.enable(true);h.r.begin('live');h.observe([h.row(0)]);const stale=h.spoken[0];h.r.stop();stale.onerror();stale.onend();stale.onstart();assert.equal(h.muted.at(-1),false);assert.equal(h.timers.size,0);assert.equal(h.r.session,'');});
test('Watchdog and synthesis errors restore English',()=>{for(const timeout of [true,false]){const h=harness();h.r.enable(true);h.r.begin('live');h.observe([h.row(0)]);if(timeout)[...h.timers.values()][0]();else h.spoken[0].onerror();assert.equal(h.muted.at(-1),false);assert.equal(h.r.paused,true);assert.equal(h.r.current,null);}});
test('New session cannot inherit previous speech or deduplication',()=>{const h=harness();h.r.enable(true);h.r.begin('old');h.r.observe({id:'old',rows:[h.row(0)]});const stale=h.spoken[0];h.r.begin('live');h.observe([h.row(0,'新会话')]);stale.onend();assert.equal(h.spoken.at(-1).text,'新会话');assert.equal(h.muted.at(-1),true);});
test('Unconfirmed suppression and non-tab capture are rejected',()=>{for(const [surface,suppressed] of [['browser',false],['browser',undefined],['monitor',true]]){const m=new Monitor();assert.throws(()=>m.attach({}, {}, {getAudioTracks:()=>[{getSettings:()=>({suppressLocalAudioPlayback:suppressed})}],getVideoTracks:()=>[{getSettings:()=>({displaySurface:surface})}]}));}});
test('Ducking touches only monitor gain; recognition source and track stay active',()=>{
  const outputs=[],audio={enabled:true,getSettings:()=>({suppressLocalAudioPlayback:true})};
  const gain={gain:{value:1,cancelScheduledValues(){},setValueAtTime(v){this.value=v;}},connect(){},disconnect(){this.disconnected=true;}};
  const context={createGain:()=>gain,currentTime:0,state:'running',destination:{}};
  const source={connect:node=>outputs.push(node)},processor={};source.connect(processor);
  const m=new Monitor();m.attach(context,source,{getAudioTracks:()=>[audio],getVideoTracks:()=>[{getSettings:()=>({displaySurface:'browser'})}]});
  m.speaking(true);assert.equal(gain.gain.value,0);assert.equal(audio.enabled,true);assert.equal(outputs[0],processor);
  m.speaking(false);assert.equal(gain.gain.value,1);m.detach();assert.equal(gain.disconnected,true);assert.equal(outputs[0],processor);
});
const out=process.argv[3];fs.mkdirSync(path.dirname(out),{recursive:true});fs.writeFileSync(out,JSON.stringify({passed:reports.length,checks:reports,not_tested:['Physical speaker output','Real YouTube sharing dialog and playback on Windows and Mac']},null,2));
