/* Real Chrome + HTTP + actual standalone Daily page, disposable fixture only.
   Start g076_daily_p0a_fixture_server.py on 127.0.0.1:5081 before running. */
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const root = process.cwd();
const tempRoot = path.resolve(root, 'artifacts/g076-p0a/chrome-local');
await fs.mkdir(tempRoot,{recursive:true});
const profile = await fs.mkdtemp(path.join(tempRoot,'chrome-'));
const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',[
  '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
  '--disable-extensions','--disable-background-networking','--disable-component-update','--disable-sync',
  '--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank',
],{windowsHide:true,stdio:'ignore'});
const pause = ms => new Promise(resolve=>setTimeout(resolve,ms));
let ws, seq=0, checks=0;
const pending = new Map();
const errors=[];
const requests=[];
function check(value,message){assert.ok(value,message);checks++;}
function send(method,params={}) {
  const id=++seq;
  return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
}
async function evaluate(expression){
  const value = await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  if(value.exceptionDetails) throw new Error(value.exceptionDetails.text+': '+value.exceptionDetails.exception?.description);
  return value.result.value;
}
async function until(expression){
  for(let i=0;i<150;i++){
    if(await evaluate(expression)) return;
    await pause(100);
  }
  throw new Error('Timeout: '+expression+' UI_ERROR='+await evaluate("window.__p0aUiError??null")+' State: '+await evaluate("document.body.innerText.slice(-2500)"));
}
async function navigate(uid){
  const previous=await evaluate('window.__p0aDocument || null');
  await send('Page.navigate',{url:'http://127.0.0.1:5081/fixture/entry/'+uid});
  await until(`window.__p0aDocument && window.__p0aDocument!==${JSON.stringify(previous)} && typeof todayData !== 'undefined' && todayData && board && !answering && document.querySelector('canvas')`);
}
async function freshPage(method,params,ready) {
  const previous=await evaluate('window.__p0aDocument || null');
  await send(method,params);
  await until(`window.__p0aDocument && window.__p0aDocument!==${JSON.stringify(previous)} && (${ready})`);
}
async function click(x,y){
  await evaluate("board.element.scrollIntoView({block:'center'})");
  await pause(150);
  const point=await evaluate(`(()=>{const r=board.element.getBoundingClientRect();return {x:r.left+board.getX(${x}),y:r.top+board.getY(${y})};})()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
}
let result;
try {
  let port;
  for(let i=0;i<100;i++){
    try{port=Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break;}catch{}
    await pause(100);
  }
  assert.ok(port,'Chrome debugging port');
  const target=await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
  ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  ws.onclose=event=>{for(const p of pending.values())p.reject(new Error('CDP socket closed '+event.code));pending.clear();};
  ws.onmessage=event=>{
    const value=JSON.parse(event.data);
    if(value.id){const p=pending.get(value.id);pending.delete(value.id);value.error?p.reject(new Error(JSON.stringify(value.error))):p.resolve(value.result);}
    if(value.method==='Runtime.exceptionThrown') errors.push(value.params.exceptionDetails.exception?.description || value.params.exceptionDetails.text);
    if(value.method==='Network.requestWillBeSent') requests.push(value.params.request.url);
  };
  await send('Runtime.enable');await send('Page.enable');await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1400,height:1100,deviceScaleFactor:1,mobile:false});
  await send('Page.addScriptToEvaluateOnNewDocument',{source:`
    window.__p0aDocument=crypto.randomUUID();
    const originalFetch=window.fetch.bind(window);
    window.legacyReceipts=[];
    window.fetch=async (...args)=>{
      const response=await originalFetch(...args);
      if(String(args[0])==='/api/daily-challenge/submit') {
        const data=await response.clone().json();
        window.legacyReceipts.push({body:args[1].body,status:response.status,data});
        if(window.loseLegacyResponse) {window.loseLegacyResponse=false;throw new Error('response lost after commit');}
      }
      return response;
    };
  `});
  for(const uid of [7,8]) {
    requests.length=0;
    await navigate(uid);
    await evaluate("['spawnXpFloat','showGlobalStats','showStatusArea','showResultPanel','loadStreak'].forEach(name=>{const orig=window[name];if(typeof orig==='function')window[name]=function(...args){try{return orig(...args)}catch(error){window.__p0aUiError=name+': '+error.stack;throw error}}})");
    check(await evaluate("location.pathname==='/daily_challenge_legacy.html' && currentProblem.tree && todayData.content.includes('B[cc]')"),'original full-SGF Daily restored');
    check(!requests.some(url=>url.includes('/api/g076/daily/today') || url.includes('/api/g076/daily/steps')),'OFF never races secure protocol');
    check(await evaluate("boardSize===5 && logicBoard[4][4]==='B'"),'real board setup');
    await until("document.querySelectorAll('.history-item').length===1");
    check(await evaluate("document.querySelector('.history-item').getAttribute('onclick').includes('loadHistoryDetail')"),'actual server history rendered');
    await click(0,0);
    await until("!answering && logicBoard[1][1]==='W'");
    check(await evaluate("logicBoard[0][0]==='B' && submittedMoves.length===1"),'real player stone and SGF opponent reply');
    await click(2,2);await until('solved');
    check(await evaluate("submittedMoves.length===2 && document.getElementById('submit-panel').classList.contains('show')"),'actual SGF terminal opens submit');
    if(uid===8) await evaluate('window.loseLegacyResponse=true');
    await evaluate("document.getElementById('btn-submit').click()");
    if(uid===8) {
      await until("legacyReceipts.length===1 && !document.getElementById('btn-submit').disabled");
      check(await evaluate('!submitted && legacyReceipts[0].data.xp_awarded===50'),'lost committed response is retryable');
      await evaluate("document.getElementById('btn-submit').click()");
    }
    await until("submitted && document.getElementById('result-panel').classList.contains('show')");
    const display=await evaluate("({submitted,solved,reply:legacyReceipts.at(-1).data,show:document.getElementById('result-panel').classList.contains('show'),loading:document.getElementById('loading-state').style.display,uiError:window.__p0aUiError??null})");
    check(display.reply.server_correct && display.reply.xp_awarded===50 && display.show,'real judge XP/result display '+JSON.stringify(display));
    if(uid===8) check(await evaluate('legacyReceipts[0].body===legacyReceipts[1].body && JSON.stringify(legacyReceipts[0].data)===JSON.stringify(legacyReceipts[1].data)'),'response-loss exact D5B replay');
    const receipt=await evaluate('legacyReceipts.at(-1)');
    await freshPage('Page.reload',{},"typeof todayData!=='undefined' && todayData?.user_submitted && submitted");
    check(await evaluate("document.querySelectorAll('.xp-float').length===0 && todayData.user_correct"),'reload restores completion with no fresh award');
    const replay=await evaluate(`fetch('/api/daily-challenge/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:${JSON.stringify(receipt.body)}}).then(r=>r.json())`);
    check(JSON.stringify(replay)===JSON.stringify(receipt.data),'same-day exact receipt replay after reload');
  }
  const effects=await evaluate("fetch('/fixture/effects').then(r=>r.json())");
  check(effects.review_log.length===2 && effects.daily_challenge_log.length===2,'two users two settlements');
  check(effects.user_stats.length===2 && effects.user_stats.every(r=>r.xp===50),'real SQLite XP once per user');
  check(effects.badges_earned.length===4 && [7,8].every(uid=>effects.badges_earned.filter(r=>r.user_id===uid).map(r=>r.badge_id).sort().join()==='daily_ace,daily_first'),'real badge effects once per user');
  await fs.writeFile(path.join(tempRoot,'legacy-completed-dom.html'),await evaluate('document.documentElement.outerHTML'));
  await fs.writeFile(path.join(tempRoot,'legacy-effects.json'),JSON.stringify(effects,null,2));
  // Direct URL cannot admit new legacy work in secure/partial mode.
  for(const bits of ['001','010','011','100','101','110','111']) {
    await evaluate(`fetch('/fixture/mode/${bits}',{method:'POST'})`);
    const status=await evaluate("fetch('/api/daily-challenge/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({submission_id:'blocked-new-'+Date.now(),correct:true,moves:[{x:0,y:0}]})}).then(r=>r.status)");
    check(status===409,'direct legacy POST rejected '+bits);
    if(bits!=='111') {
      requests.length=0;
      await freshPage('Page.navigate',{url:'http://127.0.0.1:5081/'},"document.getElementById('loading-state')?.dataset.reason==='daily_capability_blocked'");
      check(!requests.some(url=>url.includes('/api/g076/daily/today') || url.includes('/api/daily-challenge/today') || url.includes('/api/daily-challenge/history')),'partial blocks before protocol/history '+bits);
    }
  }
  await send('Network.setBlockedURLs',{urls:['*api/g076/daily/capability*']});
  requests.length=0;
  await freshPage('Page.navigate',{url:'http://127.0.0.1:5081/'},"document.getElementById('loading-state')?.dataset.reason==='daily_capability_blocked'");
  check(await evaluate("location.pathname==='/' && currentProblem===null"),'failed capability network never falls back');
  check(!requests.some(url=>url.includes('/api/g076/daily/today') || url.includes('/api/daily-challenge/today')),'failed network never starts either protocol');
  await fs.writeFile(path.join(tempRoot,'blocked-dom.html'),await evaluate('document.documentElement.outerHTML'));
  check(errors.length===0,'no uncaught exceptions '+errors.join('\n'));
  result={status:'PASS',checks,real_chrome:true,real_http:true,real_daily_page:true,sqlite:true,postgres:false,production_writes:0};
} catch(error){
  result={status:'FAIL',checks,error:error.stack,errors};
  if(ws?.readyState===WebSocket.OPEN){
    try{await fs.writeFile(path.join(tempRoot,'daily-failure.png'),Buffer.from((await send('Page.captureScreenshot')).data,'base64'));}catch{}
  }
  process.exitCode=1;
} finally {
  console.log(JSON.stringify(result,null,2));
  await fs.writeFile(path.join(tempRoot,'p0a-chrome-result.json'),JSON.stringify(result,null,2));
  if(ws?.readyState===WebSocket.OPEN){try{await send('Browser.close');}catch{} ws.close();}
  chrome.kill();
  await pause(300);
  if(!profile.startsWith(tempRoot+path.sep)) throw new Error('Unsafe temporary profile path');
  await fs.rm(profile,{recursive:true,force:true,maxRetries:10,retryDelay:200}).catch(()=>{});
}
