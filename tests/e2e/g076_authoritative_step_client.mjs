import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const src = fs.readFileSync(path.join(root, 'js/game/g076_authoritative_step_client.js'),'utf8');
const checks=[];
function check(name,fn){checks.push([name,fn]);}
const setup=(responses, opts={})=>{
  const window={};
  vm.runInNewContext(src,{window});
  const calls=[],events=[],pending=[...responses];
  const fetcher=async (url,options)=>{
    const body=JSON.parse(options.body);
    calls.push({url,body,headers:options.headers,credentials:options.credentials});
    const item=pending.shift();
    if(item instanceof Error)throw item;
    return {ok:item.ok!==false,status:item.statusCode||200,
            json:async()=>item};
  };
  const client=window.GoOdysseyG076Steps.createClient({
    fetcher,
    onState:s=>events.push({type:'state',active:s.active,step:s.stepIndex,busy:s.busy}),
    onPlayerMove:(p,r)=>events.push({type:'player',x:p.x,y:p.y,result:r.status}),
    onOpponentMove:(p,r)=>events.push({type:'reply',x:p.x,y:p.y,result:r.status}),
    onSettlement:(s,r)=>events.push({type:'settlement',result:s.result}),
    ...opts
  });
  return {client,calls,events,pending};
};
const ready={status:'READY',step_index:0,step_nonce:'n0'};
const continuing={status:'CONTINUE',step_index:1,next_step_nonce:'n1',
                  opponent_reply:[1,1],duplicate:false};
const success={status:'CORRECT',step_index:2,opponent_reply:null,
  battle_settlement:{accepted:true,result:'CORRECT',damage_to_monster:7}};

check('fetch uses same-origin JSON only',async()=>{
  const env=setup([ready,continuing,success]);
  await env.client.open({attemptId:'a1',submissionNonce:'issued-map-nonce'});
  await env.client.play(0,0);
  await env.client.play(2,2);
  assert.equal(env.calls.length,3);
  assert.equal(env.calls[0].url,'/api/adventure/map-battles/v2/steps/start');
  assert.equal(env.calls[1].credentials,'same-origin');
  assert.deepEqual(Object.keys(env.calls[1].body).sort(),
    ['attempt_id','move','step_index','step_nonce','submission_nonce'].sort());
  assert.deepEqual(env.calls[1].body.move,{x:0,y:0});
  assert.equal(env.calls[2].body.step_nonce,'n1');
  assert.ok(!src.includes('accepted_moves'));
  assert.ok(!src.includes('currentProblem.tree'));
  assert.ok(!src.includes('katago_best_move'));
});
check('correct prefix does not settle or reveal future move',async()=>{
  const env=setup([ready,continuing,success]);
  await env.client.open({attemptId:'a1',submissionNonce:'a'});
  const result=await env.client.play(0,0);
  assert.equal(result.status,'CONTINUE');
  assert.equal(env.client.state().completed,false);
  assert.equal(env.client.state().stepIndex,1);
  assert.equal(env.events.filter(e=>e.type==='settlement').length,0);
  assert.deepEqual(env.events.filter(e=>e.type==='reply'),[
    {type:'reply',x:1,y:1,result:'CONTINUE'}
  ]);
  await env.client.play(2,2);
  assert.equal(env.client.state().completed,true);
  assert.equal(env.events.filter(e=>e.type==='settlement').length,1);
  await assert.rejects(()=>env.client.play(1,1),/G076_NOT_ACTIVE/);
});
check('network error retries exact same step and one settlement',async()=>{
  const env=setup([ready,new Error('connection-lost'),success]);
  await env.client.open({attemptId:'a1',submissionNonce:'a'});
  await assert.rejects(()=>env.client.play(0,0),/connection-lost/);
  assert.equal(env.client.state().stepIndex,0);
  await env.client.retrySameStep();
  assert.deepEqual(env.calls[1].body,env.calls[2].body);
  assert.equal(env.events.filter(e=>e.type==='settlement').length,1);
});
check('wrong step settles only by server truth',async()=>{
  const env=setup([ready,{status:'INCORRECT',step_index:1,
    battle_settlement:{accepted:true,result:'INCORRECT',damage_to_player:3}}]);
  await env.client.open({attemptId:'a1',submissionNonce:'a'});
  const result=await env.client.play(8,8);
  assert.equal(result.status,'INCORRECT');
  assert.equal(env.events.filter(e=>e.type==='settlement').length,1);
});
check('forbidden client move shape and incomplete settlement fail closed',async()=>{
  const env=setup([ready,{status:'CORRECT',step_index:1}]);
  await env.client.open({attemptId:'a1',submissionNonce:'a'});
  await assert.rejects(()=>env.client.play(-1,10),/G076_INVALID_POINT/);
  await assert.rejects(()=>env.client.play(3,3),/G076_MISSING_AUTHORITATIVE_SETTLEMENT/);
  assert.equal(env.client.state().completed,false);
});
check('disabled or invalid server response stops before painting',async()=>{
  const env=setup([ready,{ok:false,statusCode:503,error:'g076_step_runtime_disabled'}]);
  await env.client.open({attemptId:'a1',submissionNonce:'a'});
  await assert.rejects(()=>env.client.play(2,2),/g076_step_runtime_disabled/);
  assert.equal(env.events.filter(e=>e.type==='player').length,0);
});
check('no client-side result or reward writes',async()=>{
  assert.ok(!src.includes('/api/srs/review'));
  assert.ok(!src.includes('localStorage'));
  assert.ok(!src.includes('sessionStorage'));
  assert.ok(!src.includes('XP +='));
  assert.ok(!src.includes('grade:'));
});
let successCount=0;
for(const [name,fn] of checks){await fn();successCount++;console.log('PASS',name);}
console.log('G076_R2_BROWSER_CLIENT '+successCount+' PASS / 0 FAIL');
