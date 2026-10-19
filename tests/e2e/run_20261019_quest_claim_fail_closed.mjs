// Executes the REAL curriculum.html claimRewards implementation in a local
// isolated DOM/HTTP harness; never contacts production or grants coins.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const html=readFileSync(path.join(root,'curriculum.html'),'utf8');
const begin=html.indexOf('async function acceptQuest(');
const end=html.indexOf('\nfunction flyCoins(',begin);
assert(begin>=0 && end>begin,'must execute actual quest claim code');
const source=html.slice(begin,end);
assert(!source.includes('gained_coins: tc'),'false synthetic grant must be removed');
const results=[];
const baseline=()=>({accepted:['demo::LV1'],claimable:[{stage_key:'demo::LV1',coins:50,xp:20}],
  open_quests:[],quest_meta:[],coins:100,xp:200});
const confirmed=()=>({accepted:[],claimable:[],open_quests:[],quest_meta:[],coins:150,xp:220});
function response(payload,status=200){return {ok:status>=200 && status<300,status,
  json:async()=>structuredClone(payload)};}
function setup(mockRequests,preview=false) {
  let posts=0,gets=0,accepts=0,abandons=0,toasts=0,renders=0,animations=0,feedback='';
  const store={_questBoard:baseline(),location:{
    protocol:preview?'file:':'http:',search:preview?'?preview=1':''
  }};
  const statusRoot={prepend(node){this.note=node;}};
  store.document={
    getElementById(id) {if(id==='quest-board')return statusRoot;
      if(id==='quest-claim-feedback')return statusRoot.note||null;return null;},
    createElement(){return {setAttribute(){},style:{},isConnected:true};},
  };
  store.fetch=async (url,init={})=>{
    if(url==='/api/rewards/sync'){posts++;return mockRequests.post(posts);}
    if(url==='/api/quest-board/accept'){accepts++;return mockRequests.accept?.(accepts)??response({ok:true});}
    if(url==='/api/quest-board/abandon'){abandons++;return mockRequests.abandon?.(abandons)??response({ok:true});}
    if(url==='/api/quest-board'){gets++;return mockRequests.get(gets);}
    throw new Error('Unexpected request '+url);
  };
  store.URLSearchParams=URLSearchParams;
  store.confirm=()=>true;
  store.qbT=()=>'';
  store._isEnCur=()=>false;
  store.rerenderBoard=()=>{renders++;};
  store.flyCoins=()=>{animations++;};
  store.showRewardToast=()=>{toasts++;};
  store.npcCongrats=()=>{};
  store.countUpWallet=()=>{animations++;};
  const context=vm.createContext(store);
  vm.runInContext(source,context,{filename:'curriculum.html:claimRewards'});
  return {
    invoke:()=>vm.runInContext('claimRewards(null)',context),
    accept:(key,href=null)=>vm.runInContext('acceptQuest('+JSON.stringify(key)+','+JSON.stringify(href)+')',context),
    abandon:key=>vm.runInContext('abandonQuest('+JSON.stringify(key)+')',context),
    state:()=>structuredClone(context._questBoard),
    location:()=>structuredClone(context.location),
    stats:()=>({posts,gets,accepts,abandons,toasts,renders,animations,feedback:statusRoot.note?.textContent||''}),
  };
}
async function test(name,fn) {await fn();results.push({name,status:'PASS'});}
await test('network_error_before_commit_restores_server_authority_no_fake_coins',async()=>{
  const x=setup({post:async()=>{throw new Error('transport offline');},
    get:async()=>response(baseline())});
  await x.invoke();
  assert.deepEqual(x.state(),baseline());
  assert.deepEqual({posts:x.stats().posts,gets:x.stats().gets,toasts:x.stats().toasts},
    {posts:1,gets:1,toasts:0});
  assert.match(x.stats().feedback,/重新向伺服器讀取/);
});
await test('reply_lost_after_server_commit_rehydrates_real_wallet_once',async()=>{
  const x=setup({post:async()=>{throw new Error('HTTP reply lost after commit');},
    get:async()=>response(confirmed())});
  await x.invoke();
  assert.deepEqual(x.state(),confirmed());
  assert.equal(x.stats().posts,1);
  assert.equal(x.stats().toasts,0,'network failure cannot announce unverified rewards');
});
await test('http_500_and_failed_reconciliation_keeps_original_balance',async()=>{
  const x=setup({post:async()=>response({error:'temporary_failure'},500),
    get:async()=>{throw new Error('GET offline');}});
  await x.invoke();
  assert.deepEqual(x.state(),baseline());
  assert.equal(x.stats().animations,0);
  assert.match(x.stats().feedback,/畫面沒有假設已發獎/);
});
await test('malformed_http_200_payload_cannot_inflate_wallet',async()=>{
  const x=setup({post:async()=>response({granted:[],coins:999999,xp:999999}),
    get:async()=>response(baseline())});
  await x.invoke();
  assert.deepEqual(x.state(),baseline());
  assert.equal(x.stats().toasts,0);
});
await test('successful_verified_post_presents_only_server_granted_total',async()=>{
  const x=setup({post:async()=>response({granted:[{stage_key:'demo::LV1'}],
    gained_coins:50,gained_xp:20,coins:150,xp:220}),
    get:async()=>{throw new Error('no GET on success');}});
  await x.invoke();
  assert.equal(x.state().coins,150);
  assert.equal(x.state().xp,220);
  assert.deepEqual(x.state().claimable,[]);
  assert.equal(x.stats().toasts,1);
  assert.equal(x.stats().posts,1);
  assert.equal(x.stats().gets,0);
});
await test('simultaneous_double_click_posts_once',async()=>{
  let unblock;
  const paused=new Promise(resolve=>{unblock=resolve;});
  const x=setup({post:async()=>{await paused;return response({granted:[],
    gained_coins:0,gained_xp:0,coins:100,xp:200});},get:async()=>response(baseline())});
  const first=x.invoke();
  const second=x.invoke();
  assert.equal(x.stats().posts,1);
  unblock();
  await Promise.all([first,second]);
  assert.equal(x.stats().posts,1);
  assert.equal(x.stats().toasts,0);
});
await test('preview_never_calls_reward_write_api',async()=>{
  const x=setup({post:async()=>{throw new Error('MUST NOT CALL POST');},
    get:async()=>{throw new Error('MUST NOT CALL GET');}},true);
  await x.invoke();
  assert.equal(x.stats().posts,0);
  assert.equal(x.stats().gets,0);
  assert.deepEqual(x.state(),baseline());
});
await test('malformed_reconcile_snapshot_cannot_replace_state',async()=>{
  const x=setup({post:async()=>{throw new Error('network failure');},
    get:async()=>response({accepted:[],claimable:[],open_quests:[],coins:-200,xp:200})});
  await x.invoke();
  assert.deepEqual(x.state(),baseline());
  assert.equal(x.stats().toasts,0);
});
await test('quest_accept_http_500_does_not_optimistically_accept',async()=>{
  const x=setup({post:async()=>{throw new Error('no reward POST');},
    accept:async()=>response({error:'unavailable'},500),get:async()=>response(baseline())});
  await x.accept('new::LV2');
  assert.deepEqual(x.state(),baseline());
  assert.equal(x.stats().accepts,1);
  assert.match(x.stats().feedback,/無法確認/);
});
await test('quest_accept_200_must_match_readback_before_navigation',async()=>{
  const updated={...baseline(),accepted:['demo::LV1','new::LV2']};
  const x=setup({post:async()=>{throw new Error('no reward POST');},
    accept:async()=>response({ok:true}),get:async()=>response(updated)});
  await x.accept('new::LV2','/?quest=new::LV2');
  assert.deepEqual(x.state(),updated);
  assert.equal(x.location().href,'/?quest=new::LV2');
  assert.equal(x.stats().accepts,1);
  assert.equal(x.stats().gets,1);
});
await test('quest_accept_readback_failure_does_not_forge_accepted_state',async()=>{
  const x=setup({post:async()=>{throw new Error('no reward POST');},
    accept:async()=>response({ok:true}),get:async()=>{throw new Error('GET failed');}});
  await x.accept('new::LV2','/?quest=new::LV2');
  assert.deepEqual(x.state(),baseline());
  assert.equal(x.location().href,undefined);
  assert.equal(x.stats().accepts,1);
});
await test('quest_abandon_http_500_does_not_optimistically_remove',async()=>{
  const x=setup({post:async()=>{throw new Error('no reward POST');},
    abandon:async()=>response({error:'unavailable'},500),get:async()=>response(baseline())});
  await x.abandon('demo::LV1');
  assert.deepEqual(x.state(),baseline());
  assert.equal(x.stats().abandons,1);
  assert.match(x.stats().feedback,/無法確認/);
});
await test('quest_abandon_200_must_reflect_authoritative_get',async()=>{
  const updated={...baseline(),accepted:[]};
  const x=setup({post:async()=>{throw new Error('no reward POST');},
    abandon:async()=>response({ok:true}),get:async()=>response(updated)});
  await x.abandon('demo::LV1');
  assert.deepEqual(x.state(),updated);
  assert.equal(x.stats().abandons,1);
  assert.equal(x.stats().gets,1);
});
await test('quest_preview_accept_and_abandon_never_send_mutations',async()=>{
  const x=setup({post:async()=>{throw new Error('NO POST');},
    accept:async()=>{throw new Error('NO ACCEPT');},
    abandon:async()=>{throw new Error('NO ABANDON');},
    get:async()=>{throw new Error('NO GET');}},true);
  await x.accept('new::LV2'); await x.abandon('demo::LV1');
  assert.deepEqual(x.state(),baseline());
  assert.equal(x.stats().accepts+x.stats().abandons+x.stats().posts+x.stats().gets,0);
});
const report={schema:'GO_G_MASTER_Q04_CLAIM_RECONCILE_NODE_R2',
  verdict:'REAL_CLIENT_SOURCE_EXECUTED_LOCAL_FIXTURE_PASS_NOT_PRODUCTION',
  passed:results.length,checks:results,
  prod_Test02:false,mutates_production:false};
console.log(JSON.stringify(report,null,2));
