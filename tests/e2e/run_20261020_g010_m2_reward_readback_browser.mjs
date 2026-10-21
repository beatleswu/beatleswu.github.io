// G010 M2 full reward READBACK on shipped Hero/Backpack/Shop/Adventure.
// No mock APIs, injected balances, forced clicks, or feature-gate override.
import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';
let stdin='';
for await (const chunk of process.stdin) stdin+=chunk;
const {origin, sessionCookie, coins, totalXp, rankXp, candyQty, zone2, zone3}=JSON.parse(stdin);
assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
assert.equal(zone2,'k21_25'); assert.equal(zone3,'k16_20');
const browser=await chromium.launch({
 headless:true,executablePath:process.env.CHROME_BIN||
 'C:/Program Files/Google/Chrome/Application/chrome.exe',
});
const touch=process.env.GO_G010_M2_TOUCH==='1';
const context=await browser.newContext({
 viewport:touch?{width:820,height:1180}:{width:1280,height:900},
 isMobile:touch,hasTouch:touch,deviceScaleFactor:touch?2:1,
 serviceWorkers:'block',
});
await context.addCookies([{name:'session',value:sessionCookie,url:origin}]);
const page=await context.newPage();
const writes=[],errors=[],failures=[];
page.on('pageerror',e=>errors.push(String(e).slice(0,300)));
page.on('request',r=>{
 const u=new URL(r.url());
 if(u.origin===origin&&u.pathname.startsWith('/api/')&&r.method()!=='GET')
   writes.push(r.method()+' '+u.pathname);
});
page.on('response',r=>{
 const u=new URL(r.url());
 if(u.origin===origin&&u.pathname.startsWith('/api/')&&r.status()>=400)
   failures.push(r.status()+' '+u.pathname);
});
let phase='hero',facts={};
try {
 const hero=await page.goto(origin+'/hero',{waitUntil:'domcontentloaded',timeout:30000});
 assert.equal(hero.status(),200);
 await page.waitForFunction(expected=>{
   const c=document.querySelector('#hero-coins-val')?.textContent?.trim();
   const xp=document.querySelector('#char-xp')?.textContent?.trim();
   return c===Number(expected.coins).toLocaleString('en-US')
     && xp?.includes(Number(expected.rankXp).toLocaleString('en-US'))
     && document.querySelector('#hero-overview-xp')?.textContent?.trim()?.length>2;
 },{coins,rankXp},{timeout:28000});
 facts.hero=await page.evaluate(()=>({
   coins:document.querySelector('#hero-coins-val')?.textContent?.trim(),
   xp:document.querySelector('#char-xp')?.textContent?.trim(),
   xpOverview:document.querySelector('#hero-overview-xp')?.textContent?.trim(),
   bar:document.querySelector('#char-xp-bar')?.style.width,
 }));
 const heroProfile=await page.evaluate(async()=>{
   const r=await fetch('/api/player/presentation',{credentials:'include',cache:'no-store'});
   return {status:r.status,body:await r.json()};
 });
 assert.equal(heroProfile.status,200);
 assert.equal(heroProfile.body.progression.xp,totalXp);
 assert.equal(heroProfile.body.progression.rank_xp,rankXp);

 phase='backpack';
 const inv=await page.goto(origin+'/inventory?category=all',{waitUntil:'domcontentloaded',timeout:30000});
 assert.equal(inv.status(),200);
 await page.waitForFunction(expected=>{
   const coin=document.querySelector('#backpack-coin-balance')?.textContent?.trim();
   const card=document.querySelector('[data-source-item-id="go_spirit_candy"]');
   return coin===Number(expected.coins).toLocaleString('en-US')
     && card?.dataset.inventorySource==='pet_inventory'
     && card?.textContent?.includes(String(expected.candyQty));
 },{coins,candyQty},{timeout:26000});
 facts.backpack=await page.evaluate(()=>({
   coins:document.querySelector('#backpack-coin-balance')?.textContent?.trim(),
   card:document.querySelector('[data-source-item-id="go_spirit_candy"]')?.textContent?.trim()?.slice(0,280),
   source:document.querySelector('[data-source-item-id="go_spirit_candy"]')?.dataset.inventorySource,
   capability:document.querySelector('[data-source-item-id="go_spirit_candy"]')?.dataset.itemCapability,
   forbiddenUseButton:!!document.querySelector('[data-source-item-id="go_spirit_candy"] [data-use-item]'),
   spiritLink:!!document.querySelector('[data-source-item-id="go_spirit_candy"] [data-backpack-spirit-link]'),
 }));
 assert.equal(facts.backpack.source,'pet_inventory');
 assert.equal(facts.backpack.capability,'managed');
 assert.equal(facts.backpack.forbiddenUseButton,false);
 assert.equal(facts.backpack.spiritLink,true);

 phase='shop';
 const shop=await page.goto(origin+'/shop',{waitUntil:'domcontentloaded',timeout:30000});
 assert.equal(shop.status(),200);
 await page.waitForFunction(expected=>
   document.querySelector('#coin-bal')?.textContent?.trim()===
   Number(expected).toLocaleString('en-US'),coins,{timeout:20000});
 facts.shop=await page.evaluate(()=>({
   coins:document.querySelector('#coin-bal')?.textContent?.trim(),
   purchaseEnabled:shopPurchaseEnabled(),
 }));
 assert.equal(facts.shop.purchaseEnabled,false);

 phase='map';
 const main=await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:30000});
 assert.equal(main.status(),200);
 try {
   await page.waitForFunction(()=>document.querySelector('#e9-world-stage-slot')?.__e9WorldStageState?.zones
      ?.some(z=>z.key==='k16_20'&&z.locked===false),undefined,{timeout:12000});
 } catch {
   const diag=await page.evaluate(()=>({
      slot:!!document.querySelector('#e9-world-stage-slot'),
      rootZones:document.querySelector('#e9-world-stage-slot')?.__e9WorldStageState?.zones
        ?.map(z=>({key:z.key,locked:z.locked,unlocked:z.unlocked,
                   canEnter:z.canEnter,status:z.status,stars:z.stars})),
      rootState:document.querySelector('#e9-world-stage-slot')?.__e9WorldStageState?.primaryAction,
      currentZone:document.querySelector('#e9-world-stage-slot')?.__e9WorldStageState?.currentZoneKey,
      startupReady:window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__,
      error:window.__GO_ADVENTURE_QUESTION_RUNTIME_ERROR__,
   }));
   throw new Error('G010_M2_ZONE3_CLIENT_MAP_NOT_READY '+JSON.stringify(diag));
 }
 const map=await page.evaluate(async()=>{
   const r=await fetch('/api/adventure/bootstrap',{cache:'no-store',credentials:'include'});
   return {http:r.status,data:await r.json()};
 });
 assert.equal(map.http,200);
 const z2=map.data.zones.find(z=>z.key===zone2),
       z3=map.data.zones.find(z=>z.key===zone3);
 assert.equal(z2.cleared,true);
 assert(z2.zone_authority_stars>=1);
 assert.equal(z3.unlocked,true);
 facts.map={zone2Cleared:z2.cleared,zone2Stars:z2.zone_authority_stars,
   zone3Unlocked:z3.unlocked};
 assert.deepEqual(errors,[]);
 assert.deepEqual(writes,[]);
 assert.deepEqual(failures,[]);
 console.log(JSON.stringify({verdict:'G010_M2_REAL_PLAYER_REWARD_SURFACES_PASS',
   input:touch?'chrome_tablet_touch':'desktop_mouse',
   production:false,realIpad:false,mockApis:false,
   facts,writes,failures,pageErrors:errors}));
}catch(e){
 console.error('G010_M2_BROWSER_REWARD_READBACK_FAILED',
   phase,String(e.stack||e),JSON.stringify({facts,writes,failures,errors,url:page.url()}));
 process.exitCode=1;
}finally{await context.close();await browser.close();}
