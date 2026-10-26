// M3 real DOM clicks with exactly one in-memory activated G009 preview page.
// The backend is unmocked native PostgreSQL and original Flask routes.
// Production HTML files remain locked; no browser API interception.
import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';
let input='';
for await(const c of process.stdin) input+=c;
const {origin,sessionCookie,reloginCookie,offerId,itemId,price,startingCoins}=JSON.parse(input);
assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const touch=process.env.GO_G010_M3_TOUCH==='1';
const browser=await chromium.launch({
 headless:true,executablePath:process.env.CHROME_BIN||
 'C:/Program Files/Google/Chrome/Application/chrome.exe',
});
const createContext=async cookie=>{
 const context=await browser.newContext({
  viewport:touch?{width:820,height:1180}:{width:1280,height:900},
  isMobile:touch,hasTouch:touch,deviceScaleFactor:touch?2:1,
  serviceWorkers:'block',
 });
 await context.addCookies([{name:'session',value:cookie,url:origin}]);
 return context;
};
const context=await createContext(sessionCookie);
const page=await context.newPage();
const writes=[],errors=[],responseErrors=[];
page.on('pageerror',e=>errors.push(String(e).slice(0,400)));
page.on('request',r=>{
 const u=new URL(r.url());
 if(u.origin===origin&&u.pathname.startsWith('/api/')&&r.method()!=='GET')
  writes.push(r.method()+' '+u.pathname);
});
page.on('response',r=>{
 const u=new URL(r.url());
 if(u.origin===origin&&u.pathname.startsWith('/api/')&&r.status()>=400)
  responseErrors.push(r.status()+' '+u.pathname);
});
let phase='shop';
try{
 const shop=await page.goto(origin+'/shop',{waitUntil:'domcontentloaded',timeout:30000});
 assert.equal(shop.status(),200);
 const button=page.locator('[data-equipment-purchase="'+offerId+'"]').first();
 await button.waitFor({state:'visible',timeout:28000});
 await page.waitForFunction(key=>{
  const b=document.querySelector('[data-equipment-purchase="'+key+'"]');
  return b && !b.disabled && shopPurchaseEnabled()
    && document.querySelector('#shop-purchase-state')?.dataset.purchaseEnabled==='true';
 },offerId,{timeout:26000});
 const before=await page.locator('#coin-bal').textContent();
 assert.equal(before.trim(),Number(startingCoins).toLocaleString('en-US'));
 // The real UI sends the purchase; a second rapid click must be ignored
 // while the first is pending, and server remains final authority.
 await button.dblclick({timeout:17000});
 await page.waitForFunction(expected=>{
  const feedback=document.querySelector('#equipment-purchase-feedback');
  return feedback?.dataset.state==='success'
    && document.querySelector('#coin-bal')?.textContent?.trim()
       ===Number(expected).toLocaleString('en-US');
 },startingCoins-price,{timeout:32000});
 const buyWrites=writes.filter(x=>x==='POST /api/shop/buy');
 assert.equal(buyWrites.length,1,'UI must not duplicate the POST on double-click');
 const buyFacts=await page.evaluate(key=>({
  result:document.querySelector('#equipment-purchase-feedback')?.dataset.state,
  coins:document.querySelector('#coin-bal')?.textContent?.trim(),
  backpackHref:document.querySelector('#equipment-purchase-feedback-backpack')?.getAttribute('href'),
  owned:document.querySelector('[data-equipment-purchase="'+key+'"]')?.disabled,
  purchaseEnabled:shopPurchaseEnabled(),
 }),offerId);
 assert.match(buyFacts.backpackHref,/^\/inventory\?equipment=\d+$/);
 assert.equal(buyFacts.owned,true);
 phase='backpack';
 // Follow actual in-game "Go to Backpack" link, never navigate an invented path.
 await page.locator('#equipment-purchase-feedback-backpack').click({timeout:17000});
 await page.waitForURL(u=>u.pathname==='/inventory',{timeout:20000});
 const wanted=new URL(page.url()).searchParams.get('equipment');
 assert.match(wanted,/^[1-9]\d*$/);
 const inventoryCard=page.locator('[data-functional-inv-id="'+wanted+'"]');
 await inventoryCard.waitFor({state:'visible',timeout:28000});
 await page.waitForFunction(id=>{
  const card=document.querySelector('[data-functional-inv-id="'+id+'"]');
  return card?.dataset.equipped==='false' && functionalEquipmentLoadoutEnabled();
 },wanted,{timeout:22000});
 await inventoryCard.click({timeout:10000});
 const equipButton=page.locator('#functional-detail-action');
 try { await equipButton.waitFor({state:'visible',timeout:3500}); }
 catch(error) {
  const debug=await page.evaluate(()=>{
   const a=document.querySelector('#functional-detail-action');
   return {g009:G009_BACKPACK_READ_ONLY,e10:E10_BACKPACK_MODE,
    capability:functionalEquipmentLoadoutEnabled(),
    hidden:a?.hidden,display:a&&getComputedStyle(a).display,
    parentDisplay:a&&getComputedStyle(a.parentElement).display,
    contentHidden:document.querySelector('#functional-equipment-detail-content')?.hidden,
    sectionDisplay:getComputedStyle(document.querySelector('[data-functional-equipment-backpack]')).display,
    outer:a?.outerHTML?.slice(0,400),
    selectors:Array.from(document.styleSheets).flatMap(sheet=>{
      try{return Array.from(sheet.cssRules).filter(rule=>rule.selectorText&&
        a?.matches(rule.selectorText)&&rule.style?.display)
        .map(rule=>({selector:rule.selectorText,display:rule.style.display,
                    important:rule.style.getPropertyPriority('display')}));}
      catch{return [];}
    }).slice(-18)};
  });
  throw new Error('REAL_EQUIP_ACTION_NOT_VISIBLE '+JSON.stringify(debug));
 }
 assert.equal(await equipButton.isEnabled(),true);
 await equipButton.click({timeout:13000});
 await page.waitForFunction(({id,expected})=>{
  const card=document.querySelector('[data-functional-inv-id="'+id+'"]');
  return card?.dataset.equipped==='true'
    && document.querySelector('#backpack-coin-balance')?.textContent?.trim()
      ===Number(expected).toLocaleString('en-US');
 },{id:wanted,expected:startingCoins-price},{timeout:23000}).catch(async()=>{
   const facts=await page.evaluate(id=>({
    card:document.querySelector('[data-functional-inv-id="'+id+'"]')?.outerHTML?.slice(0,330),
    coins:document.querySelector('#backpack-coin-balance')?.textContent,
    status:document.querySelector('#functional-equipment-status')?.textContent,
   }),wanted);
   throw new Error('BACKPACK_EQUIP_WRITEBACK_FAILED '+JSON.stringify(facts));
 });
 phase='true_3d_hero';
 await page.goto(origin+'/hero?tab=equipment',{waitUntil:'domcontentloaded',timeout:36000});
 await page.waitForFunction(()=>document.querySelector('#g008-future30-hero-stage')?.dataset.state==='ready',
  undefined,{timeout:50000});
 const expected='WEAPON_628812E9B559';
 const inspect=async p=>p.evaluate(async()=>{
  const mod=await import('/js/g008_future30_hero_renderer.js');
  return {hero:document.querySelector('#g008-future30-hero-stage')?.dataset.state,
    canvas:!!document.querySelector('#g008-future30-hero-stage canvas'),
    diagnostics:mod.getHeroSharedAttachmentHost()?.diagnostics()||null};
 });
 await page.waitForFunction(async asset=>{
  const mod=await import('/js/g008_future30_hero_renderer.js');
  return mod.getHeroSharedAttachmentHost()?.diagnostics()?.slots?.some(
    s=>s.slot==='MAIN_HAND'&&s.presentation_id===asset&&s.child_count===1);
 },expected,{timeout:42000});
 const hero=await inspect(page);
 assert.equal(hero.hero,'ready');assert(hero.canvas);
 const main=hero.diagnostics.slots.find(x=>x.slot==='MAIN_HAND');
 assert.equal(main.presentation_id,expected);
 assert.equal(main.child_count,1);
 const inv=await page.evaluate(async()=>{
  const r=await fetch('/api/player/inventory',{credentials:'include',cache:'no-store'});
  if(!r.ok)throw Error('inventory_get_'+r.status);
  return r.json();
 });
 assert.equal(inv.find(x=>x.item_id===itemId)?.equipped,true);
 phase='new_session';
 const fresh=await createContext(reloginCookie);
 const uxEvidence={};
 let freshHero;
 try {
  const p=await fresh.newPage();
  let inventoryReadCount=0;
  // Real localhost inventory GET; 3.2-second delay only, never a fake item.
  await p.route('**/api/player/inventory',async route=>{
    inventoryReadCount++;
    await new Promise(resolve=>setTimeout(resolve,3200));
    await route.continue();
  });
  await p.goto(origin+'/hero?tab=equipment',{waitUntil:'domcontentloaded',timeout:34000});
  await p.waitForFunction(()=>{
    const stage=document.querySelector('#g008-future30-hero-stage');
    const notice=document.querySelector('#g008-hero-load-notice');
    return stage?.dataset.state==='loading' && notice?.hidden===false;
  },undefined,{timeout:14000});
  uxEvidence.loading=await p.evaluate(()=>({
    state:document.querySelector('#g008-future30-hero-stage')?.dataset.state,
    shown:!document.querySelector('#g008-hero-load-notice')?.hidden,
    label:document.querySelector('#g008-hero-load-message')?.textContent,
    retryHidden:document.querySelector('#g008-hero-retry')?.hidden
  }));
  assert.equal(uxEvidence.loading.state,'loading');
  assert.equal(uxEvidence.loading.shown,true);
  assert.match(uxEvidence.loading.label,/同步/);
  assert.equal(uxEvidence.loading.retryHidden,true);
  await p.waitForFunction(async asset=>{
   const m=await import('/js/g008_future30_hero_renderer.js');
   return document.querySelector('#g008-future30-hero-stage')?.dataset.state==='ready'&&
    m.getHeroSharedAttachmentHost()?.diagnostics()?.slots?.some(
     s=>s.slot==='MAIN_HAND'&&s.presentation_id===asset&&s.child_count===1);
  },expected,{timeout:50000});
  // Hero may remount once during the initial authenticated character bootstrap.
  // A stable real hand attachment, not just a transient ready flag, is the gate.
  // A single ready frame may be superseded by authenticated rehydration.
  // Verify attachment remains stable for 600ms before accepting, while
  // the product loading notice continues to distinguish incomplete state.
  let stable=false;
  for(let attempt=0;attempt<85;attempt++){
    freshHero=await inspect(p);
    const hand=freshHero.diagnostics?.slots?.find(s=>s.slot==='MAIN_HAND');
    if(freshHero.hero==='ready'&&hand?.presentation_id===expected&&hand?.child_count===1){
      await p.waitForTimeout(600);
      freshHero=await inspect(p);
      const again=freshHero.diagnostics?.slots?.find(s=>s.slot==='MAIN_HAND');
      if(freshHero.hero==='ready'&&again?.presentation_id===expected&&again?.child_count===1){
        stable=true;
        break;
      }
    }
    await p.waitForTimeout(300);
  }
  assert.equal(stable,true,'Hero equipment did not rehydrate to stable ready within bounded 30s');
  assert.equal(freshHero.diagnostics?.slots?.find(s=>s.slot==='MAIN_HAND')?.presentation_id,expected);
  uxEvidence.initialReady=await p.evaluate(()=>({
    state:document.querySelector('#g008-future30-hero-stage')?.dataset.state,
    noticeHidden:document.querySelector('#g008-hero-load-notice')?.hidden,
    busy:document.querySelector('#char-avatar')?.getAttribute('aria-busy')
  }));
  assert.deepEqual(uxEvidence.initialReady,
    {state:'ready',noticeHidden:true,busy:'false'});
  // Negative test: only ONE future inventory HTTP request receives a 503,
  // intentionally exercising the product's fail-closed equipment projection.
  // No ownership/coins/answer is forged or changed.
  let failOnce=true;
  await p.route('**/api/player/inventory',async route=>{
    if(failOnce){
      failOnce=false;
      return route.fulfill({status:503,contentType:'application/json',
        body:JSON.stringify({error:'isolated_network_outage'})});
    }
    return route.continue();
  });
  await p.evaluate(()=>window.__G008_FUTURE30_REFRESH__());
  await p.waitForFunction(()=>{
    const hero=window.__G008_HERO_RENDER_STATE__;
    return hero?.state==='ready' && hero.equipment_status==='unavailable'
      && document.querySelector('#g008-hero-load-notice')?.hidden===false
      && document.querySelector('#g008-hero-retry')?.hidden===false;
  },undefined,{timeout:42000});
  uxEvidence.failedClosed=await p.evaluate(()=>({
    state:window.__G008_HERO_RENDER_STATE__?.state,
    equipmentStatus:window.__G008_HERO_RENDER_STATE__?.equipment_status,
    label:document.querySelector('#g008-hero-load-message')?.textContent,
    retryVisible:!document.querySelector('#g008-hero-retry')?.hidden,
  }));
  assert.match(uxEvidence.failedClosed.label,/裝備暫時/);
  uxEvidence.retryTouchTarget=await p.locator('#g008-hero-retry')
    .evaluate(el=>({width:el.getBoundingClientRect().width,
      height:el.getBoundingClientRect().height}));
  assert(uxEvidence.retryTouchTarget.height>=44,
    'visible Hero recovery touch target height must be at least 44 CSS px');
  assert(uxEvidence.retryTouchTarget.width>=44,
    'visible Hero recovery touch target width must be at least 44 CSS px');
  await p.locator('#g008-hero-retry').click({timeout:10000});
  await p.waitForFunction(async id=>{
    const m=await import('/js/g008_future30_hero_renderer.js');
    const row=m.getHeroSharedAttachmentHost()?.diagnostics()?.slots?.find(s=>s.slot==='MAIN_HAND');
    return window.__G008_HERO_RENDER_STATE__?.state==='ready'
      && window.__G008_HERO_RENDER_STATE__?.equipment_status==='ready'
      && row?.presentation_id===id && row.child_count===1
      && document.querySelector('#g008-hero-load-notice')?.hidden===true;
  },expected,{timeout:50000});
  // An authenticated renderer may briefly become ready and remount again.
  // Do not accept an intermediate frame as user-visible recovery.
  let retryStable=false;
  for(let attempt=0;attempt<85;attempt++){
    const snapshot=await p.evaluate(async asset=>{
      const mod=await import('/js/g008_future30_hero_renderer.js');
      const hand=mod.getHeroSharedAttachmentHost()?.diagnostics()?.slots?.find(s=>s.slot==='MAIN_HAND');
      return {state:document.querySelector('#g008-future30-hero-stage')?.dataset.state,
        busy:document.querySelector('#char-avatar')?.getAttribute('aria-busy'),
        noticeHidden:document.querySelector('#g008-hero-load-notice')?.hidden,
        handId:hand?.presentation_id,childCount:hand?.child_count};
    },expected);
    if(snapshot.state==='ready'&&snapshot.busy==='false'
      &&snapshot.noticeHidden===true&&snapshot.handId===expected&&snapshot.childCount===1){
      await p.waitForTimeout(650);
      const next=await p.evaluate(async()=>{
        const mod=await import('/js/g008_future30_hero_renderer.js');
        const hand=mod.getHeroSharedAttachmentHost()?.diagnostics()?.slots?.find(s=>s.slot==='MAIN_HAND');
        return {state:document.querySelector('#g008-future30-hero-stage')?.dataset.state,
          busy:document.querySelector('#char-avatar')?.getAttribute('aria-busy'),
          noticeHidden:document.querySelector('#g008-hero-load-notice')?.hidden,
          handId:hand?.presentation_id,childCount:hand?.child_count};
      });
      if(next.state==='ready'&&next.busy==='false'
        &&next.noticeHidden===true&&next.handId===expected&&next.childCount===1){
        retryStable=true;
        uxEvidence.retryRecovered=next;
        break;
      }
    }
    await p.waitForTimeout(280);
  }
  assert.equal(retryStable,true,'Hero retry never converged to stable ready with actual equipped hand');
  freshHero=await inspect(p);
  uxEvidence.realInventoryGetCount=inventoryReadCount;
  uxEvidence.isolatedTransient503InjectedOnce=!failOnce;
  // Reproduce registration arriving AFTER the WebGL parent becomes ready.
  // Delay only the actual JavaScript module response: no fake inventory,
  // weapon payload, judge, or equipment state is ever supplied.
  const lateContext=await createContext(reloginCookie);
  try {
    const late=await lateContext.newPage();
    let delayed=false;
    await late.route('**/js/g009_d_r2_shared_host_bootstrap.js',async route=>{
      if(!delayed){
        delayed=true;
        await new Promise(resolve=>setTimeout(resolve,4500));
      }
      await route.continue();
    });
    await late.goto(origin+'/hero?tab=equipment',
      {waitUntil:'domcontentloaded',timeout:35000});
    await late.waitForFunction(()=>{
      const state=window.__G008_HERO_RENDER_STATE__;
      const notice=document.querySelector('#g008-hero-load-notice');
      const retry=document.querySelector('#g008-hero-retry');
      return state?.state==='ready'&&state.equipment_status==='pending'
        &&notice?.hidden===false&&retry?.hidden===false;
    },undefined,{timeout:21000});
    uxEvidence.lateRegistrationPending=await late.evaluate(()=>({
      state:window.__G008_HERO_RENDER_STATE__?.state,
      equipmentStatus:window.__G008_HERO_RENDER_STATE__?.equipment_status,
      message:document.querySelector('#g008-hero-load-message')?.textContent,
      retryVisible:!document.querySelector('#g008-hero-retry')?.hidden
    }));
    assert.equal(uxEvidence.lateRegistrationPending.equipmentStatus,'pending');
    assert.match(uxEvidence.lateRegistrationPending.message,/等待/);
    assert.equal(delayed,true);
    await late.waitForFunction(async id=>{
      const mod=await import('/js/g008_future30_hero_renderer.js');
      const slot=mod.getHeroSharedAttachmentHost()?.diagnostics()?.slots
        ?.find(s=>s.slot==='MAIN_HAND');
      return window.__G008_HERO_RENDER_STATE__?.state==='ready'
        &&window.__G008_HERO_RENDER_STATE__?.equipment_status==='ready'
        &&slot?.presentation_id===id&&slot?.child_count===1
        &&document.querySelector('#g008-hero-load-notice')?.hidden===true;
    },expected,{timeout:42000});
    // Initial ready may be followed by character bootstrap remount.
    // Demand a stable loaded attachment and clean UX across 650 ms.
    let lateStable=false;
    for(let n=0;n<70;n++){
      const state=await late.evaluate(async()=>{
        const mod=await import('/js/g008_future30_hero_renderer.js');
        const hand=mod.getHeroSharedAttachmentHost()?.diagnostics()?.slots
          ?.find(s=>s.slot==='MAIN_HAND');
        return {state:window.__G008_HERO_RENDER_STATE__?.state,
          equipmentStatus:window.__G008_HERO_RENDER_STATE__?.equipment_status,
          noticeHidden:document.querySelector('#g008-hero-load-notice')?.hidden,
          hand:hand?.presentation_id,children:hand?.child_count};
      });
      if(state.state==='ready'&&state.equipmentStatus==='ready'
        &&state.noticeHidden===true&&state.hand===expected&&state.children===1){
        await late.waitForTimeout(650);
        const still=await late.evaluate(async()=>{
          const mod=await import('/js/g008_future30_hero_renderer.js');
          const hand=mod.getHeroSharedAttachmentHost()?.diagnostics()?.slots
            ?.find(s=>s.slot==='MAIN_HAND');
          return {state:window.__G008_HERO_RENDER_STATE__?.state,
            equipmentStatus:window.__G008_HERO_RENDER_STATE__?.equipment_status,
            noticeHidden:document.querySelector('#g008-hero-load-notice')?.hidden,
            hand:hand?.presentation_id,children:hand?.child_count};
        });
        if(still.state==='ready'&&still.equipmentStatus==='ready'
          &&still.noticeHidden===true&&still.hand===expected&&still.children===1){
          lateStable=true;
          uxEvidence.lateRegistrationRecovered=still;
          break;
        }
      }
      await late.waitForTimeout(260);
    }
    assert.equal(lateStable,true,'Late equipment rehydrator did not settle to stable server-owned ready state');
  } finally {await lateContext.close();}
  // Persistent read outage: repeated explicit retry must never invent a
  // weapon, claim settled, or turn the UI green with missing server data.
  const outageContext=await createContext(reloginCookie);
  try {
    const outage=await outageContext.newPage();
    let inventoryFailures=0;
    await outage.route('**/api/player/inventory',async route=>{
      inventoryFailures++;
      await route.fulfill({status:503,contentType:'application/json',
        body:JSON.stringify({error:'test_only_persistent_inventory_unavailable'})});
    });
    await outage.goto(origin+'/hero?tab=equipment',
      {waitUntil:'domcontentloaded',timeout:35000});
    await outage.waitForFunction(()=>window.__G008_HERO_RENDER_STATE__?.state==='ready'
      &&window.__G008_HERO_RENDER_STATE__?.equipment_status==='unavailable'
      &&document.querySelector('#g008-hero-retry')?.hidden===false,
      undefined,{timeout:33000});
    await outage.locator('#g008-hero-retry').click({timeout:10000});
    await outage.waitForFunction(()=>{
      const label=window.__G008_HERO_RENDER_STATE__;
      return label?.state==='ready' && label?.equipment_status==='unavailable'
        && document.querySelector('#g008-hero-retry')?.hidden===false;
    },undefined,{timeout:40000});
    await outage.waitForFunction(()=>document.querySelector('#g008-hero-retry')?.disabled===false,
      undefined,{timeout:40000});
    assert(inventoryFailures>=2,
      'persistent outage test must observe a separate new inventory GET from retry');
    uxEvidence.persistentOutage=await outage.evaluate(async()=>{
      const mod=await import('/js/g008_future30_hero_renderer.js');
      return {state:window.__G008_HERO_RENDER_STATE__?.state,
        equipmentStatus:window.__G008_HERO_RENDER_STATE__?.equipment_status,
        retryVisible:!document.querySelector('#g008-hero-retry')?.hidden,
        hand:mod.getHeroSharedAttachmentHost()?.diagnostics()?.slots
          ?.find(s=>s.slot==='MAIN_HAND')?.presentation_id??null};
    });
    uxEvidence.persistentOutage.inventoryFailures=inventoryFailures;
    assert.equal(uxEvidence.persistentOutage.equipmentStatus,'unavailable');
    assert.equal(uxEvidence.persistentOutage.retryVisible,true);
    assert.equal(uxEvidence.persistentOutage.hand,null);
  }finally{await outageContext.close();}
  await p.goto(origin+'/inventory?equipment='+wanted,{waitUntil:'domcontentloaded',timeout:30000});
  await p.waitForFunction(id=>document.querySelector('[data-functional-inv-id="'+id+'"]')?.dataset.equipped==='true',wanted,{timeout:22000});
  await p.goto(origin+'/shop',{waitUntil:'domcontentloaded',timeout:30000});
  await p.waitForFunction(({key,expected})=>{
   const btn=document.querySelector('[data-equipment-purchase="'+key+'"]');
   return btn?.disabled===true&&document.querySelector('#coin-bal')?.textContent?.trim()===Number(expected).toLocaleString('en-US');
  },{key:offerId,expected:startingCoins-price},{timeout:24000});
 }finally{await fresh.close()}
 assert.deepEqual(errors,[]);
 assert.deepEqual(responseErrors,[]);
 assert.equal(writes.filter(x=>x==='POST /api/shop/buy').length,1);
 assert.equal(writes.filter(x=>x==='POST /api/player/inventory/equip').length,1);
 assert.equal(writes.filter(x=>x==='POST /api/shop/use').length,0);
 console.log(JSON.stringify({verdict:'G011_REAL_PG_PURCHASE_EQUIP_TRUE_HERO_GL_B_RELOGIN_PASS',
  input:touch?'chrome_tablet_touch':'desktop_mouse',production:false,
  originalReleasePreviewLocked:true,renderedPageIsTestOnlyActivatedVariant:true,
  itemId,offerId,invId:wanted,price,coinsAfter:startingCoins-price,
  buyFacts,hero,freshHero,uxEvidence,writes,pageErrors:errors,responseErrors}));
}catch(e){
 console.error('G010_M3_BROWSER_STAGE_FAIL',phase,String(e.stack||e),
   JSON.stringify({writes,responseErrors,errors,url:page.url()}));
 process.exitCode=1;
}finally{
 await context.close();await browser.close();
}
