'use strict';
let port=null,connecting=false;
const status=document.getElementById('status'),retry=document.getElementById('retry');
function fail(message){connecting=false;retry.disabled=false;status.textContent=message;document.getElementById('setup').hidden=false;}
function connect(){
  if(connecting)return;connecting=true;retry.disabled=true;status.textContent='正在启动本机组件…';
  if(port){port.onDisconnect.removeListener(disconnected);port.disconnect();port=null;}
  try{
    port=chrome.runtime.connectNative('org.fedtranslator.bridge');
    port.onDisconnect.addListener(disconnected);
    port.onMessage.addListener(result=>{
      if(!result.ok){fail(result.error||'组件暂时无法连接。');return;}
      if(result.url!=='http://127.0.0.1:8878/?view=sidebar'){fail('组件返回了无法识别的地址，请重新安装完整测试包。');return;}
      const app=document.getElementById('app');app.src=result.url;app.hidden=false;
      document.getElementById('setup').hidden=true;connecting=false;retry.disabled=false;
    });
    port.postMessage({command:'start'});
  }catch(e){fail('尚未连接本机组件，请完成下方安装步骤后重试。');}
}
function disconnected(){
  // Reading lastError prevents raw browser diagnostics from becoming an unhandled exception.
  const reason=chrome.runtime.lastError;
  if(reason||connecting)fail('尚未连接本机组件，请运行 Install-Connector.command 后重试。');
  port=null;
}
retry.onclick=connect;
connect();
