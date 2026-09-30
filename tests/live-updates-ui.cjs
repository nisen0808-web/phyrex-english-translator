const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8');
class Element{
  constructor(tag){this.tag=tag;this.children=[];this.className='';this.textContent='';this.attrs={};this.scrollTop=29;this.scrollHeight=999;this.writes=0;}
  append(...items){for(const item of items){item.parent=this;this.children.push(item);}this.writes++;}
  replaceChildren(...items){for(const child of this.children)child.parent=null;this.children=[];this.append(...items);}
  remove(){if(this.parent){this.parent.children.splice(this.parent.children.indexOf(this),1);this.parent=null;}}
  setAttribute(k,v){this.attrs[k]=v;}
  querySelector(selector){return this.children.find(e=>e.className===selector.slice(1));}
}
const elements={transcript:new Element('main'),autoScroll:{checked:false}};
let copied;
const ctx={document:{createElement:tag=>new Element(tag)},$:id=>elements[id],clock:x=>String(x),
  canCopy:r=>r.status==='done'&&Boolean(r.text),needsReview:r=>Boolean(r.note||r.review),
  showCopyIcon:e=>{e.icon=true;},copyTranslation:(...args)=>{copied=args;}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('const renderedRows = new Map();'),source.indexOf('function render(state){')),ctx);
const session={id:'live',rows:Array.from({length:500},(_,seq)=>({seq,start:seq*4,end:seq*4+4,status:'done',text:'中文正文 '+seq,note:'',review:false}))};
session.rows[499]={...session.rows[499],text:'',status:'translating',preview:'中文预览'};
ctx.renderTranscript(session);
const original=elements.transcript.children.slice(),button=original[0].children[0].children[1];
button.disabled=true;button.icon='copied';
session.rows[499].preview+='逐字更新';ctx.renderTranscript(session);
assert.equal(elements.transcript.children.length,500);
assert.ok(original.every((node,i)=>node===elements.transcript.children[i]),'Preview updates must preserve all existing row elements');
assert.equal(button.icon,'copied');assert.equal(button.disabled,true);assert.equal(elements.transcript.scrollTop,29);
assert.equal(original[499].children[1].textContent,'中文预览逐字更新');
assert.equal(original[499].children[0].children.length,1,'Preview has no copy button');
session.rows[499]={...session.rows[499],status:'done',text:'最终译文',note:'数字待核实',review:true};delete session.rows[499].preview;
ctx.renderTranscript(session);
const finalCopy=original[499].children[0].children[1];assert.ok(finalCopy.icon);finalCopy.onclick();
assert.equal(copied[0],'live');assert.equal(copied[1],499);assert.equal(original[499].children[1].textContent,'最终译文');
assert.equal(original[499].children.filter(e=>e.className==='stream-label').length,0);
assert.match(original[499].children.at(-1).textContent,/数字待核实/);
session.rows[499].status='queued';session.rows[499].text='';ctx.renderTranscript(session);
assert.equal(original[499].children[0].children.length,1,'Retry removes copy permission');
session.rows=session.rows.slice(0,499);ctx.renderTranscript(session);assert.equal(elements.transcript.children.length,499);
console.log('PASS 500-row DOM identity, preview/final/retry transitions, review copy, and manual scroll');

const connections=[],renders=[],ui={connection:{hidden:true}},pending=[];
class EventSource{
  constructor(url){this.url=url;this.listeners={};connections.push(this);}
  addEventListener(type,fn){this.listeners[type]=fn;}
  close(){this.closed=true;}
  emit(type,data){this.listeners[type]({data:JSON.stringify(data)});}
}
const net={EventSource,AbortSignal,Date,Number,Map,Array,JSON,window:{addEventListener(){}},selected:'s1',pollBusy:false,hadLogin:false,lastLoginPoll:0,token:'old',
  active:'',running:false,lastHeartbeat:0,lastState:null,uploads:[],samples:0,totalSamples:0,
  $:id=>ui[id]||{},request:async()=>({}),finishWhenReady:()=>{},renderLatency:()=>{},
  render:state=>{renders.push(state);net.lastState=state;if(state.session)net.selected=state.session.id;},
  fetch:(url)=>url.startsWith('/api/config')?Promise.resolve({ok:true,json:async()=>({token:'fresh'})}):new Promise(resolve=>pending.push(resolve))};
vm.createContext(net);
vm.runInContext(source.slice(source.indexOf('// A reconnect always starts'),source.indexOf('async function init(){')),net);
const snapshot=(revision,id='s1',text='第一段')=>({revision,session:{id,rows:[{seq:0,status:'done',text}]},login:{running:false}});
(async()=>{
  net.ensureEventStream();let connection=connections.at(-1);connection.onopen();connection.emit('snapshot',snapshot(1));
  const stale=net.poll();
  connection.emit('update',{state:{revision:3,session:{id:'s1'},login:{}},rows:[{seq:1,status:'translating',preview:'第二段'}],removed:[]});
  pending.shift()({ok:true,json:async()=>snapshot(2)});await stale;
  assert.equal(renders.at(-1).revision,3,'Late polling must not replace newer streamed state');
  assert.equal(renders.at(-1).session.rows.length,2);
  const before=pending.length;net.maintainLivePage();assert.equal(pending.length,before,'Healthy streams stop polling');
  net.selected='history';net.ensureEventStream();assert.equal(connection.closed,true);
  const renderCount=renders.length;connection.emit('snapshot',snapshot(100));assert.equal(renders.length,renderCount,'Old selected session must not overwrite history');
  connection=connections.at(-1);connection.onopen();connection.emit('snapshot',snapshot(5,'history','历史记录'));
  assert.equal(renders.at(-1).session.rows[0].text,'历史记录');
  connection.onerror();assert.equal(pending.length,1,'Disconnect falls back to polling');
  connection.onopen();connection.emit('snapshot',snapshot(0,'history','重启后的完整记录'));
  pending.shift()({ok:true,json:async()=>snapshot(6,'history','旧响应')});await new Promise(r=>setImmediate(r));
  assert.equal(renders.at(-1).session.rows[0].text,'重启后的完整记录','Old connection response cannot overwrite restart snapshot');
  assert.equal(net.token,'fresh');
  console.log('PASS SSE delta merge, stale polling guard, history isolation, fallback and restart recovery');
})().catch(e=>{console.error(e);process.exitCode=1;});
