import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const index=fs.readFileSync(path.join(root,'index.html'),'utf8');
const head=index.indexOf('async function _g076StepOnBoardClick(x, y)');
const tail=index.indexOf('// ─── 點棋盤',head);
assert.ok(head>0 && tail>head);
const isolatedSource=index.slice(head,tail);
const checks=[];
function check(name,fn){checks.push([name,fn]);}

function fixture(client) {
  const events=[];
  const question={id:69853},state={attemptId:'isolated-a69853'};
  const context=vm.createContext({
    _g076StepUseServer:true,_g076StepClient:client,
    _g076UnconfirmedMove:null,_mapBattleV1IsActive:()=>true,
    _mapBattleV1State:state,_mapBattleV1LifecycleGeneration:8,
    _mapBattleV1Moves:[],currentQ:question,playerColor:'B',
    answering:false,solved:false,window:{},
    playStone:(x,y,c)=>{events.push(['stone',x,y,c]);return true;},
    _blockAdventureProgression:s=>events.push(['BLOCKED',s]),
    setMsg:(msg,level)=>events.push(['message',msg,level]),
    I18n:{t:s=>s},
    _e10AcceptanceTrace:(kind)=>events.push(['trace',kind]),
    _submitMapBattleV1IfActive:async(moves,result)=>{
      events.push(['settled',moves.length,result.result]);
    }
  });
  vm.runInContext(isolatedSource,context);
  return {context,events,question,state};
}

check('real index inline scripts parse as JavaScript',()=>{
  const list=[...index.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];
  const main=list.find(m=>m[2].includes('async function _g076StepOnBoardClick'));
  assert.ok(main,'real gameplay inline script missing');
  new vm.Script(main[2],{filename:'real-index-main-script'});
  assert.match(index,/g076_authoritative_step_client\.js\?v=20261023r3a/);
});
check('initial move is server adjudicated; no local solution guess',async()=>{
  const remote={
    status:'CONTINUE',step_index:1,
    opponent_reply:[1,1],next_step_nonce:'n1'
  };
  const f=fixture({play:async(x,y)=>{
    f.events.push(['rpc',x,y]);
    return remote;
  }});
  await f.context._g076StepOnBoardClick(0,0);
  assert.deepEqual(f.events.filter(e=>e[0]==='rpc'),[['rpc',0,0]]);
  assert.deepEqual(f.events.filter(e=>e[0]==='stone'),[
    ['stone',0,0,'B'],['stone',1,1,'W']
  ]);
  assert.equal(f.events.filter(e=>e[0]==='settled').length,0);
  assert.equal(f.context.solved,false);
  assert.equal(f.context.answering,false);
});
check('terminal settlement reuses Map Battle UI once with server evidence',async()=>{
  const result={
    status:'CORRECT',
    battle_settlement:{accepted:true,result:'CORRECT',monster_hp:23}
  };
  const f=fixture({play:async()=>result});
  await f.context._g076StepOnBoardClick(5,9);
  assert.deepEqual(f.events.filter(e=>e[0]==='stone'),[['stone',5,9,'B']]);
  assert.deepEqual(f.events.filter(e=>e[0]==='settled'),[
    ['settled',0,'CORRECT']
  ]);
  assert.equal(f.context.solved,true);
});
check('network timeout permits retry only of identical coordinate',async()=>{
  let submissions=0;
  const f=fixture({
    play:async()=>{submissions++;throw new Error('network timeout');},
    retrySameStep:async()=>{submissions++;return {
      status:'INCORRECT',opponent_reply:null,
      battle_settlement:{accepted:true,result:'INCORRECT'}
    }}
  });
  await f.context._g076StepOnBoardClick(5,9);
  assert.equal(f.context._g076UnconfirmedMove.retry,true);
  await f.context._g076StepOnBoardClick(2,2);
  assert.equal(submissions,1);
  await f.context._g076StepOnBoardClick(5,9);
  assert.equal(submissions,2);
  assert.deepEqual(f.events.filter(e=>e[0]==='settled'),[
    ['settled',0,'INCORRECT']
  ]);
});
check('rejected nonce blocks and never paints a stone',async()=>{
  const f=fixture({play:async()=>{const err=new Error('forbidden');
    err.status=403;err.code='step_nonce_invalid';throw err;}});
  await f.context._g076StepOnBoardClick(5,9);
  assert.equal(f.events.filter(e=>e[0]==='stone').length,0);
  assert.equal(f.events.filter(e=>e[0]==='BLOCKED').length,1);
});
check('stale question switch suppresses async visual settlement',async()=>{
  let finish;
  const future=new Promise(resolve=>finish=resolve);
  const f=fixture({play:()=>future});
  const work=f.context._g076StepOnBoardClick(5,9);
  f.context.currentQ={id:2000};
  finish({status:'CORRECT',battle_settlement:{accepted:true,result:'CORRECT'}});
  await work;
  assert.equal(f.events.filter(e=>e[0]==='stone').length,0);
  assert.equal(f.events.filter(e=>e[0]==='settled').length,0);
});
check('legacy decision remains untouched when G076 server flag OFF',()=>{
  const boardHead=index.indexOf('function onBoardClick(bx,by)');
  const boardEnd=index.indexOf('function resetProblem()',boardHead);
  assert.ok(boardHead>0 && boardEnd>boardHead);
  const source=index.slice(boardHead,boardEnd);
  assert.match(source,/_g076StepUseServer && _mapBattleV1IsActive\(\)/);
  assert.match(source,/const matched=currentNode\.children\.find/);
  assert.ok(source.indexOf('_g076StepOnBoardClick(x,y)')
    <source.indexOf('currentNode.children.find'));
});
check('secure board load cannot reuse previously cached full SGF',()=>{
  assert.match(index,/\/api\/question\/\$\{encodeURIComponent\(q.id\)\}\?view=board/);
  assert.match(index,/delete q\.native_answer;/);
  assert.match(index,/delete q\.solution;/);
  assert.match(index,/safe\?\.board_only !== true/);
  assert.match(index,/g076_capability_unavailable/);
  assert.match(index,/g076_step_resume_not_ready/);
});
check('secure flow never calls legacy submit without settlement',()=>{
  assert.match(index,/if \(_g076StepUseServer && !settledResponse\) return null;/);
  assert.match(index,/adapter\.applyAuthoritativeState\(submittedState, response\)/);
  assert.match(index,/await _submitMapBattleV1IfActive\(\[\], verdict\.battle_settlement\)/);
});
check('hints, answer reveal, reset fail closed for server steps',()=>{
  assert.match(index,/function resetProblem\(\)\{\s*if \(_g076StepUseServer/);
  assert.match(index,/function showAnswer\(\)\{\s*if \(_g076StepUseServer/);
  assert.match(index,/async function useHintTicket\(\)\{\s*if \(_g076StepUseServer/);
});
check('true gameplay onBoardClick dispatches to server before SGF matching',async()=>{
  const start=index.indexOf('function onBoardClick(bx,by)');
  const end=index.indexOf('function resetProblem()',start);
  assert.ok(start>0 && end>start);
  const seen=[];
  const ctx=vm.createContext({
    _ox:x=>x,_oy:y=>y,window:{SGFReportWidget:null},
    _questionBoardFailedClosed:false,answering:false,
    currentNode:{children:[{move:{x:0,y:0}}]},
    logicBoard:[],_koPoint:null,playerColor:'B',
    _wouldBeSuicide:()=>false,_g076StepUseServer:true,
    _mapBattleV1IsActive:()=>true,
    _g076StepOnBoardClick:async(x,y)=>seen.push([x,y]),
  });
  vm.runInContext(index.slice(start,end),ctx);
  ctx.onBoardClick(5,9);
  await Promise.resolve();
  assert.deepEqual(seen,[[5,9]]);
});
check('server-confirmed presentation error cannot reuse consumed nonce',async()=>{
  const f=fixture({play:async()=>({
    status:'CORRECT',
    battle_settlement:{accepted:true,result:'CORRECT'}
  })});
  vm.runInContext('_submitMapBattleV1IfActive=async()=>{throw Error("UI unavailable")}',f.context);
  await f.context._g076StepOnBoardClick(5,9);
  assert.equal(f.events.filter(e=>e[0]==='BLOCKED').length,1);
  assert.equal(f.context._g076UnconfirmedMove,null);
});
check('real Flask source explicitly serves the required adapter script',()=>{
  const app=fs.readFileSync(path.join(root,'app.py'),'utf8');
  assert.match(app,/def serve_g076_authoritative_step_client_js\(\)/);
  assert.match(app,/def g076_map_battle_step_capability\(\)/);
  assert.match(app,/G076_STEP_RUNTIME_ENABLED/);
});
let count=0;
for(const [name,fn] of checks){
  await fn();
  count++;
  console.log('PASS',name);
}
console.log('G076_R3_REAL_INDEX_ADAPTER',count,'PASS / 0 FAIL');
