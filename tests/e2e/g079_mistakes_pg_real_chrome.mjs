/* G079 B1: real headless Chrome drives the ORIGINAL mistakes.html served by the
   REAL app.py on loopback, backed by a disposable PostgreSQL 16 database.
   Start first: python -B tests/e2e/g079_mistakes_pg_browser_server.py
   Covers ON correct (two steps, refresh mid-question), ON wrong, retry of the
   same step after a lost response, rewards visible, and OFF legacy page. */
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';

const BASE = 'http://127.0.0.1:' + (process.env.G079_BROWSER_PORT || '55491');
const out = path.join(process.env.G079_EVIDENCE_DIR || 'D:\\g079-artifacts\\a', 'chrome');
await fs.mkdir(out, {recursive: true});
const profile = await fs.mkdtemp(path.join(out, 'profile-'));
const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--disable-extensions', '--disable-background-networking', '--disable-component-update',
  '--disable-sync', '--no-proxy-server', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
  '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank',
], {windowsHide: true, stdio: 'ignore'});
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let ws, seq = 0;
const pending = new Map(), errors = [], requests = [], checks = [];
function check(value, msg, detail) {
  checks.push({check: msg, pass: !!value, ...(detail === undefined ? {} : {detail})});
  assert.ok(value, msg + (detail === undefined ? '' : ' ' + JSON.stringify(detail)));
}
function send(method, params = {}) {
  const id = ++seq;
  return new Promise((resolve, reject) => {
    pending.set(id, {resolve, reject});
    ws.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expr) {
  const v = await send('Runtime.evaluate', {expression: expr, awaitPromise: true, returnByValue: true});
  if (v.exceptionDetails) throw new Error(v.exceptionDetails.exception?.description || v.exceptionDetails.text);
  return v.result.value;
}
async function until(expr, label) {
  for (let i = 0; i < 300; i++) {
    try { if (await evaluate(expr)) return; } catch (e) { if (!String(e).includes('ReferenceError')) throw e; }
    await pause(100);
  }
  throw new Error('Timed out ' + (label || expr) + ' msg=' +
    await evaluate("document.getElementById('msg-box')?.textContent||document.body.innerText.slice(0,300)"));
}
async function login(uid) {
  const old = await evaluate('window.__g079Doc||null');
  await send('Page.navigate', {url: BASE + '/__g079/login/' + uid});
  await until(`window.__g079Doc && window.__g079Doc!==${JSON.stringify(old)} && location.pathname==='/mistakes' && document.readyState==='complete'`, 'mistakes page');
  await until("typeof mistakesProtocol!=='undefined' && mistakesProtocol!==null && Array.isArray(displayList) && displayList.length>0", 'list loaded');
}
async function reload() {
  const old = await evaluate('window.__g079Doc||null');
  await send('Page.reload');
  await until(`window.__g079Doc && window.__g079Doc!==${JSON.stringify(old)} && typeof mistakesProtocol!=='undefined' && mistakesProtocol==='steps' && displayList.length>0`, 'reload');
}
async function effects(uid) {
  return evaluate(`fetch('/__g079/effects/${uid}').then(r=>r.json())`);
}
async function open(qid) {
  await evaluate(`selectQ(${qid})`);
  await until(`currentMistake && currentMistake.question_id===${qid} && mistakesCursor && !answering`, 'cursor ' + qid);
}
async function clickPoint(x, y) {
  const p = await evaluate(`(()=>{const r=board.element.getBoundingClientRect();return {x:r.left+board.getX(_bx(${x})),y:r.top+board.getY(_by(${y}))};})()`);
  await send('Input.dispatchMouseEvent', {type: 'mousePressed', button: 'left', clickCount: 1, ...p});
  await send('Input.dispatchMouseEvent', {type: 'mouseReleased', button: 'left', clickCount: 1, ...p});
}
const msg = () => evaluate("document.getElementById('msg-box').textContent");
let result;
try {
  let port = 0;
  for (let i = 0; i < 100; i++) {
    try { port = Number((await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); if (port) break; } catch {}
    await pause(100);
  }
  check(port > 0, 'Chrome remote debugging started');
  const target = await (await fetch('http://127.0.0.1:' + port + '/json/new?about:blank', {method: 'PUT'})).json();
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  ws.onmessage = event => {
    const v = JSON.parse(event.data);
    if (v.id) { const p = pending.get(v.id); pending.delete(v.id); v.error ? p.reject(new Error(JSON.stringify(v.error))) : p.resolve(v.result); }
    if (v.method === 'Runtime.exceptionThrown') errors.push(v.params.exceptionDetails.exception?.description || v.params.exceptionDetails.text);
    if (v.method === 'Network.requestWillBeSent') requests.push({url: v.params.request.url, method: v.params.request.method, body: v.params.request.postData || null});
  };
  await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 1280, height: 900, deviceScaleFactor: 1, mobile: false});
  // Test hook only: simulate ONE lost HTTP response for the next step POST
  // (the request reaches the real server and commits; the page sees a failure).
  await send('Page.addScriptToEvaluateOnNewDocument', {source: `
    window.__g079Doc=Math.random().toString(36).slice(2);
    const realFetch=window.fetch.bind(window);
    window.fetch=async(input,init)=>{
      const response=await realFetch(input,init);
      const url=String(input&&input.url||input);
      if(window.__g079DropNextStep && url.endsWith('/api/g076/mistakes/steps')){
        window.__g079DropNextStep=false; window.__g079Dropped=(window.__g079Dropped||0)+1;
        throw new TypeError('g079 simulated lost response');
      }
      return response;
    };`});

  // ── ON: correct two-step path with refresh mid-question ──
  await login(9101);
  check(await evaluate("mistakesProtocol==='steps'"), 'ON capability selects server steps');
  await open(7901);
  check(await evaluate("document.querySelector('#board-wrap canvas, canvas')!==null"), 'WGo canvas rendered');
  check(await evaluate("mistakesCursor.status==='READY' && mistakesCursor.board_only===true && !mistakesCursor.content.includes('B[aa]')"),
        'server sent board-only SGF without the solution');
  await clickPoint(0, 0);
  await until("mistakesCursor.status==='CONTINUE' && !answering", 'first step');
  check(await evaluate("JSON.stringify(mistakesCursor.opponent_reply)==='[1,1]'"), 'server opponent reply');
  const mid = await effects(9101);
  check(mid.review_log === 0 && mid.step_events === 1 && mid.stats.xp === 0, 'no settlement before terminal', mid);
  await reload();
  await open(7901);
  check(await evaluate("mistakesCursor.status==='READY' && mistakesCursor.step_index===1 && mistakesCursor.previous_steps.length===1"),
        'refresh resumes the server cursor mid-question');
  await clickPoint(2, 2);
  await until("mistakesCursor.status==='CORRECT' && !answering", 'terminal correct');
  const settledMsg = await msg();
  check(settledMsg.includes('+37 XP'), 'reward visible on original page', settledMsg);
  const done = await effects(9101);
  check(done.stats.xp === 37 && done.stats.total_correct === 1 && done.stats.mistake_corrected === 1 &&
        done.mistakes_reviews === 1 && done.step_events === 2, 'PG settled once with real rewards', done);
  check(done.mistake_log.find(m => m.question_id === 7901).correct_after === 1 &&
        done.srs_cards.find(c => c.question_id === 7901).progress_credited === 1, 'mistake/SRS updated', done);
  check(done.badges.includes('mistake_1') && done.daily_quests.some(q => q.quest_key === 'streak_correct' && q.progress === 1),
        'badge and daily quest written', done);
  check(await evaluate("document.getElementById('q-correct-after').textContent.includes('1')"), 'durable correct_after displayed');
  await reload();
  await open(7901);
  check(await evaluate("mistakesCursor.status==='CORRECT' && mistakesCursor.duplicate===true"), 'refresh after terminal replays the receipt');
  check(JSON.stringify(await effects(9101)) === JSON.stringify(done), 'refresh did not resettle');

  // ── ON: retry the same step after a lost response ──
  await open(7902);
  await evaluate('window.__g079DropNextStep=true');
  await clickPoint(0, 0);
  await until("window.__g079Dropped===1 && !answering && document.getElementById('btn-step-retry').style.display!=='none'", 'lost response');
  const lost = await effects(9101);
  check(lost.review_log === 2 && lost.stats.xp > 37, 'server committed despite the lost response', lost);
  await evaluate("document.getElementById('btn-step-retry').click()");
  await until("mistakesCursor && mistakesCursor.status==='CORRECT' && !answering", 'retry');
  check(await evaluate("mistakesCursor.duplicate===true"), 'retry of the same step returned the stored result');
  check(JSON.stringify(await effects(9101)) === JSON.stringify(lost), 'retry granted nothing twice');

  // ── ON: wrong path ──
  await login(9102);
  await open(7901);
  await clickPoint(1, 3);
  await until("mistakesCursor.status==='INCORRECT' && !answering", 'wrong terminal');
  const wrong = await effects(9102);
  check(wrong.stats.xp === 0 && wrong.mistakes_reviews === 1 &&
        wrong.mistake_log.find(m => m.question_id === 7901).wrong_count === 2, 'wrong path: no reward, counted wrong', wrong);
  check((await msg()).includes('Server settled incorrect'), 'wrong verdict visible');
  const spoof = await evaluate(`fetch('/api/g076/mistakes/steps',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({flow:'mistakes',attempt_token:mistakesToken,step_index:0,step_nonce:'x',move:{x:0,y:0},grade:5})}).then(r=>r.status)`);
  check(spoof === 400, 'browser grade field rejected');
  check(JSON.stringify(await effects(9102)) === JSON.stringify(wrong), 'spoof wrote nothing');

  // ── OFF: legacy page works ──
  await evaluate("fetch('/__g079/flag/off',{method:'POST'}).then(r=>r.json())");
  const before = requests.length;
  await login(9103);
  check(await evaluate("mistakesProtocol==='legacy'"), 'OFF capability is legacy');
  await evaluate('selectQ(7901)');
  await until("currentMistake && currentMistake.question_id===7901 && currentProblem && !solved && !answering", 'legacy board');
  check(await evaluate("typeof currentMistake.content==='string' && currentMistake.content.includes('B[aa]') && !currentMistake.board_only"),
        'OFF legacy list has the legacy content');
  await clickPoint(0, 0);
  await until("!answering && currentNode && currentNode.children.length===1", 'legacy reply');
  await clickPoint(2, 2);
  await until("solved", 'legacy solved');
  await pause(1500);
  const offRequests = requests.slice(before).map(r => r.url);
  check(!offRequests.some(u => u.includes('/api/g076/mistakes/attempt') || u.includes('/api/g076/mistakes/steps')),
        'OFF never uses the step routes', offRequests);
  check(offRequests.some(u => u.endsWith('/api/srs/review')), 'OFF legacy page submits the legacy review', offRequests);
  const off = await effects(9103);
  check(off.review_log === 1 && off.mistakes_reviews === 0 && off.step_events === 0 &&
        off.mistake_log[0].correct_after === 0, 'OFF legacy public review: scheduling only, as before', off);
  check(errors.length === 0, 'no uncaught page exceptions', errors);
  await fs.writeFile(path.join(out, 'mistakes-dom-off.html'), await evaluate('document.documentElement.outerHTML'));
  result = {status: 'PASS', checks: checks.length, real_chrome: true, real_http: true, real_pg16: true,
            original_mistakes_html: true, production_writes: 0, effects: {done, lost, wrong, off}, checks_detail: checks,
            off_requests: offRequests};
} catch (e) {
  result = {status: 'FAIL', checks: checks.length, error: e.stack, errors, checks_detail: checks};
  if (ws?.readyState === WebSocket.OPEN) {
    try { await fs.writeFile(path.join(out, 'failure.png'), Buffer.from((await send('Page.captureScreenshot')).data, 'base64')); } catch {}
  }
  process.exitCode = 1;
} finally {
  console.log(JSON.stringify(result, null, 2));
  await fs.writeFile(path.join(out, 'result.json'), JSON.stringify(result, null, 2));
  if (ws?.readyState === WebSocket.OPEN) { try { await send('Browser.close'); } catch {} ws.close(); }
  chrome.kill(); await pause(300);
  if (!profile.startsWith(out + path.sep)) throw new Error('Unsafe Chrome cleanup');
  await fs.rm(profile, {recursive: true, force: true, maxRetries: 10, retryDelay: 200}).catch(() => {});
}
