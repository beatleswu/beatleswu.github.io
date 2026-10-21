// Original E9 Zone 2 click -> first-entry story -> visible training CTA ->
// original WGo board click -> server-authoritative Map Battle answer.
// Isolated fixture has two Zone 2 questions; one was answered by an API
// client, the other (970032) is answered here by real browser input.
import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

let raw = '';
for await (const part of process.stdin) raw += part;
const {origin, sessionCookie} = JSON.parse(raw);
assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
assert(sessionCookie);
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_BIN ||
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
});
const touch = process.env.GO_P2_ZONE2_TOUCH === '1';
const ctx = await browser.newContext({
  viewport:touch?{width:820,height:1180}:{width:1280,height:900},
  hasTouch:touch,isMobile:touch,deviceScaleFactor:touch?2:1,
});
await ctx.addCookies([{name:'session',value:sessionCookie,url:origin}]);
const page = await ctx.newPage();
const errors = [], mapAnswers = [], badHttp = [];
page.on('pageerror', e => errors.push(String(e).slice(0,400)));
page.on('response', r => {
  const path = new URL(r.url()).pathname;
  if (path === '/api/adventure/map-battles/v1/answers')
    mapAnswers.push({status:r.status(),path});
  if (r.status() >= 400 && badHttp.length < 15)
    badHttp.push({status:r.status(),path});
});
function boardPoint() {
  return page.evaluate(() => {
    const child=(currentNode?.children||[]).find(c=>c?.move);
    if(!child)throw new Error('ZONE2_NO_WGO_SOLUTION_NODE');
    const {x,y}=child.move;
    const dx=typeof _bx==='function'?_bx(x):x;
    const dy=typeof _by==='function'?_by(y):y;
    const el=board.element, r=el.getBoundingClientRect();
    const ratio=board.pixelRatio||1;
    return {qid:currentQ.id,
      px:Math.round(r.left+board.getX(dx)/ratio*r.width/el.offsetWidth),
      py:Math.round(r.top+board.getY(dy)/ratio*r.height/el.offsetHeight)};
  });
}
let stage='initial', browserCorrect=false, before=null, after=null;
try {
  const initial=await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:30000});
  assert.equal(initial.status(),200);
  const tile=page.locator('#e9-world-stage-slot .e9-zone[data-zone="k21_25"]');
  await page.waitForFunction(()=>{
    const root=document.querySelector('#e9-world-stage-slot');
    const zone=root?.__e9WorldStageState?.zones?.find(z=>z.key==='k21_25');
    return zone?.canEnter===true&&zone?.locked===false
      &&!!root?.querySelector('.e9-zone[data-zone="k21_25"]');
  },undefined,{timeout:30000});
  before=await page.evaluate(()=>{
    const root=document.querySelector('#e9-world-stage-slot');
    const z=root.__e9WorldStageState.zones.find(z=>z.key==='k21_25');
    return {locked:z.locked,canEnter:z.canEnter,bossAvailable:z.bossAvailable,status:z.status};
  });
  stage='click_zone2';
  await tile.click({timeout:15000});
  await page.waitForFunction(()=>{
    const el=document.querySelector('#boss-cinematic');
    return el?.classList.contains('show')&&el.dataset.zoneKey==='k21_25';
  },undefined,{timeout:26000});
  stage='skip_intro_via_visible_button';
  await page.locator('#boss-cinematic .intro-skip-btn:visible').click({timeout:12000});
  await page.waitForFunction(()=>{
    const cta=document.querySelector('#e9-world-stage-primary-cta');
    return !document.querySelector('#boss-cinematic')?.classList.contains('show')
      && cta?.dataset.challengeTargetZone==='k21_25'
      && cta.disabled===false && !cta.hidden;
  },undefined,{timeout:25000});
  stage='click_zone2_training_cta';
  // Landscape drawer owns the ONE visible CTA while open; Product CSS
  // deliberately hides the redundant map CTA. Never force a hidden click.
  const mapCta=page.locator('#e9-world-stage-primary-cta');
  const drawerCta=page.locator('#e9-right-drawer-panel [data-e10-zone-cta]');
  const cardCta=page.locator('#e9-world-stage-details-cta');
  let visibleCta=null;
  if(await drawerCta.isVisible()) visibleCta=drawerCta;
  else if(await mapCta.isVisible()) visibleCta=mapCta;
  else if(await cardCta.isVisible()) visibleCta=cardCta;
  else {
    const handle=page.locator('#e9-right-drawer-toggle');
    assert(await handle.isVisible(), 'NO_VISIBLE_REAL_ZONE2_ACTION_OR_DRAWER_HANDLE');
    await handle.click({timeout:12000});
    await drawerCta.waitFor({state:'visible',timeout:12000});
    visibleCta=drawerCta;
  }
  assert.equal(await visibleCta.getAttribute('data-challenge-target-zone'),'k21_25');
  assert.equal(await visibleCta.isEnabled(),true);
  await visibleCta.click({timeout:16000});
  await page.waitForFunction(()=>{
    const wrap=document.querySelector('#board-canvas-wrap');
    return currentQ?.id===970032 && !!board?.element && !!currentNode
      && !wrap?.classList.contains('hidden')
      && (currentNode?.children||[]).some(c=>c?.move);
  },undefined,{timeout:28000});
  stage='real_wgo_board_click';
  const point=await boardPoint();
  assert.equal(point.qid,970032);
  const expected=page.waitForResponse(r=>
    new URL(r.url()).pathname==='/api/adventure/map-battles/v1/answers'
    &&r.request().method()==='POST',{timeout:22000});
  if (touch) await page.touchscreen.tap(point.px,point.py);
  else await page.mouse.click(point.px,point.py);
  const http=await expected;
  const settled=await http.json();
  assert.equal(http.status(),200,JSON.stringify(settled).slice(0,650));
  assert.equal(settled.accepted,true);
  assert.equal(settled.result,'CORRECT');
  assert.equal(settled.duplicate,false);
  browserCorrect=true;
  stage='durable_bootstrap';
  await page.waitForFunction(async()=>{
    const response=await fetch('/api/adventure/bootstrap',{cache:'no-store',credentials:'include'});
    if(!response.ok)return false;
    const data=await response.json(),z=data.zones.find(x=>x.key==='k21_25');
    return z?.unlocked===true&&z?.correct_count>=2;
  },undefined,{timeout:20000});
  after=await page.evaluate(async()=>{
    const response=await fetch('/api/adventure/bootstrap',{cache:'no-store',credentials:'include'});
    const data=await response.json(),z=data.zones.find(x=>x.key==='k21_25');
    return {unlocked:z.unlocked,correctCount:z.correct_count,
      stars:z.zone_authority_stars,cleared:z.cleared};
  });
  assert.equal(after.stars,0);
  assert.equal(after.cleared,false);
  assert.equal(mapAnswers.length,1);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({verdict:'REAL_E9_ZONE2_WGO_ANSWER_PASS',
    before,after,boardQuestion:point.qid,browserCorrect,stage,
    input:touch?'chrome_tablet_touch':'desktop_mouse',
    realIpad:false,production:false,mapAnswers,badHttp,errors}));
} catch(err) {
  console.error('E9_ZONE2_WGO_BLOCKED',String(err.stack||err),
    JSON.stringify({stage,before,after,browserCorrect,mapAnswers,badHttp,errors,
      current:await page.evaluate(()=>({
        url:location.href,question:typeof currentQ!=='undefined'?currentQ?.id:null,
        cinematic:document.querySelector('#boss-cinematic')?.className,
        cta:document.querySelector('#e9-world-stage-primary-cta')?.outerHTML?.slice(0,280),
        controls:[...document.querySelectorAll('#e9-world-stage-slot button.e9-adventure-cta')].map(b=>({
          id:b.id,hidden:b.hidden,disabled:b.disabled,
          display:getComputedStyle(b).display,visibility:getComputedStyle(b).visibility,
          rect:b.getBoundingClientRect().toJSON(),parentHidden:b.closest('[hidden]')?.id,
          label:b.textContent?.trim().slice(0,80)
        })).slice(0,8),
        stageHidden:document.querySelector('#e9-world-stage-slot')?.closest('[hidden]')?.id,
        viewport:innerWidth+'x'+innerHeight,
        boardHidden:document.querySelector('#board-canvas-wrap')?.classList.contains('hidden'),
      })).catch(()=>null)}));
  process.exitCode=1;
} finally {
  await ctx.close();await browser.close();
}
