/* Real headless Chrome/WGo/actual rating_test.html. Default: Flask fixture :15083.
   --ui-only runs a synthetic Node HTTP backend, NEVER Elo/Flask/PG evidence. */
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';

const uiOnly=process.argv.includes('--ui-only');
const root=process.cwd(), out=path.resolve(root,'artifacts/g076-rating');
await fs.mkdir(out,{recursive:true});
const runDir=await fs.mkdtemp(path.join(out,'chrome-run-'));
const profile=path.join(runDir,'profile');
let fixture;
let base='http://127.0.0.1:15083';
if(uiOnly) {
  let uid=7, gate='steps', current, count=0, now=1000;
  const events=new Map();
  const question=()=>({id:301+count,rating:1500,difficulty:'5k',discipline:'life_death',
    content:'(;SZ[5]PL[B]AB[ee])',board_only:true,transform_index:0,
    step:{attempt_id:'ui-attempt-'+count,nonce:'ui-nonce-'+count+'-0',index:0,played:[],deadline:now+35,server_now:now}});
  const payload=()=>({session_id:'ui-sid-'+uid,round:count,total_rounds:16,min_rounds:12,
    cur_rating:1500,rank_label:'UI FIXTURE',answers:[],question:current});
  fixture=http.createServer(async(req,res)=>{
    let body='';for await(const chunk of req)body+=chunk;
    const b=body?JSON.parse(body):{}, p=new URL(req.url,'http://127.0.0.1').pathname;
    const json=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
    if(p==='/fixture/login'){uid=b.uid;count=0;current=null;events.clear();return json({ok:true});}
    if(p==='/fixture/gate/hold'){gate='hold';return json({ok:true});}
    if(p==='/fixture/gate/on'){gate='steps';return json({ok:true});}
    if(p==='/fixture/effects')return json({responses:Array.from({length:count},()=>({user_id:uid}))});
    if(p==='/api/g076/rating/capability')return json({mode:gate},gate==='hold'?503:200);
    if(p==='/api/g076/rating/start'){current=question();return json(payload());}
    if(p.startsWith('/api/g076/rating/resume/'))return json(payload());
    if(p==='/api/g076/rating/step') {
      const key=b.attempt_id+':'+b.nonce;
      if(events.has(key))return json(events.get(key));
      if(b.nonce!==current.step.nonce)return json({error:'stale'},409);
      let reply;
      if(b.action==='move' && current.step.index===0 && b.move.x===0 && b.move.y===0) {
        current.step={...current.step,index:1,nonce:'ui-nonce-'+count+'-1',played:[{x:0,y:0,color:'B'},{x:1,y:1,color:'W'}]};
        reply={status:'CONTINUE',...current.step};
      } else {
        const correct=b.action==='move' && current.step.index===1 && b.move.x===2 && b.move.y===2;
        count++;current=question();reply={status:correct?'CORRECT':'INCORRECT',result:{...payload(),correct,finished:false}};
      }
      events.set(key,reply);return json(reply);
    }
    if(p==='/api/rating_test/pool_info')return json({pool_size:2});
    if(p.startsWith('/api/'))return json({},404);
    const name=p==='/'?'rating_test.html':p.slice(1);
    const file=path.resolve(root,name);
    if(!file.startsWith(root+path.sep)){res.writeHead(403);return res.end();}
    try {
      const data=await fs.readFile(file);
      const type={'.html':'text/html','.js':'application/javascript','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml'}[path.extname(file)]||'application/octet-stream';
      res.writeHead(200,{'Content-Type':type});res.end(data);
    } catch {res.writeHead(404);res.end();}
  });
  await new Promise((resolve,reject)=>{fixture.once('error',reject);fixture.listen(0,'127.0.0.1',resolve);});
  base='http://127.0.0.1:'+fixture.address().port;
}
const chrome=spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',[
  '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
  '--disable-extensions','--disable-background-networking','--disable-component-update','--disable-sync',
  '--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
  '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank',
],{windowsHide:true,stdio:['ignore','ignore','pipe']});
let chromeStderr='',chromeExit;
chrome.stderr.on('data',chunk=>{chromeStderr+=chunk.toString();});
chrome.on('exit',(code,signal)=>{chromeExit={code,signal};});
let spawnError;chrome.on('error',error=>{spawnError=error;});
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws,seq=0,checks=0,result;
const pending=new Map(), errors=[];
function check(value,message){assert.ok(value,message);checks++;}
function send(method,params={}) {
  const id=++seq;
  return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
}
async function evaluate(expression){
  const value=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  if(value.exceptionDetails)throw new Error(value.exceptionDetails.exception?.description||value.exceptionDetails.text);
  return value.result.value;
}
async function until(expression){
  for(let i=0;i<160;i++){if(await evaluate(expression))return;await pause(100);}
  throw new Error('Timeout: '+expression+' '+await evaluate('document.body.innerText.slice(-1000)'));
}
async function click(x,y){
  await evaluate('_board.element.scrollIntoView({block:"center"})');await pause(100);
  const point=await evaluate(`(()=>{const r=_board.element.getBoundingClientRect();return {x:r.left+_board.getX(_bx(${x})),y:r.top+_board.getY(_by(${y}))};})()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
}
function point(x,y,t) {
  return [[x,y],[4-y,x],[4-x,4-y],[y,4-x],[4-x,y],[x,4-y],[y,x],[4-y,4-x]][t];
}
try {
  let port;
  for(let i=0;i<100;i++){
    if(spawnError)throw spawnError;
    try{port=Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break;}catch{}
    await pause(100);
  }
  assert.ok(port,'Chrome debugger ready');
  const target=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
  ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  ws.onmessage=event=>{
    const value=JSON.parse(event.data);
    if(value.id){const p=pending.get(value.id);pending.delete(value.id);value.error?p.reject(new Error(JSON.stringify(value.error))):p.resolve(value.result);}
    if(value.method==='Runtime.exceptionThrown')errors.push(value.params.exceptionDetails.exception?.description||value.params.exceptionDetails.text);
  };
  ws.onclose=()=>{for(const p of pending.values())p.reject(new Error('CDP closed'));pending.clear();};
  await send('Runtime.enable');await send('Page.enable');await send('Network.enable');
  await send('Page.addScriptToEvaluateOnNewDocument',{source:`
    window.__ratingDoc=crypto.randomUUID();window.__ratingReceipts=[];
    const originalFetch=window.fetch.bind(window);
    window.fetch=async(...args)=>{
      const r=await originalFetch(...args);
      if(String(args[0])==='/api/g076/rating/step'){
        window.__ratingReceipts.push({body:JSON.parse(args[1].body),data:await r.clone().json()});
        if(window.__loseRatingResponse){window.__loseRatingResponse=false;throw new Error('lost response after server commit');}
      }
      return r;
    };
  `});
  for(const [uid,width,height] of [[7,1400,1100],[8,390,844]]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});
    await send('Page.navigate',{url:base+'/'});
    await until('typeof G076Rating!=="undefined" && typeof startTest==="function"');
    await evaluate(`fetch('/fixture/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid:${uid}})}).then(()=>{sessionStorage.clear();_sid=null;return startTest();})`);
    await until('Boolean(_board) && Boolean(_curQ?.step) && document.querySelector("canvas")');
    check(await evaluate('_currentNode===null && parseSGF(_curQ.content).tree===null'),'board-only actual page, no answer tree');
    check(await evaluate('_board instanceof WGo.Board'),'real WGo board');
    // Existing loopback fixture may have prior independent browser receipts.
    // Assert that THIS new answer inserts exactly ONE response for this user.
    const baselineResponses=await evaluate('fetch("/fixture/effects").then(r=>r.json()).then(x=>x.responses.filter(r=>r.user_id==='+uid+').length)');
    let t=await evaluate('_curQ.transform_index');
    await click(...point(0,0,t));
    await until('_curQ.step.index===1 && !_testAnswering');
    check(await evaluate('_curQ.step.played.length===2'),'committed opponent reply');
    const before=await evaluate('JSON.stringify(_curQ.step)');
    const previous=await evaluate('window.__ratingDoc');
    await send('Page.reload');
    await until(`window.__ratingDoc!==${JSON.stringify(previous)} && typeof _curQ!=='undefined' && _curQ?.step?.index===1 && Boolean(_board)`);
    check((await evaluate('JSON.parse('+JSON.stringify(before)+').nonce===_curQ.step.nonce')),'resume retains current nonce');
    check(await evaluate('_curQ.step.played.length===2 && _currentNode===null'),'resume replays only committed stones');
    await evaluate('window.__loseRatingResponse=true');
    await click(2,2);
    await until('_round===1 && _curQ?.step?.index===0 && !_testAnswering');
    check(await evaluate('__ratingReceipts.length===2 && JSON.stringify(__ratingReceipts[0].body)===JSON.stringify(__ratingReceipts[1].body)'),'lost terminal response repeats identical nonce/body');
    check(await evaluate('__ratingReceipts[0].data.status==="CORRECT"'),'server terminal receipt');
    const effects=await evaluate('fetch("/fixture/effects").then(r=>r.json())');
    check(effects.responses.filter(r=>r.user_id===uid).length===baselineResponses+1,
          'this round commits exactly one original settlement (fixture may retain prior runs)');
    check(await evaluate('!__ratingReceipts.some(r=>"correct" in r.body || "moves" in r.body)'),'no browser verdict/history');
    await fs.writeFile(path.join(runDir,`rating-${uid}-${width}.png`),Buffer.from((await send('Page.captureScreenshot')).data,'base64'));
    if(width<500)check(await evaluate('_board.element.getBoundingClientRect().width<=innerWidth'),'mobile board fits viewport');
    if(!uiOnly) {
      for(const kind of ['timeout','partial_timeout','give_up','late_move']) {
        await evaluate('stopTimer();sessionStorage.clear();_sid=null;startTest()');
        await until('_round===0 && _curQ?.step?.index===0 && Boolean(_board) && !_testAnswering');
        const sid=await evaluate('_sid');
        if(kind==='partial_timeout') {
          t=await evaluate('_curQ.transform_index');
          await click(...point(0,0,t));
          await until('_curQ.step.index===1 && !_testAnswering');
        }
        if(kind!=='give_up')await evaluate('fetch("/fixture/clock",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({seconds:100})})');
        const receiptIndex=await evaluate('__ratingReceipts.length');
        await evaluate('window.__loseRatingResponse=true');
        if(kind==='late_move') {
          t=await evaluate('_curQ.transform_index');
          await click(...point(0,0,t));
        } else {
          await evaluate(`${kind==='give_up'?'':'_timerLeft=0;'}submitMove('wrong')`);
        }
        await until('_round===1 && _curQ?.step?.index===0 && !_testAnswering');
        const receipts=await evaluate(`__ratingReceipts.slice(${receiptIndex})`);
        check(receipts.length===2 && JSON.stringify(receipts[0].body)===JSON.stringify(receipts[1].body),kind+' lost response exact replay');
        check(receipts[0].data.status==='INCORRECT' && receipts[0].data.result.correct===false,kind+' server failure');
        check(receipts[0].data.played.length===(kind==='partial_timeout'?2:0),kind+' no fake/late move');
        const settled=await evaluate('fetch("/fixture/effects").then(r=>r.json())');
        const rows=settled.responses.filter(r=>r.session_id===sid);
        check(rows.length===1 && rows[0].correct===0 && rows[0].ability_after<rows[0].ability_before,kind+' original Elo once');
        check(await evaluate('_currentNode===null && parseSGF(_curQ.content).tree===null'),kind+' following question board-only');
      }
    }
  }
  await evaluate("fetch('/fixture/gate/hold',{method:'POST'})");
  check(await evaluate('G076Rating.mode().then(()=>false,()=>true)'),'gate HOLD has no legacy fallback');
  check(errors.length===0,'no browser exceptions: '+errors.join('\n'));
  result={status:'PASS',checks,real_chrome:true,real_wgo:true,actual_rating_page:true,
    backend:uiOnly?'SYNTHETIC_NODE_UI_ONLY':'FLASK_SQLITE_EXTRACTED_ORIGINAL_SEAM',
    postgres:false,exact_app_integration:false};
}catch(error){result={status:'FAIL',checks,error:error.stack,errors,uiOnly,chromeExit,chromeStderr};process.exitCode=1;}
finally {
  console.log(JSON.stringify(result,null,2));
  await fs.writeFile(path.join(runDir,uiOnly?'ui-only-chrome.json':'flask-chrome.json'),JSON.stringify(result,null,2));
  if(ws?.readyState===WebSocket.OPEN){try{await send('Browser.close');}catch{}ws.close();}
  chrome.kill();
  if(fixture)await new Promise(resolve=>fixture.close(resolve));
  // Preserve isolated profile with receipts; no recursive delete needed.
}
