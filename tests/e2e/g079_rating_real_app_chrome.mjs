/* G079 C: real headless Chrome + ORIGINAL rating_test.html + REAL app.py routes
   + disposable PostgreSQL. Launched by tests/e2e/g079_rating_real_app_server.py
   (G079_BASE). Timeouts use REAL server deadlines (25 s timers), no clock fakes.
   /fixture/* routes are the server-side test oracle described in that file. */
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';

const base = process.env.G079_BASE;
assert.ok(base && base.startsWith('http://127.0.0.1:'), 'loopback base required');
const out = process.env.G079_EVIDENCE_DIR || path.join(os.tmpdir(), 'g079-c-chrome');
await fs.mkdir(out, {recursive: true});
const runDir = await fs.mkdtemp(path.join(os.tmpdir(), 'g079-c-chrome-'));
const profile = path.join(runDir, 'profile');
const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--disable-extensions', '--disable-background-networking', '--disable-component-update', '--disable-sync',
  '--no-proxy-server', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
  '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
  '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank',
], {windowsHide: true, stdio: ['ignore', 'ignore', 'pipe']});
let chromeStderr = '';
chrome.stderr.on('data', c => { chromeStderr += c.toString(); });
let spawnError; chrome.on('error', e => { spawnError = e; });
const pause = ms => new Promise(r => setTimeout(r, ms));
let ws, seq = 0, checks = 0, result;
const pending = new Map(), errors = [], log = [];
function check(value, message) { assert.ok(value, message); checks++; log.push('PASS ' + message); }
function send(method, params = {}) {
  const id = ++seq;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP timeout ' + method)); }, 60000);
    pending.set(id, {resolve: v => { clearTimeout(timer); resolve(v); }, reject: e => { clearTimeout(timer); reject(e); }});
    ws.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const v = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (v.exceptionDetails) throw new Error(v.exceptionDetails.exception?.description || v.exceptionDetails.text);
  return v.result.value;
}
async function until(expression, seconds = 20) {
  for (let i = 0; i < seconds * 10; i++) { if (await evaluate(expression)) return; await pause(100); }
  throw new Error('Timeout: ' + expression + ' :: ' + await evaluate('document.body.innerText.slice(-600)'));
}
const get = p => evaluate(`fetch(${JSON.stringify(p)},{credentials:'include'}).then(r=>r.json())`);
const post = (p, b) => evaluate(`fetch(${JSON.stringify(p)},{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify(b)})}).then(async r=>({status:r.status,data:await r.json()}))`);
async function click(x, y) {
  await evaluate('_board.element.scrollIntoView({block:"center"})'); await pause(80);
  const point = await evaluate(`(()=>{const r=_board.element.getBoundingClientRect();return {x:r.left+_board.getX(_bx(${x})),y:r.top+_board.getY(_by(${y}))};})()`);
  await send('Input.dispatchMouseEvent', {type: 'mousePressed', button: 'left', clickCount: 1, ...point});
  await send('Input.dispatchMouseEvent', {type: 'mouseReleased', button: 'left', clickCount: 1, ...point});
}
async function login(name, pagePath) {
  await send('Page.navigate', {url: base + '/try'});
  await until('document.readyState==="complete"');
  const cred = await get('/fixture/credentials/' + name);
  const r = await post('/api/auth/login', {username: cred.username, password: cred.password});
  check(r.status === 200 && r.data.ok === true, name + ' real /api/auth/login');
  await send('Page.navigate', {url: base + pagePath});
  await until('typeof G076Rating!=="undefined" && typeof startTest==="function" && document.readyState==="complete"');
  return cred.uid;
}
async function begin() {
  await evaluate('stopTimer();sessionStorage.clear();_sid=null;_round=0;_answers=[];startTest()');
  await until('Boolean(_curQ?.step) && _curQ.step.index===0 && Boolean(_board) && !_testAnswering && Boolean(document.querySelector("#board canvas, canvas"))');
  check(await evaluate('_currentNode===null && parseSGF(_curQ.content).tree===null && !("token" in _curQ) && !("accepted_moves" in _curQ)'),
        'steps payload is board-only (no answer tree/token/accepted moves)');
  return evaluate('_sid');
}
const solution = sid => get('/fixture/solution/' + sid).then(s => s.moves);
const effects = sid => get('/fixture/effects' + (sid ? '?sid=' + sid : ''));
async function terminalRound(kind, sid) {
  const round = await evaluate('_round');
  const receiptIndex = await evaluate('__ratingReceipts.length');
  const m = await solution(sid);
  if (kind === 'correct') {
    await click(m[0].x, m[0].y);
    await until('_curQ.step.index===1 && !_testAnswering');
    await click(m[1].x, m[1].y);
  } else if (kind === 'wrong') {
    await click(m[1].x, m[1].y);  // legal but not the first correct move
  } else if (kind === 'give_up') {
    await evaluate('document.getElementById("btn-skip").click()');
  } else if (kind === 'timeout' || kind === 'partial_timeout') {
    if (kind === 'partial_timeout') { await click(m[0].x, m[0].y); await until('_curQ.step.index===1 && !_testAnswering'); }
    // Real wait: the page's own timer fires submitMove at the server deadline.
  } else if (kind === 'late_move') {
    await evaluate('stopTimer()');  // a client whose timer never fired
    const wait = await evaluate('(_curQ.step.deadline-_curQ.step.server_now)');
    await pause(wait * 1000 + 2500);
    await click(m[0].x, m[0].y);   // the CORRECT first move, but after the deadline
  }
  const secs = kind.includes('timeout') ? 75 : 25;
  await until(`(_round===${round + 1} && _curQ?.step?.index===0 && !_testAnswering) || !document.getElementById('screen-result').classList.contains('hidden') || !document.getElementById('screen-placement-result').classList.contains('hidden')`, secs);
  const receipts = await evaluate(`__ratingReceipts.slice(${receiptIndex})`);
  const terminal = receipts.filter(r => r.data.status !== 'CONTINUE');
  check(terminal.length >= 1, kind + ' terminal server receipt');
  const t = terminal[0].data;
  check(t.status === (kind === 'correct' ? 'CORRECT' : 'INCORRECT'), kind + ' server verdict ' + t.status);
  if (kind === 'late_move' || kind === 'timeout' || kind === 'give_up') check(t.played.length === 0, kind + ' no fabricated or late move recorded');
  if (kind === 'partial_timeout') check(t.played.length === 2, kind + ' only committed history kept');
  check(!receipts.some(r => 'correct' in r.body || 'moves' in r.body), kind + ' browser sent no verdict/history');
  return t;
}

try {
  let port;
  for (let i = 0; i < 100; i++) {
    if (spawnError) throw spawnError;
    try { port = Number((await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break; } catch {}
    await pause(100);
  }
  assert.ok(port, 'Chrome debugger ready');
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {method: 'PUT'})).json();
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  ws.onmessage = event => {
    const v = JSON.parse(event.data);
    if (v.id) { const p = pending.get(v.id); if (p) { pending.delete(v.id); v.error ? p.reject(new Error(JSON.stringify(v.error))) : p.resolve(v.result); } }
    if (v.method === 'Runtime.exceptionThrown') errors.push(v.params.exceptionDetails.exception?.description || v.params.exceptionDetails.text);
  };
  await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable');
  await send('Page.addScriptToEvaluateOnNewDocument', {source: `
    window.__ratingDoc=crypto.randomUUID();window.__ratingReceipts=[];
    const originalFetch=window.fetch.bind(window);
    window.fetch=async(...args)=>{
      const r=await originalFetch(...args);
      if(String(args[0])==='/api/g076/rating/step'){
        window.__ratingReceipts.push({body:JSON.parse(args[1].body),data:await r.clone().json()});
        if(window.__loseRatingResponse){window.__loseRatingResponse=false;throw new Error('lost response after server commit');}
      }
      return r;
    };`});

  // ── A: desktop, formal manual trial to completion ──────────────────────
  await send('Emulation.setDeviceMetricsOverride', {width: 1400, height: 1100, deviceScaleFactor: 1, mobile: false});
  const uidA = await login('g079chrome_a', '/rating_test');
  check(await evaluate('G076Rating.mode()') === 'steps', 'server capability ON -> steps');
  let sid = await begin();
  let m = await solution(sid);
  await click(m[0].x, m[0].y);
  await until('_curQ.step.index===1 && !_testAnswering');
  check(await evaluate('_curQ.step.played.length===2'), 'committed opponent reply rendered');
  check((await effects(sid)).responses.length === 0, 'CONTINUE step settles nothing');
  const before = await evaluate('JSON.stringify(_curQ.step)');
  const prevDoc = await evaluate('window.__ratingDoc');
  await send('Page.reload');
  await until(`window.__ratingDoc!==${JSON.stringify(prevDoc)} && typeof _curQ!=='undefined' && _curQ?.step?.index===1 && Boolean(_board)`);
  check(await evaluate(`JSON.parse(${JSON.stringify(before)}).nonce===_curQ.step.nonce && _curQ.step.played.length===2`), 'refresh mid-question resumes same nonce and committed stones');
  await evaluate('window.__loseRatingResponse=true');
  await click(m[1].x, m[1].y);
  await until('_round===1 && _curQ?.step?.index===0 && !_testAnswering');
  check(await evaluate('__ratingReceipts.length===2 && JSON.stringify(__ratingReceipts[0].body)===JSON.stringify(__ratingReceipts[1].body) && JSON.stringify(__ratingReceipts[0].data)===JSON.stringify(__ratingReceipts[1].data)'),
        'lost response -> identical retry, identical receipt');
  let fx = await effects(sid);
  check(fx.responses.length === 1 && fx.responses[0].correct === 1, 'one settlement for retried round (correct=1)');
  const plan = ['give_up', 'wrong', 'correct', 'give_up', 'correct', 'wrong', 'correct', 'give_up', 'correct', 'correct', 'wrong', 'correct', 'give_up', 'correct', 'correct'];
  let rounds = 1, last;
  for (const kind of plan) {
    last = await terminalRound(kind, sid);
    rounds++;
    fx = await effects(sid);
    check(fx.responses.length === rounds, `round ${rounds}: exactly ${rounds} settlements`);
    if (fx.sessions.find(s => s.id === sid).status === 'completed') break;
  }
  await until('!document.getElementById("screen-result").classList.contains("hidden") && document.getElementById("res-elo").textContent.trim()!==""', 20);
  fx = await effects(sid);
  const sessA = fx.sessions.find(s => s.id === sid), userA = fx.users.find(u => u.id === uidA);
  check(sessA.status === 'completed' && sessA.round === rounds, 'manual session completed after ' + rounds + ' rounds');
  check(userA.elo_rating === sessA.cur_rating, 'account Elo written = final server rating');
  check(String(Math.round(sessA.cur_rating)) === (await evaluate('document.getElementById("res-elo").textContent.trim()')), 'result screen shows server Elo');
  const finalBody = (await evaluate('__ratingReceipts')).filter(r => r.data.status !== 'CONTINUE').pop();
  const replay = await post('/api/g076/rating/step', finalBody.body);
  const fx2 = await effects(sid);
  check(replay.status === 200 && JSON.stringify(replay.data) === JSON.stringify(finalBody.data), 'post-finish retry returns stored receipt');
  check(JSON.stringify(fx2) === JSON.stringify(fx), 'post-finish retry changes nothing (Elo/stats once)');
  const legacy = await post('/api/rating_test/answer', {session_id: sid, correct: true, moves: [], question_id: 1, question_token: 'x'});
  check(legacy.status === 503 && legacy.data.error === 'rating_steps_required', 'legacy answer route fails closed under ON');
  check(JSON.stringify(await effects(sid)) === JSON.stringify(fx), 'legacy bypass attempt wrote nothing');
  await fs.writeFile(path.join(out, 'chrome-A-result-1400.png'), Buffer.from((await send('Page.captureScreenshot')).data, 'base64'));

  // ── B: mobile placement with real timeouts/forfeit/late move ───────────
  await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
  const uidB = await login('g079chrome_b', '/rating_test?placement=1');
  sid = await begin();
  check(await evaluate('_board.element.getBoundingClientRect().width<=innerWidth'), 'mobile board fits viewport');
  await fs.writeFile(path.join(out, 'chrome-B-question-390.png'), Buffer.from((await send('Page.captureScreenshot')).data, 'base64'));
  const kinds = ['timeout', 'partial_timeout', 'late_move', 'give_up', 'correct', 'wrong', 'correct'];
  rounds = 0;
  for (const kind of kinds) {
    await terminalRound(kind, sid);
    rounds++;
    fx = await effects(sid);
    check(fx.responses.length === rounds, `placement round ${rounds} (${kind}): exactly ${rounds} settlements`);
  }
  await until('!document.getElementById("screen-placement-result").classList.contains("hidden")', 20);
  fx = await effects(sid);
  const sessB = fx.sessions.find(s => s.id === sid), userB = fx.users.find(u => u.id === uidB);
  check(JSON.stringify(fx.responses.map(r => r.correct)) === JSON.stringify([0, 0, 0, 0, 1, 0, 1]), 'placement verdicts are server-side: ' + fx.responses.map(r => r.correct).join(''));
  check(sessB.status === 'completed' && userB.elo_rating === sessB.cur_rating && userB.elo_provisional === 1, 'placement Elo once, provisional');
  check(fx.unlocks.some(u => u.user_id === uidB && u.source === 'placement_test'), 'placement unlock on same transaction');
  check(fx.mistakes.filter(x => x.user_id === uidB).length === 5, 'mistake_log rows = 5 wrong rounds');
  await fs.writeFile(path.join(out, 'chrome-B-placement-390.png'), Buffer.from((await send('Page.captureScreenshot')).data, 'base64'));

  // ── C: Rating OFF still works (legacy path, original client tree) ──────
  await post('/fixture/flags', {rating: 'off', privacy: 'off'});
  await send('Emulation.setDeviceMetricsOverride', {width: 1400, height: 1100, deviceScaleFactor: 1, mobile: false});
  const uidC = await login('g079chrome_c', '/rating_test');
  check(await evaluate('G076Rating.mode()') === 'legacy', 'server capability OFF -> legacy');
  const eventsBefore = (await effects()).events;
  await evaluate('stopTimer();sessionStorage.clear();_sid=null;_round=0;_answers=[];startTest()');
  await until('Boolean(_curQ) && !_curQ.step && Boolean(_board) && Boolean(_currentNode)');
  check(await evaluate('parseSGF(_curQ.content).tree!==null && typeof _curQ.token==="string"'), 'legacy payload unchanged (tree + token)');
  sid = await evaluate('_sid');
  m = await solution(sid);
  await click(m[0].x, m[0].y);
  await pause(900);
  await click(m[1].x, m[1].y);
  await until('_round===1', 20);
  fx = await effects(sid);
  check(fx.responses.length === 1 && fx.responses[0].correct === 1 && fx.responses[0].user_id === uidC, 'legacy answer judged by server once');
  check(fx.events === eventsBefore, 'OFF writes no step-ledger events');
  await post('/fixture/flags', {rating: 'on', privacy: 'off'});
  check(errors.length === 0, 'no uncaught page exceptions: ' + errors.join(' | '));
  result = {status: 'PASS', checks, base, real_chrome: true, original_rating_page: true,
            backend: 'REAL_APP_PY_FLASK + DISPOSABLE_POSTGRESQL', log};
} catch (error) {
  result = {status: 'FAIL', checks, error: error.stack, errors, log, chromeStderr: chromeStderr.slice(-2000)};
  process.exitCode = 1;
} finally {
  try { ws?.close(); } catch {}
  chrome.kill();
  await fs.writeFile(path.join(out, 'chrome-result.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify({status: result.status, checks: result.checks, error: result.error?.split('\n').slice(0, 3)}, null, 2));
}
