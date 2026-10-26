/* Product JS unit tests using explicit DOM/WGo/HTTP doubles, NOT browser/PG. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';

const source = await fs.readFile('js/game/g076_grimoire_product_client.js','utf8');
const tick = ()=>new Promise(r=>setImmediate(r));
async function until(predicate) {
  for (let n=0;n<25;n++) { if (predicate()) return; await tick(); }
  throw Error('unit client did not settle');
}
async function fixture({lost=false, terminal=false}={}) {
  const elements = new Map(), boards = [], calls = [];
  let events = [], lose = lost, denied = false, failure = false;
  const element = id => {
    if (!elements.has(id)) elements.set(id,{textContent:'',disabled:false,clientWidth:380,
      replaceChildren(){},addEventListener(name,fn){this[name]=fn;}});
    return elements.get(id);
  };
  function Board(el,config) { this.config=config;this.stones=[];boards.push(this); }
  Board.prototype.addObject=function(o){this.stones.push(o);};
  Board.prototype.addEventListener=function(name,fn){this[name]=fn;};
  const game = ()=>({turn:-1,play(){},isOnBoard(x,y){return x>=0&&y>=0&&x<9&&y<9;},
    getPosition(){return {get(){return 0;}};}});
  const state = () => ({status:events.length?'CORRECT':'OPEN',step_index:events.length,
    step_nonce:'server-nonce',board_only:true,content:'board-only-SGF',previous_steps:events});
  const fetch = async(url,options) => {
    const payload = JSON.parse(options.body);calls.push({url,payload,options});
    if (failure) throw Error('network lost');
    if (denied) return {ok:false,json:async()=>({error:'rights_required'})};
    if (url.endsWith('/admission')) return {ok:true,json:async()=>({title:'伺服器課題',attempt_token:'owned-token'})};
    if (!payload.move) return {ok:true,json:async()=>state()};
    const event = {status:'CORRECT',step_index:1,player_move:[payload.move.x,payload.move.y],
      opponent_reply:null,settlement:{submission_id:'receipt-1'}};
    events = [event];
    if (lose) {lose=false;throw Error('response lost after commit');}
    return {ok:true,json:async()=>event};
  };
  if (terminal) events = [{status:'CORRECT',player_move:[1,1],opponent_reply:null,
    settlement:{submission_id:'receipt-1'}}];
  vm.runInNewContext(source,{document:{getElementById:element},fetch,setTimeout,clearTimeout,
    AbortController,WGo:{Board,Kifu:{fromSgf(){return {size:9,root:{children:[]}};}},
      KifuReader:function(){this.game=game();}}});
  await until(()=>element('status').textContent === (terminal?'修煉完成':'輪到你落子'));
  return {element,boards,calls,deny:()=>{denied=true;},fail:()=>{failure=true;},
    restore:()=>{denied=false;failure=false;}};
}

test('server selects lesson; no browser identity, scope, gate or verdict',async()=>{
  const f = await fixture();
  assert.deepEqual(f.calls[0].payload,{});
  assert.deepEqual(f.calls[1].payload,{attempt_token:'owned-token'});
  assert.equal(f.calls[0].options.headers['X-Grimoire-Request'],'1');
  assert.equal(f.element('lesson').textContent,'伺服器課題');
});

test('lost response locks new moves and resends identical nonce, then reads receipt',async()=>{
  const f = await fixture({lost:true});
  f.boards.at(-1).click(1,1);
  await until(()=>!f.element('retry').disabled);
  f.boards.at(-1).click(2,2);
  assert.equal(f.calls.filter(c=>c.payload.move).length,1);
  f.element('retry').click();
  await until(()=>f.element('status').textContent === '修煉完成');
  const moves = f.calls.filter(c=>c.payload.move);
  assert.deepEqual(moves[0].payload,moves[1].payload);
  assert.deepEqual(Object.keys(moves[0].payload).sort(),['attempt_token','move','step_index','step_nonce']);
  assert.equal(moves[0].payload.step_nonce,'server-nonce');
  assert.match(f.element('receipt').textContent,/receipt-1/);
});

test('reloaded terminal history renders receipt and rejects further clicks',async()=>{
  const f = await fixture({terminal:true});
  const before = f.calls.length;
  f.boards.at(-1).click(2,2);await tick();
  assert.equal(f.calls.length,before);
  assert.match(f.element('receipt').textContent,/receipt-1/);
});

test('rights revocation reconnect clears stale playable state; recovery resumes',async()=>{
  const f = await fixture();f.deny();
  f.element('resume').click();
  await until(()=>!f.element('resume').disabled);
  assert.match(f.element('message').textContent,/會員資格/);
  const before = f.calls.length;f.boards.at(-1).click(1,1);await tick();
  assert.equal(f.calls.length,before);
  f.restore();f.element('resume').click();
  await until(()=>f.element('status').textContent==='輪到你落子');
  assert.equal(f.element('message').textContent,'');
});

test('network failure has retry controls and no speculative stone or local verdict',async()=>{
  const f = await fixture();f.fail();
  f.boards.at(-1).click(1,1);
  await until(()=>!f.element('retry').disabled);
  assert.equal(f.boards.at(-1).stones.length,0);
  assert.equal(f.element('status').textContent,'尚未確認這一手');
  assert.equal(f.element('resume').disabled,false);
});
