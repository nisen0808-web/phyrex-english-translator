'use strict';
let glossaryInfo=null;
'use strict';
const sidebarMode=new URLSearchParams(location.search).get('view')==='sidebar';if(sidebarMode){document.body.classList.add('sidebar-mode');document.documentElement.style.setProperty('--font','18px');}
'use strict';
const $=id=>document.getElementById(id);
let token='',selected='',active='',stream=null,ctx=null,processor=null;
let running=false,starting=false,stopping=false,uploading=false,frames=[],samples=0,quiet=0,seq=0,totalSamples=0,uploads=[];
let failedFinish='',lastSignature='',renderedSid='',fontSize=sidebarMode?18:22,chunkSeconds=20,pollBusy=false,lastState=null;
let lastHeartbeat=0,lastLoginPoll=0,hadLogin=false;
function notice(message){$('notice').textContent=message;$('notice').hidden=!message;}
async function request(path,body={},raw=false,reconnect=true){
  const res=await fetch(path,{method:'POST',signal:AbortSignal.timeout(15000),headers:{'X-Local-Token':token,'Content-Type':raw?'application/octet-stream':'application/json'},body:raw?body:JSON.stringify(body)});
  const data=await res.json();
  if(res.status===403&&reconnect){
    const cfgResponse=await fetch('/api/config',{signal:AbortSignal.timeout(5000)});
    if(cfgResponse.ok){const cfg=await cfgResponse.json();if(cfg.app==='fed-live-translator'&&cfg.token!==token){token=cfg.token;return request(path,body,raw,false);}}
  }
  if(!res.ok){const error=new Error(data.error||'本地服务请求失败');error.status=res.status;throw error;}return data;
}
function clock(seconds){const s=Math.max(0,Math.floor(seconds));return [Math.floor(s/3600),Math.floor(s%3600/60),s%60].map(x=>String(x).padStart(2,'0')).join(':');}
function needsReview(row){return Boolean(row.review||row.note?.trim());}
function canCopy(row){return row?.status==='done'&&Boolean(row.text?.trim());}
function showCopyIcon(button,copied=false){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  for(const [name,value] of Object.entries({viewBox:'0 0 24 24',width:'18',height:'18',fill:'none',stroke:'currentColor','stroke-width':'1.7','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(name,value);
  const path=document.createElementNS('http://www.w3.org/2000/svg','path');
  path.setAttribute('d',copied?'M5 12l4 4L19 6':'M8 8h12v12H8z M16 8V4H4v12h4');svg.append(path);button.replaceChildren(svg);
  button.title=copied?'已复制':'复制这一段中文（不含时间戳和待核实说明）';
}
async function copyTranslation(sessionId,sequence,button){
  const session=lastState?.session;
  const row=session?.id===sessionId?session.rows.find(item=>item.seq===sequence):null;
  if(button.disabled||!canCopy(row))return;
  const text=row.text.trim();
  button.disabled=true;
  try{
    if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);
    else{
      const input=document.createElement('textarea');input.value=text;input.readOnly=true;
      input.className='clipboard-buffer';document.body.append(input);input.select();
      try{if(!document.execCommand('copy'))throw new Error('Copy failed');}finally{input.remove();button.focus();}
    }
    showCopyIcon(button,true);
    setTimeout(()=>{if(button.isConnected)showCopyIcon(button);},2000);
  }catch(e){if(lastState?.session?.id===sessionId)notice('这一段复制失败，请允许此页面使用剪贴板后重试。');}
  finally{button.disabled=false;}
}
function onFrame(buffer){
  if(!running)return;
  const frame=new Int16Array(buffer);frames.push(frame);samples+=frame.length;
  let power=0;for(const x of frame)power+=x*x;
  quiet=Math.sqrt(power/frame.length)<200?quiet+frame.length:0;
  if(samples>=chunkSeconds*16000||(samples>=6*16000&&quiet>=9600))flush();
  $('duration').textContent=clock((totalSamples+samples)/16000);
}
function flush(){
  if(samples<160){frames=[];samples=0;return;}
  const pcm=new Int16Array(samples);let p=0;for(const f of frames){pcm.set(f,p);p+=f.length;}
  uploads.push({sid:active,seq:seq++,start:totalSamples/16000,buffer:pcm.buffer});totalSamples+=samples;
  frames=[];samples=0;quiet=0;
  if(uploads.length>=12&&running){notice('处理速度暂时跟不上播放，已停止采集。正在处理已采集内容，请稍后从视频对应位置继续。');stopCapture();}
  pump();
}
async function pump(){
  if(uploading)return;uploading=true;
  try{
    while(uploads.length){
      const item=uploads[0];
      try{
        await request(`/api/audio?session=${encodeURIComponent(item.sid)}&seq=${item.seq}&start=${item.start}`,item.buffer,true);
        uploads.shift();
      }catch(e){
        if(e.status===400||e.status===403){notice(e.message+'。缓存音频尚未提交，请保持页面打开并检查服务。');if(running)stopCapture();break;}
        notice(e.status===429?'待处理片段较多，正在排队；已采集音频暂存在内存。':'连接暂时中断，正在重试。请保持页面打开，已有中文已保存。');
        if(uploads.length>=12&&running)stopCapture();
        await new Promise(resolve=>setTimeout(resolve,2000));
      }
    }
  }finally{uploading=false;}
  await finishWhenReady();
}
async function finishWhenReady(){
  if(failedFinish&&!uploads.length&&!uploading){
    try{await request('/api/finish',{session:failedFinish});failedFinish='';stopping=false;active='';await poll();}
    catch(e){notice('结束标记尚未保存，正在重试，请保持页面打开。');}
  }
}
async function startCapture(){
  if(running||starting||stopping)return;starting=true;$('start').disabled=true;notice('');
  let sid='';
  try{
    if(!navigator.mediaDevices?.getDisplayMedia)throw new Error('请用桌面版 Chrome 或 Edge 打开这个本地地址。');
    stream=await navigator.mediaDevices.getDisplayMedia({video:true,audio:{suppressLocalAudioPlayback:false},systemAudio:'exclude',selfBrowserSurface:'exclude'});
    if(!stream.getAudioTracks().length)throw new Error('没有共享到声音。请选择正在播放的标签页，并勾选“共享标签页音频”。');
    ctx=new AudioContext();await ctx.audioWorklet.addModule('/capture.js');await ctx.resume();
    processor=new AudioWorkletNode(ctx,'pcm-capture');
    const source=ctx.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));source.connect(processor);processor.connect(ctx.destination);
    const result=await request('/api/start',{title:$('title').value,model:$('model').value,profile:$('profile').value});sid=result.id;
    selected=active=sid;running=true;if(sidebarMode)document.body.classList.add('settings-folded');seq=0;totalSamples=0;frames=[];samples=0;uploads=[];quiet=0;
    chunkSeconds=Number($('chunk').value);lastSignature='';processor.port.onmessage=e=>onFrame(e.data);
    for(const track of stream.getTracks())track.onended=()=>{if(running)stopCapture();};
    $('stop').disabled=false;notice('已开始采集。第一段中文将在音频分段和翻译完成后出现。');
  }catch(e){
    for(const track of stream?.getTracks()||[])track.stop();if(ctx)await ctx.close().catch(()=>{});ctx=null;stream=null;
    if(sid)await request('/api/finish',{session:sid}).catch(()=>{});
    notice(e.name==='NotAllowedError'?'未共享声音。准备好后，可以重新选择直播标签页。':e.message);
  }finally{starting=false;await poll();}
}
async function stopCapture(){
  if(!running&&!stopping&&lastState?.session?.status==='recording'){
    try{await request('/api/finish',{session:lastState.session.id});notice('已结束采集会话，正在完成已提交的片段。');await poll();}catch(e){notice(e.message);}return;
  }
  if(!running||stopping)return;stopping=true;running=false;$('stop').disabled=true;
  if(processor)processor.port.onmessage=null;
  flush();
  for(const track of stream?.getTracks()||[]){track.onended=null;track.stop();}
  if(ctx)await ctx.close().catch(()=>{});stream=null;ctx=null;processor=null;
  failedFinish=active;await pump();await finishWhenReady();
}
function render(state){
  lastState=state;document.getElementById('sidebarStop').hidden=!sidebarMode||(!running&&!stopping);document.getElementById('sidebarStop').disabled=stopping;
  if(state.storage_error)notice(state.storage_error);
  $('asrStatus').textContent=(state.asr.ready?'✓ ':'○ ')+state.asr.message;$('asrStatus').className=state.asr.ready?'ok':'';
  $('codexStatus').textContent=(state.codex.ready?'✓ ':'○ ')+state.codex.message;$('codexStatus').className=state.codex.ready?'ok':'';
  const login=state.login||{};
  $('login').hidden=state.codex.ready&&!login.running;$('login').disabled=Boolean(login.running);
  $('login').textContent=login.running?'等待官方页面登录…':'登录自己的 ChatGPT';
  $('loginMessage').hidden=!login.message;$('loginMessage').textContent=login.message||'';
  let officialLogin='';try{const u=new URL(login.url);if(u.protocol==='https:'&&['auth.openai.com','auth.chatgpt.com','chatgpt.com'].includes(u.hostname))officialLogin=u.href;}catch(e){}
  $('loginLink').hidden=!officialLogin;if(officialLogin)$('loginLink').href=officialLogin;else $('loginLink').removeAttribute('href');
  $('problemBox').hidden=!state.problem?.kind;$('problemMessage').textContent=state.problem?.message||'';
  if(state.problem?.kind&&running&&!stopping)stopCapture();
  const busy=state.sessions.some(s=>['recording','draining'].includes(s.status));
  $('start').disabled=!state.asr.ready||!state.codex.ready||Boolean(state.problem?.kind)||busy||running||starting||stopping;
  $('start').textContent=running?'正在采集直播声音':stopping?'正在提交剩余音频…':busy?'正在处理当前会话…':state.asr.ready?'选择直播标签页，开始翻译':'准备运行环境…';
  for(const id of ['title','profile','model','chunk'])$(id).disabled=running||starting||stopping;
  const optionSig=state.sessions.map(s=>s.id).join(',');
  if($('history').dataset.signature!==optionSig){
    $('history').replaceChildren();if(!state.sessions.length){const emptyOption=document.createElement('option');emptyOption.value='';emptyOption.textContent='暂无记录';$('history').append(emptyOption);}for(const item of state.sessions){const opt=document.createElement('option');opt.value=item.id;opt.textContent=item.title+' · '+item.created.slice(5,16).replace('T',' ');$('history').append(opt);}
    $('history').dataset.signature=optionSig;
  }
  $('sessionCount').textContent=state.sessions.length;
  const s=state.session;
  if(!s){$('liveState').textContent=state.asr.ready&&state.codex.ready?'准备就绪':'正在准备';return;}
  $('stop').disabled=stopping||(!running&&s.status!=='recording');
  $('stop').textContent=running?'结束采集并保存':'结束上次采集会话';
  selected=s.id;$('history').value=selected;$('recordTitle').textContent=s.title;
  if(renderedSid!==s.id){
    renderedSid=s.id;lastSignature='';const placeholder=document.createElement('div');placeholder.className='empty';
    const h=document.createElement('h3');h.textContent='正在等待第一段中文';const p=document.createElement('p');p.textContent='音频分段完成后会自动识别、翻译并保存。';placeholder.append(h,p);$('transcript').replaceChildren(placeholder);
  }
  $('duration').textContent=clock(running&&active===s.id?(totalSamples+samples)/16000:s.received_seconds);
  const localSeconds=uploads.filter(x=>x.sid===s.id).reduce((a,x)=>a+x.buffer.byteLength/32000,0);
  $('backlog').textContent=Math.round((state.backlog_seconds||0)+localSeconds)+' 秒';
  $('count').textContent=s.rows.filter(r=>r.status==='done').length+' 段';
  const statusNames={recording:'采集中',draining:'正在完成译文',finished:'已保存',interrupted:'上次采集中断'};
  $('liveState').textContent=statusNames[s.status]||s.status;$('liveState').className='badge '+(['recording','draining'].includes(s.status)?'active':'');
  $('retry').hidden=!state.retryable;
  document.querySelectorAll('[data-format]').forEach(b=>b.disabled=!s.rows.length);
  const signature=JSON.stringify(s.rows.map(r=>[r.seq,r.status,r.text,r.note,r.review]));
  if(signature!==lastSignature&&s.rows.length){
    const pane=$('transcript'),oldTop=pane.scrollTop;pane.replaceChildren();
    for(const row of s.rows){
      if(row.status==='silent')continue;
      const el=document.createElement('article');el.className='row '+(['queued','recognizing','translating'].includes(row.status)?'pending':row.status==='failed'?'failed':'');
      const rowHeader=document.createElement('div');rowHeader.className='row-header';
      const time=document.createElement('time');time.textContent=clock(row.start)+' — '+clock(row.end);rowHeader.append(time);
      if(canCopy(row)){
        const copy=document.createElement('button');copy.type='button';copy.className='row-copy';showCopyIcon(copy);
        copy.setAttribute('aria-label','复制 '+clock(row.start)+' 这一段译文');
        copy.onclick=()=>copyTranslation(s.id,row.seq,copy);rowHeader.append(copy);
      }
      el.append(rowHeader);
      const p=document.createElement('p');p.textContent=row.text||({queued:'等待处理…',recognizing:'正在识别这一段声音…',translating:'正在翻译这一段内容…'}[row.status]||'');el.append(p);
      if(needsReview(row)){const note=document.createElement('div');note.className='note';note.textContent='待核实 · '+(row.note||'这一段内容需要复核。');el.append(note);}
      pane.append(el);
    }
    if(!pane.children.length){const p=document.createElement('p');p.className='muted';p.textContent='暂未识别到讲话，请确认视频正在播放且共享了声音。';pane.append(p);}
    if($('autoScroll').checked)pane.scrollTop=pane.scrollHeight;else pane.scrollTop=oldTop;
    lastSignature=signature;
  }
}
async function poll(){
  if(pollBusy)return;pollBusy=true;
  try{
    const response=await fetch('/api/state'+(selected?'?session='+encodeURIComponent(selected):''),{signal:AbortSignal.timeout(5000)});if(!response.ok)throw new Error();
    const state=await response.json();render(state);$('connection').hidden=true;
    if(active&&running&&Date.now()-lastHeartbeat>10000){lastHeartbeat=Date.now();await request('/api/heartbeat',{session:active});}
    if(hadLogin&&!state.login?.running&&Date.now()-lastLoginPoll>5000){hadLogin=false;lastLoginPoll=Date.now();await request('/api/check-login');}
    hadLogin=Boolean(state.login?.running)||hadLogin;
  }
  catch(e){$('connection').textContent='本地服务连接中断，正在自动重连。请保持页面打开；如服务已关闭，请运行“启动翻译”。';$('connection').hidden=false;}
  finally{pollBusy=false;}
}
async function init(){
  try{const cfg=await(await fetch('/api/config')).json();token=cfg.token;glossaryInfo=cfg.glossary_info;$('glossary').value=Object.entries(cfg.glossary).map(([k,v])=>k+' = '+v).join('\n');updateGlossaryInfo();await poll();}
  catch(e){notice('无法连接本地服务，请重新启动工具。');}
  setInterval(()=>{poll();finishWhenReady();},1200);
}
$('start').onclick=startCapture;$('stop').onclick=stopCapture;
$('profile').onchange=()=>{if(['美联储发布会','英语直播'].includes($('title').value))$('title').value=$('profile').value==='fed'?'美联储发布会':'英语直播';};
$('login').onclick=async()=>{try{$('login').disabled=true;await request('/api/login');hadLogin=true;await poll();}catch(e){notice(e.message);$('login').disabled=false;}};
$('resume').onclick=async()=>{try{$('resume').disabled=true;await request('/api/resume',{session:selected,model:$('model').value});notice('已恢复处理，已采集内容会继续翻译。');await poll();}catch(e){notice(e.message);}finally{$('resume').disabled=false;}};
$('history').onchange=()=>{selected=$('history').value;lastSignature='';poll();};
$('retry').onclick=async()=>{try{if(lastState?.problem?.kind){notice('请先解决上方暂停原因，再点击“继续处理”。');return;}await request('/api/retry',{session:selected});notice('正在重试失败段落。');await poll();}catch(e){notice(e.message);}};
$('checkLogin').onclick=async()=>{try{await request('/api/check-login');await poll();}catch(e){notice(e.message);}};
$('saveGlossary').onclick=async()=>{try{const glossary=parseGlossary();await request('/api/glossary',{glossary});updateGlossaryInfo();notice('术语库已保存，将用于下一场美联储 / 财经翻译。');}catch(e){notice(e.message);}};
$('smaller').onclick=()=>{fontSize=Math.max(16,fontSize-2);document.documentElement.style.setProperty('--font',fontSize+'px');};
$('larger').onclick=()=>{fontSize=Math.min(36,fontSize+2);document.documentElement.style.setProperty('--font',fontSize+'px');};
document.querySelectorAll('[data-format]').forEach(b=>b.onclick=()=>{if(selected){const a=document.createElement('a');a.href=`/api/export?session=${encodeURIComponent(selected)}&format=${b.dataset.format}&times=${$('withTimes').checked?1:0}`;a.download=`fed-${selected}.${b.dataset.format}`;document.body.append(a);a.click();a.remove();}});
window.addEventListener('beforeunload',e=>{if(running||uploads.length||stopping){e.preventDefault();e.returnValue='';}});
window.addEventListener('pagehide',()=>{if(active)fetch('/api/finish',{method:'POST',keepalive:true,headers:{'X-Local-Token':token,'Content-Type':'application/json'},body:JSON.stringify({session:active})}).catch(()=>{});});
init();

const settingToggle=document.getElementById('toggleSettings');settingToggle.onclick=()=>document.body.classList.toggle('settings-folded');
document.getElementById('sidebarStop').onclick=stopCapture;

function parseGlossary(){
  const result=Object.create(null);
  for(const line of $('glossary').value.split('\n')){
    if(!line.trim())continue;
    const at=line.indexOf('='),key=line.slice(0,at).trim(),value=line.slice(at+1).trim();
    if(at<1||!key||!value)throw new Error('请按“英文术语 = 中文译法”填写，每行一条，译法不可为空。');
    if(key.length>120||value.length>200)throw new Error('每条英文术语和中文译法分别不超过 120 和 200 个字符。');
    result[key]=value;
  }
  if(Object.keys(result).length>1000)throw new Error('术语库最多保存 1000 条。');
  return result;
}
function updateGlossaryInfo(){
  const entries=new Set($('glossary').value.split('\n').filter(line=>line.includes('=')).map(line=>line.slice(0,line.indexOf('=')).trim()).filter(Boolean));
  const builtins=glossaryInfo?`内置 ${glossaryInfo.count} 条 · ${Object.keys(glossaryInfo.categories).length} 类 · `:'';
  $('glossaryInfo').textContent=builtins+`当前编辑 ${entries.size} 条（含缩写和常见变体）`;
}
$('glossary').addEventListener('input',updateGlossaryInfo);
$('addBuiltinGlossary').onclick=async()=>{
  try{
    const current=parseGlossary(), response=await fetch('/api/glossary-default');
    if(!response.ok)throw new Error('内置术语加载失败，请重试。');
    const defaults=await response.json(),combined={...defaults,...current},count=Object.keys(combined).length;
    if(count>1000)throw new Error('补充后超过 1000 条，请先减少自定义词条。');
    $('glossary').value=Object.entries(combined).map(([key,value])=>key+' = '+value).join('\n');
    updateGlossaryInfo();notice(`已补充 ${count-Object.keys(current).length} 条，保留已有译法。点击“保存术语库”后生效。`);
  }catch(e){notice(e.message);}
};
