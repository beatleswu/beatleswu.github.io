// G010 M4 real Chrome Quest V2 claim => server leaderboard projection.
import assert from 'node:assert/strict';
import {chromium} from 'file:///D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core/index.mjs';
let data='';
for await (const chunk of process.stdin) data+=chunk;
const {origin,sessionCookie,reloginCookie,questId,beforeXp,afterXp,coinsAfter}=JSON.parse(data);
assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const touch=process.env.GO_G010_M4_TOUCH==='1';
const browser=await chromium.launch({
 headless:true,executablePath:process.env.CHROME_BIN||
 'C:/Program Files/Google/Chrome/Application/chrome.exe',
});
const context=async cookie=>{
 const ctx=await browser.newContext({
  viewport:touch?{width:820,height:1180}:{width:1280,height:900},
  isMobile:touch,hasTouch:touch,deviceScaleFactor:touch?2:1,
  serviceWorkers:'block',
 });
 await ctx.addCookies([{name:'session',value:cookie,url:origin}]);
 return ctx;
};
const ctx=await context(sessionCookie);
const page=await ctx.newPage();
const writes=[],errors=[],httpFailures=[];
page.on('pageerror',e=>errors.push(String(e).slice(0,250)));
page.on('request',r=>{
 const u=new URL(r.url());
 if(u.origin===origin && u.pathname.startsWith('/api/') && r.method()!=='GET')
  writes.push(r.method()+' '+u.pathname);
});
page.on('response',r=>{
 const u=new URL(r.url());
 if(u.origin===origin && u.pathname.startsWith('/api/') && r.status()>=400)
  httpFailures.push(r.status()+' '+u.pathname);
});
const serverView=async p=>p.evaluate(async()=>{
 const req=async route=>{
  const res=await fetch(route,{credentials:'include',cache:'no-store'});
  return {status:res.status,data:await res.json()};
 };
 const [board,quests,xp,coins]=await Promise.all([
  req('/api/community/leaderboard'),req('/api/quests/v2'),
  req('/api/xp/status'),req('/api/shop/catalog'),
 ]);
 return {board,quests,xp,coins};
});
const ownScore=(board,key)=>{
 const me=board?.[key]?.find(x=>x.is_you===true);
 return me?Number(me.score):null;
};
let phase='initial';
try{
 const resp=await page.goto(origin+'/community',{waitUntil:'domcontentloaded',timeout:30000});
 assert.equal(resp.status(),200);
 const card=page.locator('[data-m4-quest="'+questId+'"]');
 await card.waitFor({state:'visible',timeout:25000});
 assert.equal(await card.getAttribute('data-claimable'),'true');
 assert.equal(await page.locator('#g010-m4-quest-panel').isVisible(),true);
 await page.waitForFunction(()=>document.querySelector('#leaderboard-context')?.dataset.boardContext==='weekly',
  undefined,{timeout:22000});
 const before=await serverView(page);
 assert.equal(before.board.status,200);
 assert.equal(before.quests.status,200);
 assert.equal(before.xp.status,200);
 assert.equal(before.coins.status,200);
 assert.equal(before.xp.data.xp,beforeXp);
 assert.equal(ownScore(before.board.data,'alltime'),beforeXp);
 assert.equal(before.quests.data.client_calculates_completion,false);
 phase='claim';
 const btn=card.locator('button[data-m4-claim]');
 await btn.dblclick({timeout:15000});
 await page.waitForFunction(key=>{
  const a=document.querySelector('[data-m4-quest="'+key+'"]');
  return a?.dataset.status==='CLAIMED'&&
     !a.querySelector('button[data-m4-claim]');
 },questId,{timeout:25000});
 // The shipped community page keeps its ranking state in a lexical const,
 // not window.state. Exercise the ACTUAL leaderboard tab and visible row.
 await page.locator('[data-lb="alltime"]').click({timeout:12000});
 await page.waitForFunction(expected=>{
  const row=document.querySelector('#leaderboard-table tr.me .score');
  return document.querySelector('#leaderboard-context')?.dataset.boardContext==='alltime'
    && row?.textContent?.includes(String(expected));
 },afterXp,{timeout:23000});
 const after=await serverView(page);
 assert.equal(after.xp.data.xp,afterXp);
 assert.equal(ownScore(after.board.data,'alltime'),afterXp);
 assert.equal(after.coins.data.coins,coinsAfter);
 for(const key of ['weekly','monthly']){
  assert.equal(ownScore(after.board.data,key),ownScore(before.board.data,key),
   'Quest XP grant must not inflate weekly/monthly server-scored correct answer counts');
 }
 assert.equal(after.quests.data.quests.find(x=>x.quest_id===questId)?.claimed,true);
 await page.locator('[data-lb="alltime"]').click({timeout:12000});
 await page.waitForFunction(expected=>
  document.querySelector('#leaderboard-context')?.dataset.boardContext==='alltime' &&
  document.querySelector('#leaderboard-table tr.me .score')?.textContent
    ?.includes(String(expected)),afterXp,{timeout:15000});
 assert.equal(writes.filter(w=>w==='POST /api/quests/v2/claim').length,1);
 phase='relogin';
 const other=await context(reloginCookie);
 try{
  const p=await other.newPage();
  await p.goto(origin+'/community',{waitUntil:'domcontentloaded',timeout:30000});
  const c=p.locator('[data-m4-quest="'+questId+'"]');
  await c.waitFor({state:'visible',timeout:25000});
  assert.equal(await c.getAttribute('data-status'),'CLAIMED');
  assert.equal(await c.locator('button[data-m4-claim]').count(),0);
  const fromNew=await serverView(p);
  assert.equal(fromNew.xp.data.xp,afterXp);
  assert.equal(fromNew.coins.data.coins,coinsAfter);
  assert.equal(ownScore(fromNew.board.data,'alltime'),afterXp);
 }finally{await other.close();}
 assert.deepEqual(errors,[]);
 assert.deepEqual(httpFailures,[]);
 assert.deepEqual(writes,['POST /api/quests/v2/claim']);
 console.log(JSON.stringify({
  verdict:'G010_M4_REAL_CHROME_QUEST_RANKING_RELOGIN_PASS',
  input:touch?'chrome_tablet_touch':'desktop_mouse',production:false,
  serverScoredWeeklyUnchanged:true,serverScoredMonthlyUnchanged:true,
  lifetimeXpBefore:beforeXp,lifetimeXpAfter:afterXp,
  coinsAfter,writes,httpFailures,errors,
 }));
}catch(e){
 const debug=await page.evaluate(async()=>{
  const panel=document.querySelector('#g010-m4-quest-panel');
  let quest={};
  try {const r=await fetch('/api/quests/v2',{credentials:'include'});quest={
    status:r.status,body:JSON.stringify(await r.json()).slice(0,220),
  };}catch(ex){quest={error:String(ex)};}
  return {panel:!!panel,hidden:panel?.hidden,display:panel&&getComputedStyle(panel).display,
    script:!!Array.from(document.scripts).find(s=>s.src.includes('g010_m4_quest_leaderboard')),
    runtime:!!window.G010M4QuestPanel,quest,grid:document.querySelector('#g010-m4-quest-grid')?.innerHTML.slice(0,360)};
 }).catch(ex=>({evalError:String(ex)}));
 console.error('G010_M4_CHROME_BLOCKED',phase,String(e.stack||e),
 JSON.stringify({writes,httpFailures,errors,url:page.url(),debug}));
 process.exitCode=1;
}finally{await ctx.close();await browser.close();}
