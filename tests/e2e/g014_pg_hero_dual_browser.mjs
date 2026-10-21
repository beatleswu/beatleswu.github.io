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
 const response=await p.goto(origin+
  "/tests/e2e/fixtures/g013_p038_dual_hand_qa.html?g013_qa=1",
  {waitUntil:"domcontentloaded",timeout:32000});
 assert.equal(response.status(),200);
 watch(p);
 await p.waitForFunction(()=>window.__g013P038DualReady===true,undefined,{timeout:30000});
 const serverState=await inventory(p);
 const eq=serverState.filter(x=>x.equipped && ["weapon","offhand"].includes(x.slot));
 assert.equal(eq.length,2);
 assert.equal(eq.find(x=>x.slot==="weapon")?.item_id,main.id);
 assert.equal(eq.find(x=>x.slot==="offhand")?.item_id,off.id);
 const appearance=await p.evaluate(async()=>{
  const r=await fetch("/api/player/appearance",{credentials:"include",cache:"no-store"});
  if(!r.ok)throw Error("appearance_http_"+r.status);
  return r.json();
 });
 assert.equal(appearance.character_key,"A1");
 assert.equal(appearance.character_entitled,true);
 const info=await p.evaluate(x=>window.startHero(x),{
  characterKey:appearance.character_key,heroPath:heroGlb});
 assert.equal(info.liveRenderers,1);
 // No guessed model mapping: exact QA ID from the server-owned item's
 // authorized fixture identity; both descriptors must be unreleased.
 const proof=await p.evaluate(({main,off})=>{
  const current=window.__g013P038QACatalog.all;
  if(current.length!==12 || window.__g013P038QACatalog.releaseAdmitted!==false)
   throw Error("g014_nonrelease_catalog_rejected");
  for(const x of [main,off]){
   const descriptor=current.find(z=>z.asset_id===x.qa_id);
   if(!descriptor || descriptor.slot!==x.hand_slot||descriptor.test_only!==true)
     throw Error("g014_slot_authority_mapping_rejected");
  }
  return window.attachP038Dual({mainId:main.qa_id,offId:off.qa_id});
 },{main,off});
 assert.equal(proof.realGeometry,true);
 assert.equal(proof.mainCount,1);assert.equal(proof.offCount,1);
 assert.equal(proof.maxRenderers,1);
 for(const [x,m] of [[main,proof.metrics[0]],[off,proof.metrics[1]]]){
  assert.equal(m.asset_id,x.qa_id);
  assert.equal(m.actualSha,x.sha);
  assert.equal(m.childCount,1);
  assert.match(m.anchorSource,/^HAND_BONE:/);
  assert(m.boneMatrixDelta<1e-3);
  assert(m.centerHandRatio<0.38);
 }
 const render=await p.locator("canvas").evaluate(canvas=>({
  width:canvas.width,height:canvas.height,
  webgl:!!(canvas.getContext("webgl2")||canvas.getContext("webgl"))}));
 assert(render.width>=600&&render.height>=600&&render.webgl);
 return {main:main.id,off:off.id,realCanvas:render,
  mainBone:proof.metrics[0].anchorSource,offBone:proof.metrics[1].anchorSource,
  matrixDeltaMax:Math.max(...proof.metrics.map(x=>x.boneMatrixDelta)),
  serverInventoryAuthoritative:true,shaCorrect:true};
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
 assert.deepEqual(errors,[]);
 assert.equal(requests.filter(x=>x==="POST /api/player/inventory/equip").length,4);
 assert.equal(requests.filter(x=>x==="POST /api/shop/buy").length,0);
 console.log(JSON.stringify({verdict:"G014_REAL_PG_BACKPACK_DUAL_3D_FRESH_LOGIN_PASS",
  syntheticUser:true,realWebGL:true,dualRenders:results.length,
  twoDifferentMainShields:true,serverWrites:requests,results,errorCount:errors.length,
  formalRelease:false,realProductUiReleased:false}));
}catch(e){
 console.error("G014_DUAL_E2E_FAIL",String(e.stack||e).slice(0,2700),
   JSON.stringify({results,errors,requests}).slice(0,1800));
 process.exitCode=1;
}finally{await first.close();await bc.close();}
