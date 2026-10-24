// G085H isolated REAL Chrome/WebGL player — Hero/Backpack/Shop share G008/G009.
// No mocked inventory, appearance, assets, ownership or equipment APIs.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {chromium} from "playwright-core";
let raw="";for await(const b of process.stdin)raw+=b;
const data=JSON.parse(raw);
const {origin,sessionCookie,freshSessionCookie,bambooInvId,bambooAssetId,clothInvId}=data;
assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const out=process.env.G085H_EVIDENCE_ROOT;
if(!out||!path.isAbsolute(out))throw Error("isolated_artifact_path_required");
fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({headless:true,
 executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",
 args:["--use-gl=angle","--use-angle=swiftshader",
 "--enable-webgl","--enable-unsafe-swiftshader"]});
const ctx=await browser.newContext({viewport:{width:1024,height:860},
 serviceWorkers:"block",hasTouch:Boolean(data.touch)});
await ctx.addCookies([{url:origin,name:"session",value:sessionCookie}]);
const page=await ctx.newPage();
const apiWrites=[],unexpectedHttp=[],errors=[];
page.on("pageerror",e=>errors.push(e.message.slice(0,240)));
page.on("request",r=>{
 const url=new URL(r.url());
 if(url.origin===origin&&url.pathname.startsWith("/api/")&&r.method()!=="GET")
 apiWrites.push(r.method()+" "+url.pathname);
});
page.on("response",r=>{
 const url=new URL(r.url());
 if(url.origin===origin&&r.status()>=400
   &&(url.pathname.startsWith("/api/")||url.pathname.endsWith(".glb")))
 unexpectedHttp.push(r.status()+" "+url.pathname);
});
async function viewSnapshot(){
 return page.evaluate(()=>window.GoOdysseyUnified3D?.getSnapshot()||null);
}
async function waitFor(itemId,expectedId,status="ready"){
 await page.waitForFunction(({itemId,expectedId,status})=>{
  const s=window.GoOdysseyUnified3D?.getSnapshot();
  return s?.status===status&&s?.item_id===itemId
   &&(expectedId===null?s?.main_hand_id==null:s?.main_hand_id===expectedId)
   &&s?.canvas_count===1;
 },{itemId,expectedId,status},{timeout:60000});
 return viewSnapshot();
}
let hero,backpack,cloth,shop,afterReload,rotate,zoom,shopSurfaceVisible=false;
try {
 await page.goto(origin+"/hero?tab=hero",{waitUntil:"domcontentloaded",timeout:35000});
 await page.waitForFunction(async expected=>{
  const G=await import("/js/g008_future30_hero_renderer.js");
  const slot=G.getHeroSharedAttachmentHost()?.diagnostics()?.slots
    ?.find(s=>s.slot==="MAIN_HAND");
  return document.getElementById("g008-future30-hero-stage")?.dataset.state==="ready"
    &&slot?.presentation_id===expected&&slot.child_count===1;
 },bambooAssetId,{timeout:65000});
 // G085I: A momentary ready frame is not stable Hero acceptance. Verify
 // that the same WebGL hero+equipment remain ready after late rehydration,
 // then force an authorized read-only refresh and verify again.
 async function heroStability(label){
   await page.waitForFunction(async expected=>{
     const G=await import("/js/g008_future30_hero_renderer.js");
     const slot=G.getHeroSharedAttachmentHost()?.diagnostics()?.slots
       ?.find(x=>x.slot==="MAIN_HAND");
     return window.__G008_HERO_RENDER_STATE__?.state==="ready"
       &&document.getElementById("g008-future30-hero-stage")?.dataset.state==="ready"
       &&slot?.presentation_id===expected&&slot?.child_count===1;
   },bambooAssetId,{timeout:32000});
   const snapshots=[];
   for(let t=0;t<20;t++){
     await page.waitForTimeout(250);
     const snap=await page.evaluate(async()=>{
       const G=await import("/js/g008_future30_hero_renderer.js");
       const state=window.__G008_HERO_RENDER_STATE__||{};
       const hand=G.getHeroSharedAttachmentHost()?.diagnostics()?.slots
         ?.find(x=>x.slot==="MAIN_HAND");
       return {state:state.state,equipment_status:state.equipment_status,
         hand_id:hand?.presentation_id||null,
         child_count:hand?.child_count??-1,
         canvas_count:document.querySelectorAll("#g008-future30-hero-stage canvas").length};
     });
     snapshots.push(snap);
   }
   const lastTwoSeconds=snapshots.slice(-8);
   const stable=s=>s.state==="ready"&&s.hand_id===bambooAssetId
     &&s.child_count===1&&s.canvas_count===1
     &&s.equipment_status==="ready";
   assert(lastTwoSeconds.length===8&&lastTwoSeconds.every(stable),
     "G085I_HERO_DID_NOT_SETTLE_"+label+" "+JSON.stringify(snapshots));
   return {label,transitions:snapshots.map(s=>s.state),
     settled_last_2s:true,final:lastTwoSeconds.at(-1),
     loading_samples:snapshots.filter(s=>s.state==="loading").length};
 }
 const initialStable=await heroStability("initial");
 await page.evaluate(async()=>{
   const G=await import("/js/g008_future30_hero_renderer.js");
   await G.refreshHeroAppearance();
 });
 const postRefreshStable=await heroStability("post_refresh");
 hero={model:"G008",hand:bambooAssetId,state:"ready",
   initialStable,postRefreshStable};
 await page.goto(origin+"/inventory?equipment="+bambooInvId,
  {waitUntil:"domcontentloaded",timeout:35000});
 await page.locator('[data-functional-inv-id="'+bambooInvId+'"]')
   .waitFor({state:"visible",timeout:28000});
 backpack=await waitFor("bamboo_shadow_blade",bambooAssetId);
 assert.equal(backpack.main_hand_child_count,1);
 assert(backpack.framing_ndc?.min_y>-0.96
   &&backpack.framing_ndc?.max_y<0.96,
   "3D model head/feet must be in camera frustum: "+JSON.stringify(backpack.framing_ndc));
 assert.equal(await page.locator("#functional-wearable-preview-fallback").count(),0);
 assert.equal(await page.locator("#functional-wearable-preview .rpg-wearable-layer").count(),0);
 const canvas=page.locator("#functional-wearable-preview-host canvas");
 const rect=await canvas.boundingBox();
 assert(rect?.width>=180&&rect?.height>=150,JSON.stringify(rect));
 await page.screenshot({path:path.join(out,"G085H_BACKPACK_BAMBOO_REAL_3D.png")});
 const host=page.locator("#functional-wearable-preview-host");
 let box=await host.boundingBox();assert(box);
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
 await page.mouse.down();await page.mouse.move(box.x+box.width/2+94,box.y+box.height/2,{steps:6});
 await page.mouse.up();
 rotate=await viewSnapshot();
 assert(Math.abs(rotate.orbit_yaw_radians)>0.12,JSON.stringify(rotate));
 await page.mouse.wheel(0,230);await page.waitForTimeout(220);
 zoom=await viewSnapshot();
 assert(zoom.zoom>1.05,JSON.stringify(zoom));
 await page.locator('[data-functional-inv-id="'+clothInvId+'"]').click();
 cloth=await waitFor("cloth_robe",null,"unsupported");
 assert.equal(cloth.presentation_id,null);
 assert.equal(cloth.canvas_count,1);
 await page.screenshot({path:path.join(out,"G085H_BACKPACK_CLOTH_MISSING_3D_NO_FAKE.png")});
 await page.goto(origin+"/shop",{waitUntil:"domcontentloaded",timeout:35000});
 await page.waitForFunction(()=>window.GoOdysseyUnified3D?.getSnapshot()?.canvas_count===1,
  undefined,{timeout:55000});
 // Validate the real 3D viewer uses the G009 exact Preview Rights mapping.
 // Shop selection is visual-only even for a product not yet released for sale.
 const tryOnButton=page.locator('[data-g085-shop3d-item-id="bamboo_shadow_blade"]');
 await tryOnButton.waitFor({state:"visible",timeout:30000});
 await tryOnButton.click();
 shop=await waitFor("bamboo_shadow_blade",bambooAssetId);
 const shopBox=await page.locator("#g085-shop-character-3d").boundingBox();
 shopSurfaceVisible=Boolean(shopBox?.width>=100&&shopBox?.height>=140);
 assert.equal(shopSurfaceVisible,true,"Shop 3D try-on must be visibly available while purchases remain locked");
 assert.equal(await tryOnButton.getAttribute("aria-pressed"),"true");
 if(shopSurfaceVisible)await page.screenshot({
  path:path.join(out,"G085H_SHOP_READONLY_3D_TRYON.png")});
 // Traverse all four publicly preview-admitted G009 3D items from visible
 // Shop buttons. They must resolve the exact model hash/hand slot even if
 // the synthetic player does NOT own the other three items.
 const previewRows=[
  ["iron_sword","WEAPON_C43E15596CA6"],
  ["fox_fang","WEAPON_6F06505A7BED"],
  ["riverstone_sabre","WEAPON_EC86CE30E759"],
  ["bamboo_shadow_blade","WEAPON_C84A8635BED2"],
 ];
 const tryOnSnapshots=[];
 for(const [id,visual]of previewRows){
   const button=page.locator('[data-g085-shop3d-item-id="'+id+'"]');
   await button.waitFor({state:"visible",timeout:20000});
   await button.click();
   const loaded=await waitFor(id,visual);
   assert.equal(loaded.main_hand_child_count,1);
   tryOnSnapshots.push({item_id:id,presentation_id:loaded.main_hand_id,
     child_count:loaded.main_hand_child_count});
 }
 const shopShop=page.locator('#g085-shop-character-3d');
 assert(await shopShop.isVisible());
 // RACE: click all four options without awaiting GLB fetches. The LAST
 // selection must win after all late older responses settle; stale
 // attachments may not return and only one MAIN_HAND child may remain.
 await page.evaluate(()=>{
   for(const id of ['iron_sword','fox_fang','riverstone_sabre','bamboo_shadow_blade']){
     document.querySelector('[data-g085-shop3d-item-id="'+id+'"]').click();
   }
 });
 await waitFor('bamboo_shadow_blade',bambooAssetId);
 await page.waitForTimeout(1750);
 const postRace=await viewSnapshot();
 assert.equal(postRace.item_id,'bamboo_shadow_blade');
 assert.equal(postRace.main_hand_id,bambooAssetId);
 assert.equal(postRace.main_hand_child_count,1);
 assert.equal(postRace.canvas_count,1);
 assert.equal(postRace.status,'ready');
 shop={...shop,rapid_four_switch_last_wins:true,postRace};
 await page.evaluate(()=>window.GoOdysseyUnified3D.show('cloth_robe',{tryOn:true}));
 const missingShop=await waitFor('cloth_robe',null,'unsupported');
 assert.equal(missingShop.main_hand_child_count,0);
 shop={...shop,clothUnavailableNoFake:true};
 // Shop try-on is an appearance-only interpretation of the approved G009
 // GLB catalog; no blanket entitlement and no Shop purchase capability.
 shop={...shop,allFourExactMappedPreview:tryOnSnapshots};
 await page.goto(origin+"/inventory?equipment="+bambooInvId,
  {waitUntil:"domcontentloaded",timeout:35000});
 afterReload=await waitFor("bamboo_shadow_blade",bambooAssetId);
 assert.equal(afterReload.main_hand_child_count,1);
 // Genuine independent signed session + new Chrome context, not a local
 // storage replay, verifies persistence is from the server-owned PG state.
 const freshContext=await browser.newContext({viewport:{width:920,height:780},
   serviceWorkers:"block"});
 await freshContext.addCookies([{
   name:"session",value:freshSessionCookie,url:origin
 }]);
 let freshContextAfterRelogin=null;
 try {
   const freshPage=await freshContext.newPage();
   freshPage.on("pageerror",e=>errors.push("fresh_session:"+e.message.slice(0,230)));
   freshPage.on("request",r=>{
     const u=new URL(r.url());
     if(u.origin===origin&&u.pathname.startsWith("/api/")&&r.method()!=="GET")
       apiWrites.push("fresh_"+r.method()+" "+u.pathname);
   });
   await freshPage.goto(origin+"/inventory?equipment="+bambooInvId,
     {waitUntil:"domcontentloaded",timeout:35000});
   await freshPage.waitForFunction(expected=>{
     const snap=window.GoOdysseyUnified3D?.getSnapshot();
     return snap?.status==="ready"&&snap?.main_hand_id===expected
       &&snap?.main_hand_child_count===1&&snap?.canvas_count===1;
   },bambooAssetId,{timeout:60000});
   freshContextAfterRelogin=await freshPage.evaluate(()=>
     window.GoOdysseyUnified3D.getSnapshot());
 }finally{await freshContext.close();}
 assert.deepEqual(apiWrites,[],"Preview must never buy, equip, claim or debit");
 assert.deepEqual(unexpectedHttp,[],"Authenticated model/API responses must not fail");
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({verdict:"G085H_SHARED_G008_G009_BACKPACK_SHOP_REAL_CHROME_PG_PASS",
  hero,backpack,cloth,shop,afterReload,freshContextAfterRelogin,rotate,zoom,shopSurfaceVisible,
  screenshots:fs.readdirSync(out).filter(x=>x.endsWith(".png")),
  apiWrites,badResponses:unexpectedHttp,pageErrors:errors}));
}catch(e){
 console.error("G085H_SHARED_3D_BROWSER_FAIL",String(e.stack||e),
  JSON.stringify({hero,backpack,cloth,shop,apiWrites,unexpectedHttp,errors,url:page.url()}));
 process.exitCode=1;
}finally{await ctx.close();await browser.close();}
