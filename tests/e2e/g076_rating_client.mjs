/* Executable client contract tests; Node VM is NOT real Chrome/PG evidence. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const code=fs.readFileSync('js/game/g076_rating_step_client.js','utf8');
let checks=0;
function check(value){assert.ok(value);checks++;}
function client(fetch){
  const context=vm.createContext({window:{},fetch});
  vm.runInContext(code,context);
  return context.window.G076Rating;
}
for(const mode of ['steps','legacy']) {
  let args;
  const api=client(async (...a)=>{args=a;return {ok:true,json:async()=>({mode})};});
  check(await api.mode()===mode);
  check(args[0]==='/api/g076/rating/capability');
  check(args[1].credentials==='include' && args[1].cache==='no-store');
}
for(const response of [
  {ok:false,json:async()=>({mode:'hold'})},
  {ok:true,json:async()=>({mode:'hold'})},
  {ok:false,json:async()=>{throw new Error('404 HTML');}},
]) {
  await assert.rejects(client(async()=>response).mode());checks++;
}
let calls=[];
const api=client(async (url,options)=>{
  calls.push([url,options]);
  if(calls.length===1) throw new Error('lost committed response');
  return {ok:true,json:async()=>({status:'CORRECT'})};
});
const body={session_id:'sid',attempt_id:'attempt',nonce:'nonce',action:'move',move:{x:0,y:0}};
check((await api.post('/api/g076/rating/step',body,1)).status==='CORRECT');
check(calls.length===2 && JSON.stringify(calls[0][1])===JSON.stringify(calls[1][1]));
check(calls[0][1].body===JSON.stringify(body));
check(!calls[0][1].body.includes('correct'));
let failures=0;
await assert.rejects(client(async()=>{failures++;throw new Error('offline');}).post('/step',body,1));
check(failures===2);
const html=fs.readFileSync('rating_test.html','utf8');
const inline=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(x=>x[1]).filter(Boolean);
for(const script of inline) {new vm.Script(script);checks++;}
new vm.Script(code);checks++;
const click=html.slice(html.indexOf('function onBoardClick'),html.indexOf('// ── Timer'));
check(click.indexOf('ratingSecureStep')<click.indexOf('_currentNode.children'));
const submit=html.slice(html.indexOf('async function submitMove'),html.indexOf('// ── Result rendering'));
check(submit.indexOf('if (_curQ?.step)')<submit.indexOf("fetch('/api/rating_test/answer'"));
check(html.includes("secureMode === 'steps' ? {trigger:"));
// Execute the actual page start function with inert DOM/layout effects.
const startFunction=html.slice(html.indexOf('async function startTest()'),html.indexOf('function loadTestQuestion(q)'));
for(const secureMode of ['legacy','steps']) {
  let sent;
  const elements=new Map();
  const context=vm.createContext({
    G076Rating:{mode:async()=>secureMode},
    document:{getElementById:id=>{if(!elements.has(id))elements.set(id,{});return elements.get(id);}},
    sessionStorage:{setItem:()=>{}},
    fetch:async(url,options)=>{sent={url,body:JSON.parse(options.body)};return {json:async()=>({
      session_id:'fixture',question:secureMode==='steps'?{step:{}}:{},cur_rating:1500,
    })};},
    console,alert:()=>{},I18n:{t:k=>k},
    _isPlacement:false,_placementInitElo:0,_selfFillElo:0,_knownInitElo:1999,
    _ratingStorageKey:'fixture',_recentQuestionIds:()=>[1,2],
    updateRatingUI:()=>{},showScreen:()=>{},requestAnimationFrame:()=>{},showRatingHold:()=>{throw new Error('unexpected HOLD');},
  });
  vm.runInContext(startFunction,context);
  await vm.runInContext('startTest()',context);
  check(sent.url===(secureMode==='steps'?'/api/g076/rating/start':'/api/rating_test/start'));
  assert.deepEqual(sent.body,secureMode==='steps'?{trigger:'manual'}:{trigger:'manual',init_elo:1999,exclude_question_ids:[1,2]});checks++;
}
// A board-only step can route without any client answer tree at all.
let clicked;
const clickContext=vm.createContext({_curQ:{step:{}},_answered:false,_testSolved:false,_testAnswering:false,
  _ox:x=>x+2,_oy:y=>y+3,ratingSecureStep:(action,move)=>{clicked={action,...move};}});
vm.runInContext(click,clickContext);
vm.runInContext('onBoardClick(1,2)',clickContext);
assert.deepEqual(clicked,{action:'move',x:3,y:5});checks++;
console.log(JSON.stringify({status:'PASS',checks,scope:'Node VM client/syntax only',python:false,chrome:false,postgres:false},null,2));
