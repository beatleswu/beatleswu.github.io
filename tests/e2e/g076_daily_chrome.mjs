/* Real Chrome + HTTP + actual standalone Daily page, disposable fixture only.
   Start g076_daily_fixture_server.py on 127.0.0.1:5079 before running. */
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const root = process.cwd();
const tempRoot = path.resolve(root, '.g076-daily-tmp');
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
  throw new Error('Timeout: '+expression+' State: '+await evaluate("document.body.innerText.slice(-2500)"));
}
async function navigate(uid){
  await send('Page.navigate',{url:'http://127.0.0.1:5079/fixture/entry/'+uid});
  await until("typeof todayData !== 'undefined' && todayData && board && !answering && document.querySelector('canvas')");
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
  ws.onclose=event=>{for(const p of pending.values())p.reject(new Error('CDP socket closed '+event.code+' '+event.reason));pending.clear();};
  ws.onmessage=event=>{
    const value=JSON.parse(event.data);
    if(value.id){const p=pending.get(value.id);pending.delete(value.id);value.error?p.reject(new Error(JSON.stringify(value.error))):p.resolve(value.result);}
    if(value.method==='Runtime.exceptionThrown') errors.push(value.params.exceptionDetails.exception?.description || value.params.exceptionDetails.text);
  };
  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1400,height:1100,deviceScaleFactor:1,mobile:false});
  await send('Page.addScriptToEvaluateOnNewDocument',{source:`
    const nativeFetch=window.fetch.bind(window);
    window.dailyResponses=[];
    window.fetch=async (...args)=>{
      const r=await nativeFetch(...args);
      if(String(args[0]).startsWith('/api/g076/daily/')) {
        const data=await r.clone().json();window.dailyResponses.push({path:String(args[0]),data});
        if(window.loseDailyResponse && String(args[0])==='/api/g076/daily/steps') {
          window.loseDailyResponse=false;throw new Error('fixture response lost after server commit');
        }
      }
      return r;
    };
  `});
  await navigate(7);
  check(await evaluate("boardSize===5 && playerColor==='B' && logicBoard[4][4]==='B'"),'actual WGo initial setup');
  check(await evaluate("todayData.board_only && !todayData.content.includes('B[aa]') && !todayData.content.includes('B[cc]')"),'board-only API response');
  check(await evaluate("!('tree' in currentProblem)"),'page holds no local solution tree');
  check(await evaluate("['btn-answer','btn-giveup','btn-submit'].every(id=>getComputedStyle(document.getElementById(id)).display==='none')"),'unauthorized answer/abandon/legacy submission hidden');
  const csrfStatus=await evaluate("fetch('/api/g076/daily/steps/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({flow:'daily',attempt_token:todayData.attempt_token})}).then(r=>r.status)");
  check(csrfStatus===403,'live CSRF rejection');
  await click(0,0);
  await until("!answering && logicBoard[1][1]==='W'");
  check(await evaluate("logicBoard[0][0]==='B' && !submitted"),'real click + forced server opponent + nonterminal');
  check(await evaluate("dailyResponses.filter(x=>x.path==='/api/g076/daily/steps').some(x=>x.data.status==='CONTINUE' && x.data.opponent_reply.join()==='1,1' && !JSON.stringify(x.data).includes('cc'))"),'real HTTP server verdict without next answer');
  await send('Page.reload');
  await until("typeof todayData !== 'undefined' && todayData && !answering && logicBoard?.[1]?.[1]==='W'");
  check(await evaluate("logicBoard[0][0]==='B'"),'reload reconstructs committed history');
  await click(2,2);
  await until('submitted');
  check(await evaluate("solved && logicBoard[2][2]==='B' && document.getElementById('result-panel').classList.contains('show')"),'terminal verdict displays actual page result');
  check((await evaluate("fetch('/fixture/counts').then(r=>r.json())")).review_log===1,'one real D5B review settlement');
  await send('Page.reload');
  await until("typeof todayData !== 'undefined' && todayData?.user_submitted && submitted");
  check(await evaluate("document.querySelectorAll('.xp-float').length===0"),'reload does not animate second award');

  await navigate(8);
  await evaluate('window.loseDailyResponse=true');
  await click(0,0);
  await until('stepUncertain && !answering');
  check(await evaluate("!logicBoard[0][0] && getComputedStyle(document.getElementById('btn-retry')).display!=='none'"),'response loss freezes move and exposes retry');
  await click(3,3);
  check(await evaluate('pendingDailyMove.x===0 && pendingDailyMove.y===0'),'uncertain move cannot change');
  await evaluate("document.getElementById('btn-retry').click()");
  await until("!stepUncertain && !answering && logicBoard[1][1]==='W'");
  check(await evaluate("logicBoard[0][0]==='B'"),'retry restores committed step exactly once');
  await evaluate('window.loseDailyResponse=true');
  await click(2,2);
  await until('stepUncertain && !answering');
  await evaluate("document.getElementById('btn-retry').click()");
  await until('submitted && !answering');
  check(await evaluate("solved && document.querySelectorAll('.xp-float').length===0"),'terminal response-loss receipt replay has no duplicate award animation');
  const counts=await evaluate("fetch('/fixture/counts').then(r=>r.json())");
  check(counts.review_log===2 && counts.daily_challenge_log===2 && counts.badges_earned===4,'two users each settle once with actual badge effects');
  await send('Page.navigate',{url:'http://127.0.0.1:5079/fixture/white-entry'});
  await until("typeof todayData !== 'undefined' && todayData && board && !answering && playerColor==='W'");
  check(await evaluate("logicBoard[4][4]==='W' && !('tree' in currentProblem)"),'white setup and side from safe board');
  await click(0,0);
  await until("!answering && logicBoard[1][1]==='B'");
  check(await evaluate("logicBoard[0][0]==='W' && !submitted"),'white player receives black forced reply');
  await click(2,2);
  await until('submitted');
  check(await evaluate('solved'),'white multistep terminal result');
  await send('Page.navigate',{url:'http://127.0.0.1:5079/fixture/disabled-entry'});
  await until("document.getElementById('loading-state')?.dataset.reason==='daily_steps_disabled_or_unconfigured'");
  check(await evaluate("currentProblem===null && document.getElementById('main-content').style.display==='none'"),'flag OFF fails closed on the actual page');
  check(errors.length===0,'no uncaught browser exceptions: '+errors.join('\n'));
  result={status:'PASS',checks,real_chrome:true,real_http:true,real_daily_page:true,sqlite:true,production_writes:0};
} catch(error){
  result={status:'FAIL',checks,error:error.stack,errors};
  if(ws?.readyState===WebSocket.OPEN){
    try{await fs.writeFile(path.join(tempRoot,'daily-failure.png'),Buffer.from((await send('Page.captureScreenshot')).data,'base64'));}catch{}
  }
  process.exitCode=1;
} finally {
  console.log(JSON.stringify(result,null,2));
  await fs.writeFile(path.join(tempRoot,'chrome-result.json'),JSON.stringify(result,null,2));
  if(ws?.readyState===WebSocket.OPEN){try{await send('Browser.close');}catch{} ws.close();}
  chrome.kill();
  await pause(300);
  if(!profile.startsWith(tempRoot+path.sep)) throw new Error('Unsafe temporary profile path');
  await fs.rm(profile,{recursive:true,force:true,maxRetries:10,retryDelay:200}).catch(()=>{});
}
