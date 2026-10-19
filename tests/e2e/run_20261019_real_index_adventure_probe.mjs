// Real shipped index.html and WGo canvas: actual pointer answer event,
// real Flask/PG adjudication, XP and Adventure readback. No request mocks.
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const input=await new Promise((resolve,reject)=>{let v='';process.stdin.setEncoding('utf8');
  process.stdin.on('data',d=>v+=d);process.stdin.on('end',()=>{
  try{resolve(JSON.parse(v))}catch(e){reject(e)}});
});
assert.match(input.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const browser=await chromium.launch({
  headless:true,executablePath:process.env.CHROME_BIN||
  'C:/Program Files/Google/Chrome/Application/chrome.exe'
});
const touchMode=process.env.GO_P1_TOUCH_EMULATION==='1';
const ctx=await browser.newContext({
 viewport:touchMode?{width:820,height:1180}:{width:1120,height:820},
 deviceScaleFactor:touchMode?2:1,
 hasTouch:touchMode,isMobile:touchMode,acceptDownloads:false
});
await ctx.addCookies([{name:'session',value:input.sessionCookie,url:input.origin}]);
const page=await ctx.newPage();
const jsErrors=[],fails=[],checks=[],spiritChooseStatuses=[];
page.on('pageerror',e=>jsErrors.push(String(e).slice(0,300)));
page.on('response',r=>{
 const path=new URL(r.url()).pathname;
 if(path==='/api/pet/choose') spiritChooseStatuses.push(r.status());
 if(r.status()>=400&&fails.length<40)
 fails.push({status:r.status(),path});
});
async function check(name,fn){await fn();checks.push({name,status:'PASS'});}
async function serverTruth(){
 return page.evaluate(async()=>{
   async function get(path){const r=await fetch(path,{credentials:'include',cache:'no-store'});
     if(!r.ok)throw new Error('READ_FAILED:'+path+':'+r.status);return r.json();}
   const [xp,hero,map]=await Promise.all([
     get('/api/xp/status'),get('/api/player/presentation'),get('/api/adventure/bootstrap')]);
   const zone=map.zones.find(z=>z.key==='k26_30');
   return {xp:xp.xp,level:xp.lv,rank_xp:xp.rank_xp,
     hero_xp:hero.progression.xp,hero_level:hero.progression.level,
     zoneCorrect:zone?.correct_count,zoneSeen:zone?.seen,zoneCleared:zone?.cleared};
 });
}
try{
 const resp=await page.goto(input.origin+'/?zone=k26_30&adventure=1&resume=1&lang=zh',
     {waitUntil:'domcontentloaded',timeout:25000});
 await page.waitForFunction(()=>window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__===true
   && typeof _mapBattleV1Mode==='string' && _mapBattleV1Mode==='active'
   && !!board?.element && currentQ?.id===710019,undefined,{timeout:30000});
 const state=await page.evaluate(()=>({
   mode:_mapBattleV1Mode,currentQ:currentQ?.id,
   boardVisible:!document.querySelector('#board-canvas-wrap')?.classList.contains('hidden'),
   active:!!_mapBattleV1State?.attemptId,
   zoneQuestions:_adventureActiveQuestions?.length||0,
 }));
 await check('real_index_WGo_visible_map_question_and_server_attempt',async()=>{
   assert.equal(resp.status(),200);
   assert.equal(state.mode,'active');
   assert.equal(state.currentQ,710019);
   assert.equal(state.boardVisible,true);
   assert.equal(state.active,true);
   assert.equal(state.zoneQuestions,1);
 });
 await page.waitForFunction(async()=>{
   const r=await fetch('/api/pet/status',{credentials:'include',cache:'no-store'});
   if(!r.ok)return false;
   const d=await r.json();return d.pet?.pet_key==='ink_drop_kelpie';
 },undefined,{timeout:12000});
 await check('new_player_auto_selects_governed_spirit_without_503',async()=>{
   assert.deepEqual(spiritChooseStatuses,[200],
     'one real server-authorized starter Spirit POST; no 503 or duplicate 409');
 });
 // An authentic Zone 1 entry may show the PRE_PLAY cinematic above a
 // loaded (but not yet clickable) WGo board. Follow the actual player's
 // "Skip animation" -> "Begin training" controls before touching WGo.
 if(await page.locator('#boss-cinematic.show').isVisible()){
   await page.locator('#intro-film-stage .intro-skip-btn').click({timeout:8000});
   await page.waitForFunction(()=>{
     const el=document.querySelector('#boss-cinematic');
     return !el?.classList.contains('show') ||
       (el?.classList.contains('ready') &&
       !document.querySelector('#boss-cinematic-btn')?.disabled);
   },undefined,{timeout:9000});
   const afterSkip=await page.evaluate(()=>({
     overlayClass:document.querySelector('#boss-cinematic')?.className,
     overlayShown:document.querySelector('#boss-cinematic')?.classList.contains('show'),
     buttonDisabled:document.querySelector('#boss-cinematic-btn')?.disabled,
     stageHidden:document.querySelector('#intro-film-stage')?.getAttribute('aria-hidden'),
     cinematicPhase:typeof _introFilmActiveOpts!=='undefined'?_introFilmActiveOpts?.phase:null,
     zoneCard:document.querySelector('[id*=zone-card].show')?.id||null,
   }));
   if(afterSkip.overlayShown)await page.locator('#boss-cinematic-btn').click({timeout:10000});
   await page.waitForFunction(()=>!document.querySelector('#boss-cinematic')?.classList.contains('show')
     && _mapBattleV1Mode==='active' && !!_mapBattleV1State?.attemptId,
     undefined,{timeout:12000});
 }
 await check('cinematic_completed_by_actual_player_controls_and_WGo_uncovered',async()=>{
   const clickTarget=await page.evaluate(()=>{
     const e=board?.element;const rect=e?.getBoundingClientRect();
     return {overlay:document.querySelector('#boss-cinematic')?.classList.contains('show'),
       boardVisible:!!e&&!document.querySelector('#board-canvas-wrap')?.classList.contains('hidden'),
       question:currentQ?.id,rectWidth:rect?.width||0};
   });
   assert.equal(clickTarget.overlay,false,'story overlay must be dismissed by visible controls');
   assert.equal(clickTarget.boardVisible,true);
   assert.equal(clickTarget.question,710019);
 });
 const before=await serverTruth();
 await check('actual_index_player_starts_at_lv1_119xp',async()=>{
   assert.equal(before.xp,119);assert.equal(before.level,1);
   assert.equal(before.zoneCorrect,0);
 });
 const point=await page.evaluate(()=>{
   const node=(currentNode?.children||[]).find(n=>n?.move);
   if(!node)throw new Error('NO_WGO_ANSWER_NODE');
   const {x,y}=node.move;
   const dx=typeof _bx==='function'?_bx(x):x;
   const dy=typeof _by==='function'?_by(y):y;
   const element=board.element;
   const rect=element.getBoundingClientRect();
   const ratio=board.pixelRatio||1;
   const sx=element.offsetWidth?rect.width/element.offsetWidth:1;
   const sy=element.offsetHeight?rect.height/element.offsetHeight:1;
   const cx=board.getX(dx)/ratio,cy=board.getY(dy)/ratio;
   return {x,y,px:Math.round(rect.left+cx*sx),
     py:Math.round(rect.top+cy*sy),rect:{w:rect.width,h:rect.height}};
 });
 assert.equal(point.x,3);assert.equal(point.y,3);
 assert(point.px>0&&point.py>0,'WGo pointer target within viewport');
 const responseWait=page.waitForResponse(r=>
   r.url().includes('/api/adventure/map-battles/v1/answers')
   && r.request().method()==='POST', {timeout:6500});
 if(touchMode) await page.touchscreen.tap(point.px,point.py);
 else await page.mouse.click(point.px,point.py);
 let posted;
 try { posted=await responseWait; }
 catch(error){
   const diag=await page.evaluate(({px,py})=>({
     elementAtPoint:(()=>{
       const e=document.elementFromPoint(px,py);
       return e?{tag:e.tagName,id:e.id,className:String(e.className||'').slice(0,90)}:null;
     })(),
     currentNodeMoves:(currentNode?.children||[]).map(n=>n?.move||null),
     currentQ:currentQ?.id,
     mode:_mapBattleV1Mode,
     lifecycle:typeof _mapBattleV1Moves!=='undefined'?_mapBattleV1Moves:null,
     lastMessage:document.querySelector('#msg-box')?.textContent?.slice(0,240)||null,
     boardVisible:!document.querySelector('#board-canvas-wrap')?.classList.contains('hidden'),
     activeState:_mapBattleV1State?.attemptId||null,
     boardPlayerColor:typeof currentProblem!=='undefined'?currentProblem?.color:null
   }),{px:point.px,py:point.py});
   throw new Error('REAL_WGO_CLICK_NO_REQUEST '+JSON.stringify({
     point,diag,javascriptErrors:jsErrors.slice(-5),failedResources:fails.slice(-8)
   }));
 }
 const result=await posted.json();
 await check('real_WGo_mouse_click_hits_real_authoritative_answer_endpoint',async()=>{
   assert.equal(posted.status(),200,JSON.stringify(result).slice(0,450));
   assert.equal(result.result,'CORRECT');
   assert.equal(result.progression?.status,'applied');
   assert.equal(result.duplicate,false);
 });
 await page.waitForFunction(async()=>{
   const r=await fetch('/api/xp/status',{credentials:'include',cache:'no-store'});
   return r.ok&&(await r.json()).xp===135;
 },undefined,{timeout:15000});
 const after=await serverTruth();
 await check('XP_and_hero_level_progress_from_real_WGo_click',async()=>{
   assert.equal(after.xp,135);
   assert.equal(after.level,2);
   assert.equal(after.hero_xp,135);
   assert.equal(after.hero_level,2);
 });
 await check('adventure_correct_count_saved_without_spurious_zone_clear',async()=>{
   assert.equal(after.zoneCorrect,1);
   assert.equal(after.zoneSeen,1);
   assert.equal(after.zoneCleared,false);
 });
 await page.reload({waitUntil:'domcontentloaded'});
 const fresh=await serverTruth();
 await check('full_index_refresh_retains_level_and_zone_score',async()=>{
   assert.equal(fresh.xp,135);assert.equal(fresh.level,2);
   assert.equal(fresh.zoneCorrect,1);assert.equal(fresh.zoneCleared,false);
 });
 // Navigate to the original Hero page, let it fetch its own server data,
 // and inspect the real rendered DOM (not manually invoked renderer JS).
 await page.goto(input.origin+'/hero?tab=character',{waitUntil:'domcontentloaded',timeout:25000});
 await page.waitForFunction(()=>{
   const lv=document.getElementById('badge-lv');
   const xp=document.getElementById('char-xp');
   return lv?.textContent?.trim()==='LV2' && !!xp?.textContent?.includes('15 / 160 XP');
 },undefined,{timeout:20000});
 const actualHero=await page.evaluate(()=>({
   lv:document.getElementById('badge-lv')?.textContent?.trim(),
   xp:document.getElementById('char-xp')?.textContent?.trim(),
   overviewXp:document.getElementById('hero-overview-xp')?.textContent?.trim(),
   pct:document.getElementById('char-xp-pct')?.textContent?.trim(),
   bar:document.getElementById('char-xp-bar')?.style?.width,
 }));
 await check('actual_hero_page_shows_new_level_and_correct_current_XP',async()=>{
   assert.equal(actualHero.lv,'LV2');
   assert.match(actualHero.xp,/15 \/ 160 XP/);
   assert.match(actualHero.xp,/135/);
   assert.equal(actualHero.pct,'9%');
   assert.equal(actualHero.bar,'9%');
 });
 // The active Hero UI is G009. Its legacy #hero-tab-pet is hidden by
 // design: use the real visible G009 Companion navigation instead.
 await page.locator('[data-g009-hub-tab="pet"]').click({timeout:10000});
 await page.waitForSelector(
   '#g009-panel-companion:not([hidden]) #g009-companion-active .g009-companion-card[data-pet-key="ink_drop_kelpie"]',
   {timeout:14000});
 const actualSpirit=await page.evaluate(()=>({
   key:document.querySelector('#g009-companion-active .g009-companion-card')?.dataset.petKey,
   name:document.querySelector('#g009-companion-active .g009-companion-card strong')?.textContent?.trim(),
   ownedCard:!!document.querySelector('#g009-companion-active .g009-companion-card'),
   tabVisible:!document.querySelector('#g009-panel-companion')?.hasAttribute('hidden'),
 }));
 await check('hero_spirit_tab_displays_server_owned_starter_after_answer',async()=>{
   assert.equal(actualSpirit.key,'ink_drop_kelpie');
   assert.equal(actualSpirit.ownedCard,true);
   assert.equal(actualSpirit.tabVisible,true);
   assert(actualSpirit.name);
 });
 console.log(JSON.stringify({
   schema:'GO_P1_REAL_INDEX_WGO_CLICK_TO_NATIVE_PG_R1',
   verdict:'REAL_INDEX_REAL_WGO_REAL_MAP_ANSWER_PG_PASS',
   passed:checks.length,checks,spiritChooseStatuses,
   before,after,fresh,point,actualHero,actualSpirit,
   javascript_errors:jsErrors.slice(0,10),
   failed_resources:fails.slice(0,25),
   actual_shipped_index_used:true,
   actual_wgo_pointer_event_used:true,
   emulated_touch_mode:touchMode,
   production:false,real_ipad:false
 },null,2));
}catch(e){console.error('INDEX_WGO_REAL_PG_E2E_FAILED',e.stack||String(e));process.exitCode=1;}
finally{await ctx.close();await browser.close();}
