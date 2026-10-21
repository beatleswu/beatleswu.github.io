// M3 real DOM clicks with exactly one in-memory activated G009 preview page.
// The backend is unmocked native PostgreSQL and original Flask routes.
// Production HTML files remain locked; no browser API interception.
import assert from 'node:assert/strict';
// Use the already-installed authorized beatles Playwright runtime; no npm install.
import {chromium} from 'file:///D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core/index.mjs';
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
 phase='consumable_use';
 // This XP potion is a separately seeded synthetic already-owned item,
 // never represented as a legacy-shop purchase. The existing Backpack
 // button exercises the unmocked item-consumption server route.
 const potionCard=page.locator('[data-source-item-id="xp_potion"]');
 await potionCard.waitFor({state:'visible',timeout:18000});
 const potionUse=potionCard.locator('[data-use-item="xp_potion"]');
 await potionUse.waitFor({state:'visible',timeout:9000});
 assert.equal(await potionUse.isEnabled(),true);
 await potionUse.click({timeout:13000});
 await page.waitForFunction(()=>!document.querySelector(
  '[data-source-item-id="xp_potion"]'),undefined,{timeout:23000});
 assert.equal(writes.filter(x=>x==='POST /api/shop/use').length,1);
 phase='new_session';
 const fresh=await createContext(reloginCookie);
 try{
  const p=await fresh.newPage();
  await p.goto(origin+'/inventory?equipment='+wanted,{waitUntil:'domcontentloaded',timeout:30000});
  await p.waitForFunction(id=>document.querySelector('[data-functional-inv-id="'+id+'"]')?.dataset.equipped==='true',
    wanted,{timeout:20000});
  await p.waitForFunction(()=>document.querySelector('#backpack-coin-balance')?.dataset.g009BalanceState==='authoritative',
    undefined,{timeout:20000});
  assert.equal(await p.locator('[data-source-item-id="xp_potion"]').count(),0);
  await p.goto(origin+'/shop',{waitUntil:'domcontentloaded',timeout:30000});
  await p.waitForFunction(({key,expected})=>{
    const btn=document.querySelector('[data-equipment-purchase="'+key+'"]');
    return btn?.disabled===true&&document.querySelector('#coin-bal')?.textContent?.trim()===Number(expected).toLocaleString('en-US');
  },{key:offerId,expected:startingCoins-price},{timeout:24000});
  assert.equal(await p.locator('[data-equipment-purchase="'+offerId+'"]').first().isEnabled(),false);
 } finally { await fresh.close(); }
 assert.deepEqual(errors,[]);
 assert.deepEqual(responseErrors,[]);
 assert.equal(writes.filter(x=>x==='POST /api/shop/buy').length,1);
 assert.equal(writes.filter(x=>x==='POST /api/player/inventory/equip').length,1);
 assert.equal(writes.filter(x=>x==='POST /api/shop/use').length,1);
 console.log(JSON.stringify({verdict:'G010_M3_REAL_BROWSER_PURCHASE_EQUIP_RELOGIN_PASS',
  input:touch?'chrome_tablet_touch':'desktop_mouse',production:false,
  originalReleasePreviewLocked:true,renderedPageIsTestOnlyActivatedVariant:true,
  itemId,offerId,invId:wanted,price,coinsAfter:startingCoins-price,
  buyFacts,writes,pageErrors:errors,responseErrors}));
}catch(e){
 console.error('G010_M3_BROWSER_STAGE_FAIL',phase,String(e.stack||e),
   JSON.stringify({writes,responseErrors,errors,url:page.url()}));
 process.exitCode=1;
}finally{
 await context.close();await browser.close();
}
