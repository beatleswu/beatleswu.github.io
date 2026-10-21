// G012: 4 rights-cleared but NOT-ADMITTED weapons. Synthetic PG-owned items only.
import assert from "node:assert/strict";
import { chromium } from "file:///D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core/index.mjs";
let raw="";for await(const block of process.stdin)raw+=block;
const input=JSON.parse(raw);
const {origin,sessionCookie,secondSessionCookie,items}=input;
assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
assert.equal(items.length,4);
assert.equal(new Set(items.map(x=>x.item_id)).size,4);
const browser=await chromium.launch({headless:true,
 executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",
 args:["--use-gl=angle","--use-angle=swiftshader","--enable-webgl","--enable-unsafe-swiftshader"]});
const makeContext=async cookie=>{
 const ctx=await browser.newContext({viewport:{width:1190,height:920},serviceWorkers:"block"});
 await ctx.addCookies([{name:"session",value:cookie,url:origin}]);return ctx;
};
const errors=[],badResponses=[],writes=[],cases=[];
const main=await makeContext(sessionCookie),page=await main.newPage();
function observe(p){
 p.on("pageerror",e=>errors.push(String(e).slice(0,400)));
 p.on("response",r=>{
  const u=new URL(r.url());
  if(u.origin===origin&&r.status()>=400&&
     (u.pathname.startsWith("/api/")||u.pathname.includes("3d_shop"))) {
   badResponses.push(r.status()+" "+u.pathname);
  }
 });
 p.on("request",r=>{
  const u=new URL(r.url());
  if(u.origin===origin&&u.pathname.startsWith("/api/")&&r.method()!=="GET")
   writes.push(r.method()+" "+u.pathname);
 });
}
observe(page);
async function readInventory(p){
 return await p.evaluate(async()=>{
  const result=await fetch("/api/player/inventory",{cache:"no-store",credentials:"include"});
  if(result.status!==200)throw Error("inventory_http_"+result.status);
  return result.json();
 });
}
async function checkHero(p,item) {
 await p.goto(origin+"/hero?tab=equipment",{waitUntil:"domcontentloaded",timeout:32000});
 await p.waitForFunction(async asset=>{
  const module=await import("/js/g008_future30_hero_renderer.js");
  const s=module.getHeroSharedAttachmentHost()?.diagnostics()?.slots;
  return document.getElementById("g008-future30-hero-stage")?.dataset.state==="ready"
   && !!document.querySelector("#g008-future30-hero-stage canvas")
   && s?.find(x=>x.slot==="MAIN_HAND")?.presentation_id===asset
   && s?.find(x=>x.slot==="MAIN_HAND")?.child_count===1;
 },item.asset_id,{timeout:55000});
 // A diagnostic alone is insufficient; the browser must have fetched the real
 // rights-cleared GLB and it must be the hash-authorized binary.
 let asset;
 for(let attempt=0;attempt<14;attempt++){
  asset=await p.evaluate(async data=>{
   const mod=await import("/js/g008_future30_hero_renderer.js");
   const diag=mod.getHeroSharedAttachmentHost()?.diagnostics();
   if(!diag?.slots?.some(s=>s.slot==="MAIN_HAND"&&s.presentation_id===data.asset_id&&s.child_count===1))
     return {ready:false};
   const glb=await fetch(data.runtime_asset,{cache:"no-store"});
   if(glb.status!==200)throw Error("model_http_"+glb.status);
   const bytes=await glb.arrayBuffer();
   const sha=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)))
     .map(x=>x.toString(16).padStart(2,"0")).join("");
   const canv=document.querySelector("#g008-future30-hero-stage canvas");
   return {ready:true,actual_sha:sha,glb_size:bytes.byteLength,
     canvas_width:canv?.width,canvas_height:canv?.height,
     main:diag.slots.find(x=>x.slot==="MAIN_HAND"),
     equip_count:diag.slots.filter(x=>x.slot==="MAIN_HAND"&&x.child_count===1).length,
     character_state:document.querySelector("#g008-future30-hero-stage").dataset.state};
  },item);
  if(asset.ready)break;
  await p.waitForTimeout(350);
 }
 assert.equal(asset.ready,true);
 assert.equal(asset.actual_sha,item.runtime_sha256);
 assert(asset.glb_size>1024 && asset.canvas_width>=200 && asset.canvas_height>=300,JSON.stringify(asset));
 assert.equal(asset.main.presentation_id,item.asset_id);
 assert.equal(asset.equip_count,1);
 return asset;
}
try {
 for(let index=0;index<items.length;index++){
  const item=items[index];
  const invPath=origin+"/inventory?equipment="+item.inv_id;
  await page.goto(invPath,{waitUntil:"domcontentloaded",timeout:30000});
  const locator=page.locator('[data-functional-inv-id="'+item.inv_id+'"]');
  await locator.waitFor({state:"visible",timeout:22000});
  await page.waitForFunction(id=>
    !!document.querySelector('[data-functional-inv-id="'+id+'"]')
     && functionalEquipmentLoadoutEnabled(),String(item.inv_id),{timeout:20000});
  await locator.click({timeout:15000});
  const btn=page.locator("#functional-detail-action");
  await btn.waitFor({state:"visible",timeout:20000});
  assert.equal(await btn.isEnabled(),true);
  await btn.click({timeout:18000});
  await page.waitForFunction(id=>document.querySelector(
    '[data-functional-inv-id="'+id+'"]')?.dataset.equipped==="true",
    String(item.inv_id),{timeout:20000});
  const serverRows=await readInventory(page);
  const eq=serverRows.filter(x=>x.equipped===true && x.slot==="weapon");
  assert.equal(eq.length,1);
  assert.equal(eq[0].item_id,item.item_id);
  const hero=await checkHero(page,item);
  const fresh=await makeContext(secondSessionCookie),another=await fresh.newPage();
  observe(another);
  let freshHero;
  try{
   freshHero=await checkHero(another,item);
   const freshInventory=await readInventory(another);
   assert.equal(freshInventory.filter(x=>x.equipped===true&&x.slot==="weapon").length,1);
   assert.equal(freshInventory.find(x=>x.item_id===item.item_id).equipped,true);
  }finally{await fresh.close()}
  cases.push({item_id:item.item_id,asset_id:item.asset_id,
   main_child_count:hero.main.child_count,sha256:hero.actual_sha,bytes:hero.glb_size,
   rendered3d:true,relogin:true,exact_one_server_equipped:true,
   previous_weapon_replaced:index===0?null:items[index-1].item_id});
 }
 assert.deepEqual(errors,[]);
 assert.deepEqual(badResponses,[]);
 assert.equal(writes.filter(x=>x==="POST /api/player/inventory/equip").length,4);
 assert.equal(writes.filter(x=>x==="POST /api/shop/buy").length,0);
 console.log(JSON.stringify({verdict:"G012_FORMAL9_4_REAL_PG_HERO_WEBGL_RELOGIN_PASS",
  realBrowser:"Chrome WebGL",fourMainhandAssets:4,postEquipCount:4,
  formalRelease:false,shopPurchases:0,syntheticGrants:true,
  cases,writes,browserErrors:errors,httpErrors:badResponses}));
}catch(e){
 console.error("G012_FORMAL9_REAL_PLAYER_FAIL",String(e.stack||e),
  JSON.stringify({cases,writes,errors,badResponses,url:page.url()}));
 process.exitCode=1;
}finally{await main.close();await browser.close();}
