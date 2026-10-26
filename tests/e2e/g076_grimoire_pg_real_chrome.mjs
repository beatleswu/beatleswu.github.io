/* Real Chrome WGo + PG16 + loopback fixture, NOT official Grimoire UI.
   Start python -B tests/e2e/g076_grimoire_pg_fixture_server.py (5083). */
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=process.cwd();
const out=path.join(root,'artifacts/g076-r5-pg-chrome');
await fs.mkdir(out,{recursive:true});
const profile=await fs.mkdtemp(path.join(out,'profile-'));
const chrome=spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',[
  '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
  '--disable-extensions','--disable-background-networking','--disable-component-update',
  '--disable-sync','--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
  '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'
],{windowsHide:true,stdio:'ignore'});
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws,seq=0,checks=0;
const pending=new Map(),errors=[],requests=[];
function check(value,msg){assert.ok(value,msg);checks++;}
function send(method,params={}){
 const id=++seq;
 return new Promise((resolve,reject)=>{
 pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));
 });
}
async function evaluate(expr){
 const v=await send('Runtime.evaluate',{expression:expr,awaitPromise:true,returnByValue:true});
 if(v.exceptionDetails)throw new Error(v.exceptionDetails.exception?.description||v.exceptionDetails.text);
 return v.result.value;
}
async function until(expr){
 for(let i=0;i<200;i++){
  try{if(await evaluate(expr))return;}catch(e){if(!String(e).includes('ReferenceError'))throw e;}
  await pause(100);
 }
 throw new Error('Timed out '+expr+' view='+await evaluate('document.body.innerText.slice(-500)'));
}
async function navigate(uid){
 const old=await evaluate('window.__g076PlayerDocument||null');
 await send('Page.navigate',{url:'http://127.0.0.1:5083/fixture/entry/'+uid});
 await until('window.__g076PlayerDocument && window.__g076PlayerDocument!=='+JSON.stringify(old)+' && window.goPlayer?.ready');
}
async function clickWgo(x,y){
 const point=await evaluate('(()=>{const b=board;const r=b.element.getBoundingClientRect();return {x:r.left+b.getX('+x+'),y:r.top+b.getY('+y+')};})()');
 await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
 await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
}
let result;
try{
 let port=0;
 for(let i=0;i<100;i++){
  try{port=Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);if(port)break;}
  catch{}await pause(100);
 }
 check(port>0,'Chrome remote debugging started');
 const target=await(await fetch('http://127.0.0.1:'+port+'/json/new?about:blank',{method:'PUT'})).json();
 ws=new WebSocket(target.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
 ws.onmessage=event=>{
  const v=JSON.parse(event.data);
  if(v.id){const p=pending.get(v.id);pending.delete(v.id);v.error?p.reject(new Error(JSON.stringify(v.error))):p.resolve(v.result);}
  if(v.method==='Runtime.exceptionThrown')errors.push(v.params.exceptionDetails.exception?.description||v.params.exceptionDetails.text);
  if(v.method==='Network.requestWillBeSent')requests.push(v.params.request.url);
 };
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');
 await send('Emulation.setDeviceMetricsOverride',{width:960,height:900,deviceScaleFactor:1,mobile:false});
 await send('Page.addScriptToEvaluateOnNewDocument',{source:'window.__g076PlayerDocument=Math.random().toString(36).slice(2)'});
 await navigate(101);
 check(await evaluate("document.querySelector('#board canvas')!==null"),'actual WGo Canvas rendered');
 check(await evaluate("window.goPlayer.initial.board_only && window.goPlayer.initial.content==='(;SZ[5]PL[B]AB[ee])'"),'board only no answer');
 const token101=await evaluate('window.goPlayer.token');
 await clickWgo(0,0);
 await until("document.getElementById('status').textContent==='CORRECT'");
 check(await evaluate("goPlayer.responses.at(-1).status==='CORRECT' && goPlayer.responses.at(-1).duplicate===false"),'real server terminal');
 const afterOne=await evaluate("fetch('/fixture/effects').then(r=>r.json())");
 check(afterOne.node_mastery===1&&afterOne.player_grimoire_progress===1&&afterOne.g076_grimoire_events===1,'PG first state and reward once');
 const old=await evaluate('window.__g076PlayerDocument');
 await send('Page.reload');
 await until('window.__g076PlayerDocument && window.__g076PlayerDocument!=='+JSON.stringify(old)+' && window.goPlayer?.ready');
 check(await evaluate("document.getElementById('status').textContent==='CORRECT' && goPlayer.initial.previous_steps.length===1"),'refresh resumes server terminal');
 const stillOne=await evaluate("fetch('/fixture/effects').then(r=>r.json())");
 check(JSON.stringify(stillOne)===JSON.stringify(afterOne),'refresh did not resettle');
 await navigate(202);
 check(await evaluate("document.getElementById('status').textContent==='OPEN'"),'other signed user own attempt');
 await evaluate('goPlayer.loseResponse=true');
 await clickWgo(0,0);
 await until("document.getElementById('status').textContent==='UNCERTAIN'");
 check(await evaluate("!document.getElementById('retry').disabled"),'lost response exposes retry');
 await evaluate("document.getElementById('retry').click()");
 await until("document.getElementById('status').textContent==='CORRECT'");
 check(await evaluate("goPlayer.responses.at(-1).duplicate===true"),'committed response replay exactly once');
 const afterTwo=await evaluate("fetch('/fixture/effects').then(r=>r.json())");
 check(afterTwo.node_mastery===2&&afterTwo.player_grimoire_progress===2&&afterTwo.g076_grimoire_events===2,'two users independent one settlement');
 const cross=await evaluate("fetch('/api/g076/grimoire/steps',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({attempt_token:"+JSON.stringify(token101)+"})}).then(r=>r.status)");
 check(cross===409,'cross owner token denied');
 const forged=await evaluate("fetch('/api/g076/grimoire/steps',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({attempt_token:goPlayer.token,correct:true})}).then(r=>r.status)");
 check(forged===400,'browser correct cannot influence server');
 check(errors.length===0,'Chrome no uncaught exceptions');
 await fs.writeFile(path.join(out,'grimoire-pg-real-chrome-dom.html'),await evaluate('document.documentElement.outerHTML'));
 await fs.writeFile(path.join(out,'grimoire-pg-effects.json'),JSON.stringify(afterTwo,null,2));
 result={status:'PASS',checks,real_chrome:true,real_http:true,real_pg16:true,official_grimoire_product_ui:false,production_writes:0};
}catch(e){
 result={status:'FAIL',checks,error:e.stack,errors};
 if(ws?.readyState===WebSocket.OPEN){try{await fs.writeFile(path.join(out,'failure.png'),Buffer.from((await send('Page.captureScreenshot')).data,'base64'));}catch{}}
 process.exitCode=1;
}finally{
 console.log(JSON.stringify(result,null,2));
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
 if(ws?.readyState===WebSocket.OPEN){try{await send('Browser.close');}catch{}ws.close();}
 chrome.kill();await pause(300);
 if(!profile.startsWith(out+path.sep))throw new Error('Unsafe Chrome cleanup');
 await fs.rm(profile,{recursive:true,force:true,maxRetries:10,retryDelay:200}).catch(()=>{});
}
