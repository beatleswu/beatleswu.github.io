// Real, authenticated Shop + Backpack presentation on disposable PostgreSQL.
// The Product intentionally locks purchasing and loadout in this browser pass.
// Never intercept APIs, fake inventory, or click a hidden purchasing control.
import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

let raw = '';
for await (const chunk of process.stdin) raw += chunk;
const {origin, sessionCookie, expectedInvId} = JSON.parse(raw);
assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
assert(sessionCookie);
const browser = await chromium.launch({
  headless:true, executablePath:process.env.CHROME_BIN ||
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
});
const context = await browser.newContext({
  viewport:{width:1280,height:900}, serviceWorkers:'block',
});
await context.addCookies([{name:'session',value:sessionCookie,url:origin}]);
const page = await context.newPage();
const pageErrors = [], writes = [], httpFailures=[];
page.on('pageerror',e => pageErrors.push(String(e).slice(0,300)));
page.on('request',r => {
  const u = new URL(r.url());
  if (u.origin===origin && u.pathname.startsWith('/api/') && r.method()!=='GET')
    writes.push(r.method()+' '+u.pathname);
});
page.on('response',r=>{
  const u=new URL(r.url());
  if(u.origin===origin && u.pathname.startsWith('/api/') && r.status()>=400)
    httpFailures.push(r.status()+' '+u.pathname);
});
let phase='shop';
try {
  const shop=await page.goto(origin+'/shop',{waitUntil:'domcontentloaded',timeout:30000});
  assert.equal(shop.status(),200);
  await page.waitForFunction(()=>
    document.querySelector('#coin-bal')?.textContent?.trim()==='700'
    && document.querySelector('#shop-purchase-state')?.dataset.purchaseEnabledSource==='g009-browse-preview-locked',
    undefined,{timeout:25000});
  const shopFacts=await page.evaluate(()=>({
    coins:document.querySelector('#coin-bal')?.textContent?.trim(),
    buyEnabled:shopPurchaseEnabled(),
    previewSource:document.querySelector('#shop-purchase-state')?.dataset.purchaseEnabledSource,
    pagePurchaseFlag:document.querySelector('#shop-purchase-state')?.dataset.purchaseEnabled,
    previewCopy:document.querySelector('#shop-purchase-state')?.textContent?.trim()?.slice(0,160),
  }));
  assert.equal(shopFacts.coins,'700');
  assert.equal(shopFacts.buyEnabled,false);
  assert.equal(shopFacts.pagePurchaseFlag,'false');
  phase='inventory';
  const inv=await page.goto(origin+'/inventory',{waitUntil:'domcontentloaded',timeout:30000});
  assert.equal(inv.status(),200);
  await page.waitForFunction((wanted)=>{
    const c=document.querySelector('[data-functional-inv-id="'+wanted+'"]');
    return c?.dataset.equipped==='true' &&
      document.querySelector('#backpack-coin-balance')?.textContent?.trim()==='700';
  },String(expectedInvId),{timeout:28000});
  const inventoryFacts=await page.evaluate((wanted)=>({
    coins:document.querySelector('#backpack-coin-balance')?.textContent?.trim(),
    loadoutEnabled:typeof functionalEquipmentLoadoutEnabled==='function'?
      functionalEquipmentLoadoutEnabled():null,
    item:typeof functionalEquipmentItems==='undefined'?null:
      functionalEquipmentItems.find(x=>String(x.inv_id)===String(wanted)),
    card:document.querySelector('[data-functional-inv-id="'+wanted+'"]')?.dataset.equipped,
    status:document.querySelector('#functional-equipment-status')?.textContent?.trim(),
  }),String(expectedInvId));
  assert.equal(inventoryFacts.coins,'700');
  assert.equal(inventoryFacts.card,'true');
  assert.equal(inventoryFacts.loadoutEnabled,false);
  assert.equal(inventoryFacts.item?.equipped,true);
  assert.equal(writes.length,0,'read-only browsing cannot mutate player');
  assert.deepEqual(pageErrors,[]);
  console.log(JSON.stringify({verdict:'REAL_SHOP_BACKPACK_GOVERNED_BROWSER_PASS',
    realProduct:true,disposablePostgres:true,production:false,
    shop:shopFacts,backpack:{
      coins:inventoryFacts.coins,itemId:inventoryFacts.item?.id,
      itemName:inventoryFacts.item?.name,invId:inventoryFacts.item?.inv_id,
      equipped:inventoryFacts.item?.equipped,
      loadoutEnabled:inventoryFacts.loadoutEnabled,
    },writes,httpFailures,pageErrors}));
} catch(error) {
  console.error('REAL_SHOP_BACKPACK_BROWSER_BLOCKED',phase,
    String(error.stack||error),JSON.stringify({writes,httpFailures,pageErrors,
    url:page.url()}));
  process.exitCode=1;
} finally {
  await context.close();await browser.close();
}
