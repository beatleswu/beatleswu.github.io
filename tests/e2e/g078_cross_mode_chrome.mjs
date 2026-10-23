/* G078: real local headless Chrome + repository WGo + actual nonmap client.
   file:// OFFLINE and loopback HTTP SYNTHETIC_NODE protocol fixtures only.
   No official HTML/app/Flask/PG or all-mode browser-playability claim. Uses
   the same local Chrome/CDP pattern as g076_rating_chrome.mjs, no downloads. */
import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import http from 'node:http';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
assert.equal(path.resolve(process.cwd()),root,'Run from authorized worktree');
const head=execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim();
assert.equal(head,'fe696e87806a177d74e3ebfd4e3bd37cd2571a64');
const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'g078-chrome-'));
const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const source = await Promise.all(['wgo/wgo.min.js', 'js/game/g076_nonmap_step_client.js']
  .map(p => fs.readFile(path.join(root, p), 'utf8')));
let server, chrome, ws, checks = 0, seq = 0, result;
const pending = new Map();
const pause = ms => new Promise(r => setTimeout(r, ms));
const check = (value, message) => { assert.ok(value, message); checks++; };
let chromeError, stderr = '';
function send(method, params = {}) {
  const id = ++seq;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP timeout: ' + method)); }, 15000);
    pending.set(id, {resolve: v => {clearTimeout(timer); resolve(v);}, reject: e => {clearTimeout(timer); reject(e);}});
    ws.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const r = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
}
function page() {
  return `<!doctype html><meta charset="utf-8"><div id="board"></div>
    <script>${source[0].replaceAll('</script', '<\\/script')}</script>
    <script>${source[1].replaceAll('</script', '<\\/script')}</script>
    <script>
    window.g078Document = crypto.randomUUID();
    window.board = new WGo.Board(document.getElementById('board'), {size:5,width:320});
    board.addObject({x:4,y:4,c:WGo.B});
    window.offlineChecks = async () => {
      const c=GoOdysseyG076NonMapSteps.createClient({fetchImpl:async()=>{throw Error('offline');}});
      let closed=false, inactive=false;
      try{await c.open('practice','offline-token');}catch(e){closed=e.message==='offline';}
      try{await c.play(0,0);}catch(e){inactive=e.message==='step_not_active';}
      return {closed,inactive,canvas:!!document.querySelector('canvas'),size:board.size};
    };
    window.httpChecks = async () => {
      const create=GoOdysseyG076NonMapSteps.createClient;
      let lose=true, calls=[];
      const c=create({fetchImpl:async(p,o)=>{calls.push(JSON.parse(o.body));const r=await fetch(p,o);
        if(p.endsWith('/steps')&&lose){lose=false;await r.clone().json();throw Error('lost_after_commit');}return r;}});
      let opened=await c.open('practice','fixture-owner-101');
      let lost=false;try{await c.play(0,0);}catch(e){lost=e.message==='lost_after_commit';}
      const replay=await c.retry();
      board.addObject({x:0,y:0,c:WGo.B});board.addObject({x:1,y:1,c:WGo.W});
      const resumed=create();const ready=await resumed.open('practice','fixture-owner-101');
      const terminal=await resumed.play(2,2);
      const effects=await fetch('/fixture/effects').then(r=>r.json());
      const other=create();let denied=false,inactive=false;
      try{await other.open('practice','other-account-token');}catch(e){denied=e.status===403;}
      try{await other.play(0,0);}catch(e){inactive=e.message==='step_not_active';}
      await fetch('/fixture/hold',{method:'POST'});
      let hold=false,cleared=false;
      try{await resumed.open('daily','fixture-owner-101');}catch(e){hold=e.status===503;}
      try{await resumed.play(0,0);}catch(e){cleared=e.message==='step_not_active';}
      return {opened,lost,replay,ready,terminal,effects,denied,inactive,hold,cleared,
        exactReplay:JSON.stringify(calls[1])===JSON.stringify(calls[2]),
        canvas:!!document.querySelector('canvas')};
    };
    </script>`;
}
try {
  let index = 0, effects = 0, hold = false;
  const events = new Map();
  const ready = () => ({status:'READY',step_index:index,step_nonce:'nonce-'+index,
    board_only:true,content:'(;SZ[5]PL[B]AB[ee])'});
  server = http.createServer(async(req,res) => {
    const chunks=[];for await(const part of req) chunks.push(part);
    const raw=Buffer.concat(chunks).toString();const b=raw?JSON.parse(raw):{};
    const json=(v,status=200)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(v));};
    if(req.url==='/'){res.writeHead(200,{'Content-Type':'text/html'});return res.end(page());}
    if(req.url==='/fixture/effects')return json({settlements:effects});
    if(req.url==='/fixture/hold'){hold=true;return json({ok:true});}
    if(hold)return json({error:'fixture_hold'},503);
    if(b.attempt_token!=='fixture-owner-101')return json({error:'fixture_owner_mismatch'},403);
    if(req.url==='/api/g076/nonmap/steps/start')return json(ready());
    if(req.url==='/api/g076/nonmap/steps'){
      const key=JSON.stringify(b);
      if(events.has(key))return json(events.get(key));
      if(b.step_nonce!=='nonce-'+index)return json({error:'fixture_stale'},409);
      const target=index===0?0:2;
      if(b.move?.x!==target||b.move?.y!==target)return json({error:'fixture_bad_move'},400);
      index++;
      const response=index===1?{status:'CONTINUE',step_index:1,step_nonce:'nonce-1',opponent_reply:[1,1]}:
        {status:'CORRECT',step_index:2,settlement:{submission_id:'fixture-once'}};
      if(index===2)effects++;
      events.set(key,response);return json(response);
    }
    return json({error:'unknown_fixture_route'},404);
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const offline=path.join(temp,'offline.html');await fs.writeFile(offline,page());
  chrome=spawn(chromePath,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
    '--disable-extensions','--disable-background-networking','--disable-component-update','--disable-sync',
    '--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
    '--remote-debugging-port=0','--user-data-dir='+path.join(temp,'profile'),'about:blank'],
    {windowsHide:true,stdio:['ignore','ignore','pipe']});
  chrome.on('error',e=>{chromeError=e;});chrome.stderr.on('data',x=>{stderr+=x;});
  let port;
  for(let i=0;i<100;i++){
    if(chromeError)throw chromeError;
    try{port=Number((await fs.readFile(path.join(temp,'profile/DevToolsActivePort'),'utf8')).split('\n')[0]);break;}catch{}
    await pause(100);
  }
  assert.ok(port,'local Chrome CDP ready');
  const target=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
  ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  ws.onmessage=e=>{const v=JSON.parse(e.data);if(v.id){const p=pending.get(v.id);pending.delete(v.id);
    if(p)v.error?p.reject(Error(JSON.stringify(v.error))):p.resolve(v.result);}};
  await send('Runtime.enable');await send('Page.enable');
  let previous;
  for(const [mode,url] of [['OFFLINE_FILE',pathToFileURL(offline).href],
                          ['LOOPBACK_HTTP','http://127.0.0.1:'+server.address().port+'/']]){
    await send('Page.navigate',{url});
    let current;
    for(let i=0;i<100;i++){
      current=await evaluate('window.g078Document');
      if(current&&current!==previous)break;
      await pause(100);
    }
    check(current&&current!==previous,mode+' fresh document');previous=current;
    const offlineResult=await evaluate('offlineChecks()');
    check(offlineResult.canvas&&offlineResult.size===5,mode+' actual WGo board');
    check(offlineResult.closed&&offlineResult.inactive,mode+' offline denies fallback');
    if(mode==='LOOPBACK_HTTP'){
      const r=await evaluate('httpChecks()');
      check(r.opened.board_only&&!r.opened.content.includes(';B['),'HTTP private board');
      check(r.lost&&r.exactReplay,'HTTP exact request retry after lost response');
      check(r.replay.status==='CONTINUE'&&r.ready.step_index===1,'HTTP authoritative resume');
      check(r.terminal.status==='CORRECT'&&r.effects.settlements===1,'HTTP synthetic settlement once');
      check(r.denied&&r.inactive,'HTTP account rejection clears cursor');
      check(r.hold&&r.cleared,'HTTP 503 HOLD clears previous mode cursor');
    }
  }
  result={status:'PASS',checks,head,
    source_sha256:source.map(s=>createHash('sha256').update(s).digest('hex')),
    real_chrome:true,real_wgo:true,offline_file:true,loopback_http:true,
    backend:'SYNTHETIC_NODE_ONLY',official_app:false,official_pages:false,flask:false,postgres:false,
    full_six_mode_browser_matrix:'NOT_EXECUTED',profile:temp};
}catch(error){result={status:'FAIL',checks,error:error.stack,chromeError:String(chromeError||''),stderr};process.exitCode=1;}
finally{
  console.log(JSON.stringify(result,null,2));
  if(ws?.readyState===WebSocket.OPEN){try{await send('Browser.close');}catch{}ws.close();}
  chrome?.kill();
  if(server)await new Promise(resolve=>server.close(resolve));
}
