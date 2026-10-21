// G019 regression: original Shop & Backpack must remain visually closed when
// any of three independent SERVER gates is false. No HTML substitutions.
import assert from "node:assert/strict";
import {chromium} from "file:///D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core/index.mjs";
let t="";for await(const x of process.stdin)t+=x;
const {origin,cookie,invId,expectedShopBackend,expectedShopUi}=JSON.parse(t);
const browser=await chromium.launch({headless:true,
 executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const context=await browser.newContext({serviceWorkers:"block"});
await context.addCookies([{name:"session",value:cookie,url:origin}]);
const page=await context.newPage();
const errors=[],writes=[];
page.on("pageerror",e=>errors.push(String(e)));
page.on("request",r=>{
 if(r.method()!=="GET" && new URL(r.url()).pathname.startsWith("/api/"))
  writes.push(r.method()+" "+new URL(r.url()).pathname);
});
try{
 const response=await page.goto(origin+"/shop",{waitUntil:"domcontentloaded",timeout:28000});
 assert.equal(response.status(),200);
 await page.waitForFunction(()=>
   document.querySelector('#coin-bal')?.dataset.c044BalanceState==="authoritative",
   undefined,{timeout:25000});
 const shop=await page.evaluate(()=>{
  const catalogKnown=typeof catalog!=="undefined"&&catalog&&!catalog.error;
  const buttons=[...document.querySelectorAll("[data-equipment-purchase]")];
  return {catalogKnown,backend:catalog?.purchase_enabled,
   release:catalog?.approved_equipment_purchase_ui_enabled,
   g019:g019ServerApprovedEquipmentUi(catalog),
   equipmentCount:catalog?.equipment_offers?.length,
   enabledButtons:buttons.filter(x=>!x.disabled && !x.hidden && x.getClientRects().length>0).length,
   unexpectedEnabled:buttons.filter(x=>!x.disabled && !x.hidden && x.getClientRects().length>0).map(x=>x.outerHTML.slice(0,650)),
   totalButtons:buttons.length,
   publicPurchase:shopPurchaseEnabled(),
   status:document.querySelector("#equipment-commerce-panel")?.dataset.g019CanonicalPurchaseUi};
 });
 assert.equal(shop.catalogKnown,true);
 assert.equal(shop.backend,expectedShopBackend);
 assert.equal(shop.release,expectedShopUi);
 assert.equal(shop.g019,false);
 assert.equal(shop.publicPurchase,false);
 assert.equal(shop.enabledButtons,0,JSON.stringify(shop));
 const inv=await page.goto(origin+"/inventory?equipment="+invId,
   {waitUntil:"domcontentloaded",timeout:28000});
 assert.equal(inv.status(),200);
 await page.locator('[data-functional-inv-id="'+invId+'"]').waitFor(
   {state:"visible",timeout:23000});
 await page.locator('[data-functional-inv-id="'+invId+'"]').click();
 const bp=await page.evaluate(()=>{
  const action=document.querySelector("#functional-detail-action");
  return {hidden:action?.hidden,disabled:action?.disabled,
    ui:document.body.dataset.g019EquipmentActionsUi,
    capability:typeof functionalEquipmentLoadoutEnabled==="function"?
      functionalEquipmentLoadoutEnabled():null};
 });
 assert.equal(bp.hidden,true);
 assert.equal(bp.disabled,true);
 assert.equal(bp.ui,"default-closed");
 assert.deepEqual(writes,[]);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({verdict:"G019_SHIPPED_PUBLIC_SHOP_BACKPACK_FAIL_CLOSED_PASS",
  shop,bp,writes,errors}));
}catch(e){
 console.error("G019_NORMAL_PREVIEW_GUARD_FAIL",String(e.stack||e),JSON.stringify({writes,errors}));
 process.exitCode=1;
}finally{await context.close();await browser.close();}
