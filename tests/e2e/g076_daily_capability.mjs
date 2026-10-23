/* Executes the actual page's capability + onload code; no browser/DB claim. */
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import crypto from 'node:crypto';
const html=fs.readFileSync('daily_challenge.html','utf8');
const start=html.indexOf('async function selectDailyProtocol()');
const end=html.indexOf('\n// ═',html.indexOf('window.onload = async',start));
assert.ok(start>0 && end>start);
const source=html.slice(start,end);
let checks=0;
const check=(ok,msg)=>{assert.ok(ok,msg);checks++;};
async function run(reply, throws=false) {
  const calls=[], boxes={}; let release;
  const pending=new Promise(resolve=>release=resolve);
  const scope={AbortController, setTimeout, clearTimeout,
    document:{getElementById:id=>boxes[id]??=( {dataset:{},style:{}} )},
    location:{replace:p=>calls.push(['replace',p])},
    window:{}, I18n:{renderSwitcher(){},apply(){}},
    rotateNoraLine(){}, loadNavAvatar(){calls.push(['avatar']);},
    startCountdown(){}, loadToday(){calls.push(['today']);},
    loadHistory(){calls.push(['history']);},
    fetch:async (url,options)=>{
      calls.push([url,options]);
      if(url==='/api/auth/me') return {json:async()=>({logged_in:true})};
      await pending;
      if(throws) throw new Error('network down');
      return reply;
    }};
  vm.createContext(scope);vm.runInContext(source,scope);
  const loading=scope.window.onload();
  check(calls.length===1 && calls[0][0]==='/api/g076/daily/capability','no racing history, auth or new Daily request');
  check(calls[0][1].credentials==='same-origin' && calls[0][1].cache==='no-store' && calls[0][1].redirect==='error','authenticated noncached transport with no redirected login trust');
  release();await loading;
  return {calls,boxes};
}
for(const status of [401,409,503]) {
  const {calls,boxes}=await run({ok:false,status,json:async()=>({mode:'legacy'})});
  check(calls.length===1 && boxes['loading-state'].dataset.reason==='daily_capability_blocked','HTTP '+status+' cannot fail open');
}
for(const body of [{},null,{mode:'hold'},{mode:'LEGACY'},{mode:'legacy',enabled:true}]) {
  const {calls,boxes}=await run({ok:true,json:async()=>body});
  if(body?.mode==='legacy') check(calls[1]?.[1]==='/daily_challenge_legacy.html' && calls.length===2,'fixed same-origin bounded redirect');
  else check(calls.length===1 && boxes['loading-state'].dataset.reason==='daily_capability_blocked','unknown mode blocks');
}
let r=await run(null,true);
check(r.calls.length===1 && r.boxes['main-content'].style.display==='none','network failure blocks');
r=await run({ok:true,json:async()=>{throw new SyntaxError('bad json');}});
check(r.calls.length===1 && r.boxes['loading-state'].dataset.reason==='daily_capability_blocked','malformed response blocks');
r=await run({ok:true,json:async()=>({mode:'steps'})});
check(r.calls.some(c=>c[0]==='today') && r.calls.some(c=>c[0]==='history') && !r.calls.some(c=>c[0]==='replace'),'steps retains original initialization');
// Exercise the real abort deadline without waiting eight seconds in a unit test.
{
  let aborted=false;
  const boxes={'loading-state':{dataset:{}},'main-content':{style:{}}};
  const scope={AbortController,clearTimeout(){},setTimeout(fn,ms){check(ms===8000,'bounded timeout');queueMicrotask(fn);return 1;},
    fetch:async(url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>{aborted=true;reject(new Error('aborted'));})),
    document:{getElementById:id=>boxes[id]},window:{},location:{replace(){throw new Error('timeout redirected');}}};
  vm.createContext(scope);vm.runInContext(source,scope);
  check(await scope.selectDailyProtocol()===false && aborted && boxes['loading-state'].dataset.reason==='daily_capability_blocked','timeout blocks with no redirect');
}
const legacy=fs.readFileSync('daily_challenge_legacy.html');
for(const [name,text] of [['daily_challenge.html',html],['daily_challenge_legacy.html',legacy.toString('utf8')]]) {
  for(const match of text.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
    new vm.Script(match[1],{filename:name});
  }
  check(true,'all inline scripts compile '+name);
}
const originalLegacy=execFileSync('git',['show','b39b3548:daily_challenge.html']);
const newGuard=Buffer.from(`      // The old header may be omitted by responsive/template variants.
      // Never turn a committed XP/badge award into a misleading submit-failed UI.
      const participantWrap = document.getElementById('hdr-participants-wrap');
      const participantCount = document.getElementById('hdr-participants');
      if (participantWrap) participantWrap.style.display = '';
      if (participantCount) participantCount.textContent = stats.total;`);
const oldHeader=Buffer.from(`      document.getElementById('hdr-participants-wrap').style.display = '';
      document.getElementById('hdr-participants').textContent = stats.total;`);
check(legacy.includes(newGuard) && legacy.subarray(0).toString().replace(newGuard.toString(),oldHeader.toString())===originalLegacy.toString(),'legacy differs from original only by bounded post-settlement header null guard');
check(!legacy.includes(Buffer.from('g076/daily/')),'legacy contains no secure-step protocol call');
check(legacy.includes(Buffer.from('moves: submittedMoves')) && legacy.includes(Buffer.from('attempt_token: todayData?.attempt_token')),'actual SGF moves and signed attempt submitted');
const app=fs.readFileSync('app.py','utf8');
const submit=app.slice(app.indexOf('def dc_submit():'),app.indexOf('def dc_history():'));
check(submit.indexOf('if replay is not None:')<submit.indexOf("if mode != 'legacy':") && submit.indexOf("if mode != 'legacy':")<submit.indexOf('judge_daily_answer('),'exact replay precedes new admission and real judge');
check(app.includes("@app.route('/daily_challenge_legacy.html')\n@login_required") && app.includes("_serve_live_static_or_baked('daily_challenge_legacy.html')"),'authenticated explicit static route');
const manifest=JSON.parse(fs.readFileSync('deploy/build-manifest.json','utf8'));
const docker=fs.readFileSync('Dockerfile','utf8');
for(const name of ['g076_daily_capability.py','daily_challenge_legacy.html']) {
  check(manifest.build_inputs.tracked_in_canonical_branch_this_sprint.filter(n=>n===name).length===1,'tracked packaging '+name);
  check(manifest.post_build_verification_files.filter(n=>n==='/app/'+name).length===1,'baked verification '+name);
  check(docker.includes(name),'Docker copy includes '+name);
}
console.log(JSON.stringify({status:'PASS',checks,kind:'actual inline JS in Node VM plus source/packaging assertions',legacy_sha256:crypto.createHash('sha256').update(legacy).digest('hex'),real_chrome:false,real_http:false},null,2));
