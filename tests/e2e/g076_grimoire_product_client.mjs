/* Real Chrome + real WGo + actual Product HTML/JS, with a CONTRACT HTTP stub.
   This is NOT Flask/PG or official Product registration evidence. No database.
   No packages required; node >=22, local Chrome. Every receipt directory is new. */
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import assert from 'node:assert/strict';

const root = process.cwd();
const out = path.join(root,'artifacts','g076-r5-product-adapter-'+Date.now());
await fs.mkdir(out,{recursive:true});
let history = [], lost = false, submissions = [], unavailable = false;
const preview = '(;SZ[9]PL[W]AB[aa:ab]AW[ii]LB[cc:目標\\]位置])';
const event = {status:'CONTINUE',step_index:1,player_move:[1,1],opponent_reply:[2,2],step_nonce:'n1'};
function row() {
  return {status:history.length === 2 ? 'CORRECT':'OPEN',step_index:history.length,
    step_nonce:'n'+history.length,board_only:true,content:preview,previous_steps:history};
}
const files = {'/grimoire/player':'grimoire_player.html',
  '/grimoire/player.js':'js/game/g076_grimoire_product_client.js',
  '/wgo/wgo.min.js':'wgo/wgo.min.js','/wgo/wgo.player.min.js':'wgo/wgo.player.min.js'};
const server = http.createServer(async(req,res) => {
  try {
    if (files[req.url]) {
      let body = await fs.readFile(path.join(root,files[req.url]),'utf8');
      if (req.url === '/grimoire/player.js') body = `
        window.__boards=[]; const BaseBoard=WGo.Board;
        const WrappedBoard=function(...args){const b=new BaseBoard(...args);window.__boards.push(b);return b;};
        // WGo's constructor reads WGo.Board.default during construction.
        // Preserve its static defaults while instrumenting a real WGo board.
        Object.assign(WrappedBoard,BaseBoard);WrappedBoard.prototype=BaseBoard.prototype;
        WGo.Board=WrappedBoard;
        ` + body;
      res.setHeader('Content-Type',req.url.endsWith('.js')?'application/javascript':'text/html; charset=utf-8');
      res.end(body); return;
    }
    if (req.url.startsWith('/api/g076/grimoire/product/') && req.method === 'POST') {
      let text = ''; for await (const chunk of req) text += chunk;
      const data = JSON.parse(text);
      assert.equal(req.headers['x-grimoire-request'],'1');
      let result;
      if (unavailable) { res.writeHead(503,{'Content-Type':'application/json'});res.end('{"error":"grimoire_backend_unavailable"}');return; }
      if (req.url.endsWith('/admission')) {
        assert.deepEqual(data,{}); result = {attempt_token:'contract-server-token',title:'讀棋與應手'};
      } else if (!('move' in data)) {
        assert.deepEqual(data,{attempt_token:'contract-server-token'}); result = row();
      } else {
        submissions.push(data);
        assert.deepEqual(Object.keys(data).sort(),['attempt_token','move','step_index','step_nonce']);
        assert.equal(data.attempt_token,'contract-server-token');
        if (data.step_index === 0) {
          assert.equal(data.step_nonce,'n0'); assert.deepEqual(data.move,{x:1,y:1});
          if (!history.length) history.push(event);
          result = {...event,duplicate:lost};
          if (!lost) { lost = true; res.destroy(); return; }
        } else {
          assert.equal(data.step_index,1); assert.equal(data.step_nonce,'n1');
          assert.deepEqual(data.move,{x:3,y:3});
          result = {status:'CORRECT',step_index:2,player_move:[3,3],opponent_reply:null,
            settlement:{submission_id:'contract-receipt'}};
          history = [event,result];
        }
      }
      res.setHeader('Content-Type','application/json');res.end(JSON.stringify(result));return;
    }
    res.writeHead(404);res.end();
  } catch(e) { res.writeHead(500);res.end(String(e)); }
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin = 'http://127.0.0.1:'+server.address().port;
let chrome, ws, seq = 0, checks = 0;
const waiting = new Map();
function check(value,msg) { assert.ok(value,msg); checks++; }
function send(method,params={}) {
  const id = ++seq;
  return new Promise((resolve,reject)=>{
    const timer = setTimeout(()=>{waiting.delete(id);reject(Error('CDP timeout '+method));},10000);
    waiting.set(id,{resolve:v=>{clearTimeout(timer);resolve(v);},reject:e=>{clearTimeout(timer);reject(e);}});
    ws.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression) {
  const r = await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || 'browser exception');
  return r.result.value;
}
const pause = ms=>new Promise(r=>setTimeout(r,ms));
async function until(expr) {
  for (let n=0;n<100;n++) { if(await evaluate(expr)) return; await pause(100); }
  throw Error('timeout: '+expr+' body='+await evaluate('document.body.innerText'));
}
async function click(x,y) {
  await evaluate('window.__boards.at(-1).element.scrollIntoView({block:"center"})');
  await pause(160);
  const p = await evaluate(`(()=>{const b=window.__boards.at(-1),r=b.element.getBoundingClientRect();return {x:r.left+b.getX(${x}),y:r.top+b.getY(${y})};})()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...p});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...p});
}
try {
  chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',[
    '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
    '--disable-extensions','--disable-background-networking','--disable-component-update',
    '--disable-sync','--no-proxy-server','--remote-debugging-port=0',
    '--user-data-dir='+path.join(out,'chrome-profile'),'about:blank'
  ],{windowsHide:true,stdio:['ignore','ignore','pipe']});
  let stderr = ''; chrome.stderr.on('data',b=>{stderr+=b;});
  chrome.on('error',e=>{stderr+=String(e);});
  let active;
  for(let n=0;n<80;n++) {
    try { active = (await fs.readFile(path.join(out,'chrome-profile','DevToolsActivePort'),'utf8')).split('\n')[0];break; } catch {}
    if(chrome.exitCode !== null) throw Error('Chrome exited '+chrome.exitCode+' '+stderr.slice(-500));
    await pause(100);
  }
  if (!active) throw Error('Chrome CDP unavailable '+stderr.slice(-500));
  const targets = await fetch('http://127.0.0.1:'+active+'/json/list').then(r=>r.json());
  ws = new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  ws.onmessage = msg=>{const data=JSON.parse(msg.data);const p=waiting.get(data.id);if(p){waiting.delete(data.id);data.error?p.reject(Error(JSON.stringify(data.error))):p.resolve(data.result);}};
  await send('Page.enable');
  await send('Page.navigate',{url:origin+'/grimoire/player'});
  await until('document.getElementById("status")?.textContent === "輪到你落子"');
  check(await evaluate('document.querySelectorAll("canvas").length > 0'),'actual WGo canvas');
  check(await evaluate('__boards.at(-1).size===9'),'actual SGF size');
  check(await evaluate('__boards.at(-1).obj_arr[0][1].some(o=>o.c===WGo.B)'),'SGF compressed setup range');
  await click(1,1);
  // A loopback Chromium network retry may automatically resend after ECONNRESET
  // before the app surfaces an uncertain receipt. Both paths must be durable.
  await until('!document.getElementById("retry").disabled || '+
              'document.getElementById("status").textContent === "輪到你落子" && '+
              'document.getElementById("receipt").textContent === "" && '+
              'document.querySelectorAll("canvas").length > 0 && '+
              'window.__boards.length > 0 && '+
              'window.__boards.at(-1).obj_arr[1][1].some(o=>o.c===WGo.W)');
  check(history.length===1,'lost response committed once');
  if (!(await evaluate('document.getElementById("retry").disabled')))
    await evaluate('document.getElementById("retry").click()');
  await until('document.getElementById("retry").disabled && document.getElementById("status").textContent === "輪到你落子"');
  check(submissions.length===2 && JSON.stringify(submissions[0])===JSON.stringify(submissions[1]),'identical nonce and move retry');
  check(await evaluate('__boards.at(-1).obj_arr[1][1].some(o=>o.c===WGo.W)'),'SGF white player');
  check(await evaluate('__boards.at(-1).obj_arr[2][2].some(o=>o.c===WGo.B)'),'server opponent reply');
  await send('Page.reload');
  await until('document.getElementById("status")?.textContent === "輪到你落子"');
  check(await evaluate('__boards.at(-1).obj_arr[1][1].some(o=>o.c===WGo.W)'),'reload recovers server history');
  await click(3,3);
  await until('document.getElementById("status").textContent === "修煉完成"');
  check(await evaluate('document.getElementById("receipt").textContent.includes("contract-receipt")'),'terminal receipt');
  await click(4,4); await pause(100);
  check(submissions.length===3,'terminal board locked');
  unavailable = true;
  await evaluate('document.getElementById("resume").click()');
  await until('document.getElementById("message").textContent.includes("重新連線")');
  await click(4,4); await pause(100);
  check(submissions.length===3,'failed reconnect cannot use stale board');
  unavailable = false;
  await evaluate('document.getElementById("resume").click()');
  await until('document.getElementById("status").textContent === "修煉完成"');
  check(true,'manual reconnect resumes terminal state');
  await fs.writeFile(path.join(out,'dom.html'),await evaluate('document.documentElement.outerHTML'));
  const {data} = await send('Page.captureScreenshot',{format:'png'});
  await fs.writeFile(path.join(out,'player.png'),Buffer.from(data,'base64'));
  const result = {status:'PASS',checks,evidence:'real Chrome/WGo Product client; contract HTTP stub; NOT Flask/PG',submissions:submissions.length};
  await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify({...result,out}));
} catch(e) {
  await fs.writeFile(path.join(out,'result.json'),JSON.stringify({status:'FAIL_OR_BLOCKED',checks,error:String(e),evidence:'contract HTTP stub; NOT Flask/PG'},null,2));
  throw e;
} finally {
  ws?.close();chrome?.kill();server.closeAllConnections();server.close();
}
