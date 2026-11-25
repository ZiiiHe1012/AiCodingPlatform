// Invoked only by the network-isolated runner. The learner's browser receives pixels and control labels.
const {spawn} = require('node:child_process');
const fs = require('node:fs/promises');
const {createServer} = require('node:http');
const os = require('node:os');
const path = require('node:path');

const WIDTH = 960;
const HEIGHT = 600;
const controls = 'button,input:not([type="hidden"]):not([type="password"]):not([type="file"]),textarea,select,a[href]';
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

function devTools(child) {
  let sequence = 0;
  let buffer = Buffer.alloc(0);
  const pending = new Map();
  child.stdio[4].on('data', bytes => {
    buffer = Buffer.concat([buffer, bytes]);
    for (let end; (end=buffer.indexOf(0)) >= 0;) {
      const packet = JSON.parse(buffer.subarray(0, end).toString());
      buffer = buffer.subarray(end + 1);
      const entry = pending.get(packet.id);
      if (!entry) continue;
      pending.delete(packet.id);
      clearTimeout(entry.timer);
      if (packet.error) entry.reject(new Error('浏览器执行预览失败。'));
      else entry.resolve(packet.result);
    }
  });
  function closed() {
    for (const entry of pending.values()) {
      clearTimeout(entry.timer);
      entry.reject(new Error('预览浏览器已退出。'));
    }
    pending.clear();
  }
  child.on('error', closed);
  child.once('exit', closed);
  child.stdio[3].on('error', closed);
  return (method, params={}, sessionId=undefined) => new Promise((resolve, reject) => {
    if (child.exitCode !== null || child.signalCode) return reject(new Error('预览浏览器未运行。'));
    const id = ++sequence;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error('预览浏览器响应超时，请重新构建。'));
    }, 7000);
    pending.set(id, {resolve,reject,timer});
    child.stdio[3].write(JSON.stringify({id, method, params, sessionId})+'\0');
  });
}

async function main() {
  const bundle = await fs.realpath(process.argv[2]);
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const {actions=[], problem_id} = JSON.parse(Buffer.concat(chunks));
  if (!Array.isArray(actions) || actions.length > 25) throw new Error('预览操作过多，请重置预览。');
  const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8',
    '.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2','.json':'application/json'};
  const server = createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      if (problem_id === 'E1006' && url.pathname === '/api/customers') {
        const q = url.searchParams.get('q')?.trim().toLowerCase() || '';
        const items = ['客户 A · 上海', '客户 B · 北京', '客户 C · 杭州'];
        res.writeHead(200, {'Content-Type':'application/json; charset=utf-8'});
        return res.end(JSON.stringify(items.filter(x => x.toLowerCase().includes(q))));
      }
      const pathname = url.pathname === '/' ? '/index.html' : decodeURIComponent(url.pathname);
      const file = await fs.realpath(path.join(bundle, pathname));
      if (!file.startsWith(bundle+path.sep)) throw new Error();
      const content = await fs.readFile(file);
      res.writeHead(200, {'Content-Type':mime[path.extname(file)] || 'application/octet-stream',
        'X-Content-Type-Options':'nosniff'});
      res.end(content);
    } catch {res.writeHead(404); res.end();}
  });
  await new Promise((resolve, reject) => {server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const profile = await fs.mkdtemp(path.join(os.tmpdir(),'browser-'));
  const chrome = spawn(process.env.CODELAB_CHROMIUM || '/usr/bin/chromium', [
    '--headless','--no-sandbox','--no-zygote','--disable-gpu','--disable-dev-shm-usage','--disable-extensions',
    '--disable-background-networking','--no-first-run','--no-default-browser-check','--disable-sync',
    '--renderer-process-limit=1','--remote-debugging-pipe','--user-data-dir='+profile,'about:blank'
  ], {stdio:['ignore','ignore','ignore','pipe','pipe']});
  const send = devTools(chrome);
  const exited = new Promise(resolve=>chrome.once('exit', resolve));
  try {
    const {targetId} = await send('Target.createTarget',{url:'about:blank'});
    const {sessionId} = await send('Target.attachToTarget',{targetId,flatten:true});
    const call = (method,params={})=>send(method,params,sessionId);
    async function evaluate(expression) {
      const reply=await call('Runtime.evaluate',{expression,returnByValue:true,timeout:1800});
      if(reply.exceptionDetails) throw new Error('页面脚本执行失败。');
      return reply.result.value;
    }
    await call('Page.enable');
    await call('Emulation.setDeviceMetricsOverride',{width:WIDTH,height:HEIGHT,deviceScaleFactor:1,mobile:false});
    const addr='http://127.0.0.1:'+server.address().port+'/';
    await call('Page.navigate',{url:addr});
    let ready=false;
    for(let i=0;i<60;i++) {
      await delay(50);
      if(await evaluate('location.href === '+JSON.stringify(addr)+' && document.readyState === "complete"')) {ready=true;break;}
    }
    if (!ready) throw new Error('网页在限时内未能加载。');
    await delay(100);
    const find='Array.from(document.querySelectorAll('+JSON.stringify(controls)+')).filter(e=>e.getClientRects().length && !e.disabled)';
    for(const act of actions) {
      if(!Number.isInteger(act.index)||act.index<0||act.index>=60) throw new Error('预览控件无效。');
      const expr='(()=>{const e='+find+'['+act.index+']; if(!e)return false; e.scrollIntoView({block:"nearest"});';
      let op;
      if(act.kind==='click') op='e.click();';
      else if(act.kind==='fill' && typeof act.value==='string' && act.value.length<=500) {
        op='if(!["INPUT","TEXTAREA","SELECT"].includes(e.tagName))return false;e.value='+JSON.stringify(act.value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));';
      } else throw new Error('预览操作无效。');
      if(!await evaluate(expr+op+'return true;})()')) throw new Error('预览控件已更改，请重置后再操作。');
      await delay(180);
    }
    const metadata=await evaluate('(()=>({text:document.body.innerText.slice(0,1400),controls:'+find+'.slice(0,60).map((e,index)=>({index,label:(e.getAttribute("aria-label")||e.labels?.[0]?.innerText||e.innerText||e.placeholder||e.name||e.type||e.tagName).trim().slice(0,90),kind:e.tagName==="SELECT"?"select":(["TEXTAREA","INPUT"].includes(e.tagName)&&!["button","submit","reset","checkbox","radio"].includes(e.type)?"input":"button"),inputType:e.type||"text",value:String(e.value||"").slice(0,500),options:e.tagName==="SELECT"?Array.from(e.options).slice(0,60).map(o=>({value:o.value.slice(0,500),label:o.text.slice(0,90)})):[]}))}))()');
    const screenshot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    if(screenshot.data.length>1600000) throw new Error('预览图像过大，请简化页面。');
    process.stdout.write(JSON.stringify({width:WIDTH,height:HEIGHT,image:screenshot.data,...metadata}));
  } finally {
    if (chrome.exitCode === null && !chrome.signalCode) {
      send('Browser.close').catch(()=>{});
      let timer;
      await Promise.race([exited, new Promise(resolve=>{timer=setTimeout(resolve,900);})]);
      clearTimeout(timer);
      if (chrome.exitCode === null && !chrome.signalCode) chrome.kill('SIGKILL');
    }
    server.closeAllConnections(); server.close();
    await fs.rm(profile,{recursive:true,force:true,maxRetries:2}).catch(()=>{});
  }
}
main().catch(e=>{console.error(e.message || '网页预览失败。');process.exitCode=1;});
