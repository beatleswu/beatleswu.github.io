import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
let checks=0;
function check(ok,message){assert.ok(ok,message);checks++;}
function load(fetchImpl){
  const scope={fetch:fetchImpl};scope.globalThis=scope;
  vm.createContext(scope);
  for(const file of ['js/game/g076_nonmap_step_client.js','js/game/g076_daily_step_client.js']){
    vm.runInContext(readFileSync(file,'utf8'),scope,{filename:file});
  }
  return scope.GoOdysseyG076DailySteps.createClient({fetchImpl});
}
let loss=false;
const requests=[];
const fetchImpl=async(path,options)=>{
  requests.push([path,options]);
  const value=path.endsWith('/today') ? {board_only:true,csrf_token:'test-only-csrf',attempt_token:'test-only-token'}
    : path.endsWith('/start') ? {status:'READY',step_index:0,step_nonce:'nonce-0',board_only:true,content:'(;SZ[5]PL[B])'}
    : JSON.parse(options.body).step_index===0 ? {status:'CONTINUE',step_index:1,step_nonce:'nonce-1',opponent_reply:[1,1]}
    : {status:'CORRECT',step_index:2,opponent_reply:null,settlement:{submission_id:'daily-test-receipt',xp_awarded:50}};
  if(loss){loss=false;throw new Error('lost_after_commit');}
  return {ok:true,json:async()=>value};
};
const client=load(fetchImpl);
const data=await client.load();
check(data.board_only,'private load required');
await client.open(data.attempt_token);
check(requests.at(-1)[0]==='/api/g076/daily/steps/start','Daily namespace');
check(requests.at(-1)[1].headers['X-G076-Daily-CSRF']==='test-only-csrf','synchronizer CSRF header');
check(requests.at(-1)[1].credentials==='same-origin','authenticated same-origin transport');
const first=await client.play(0,0);
check(first.status==='CONTINUE' && first.opponent_reply.join()==='1,1','server reply forwarded');
check(Object.keys(JSON.parse(requests.at(-1)[1].body)).sort().join() === 'attempt_token,flow,move,step_index,step_nonce','no client grade/history/uid/date');
loss=true;
await assert.rejects(client.play(2,2),/lost_after_commit/);checks++;
const uncertain=requests.at(-1)[1].body;
await assert.rejects(client.play(3,3),/step_retry_required/);checks++;
const terminal=await client.retry();
check(requests.at(-1)[1].body===uncertain,'retry exact frozen request');
check(terminal.status==='CORRECT' && terminal.settlement.xp_awarded===50,'only server settlement');
await assert.rejects(client.play(4,4),/step_not_active/);checks++;
for(const value of [{error:'daily_steps_disabled_or_unconfigured'}, {csrf_token:'x',content:'full tree'}]){
  const unsafe=load(async()=>({ok:!value.error,json:async()=>value}));
  await assert.rejects(unsafe.load(),/daily_steps_disabled_or_unconfigured|daily_authority_unavailable/);checks++;
  await assert.rejects(unsafe.play(0,0),/step_not_active/);checks++;
}
console.log(JSON.stringify({status:'PASS',checks,kind:'Daily JS transport and fail-closed UI contract'}));
