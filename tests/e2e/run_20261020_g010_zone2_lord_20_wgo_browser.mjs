// Product P1: every Lord answer through original index.html WGo mouse/touch.
// No network mocks, no direct submitSRS call, no fabricated grade / finish.
// Server/PG validation is performed independently in the Python owner.
import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';

let stdin='';
for await(const chunk of process.stdin)stdin+=chunk;
const {origin,sessionCookie}=JSON.parse(stdin);
assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
assert(sessionCookie);
const touch=process.env.GO_P1_LORD_TOUCH==='1';
const browser=await chromium.launch({
 executablePath:process.env.CHROME_BIN||'C:/Program Files/Google/Chrome/Application/chrome.exe',
 headless:true
});
const ctx=await browser.newContext({
 viewport:touch?{width:820,height:1180}:{width:1280,height:900},
 deviceScaleFactor:touch?2:1,hasTouch:touch,isMobile:touch
});
await ctx.addCookies([{name:'session',value:sessionCookie,url:origin}]);
const page=await ctx.newPage();
const errors=[],httpErrors=[],reviews=[],bossFinishes=[];
page.on('pageerror',e=>{if(errors.length<10)errors.push(String(e).slice(0,270))});
page.on('response',async r=>{
 const path=new URL(r.url()).pathname;
 if(r.status()>=400&&httpErrors.length<30)httpErrors.push({path,status:r.status()});
 if(path==='/api/srs/review')reviews.push({status:r.status()});
 if(path==='/api/adventure/boss/finish')bossFinishes.push({status:r.status()});
});
let answered=0,trace=[],finishBodyForDiag=null;
function state(){
 return page.evaluate(()=>({
  bossMode:typeof _bossMode!=='undefined'?_bossMode:null,
  bossIndex:typeof _bossIndex!=='undefined'?_bossIndex:null,
  correct:typeof _bossCorrect!=='undefined'?_bossCorrect:null,
  question:typeof currentQ!=='undefined'?currentQ?.id:null,
  queue:typeof _bossQueue!=='undefined'?_bossQueue?.length:null,
  canvas:!!document.querySelector('#board-canvas-wrap canvas'),
  boardHidden:document.querySelector('#board-canvas-wrap')?.classList.contains('hidden'),
  cinematic:document.querySelector('#boss-cinematic')?.className,
  bossResults:document.querySelector('#boss-result-modal')?.className,
 }));
}
function point(){
 return page.evaluate(()=>{
  const node=(currentNode?.children||[]).find(v=>v?.move);
  if(!node)throw new Error('NO_CURRENT_NODE_ANSWER');
  const {x,y}=node.move;
  const dx=typeof _bx==='function'?_bx(x):x;
  const dy=typeof _by==='function'?_by(y):y;
  const el=board.element;const r=el.getBoundingClientRect();
  const ratio=board.pixelRatio||1;
  return {qid:currentQ.id,x,y,
   px:Math.round(r.left+board.getX(dx)/ratio*r.width/el.offsetWidth),
   py:Math.round(r.top+board.getY(dy)/ratio*r.height/el.offsetHeight)};
 });
}
try{
 await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:30000});
 try{
  await page.waitForFunction(()=> {
   const root=document.querySelector('#e9-world-stage-slot');
   const x=root?.__e9WorldStageState;
   return x?.primaryAction?.zoneKey==='k21_25' &&
     x?.zones?.some(z=>z.key==='k21_25'&&z.bossAvailable===true);
  },undefined,{timeout:11000});
 }catch(e){
  const diag=await page.evaluate(async()=>{
   const el=document.querySelector('#e9-world-stage-slot');
   const cta=document.querySelector('#e9-world-stage-primary-cta');
   const zones=await (await fetch('/api/adventure/bootstrap',{credentials:'include'})).json();
   return {slotExists:!!el,slotData:JSON.stringify({primaryAction:el?.__e9WorldStageState?.primaryAction,zone:el?.__e9WorldStageState?.zones?.[0],currentZoneKey:el?.__e9WorldStageState?.currentZoneKey}).slice(0,700),
     ctaExists:!!cta,ctaText:cta?.textContent?.trim(),
     ctaTarget:cta?.dataset?.challengeTargetZone,
     zones:zones?.zones?.slice(0,2).map(z=>({key:z.key,boss_ready:z.boss_ready,seen:z.seen,unlocked:z.unlocked})),
     startupFlags:{ready:window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__,
       error:window.__GO_ADVENTURE_QUESTION_RUNTIME_ERROR__}};
  });
  throw new Error('E9_HOME_STAGE_CTA_NOT_READY '+JSON.stringify(diag));
 }
 // E9 responsive shell intentionally hides its redundant map button on
 // tablet. Use the visible drawer/card action rather than force-clicking it.
 const mapCta=page.locator('#e9-world-stage-primary-cta');
 const drawerCta=page.locator('#e9-right-drawer-panel [data-e10-zone-cta]');
 const cardCta=page.locator('#e9-world-stage-details-cta');
 let visibleCta=null;
 if(await drawerCta.isVisible())visibleCta=drawerCta;
 else if(await mapCta.isVisible())visibleCta=mapCta;
 else if(await cardCta.isVisible())visibleCta=cardCta;
 else{
  const handle=page.locator('#e9-right-drawer-toggle');
  assert(await handle.isVisible(),'NO_VISIBLE_REAL_ZONE2_LORD_CTA');
  await handle.click({timeout:12000});
  await drawerCta.waitFor({state:'visible',timeout:13000});
  visibleCta=drawerCta;
 }
 assert.equal(await visibleCta.getAttribute('data-challenge-target-zone'),'k21_25');
 assert.equal(await visibleCta.isEnabled(),true);
 await visibleCta.click({timeout:13000});
 await page.locator('#boss-cinematic.show').waitFor({timeout:22000});
 // Clicking the visible Begin Challenge CTA, not invoking internal JS.
 await page.locator('#boss-cinematic-btn').click({timeout:20000});
 await page.waitForFunction(()=> _bossMode===true&&
  _bossQueue?.length===20&&!!board?.element&&!!currentNode
  &&!document.querySelector('#board-canvas-wrap')?.classList.contains('hidden'),
  undefined,{timeout:30000});
 const opened=await state();
 assert.equal(opened.queue,20);

 const uniqueQueue=await page.evaluate(()=>new Set(_bossQueue||[]).size);
 assert.equal(uniqueQueue,20,'Lord 20-question queue must contain 20 unique questions');
 let finalFinishResponse=null;
 let previousQuestionId=null;
 for(let i=0;i<20;i++){
  // A successful review may increment _bossIndex BEFORE WGo publishes the
  // next question/board tree. Never click an old tree after index advances:
  // Chrome touch races previously replayed the previous SGF qid at step 18.
  await page.waitForFunction(({index,prior})=>_bossMode===true
    && _bossIndex===index
    && currentQ?.id===_bossQueue[index]
    && currentQ?.id!==prior
    && (currentNode?.children||[]).some(child=>!!child?.move)
    && !!board?.element
    && !document.querySelector('#board-canvas-wrap')?.classList.contains('hidden'),
    {index:i,prior:previousQuestionId},{timeout:22000});
  // Require the actual browser's next paint before deriving pixel coords.
  await page.evaluate(()=>new Promise(done=>requestAnimationFrame(
    ()=>requestAnimationFrame(done))));
  const p=await point();
  assert.notEqual(p.qid,previousQuestionId,'WGo must advance to a new Lord SGF');
  previousQuestionId=p.qid;
  const expectReview=page.waitForResponse(r=>
   new URL(r.url()).pathname==='/api/srs/review'&&r.request().method()==='POST',
   {timeout:20000});
  // Subscribe BEFORE the final real WGo click. Boss finish is asynchronous;
  // the database may commit slightly before Chrome receives its response.
  if(i===19)finalFinishResponse=page.waitForResponse(r=>
    new URL(r.url()).pathname==='/api/adventure/boss/finish'&&
    r.request().method()==='POST',{timeout:35000});
  if(touch)await page.touchscreen.tap(p.px,p.py);
  else await page.mouse.click(p.px,p.py);
  const r=await expectReview;
  const payload=await r.json();
  assert.equal(r.status(),200,JSON.stringify({i,qid:p.qid,payload}).slice(0,300));
  assert.equal(payload.ok,true,JSON.stringify({i,qid:p.qid,payload}).slice(0,300));
  trace.push({step:i+1,qid:p.qid,http:r.status(),reply:JSON.stringify(payload).slice(0,400)});
  answered++;
  if(i<19){
   await page.waitForFunction(index=>_bossIndex===index+1,
    i,{timeout:23000});
  }
 }
 // Wait for the ACTUAL asynchronous Boss finish response, not merely the
 // earlier database commit observed by a concurrent read-only poll.
 assert(finalFinishResponse,'Missing final-click Boss finish watcher');
 const finishHTTP=await finalFinishResponse;
 const finishBody=await finishHTTP.json();
 finishBodyForDiag=finishBody;
 assert.equal(finishHTTP.status(),200,JSON.stringify(finishBody).slice(0,500));
 assert.equal(finishBody.ok,true);
 assert.equal(finishBody.passed,true);
 assert(finishBody.correct>=finishBody.pass_score &&
        finishBody.correct<=20,
        'Server-judged 20-question Lord pass threshold is not satisfied');
 assert.equal(finishBody.total,20);
 assert.equal(finishBody.first_clear_projection?.status,'COMPLETED');
 assert.equal(finishBody.reward?.first_clear,true);
 // An independent authoritative read verifies actual persistence and unlock.
 await page.waitForFunction(async()=>{
  const r=await fetch('/api/adventure/bootstrap',{credentials:'include',cache:'no-store'});
  if(!r.ok)return false;
  const map=await r.json();const by=Object.fromEntries(map.zones.map(z=>[z.key,z]));
  return by.k21_25?.cleared===true&&by.k16_20?.unlocked===true;
 },undefined,{timeout:32000});

 const fresh=await page.evaluate(async()=>{
  const r=await fetch('/api/adventure/bootstrap',{credentials:'include',cache:'no-store'});
  const x=await r.json();return Object.fromEntries(x.zones.map(z=>[z.key,{
   cleared:z.cleared,unlocked:z.unlocked,stars:z.stars,attempts:z.attempts}]));
 });
 assert.equal(reviews.length,20);
 assert(bossFinishes.some(x=>x.status===200));
 assert.equal(finishBody.reward?.first_clear,true);
 console.log(JSON.stringify({
  verdict:'REAL_ZONE2_LORD_20_WGO_FIRST_CLEAR_PASS',
  input:touch?'chrome_tablet_touch':'desktop_mouse',
  answered,opened,after:await state(),fresh,
  serverReviews:reviews,finishResponses:bossFinishes,trace,
  pageErrors:errors,httpErrors,
  actualIndex:true,actualWGoClicks:true,usedMockRoutes:false,
  production:false,realIpad:false
 },null,2));
}catch(e){
 console.error('REAL_ZONE2_LORD_20_WGO_BLOCKED',String(e.stack||e),JSON.stringify({
  answered,trace:trace.slice(0,3).concat(trace.slice(-3)).map(t=>({...t,reply:t.reply.slice(0,180)})),
  state:await state().catch(()=>null),
  finishSummary:finishBodyForDiag?{passed:finishBodyForDiag.passed,correct:finishBodyForDiag.correct,total:finishBodyForDiag.total,reason:finishBodyForDiag.reason,error:finishBodyForDiag.error,keys:Object.keys(finishBodyForDiag)}:null,
  reviews:reviews.length,bossFinishes,httpErrors: httpErrors.slice(-12),errors
 }));
 process.exitCode=1;
}finally{await ctx.close();await browser.close()}

