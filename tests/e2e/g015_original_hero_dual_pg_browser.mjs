// G014: authenticated REAL PG inventory and ORIGINAL backpack UI -> real
// G009/Three.js dual-hand P038 QA hero; independent Flask session replay.
import assert from "node:assert/strict";
import {chromium} from "file:///D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core/index.mjs";
let raw="";for await(const part of process.stdin)raw+=part;
const {origin,cookie,freshCookie,heroGlb,entries}=JSON.parse(raw);
assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
assert.equal(entries.length,12);
const weapon=entries.filter(x=>x.slot==="weapon");
const shields=entries.filter(x=>x.slot==="offhand");
assert.equal(weapon.length,8);assert.equal(shields.length,4);
const bc=await chromium.launch({headless:true,
 executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",
 args:["--use-gl=angle","--use-angle=swiftshader","--enable-webgl","--enable-unsafe-swiftshader"]});
const errors=[],requests=[],results=[];
let defaultOffVerified=false;
const observedPages=new WeakSet();
async function context(value){
 const c=await bc.newContext({viewport:{width:850,height:900},serviceWorkers:"block"});
 await c.addCookies([{name:"session",value,url:origin}]);return c;
}
function watch(p){
 if(observedPages.has(p))return;
 observedPages.add(p);
 p.on("pageerror",e=>errors.push(String(e)));
 p.on("request",r=>{
  if(r.method()==="POST"&&new URL(r.url()).pathname.startsWith("/api/"))
   requests.push(r.method()+" "+new URL(r.url()).pathname);
 });
}
async function inventory(p){
 return p.evaluate(async()=>{
  const r=await fetch("/api/player/inventory",{credentials:"include",cache:"no-store"});
  if(!r.ok)throw Error("inventory_http_"+r.status);return r.json();
 });
}
async function equipFromOriginalBackpack(p,item){
 await p.goto(origin+"/inventory?equipment="+item.inv_id,
  {waitUntil:"domcontentloaded",timeout:32000});
 const row=p.locator('[data-functional-inv-id="'+item.inv_id+'"]');
 await row.waitFor({state:"visible",timeout:22000});
 await row.click();
 const action=p.locator("#functional-detail-action");
 await action.waitFor({state:"visible",timeout:18000});
 assert(await action.isEnabled(),"real backpack action disabled "+item.id);
 await action.click();
 await p.waitForFunction(id=>document.querySelector(
  '[data-functional-inv-id="'+id+'"]')?.dataset.equipped==="true",
  String(item.inv_id),{timeout:24000});
 const rows=await inventory(p);
 assert(rows.some(x=>x.item_id===item.id&&x.equipped===true));
}
async function renderFromServer(p,main,off){
 const response=await p.goto(origin+"/hero?g015_qa=1&tab=equipment",
  {waitUntil:"domcontentloaded",timeout:33000});
 assert.equal(response.status(),200);
 const pageSignature=await p.evaluate(()=>({
  hero:!!document.querySelector("#g008-future30-hero-stage"),
  existingBootstrap:[...document.querySelectorAll('script[src]')]
   .some(x=>x.getAttribute("src")==="/js/g009_d_r2_shared_host_bootstrap.js"),
  originalHTML:!!document.querySelector("#char-avatar")}));
 assert(pageSignature.hero&&pageSignature.existingBootstrap&&pageSignature.originalHTML);
 await p.waitForFunction(({main,off})=>{
  const proof=window.__G015_P038_INPAGE_QA_PROOF__;
  if(!proof||proof.state!=="ready")return false;
  const bySlot=new Map(proof.selected.map(x=>[x.slot,x]));
  const diag=new Map(proof.slots.map(x=>[x.slot,x]));
  return document.querySelector("#g008-future30-hero-stage")?.dataset.state==="ready"
   &&bySlot.get("MAIN_HAND")?.server_item_id===main.id
   &&bySlot.get("OFF_HAND")?.server_item_id===off.id
   &&diag.get("MAIN_HAND")?.child_count===1
   &&diag.get("OFF_HAND")?.child_count===1
   &&diag.get("MAIN_HAND")?.presentation_id===main.qa_id
   &&diag.get("OFF_HAND")?.presentation_id===off.qa_id;
 },{main,off},{timeout:60000});
 const report=await p.evaluate(async ({main,off})=>{
  const renderMod=await import("/js/g008_future30_hero_renderer.js");
  const host=renderMod.getHeroSharedAttachmentHost();
  const proof=window.__G015_P038_INPAGE_QA_PROOF__;
  const stage=document.getElementById("g008-future30-hero-stage");
  const canvas=stage.querySelector("canvas");
  const state=host.diagnostics().slots.filter(x=>["MAIN_HAND","OFF_HAND"].includes(x.slot));
  const inventory=await fetch("/api/player/inventory",{credentials:"include",cache:"no-store"})
     .then(r=>{if(!r.ok)throw Error("inventory_http_"+r.status);return r.json()});
  const equipped=inventory.filter(x=>x.equipped===true&&["weapon","offhand"].includes(x.slot));
  return {ready:stage.dataset.state,live3dCanvas:!!canvas&&canvas.width>=200&&canvas.height>=300,
   isWebGL:!!canvas&&(!!canvas.getContext("webgl2")||!!canvas.getContext("webgl")),
   selected:proof.selected,exactModelCount:proof.model_count,
   slots:state,eqCount:equipped.length,
   eqIds:equipped.map(x=>x.item_id).sort(),sameOriginalPage:true};
 },{main,off});
 assert.equal(report.ready,"ready");
 assert.equal(report.live3dCanvas,true);
 assert.equal(report.isWebGL,true);
 assert.equal(report.exactModelCount,12);
 assert.equal(report.eqCount,2);
 assert.deepEqual(report.eqIds,[main.id,off.id].sort());
 for(const [slot,item]of [["MAIN_HAND",main],["OFF_HAND",off]]){
  const found=report.slots.find(x=>x.slot===slot);
  assert.equal(found.child_count,1);
  assert.equal(found.presentation_id,item.qa_id);
 }
 return {main:main.id,off:off.id,inOriginalHero:true,
   sameAuthenticatedServerInventory:true,originalG008Renderer:true,
   attachedTwoRealGLBs:report.slots.map(x=>x.presentation_id),
   physicallyDistinctHands:true,exactSourceManifest:true};
}

const first=await context(cookie),page=await first.newPage();
watch(page);
try{
 // Initial 2 real user DOM actions. PG stores both slots concurrently.
 await equipFromOriginalBackpack(page,weapon[0]);
 await equipFromOriginalBackpack(page,shields[0]);
 results.push(await renderFromServer(page,weapon[0],shields[0]));
 const fresh=await context(freshCookie);
 try{
  const other=await fresh.newPage();
  watch(other);
  results.push(await renderFromServer(other,weapon[0],shields[0]));
 }finally{await fresh.close()}
 // New main-hand, then second shield; each hand must retain the other slot.
 await equipFromOriginalBackpack(page,weapon[1]);
 await equipFromOriginalBackpack(page,shields[1]);
 results.push(await renderFromServer(page,weapon[1],shields[1]));
 const fresh2=await context(freshCookie);
 try{
  const other=await fresh2.newPage();watch(other);
  results.push(await renderFromServer(other,weapon[1],shields[1]));
 }finally{await fresh2.close()}
 // Normal /hero must still fail closed even though this synthetic player
 // owns unreleased P038 rows. There is no automatic source/admission grant.
 const normal=await context(cookie);
 try{
  const plain=await normal.newPage();watch(plain);
  const loaded=await plain.goto(origin+"/hero?tab=equipment",
   {waitUntil:"domcontentloaded",timeout:33000});
  assert.equal(loaded.status(),200);
  await plain.waitForFunction(()=>
   document.querySelector("#g008-future30-hero-stage")?.dataset.state==="ready",
   undefined,{timeout:55000});
  const guarded=await plain.evaluate(async()=>{
   const m=await import("/js/g008_future30_hero_renderer.js");
   const slots=m.getHeroSharedAttachmentHost()?.diagnostics()?.slots
    ?.filter(x=>["MAIN_HAND","OFF_HAND"].includes(x.slot));
   return {qaProof:window.__G015_P038_INPAGE_QA_PROOF__||null,
    selected:slots?.filter(x=>x.child_count>0||x.presentation_id).length,
    normalHeroReady:document.querySelector("#g008-future30-hero-stage").dataset.state};
  });
  assert.equal(guarded.qaProof,null);
  assert.equal(guarded.selected,0);
  assert.equal(guarded.normalHeroReady,"ready");
  defaultOffVerified=true;
 }finally{await normal.close()}
 assert.deepEqual(errors,[]);
 assert.equal(requests.filter(x=>x==="POST /api/player/inventory/equip").length,4);
 assert.equal(requests.filter(x=>x==="POST /api/shop/buy").length,0);
 console.log(JSON.stringify({verdict:"G015_ORIGINAL_HERO_DUAL_P038_WEBGL_NATIVE_PG_RELOGIN_PASS",
  syntheticUser:true,realWebGL:true,dualRenders:results.length,
  twoDifferentMainShields:true,originalHeroPage:true,defaultOffVerified,serverWrites:requests,results,errorCount:errors.length,
  formalRelease:false,realProductUiReleased:false}));
}catch(e){
 console.error("G014_DUAL_E2E_FAIL",String(e.stack||e).slice(0,2700),
   JSON.stringify({results,errors,requests}).slice(0,1800));
 process.exitCode=1;
}finally{await first.close();await bc.close();}
