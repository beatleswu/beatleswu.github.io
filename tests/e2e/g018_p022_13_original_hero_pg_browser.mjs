// Original Backpack + original /hero (G008) authenticated synthetic PG,
// 13 unreleased P022 source-derived QA identities, NO 3 arrows as equipment.
// Actual click -> POST -> source-SHA verified GLB -> reload signed Session.
import assert from "node:assert/strict";
import {chromium} from "file:///D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core/index.mjs";
let input="";for await(const chunk of process.stdin)input+=chunk;
const {origin,cookie,freshCookie,entries,projectiles}=JSON.parse(input);
assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
assert.equal(entries.length,13);assert.equal(projectiles.length,3);
assert.equal(new Set(entries.map(x=>x.id)).size,13);
assert(entries.every(x=>x.slot==="weapon"&&x.qa_id.startsWith("G017_P022_")));
const browser=await chromium.launch({headless:true,
 executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",
 args:["--use-gl=angle","--use-angle=swiftshader","--enable-webgl","--enable-unsafe-swiftshader"]});
const errors=[],writes=[],renders=[],relogins=[];
const seen=new WeakSet();
function observe(page){
 if(seen.has(page))return;seen.add(page);
 page.on("pageerror",e=>errors.push(String(e)));
 page.on("request",req=>{
  const p=new URL(req.url()).pathname;
  if(req.method()==="POST"&&p.startsWith("/api/"))
   writes.push(p);
 });
}
async function context(token){
 const cx=await browser.newContext({viewport:{width:810,height:870},serviceWorkers:"block"});
 await cx.addCookies([{name:"session",value:token,url:origin}]);return cx;
}
async function readInventory(page){
 return page.evaluate(async()=>{
  const x=await fetch("/api/player/inventory",{credentials:"include",cache:"no-store"});
  if(!x.ok)throw Error("inventory_http:"+x.status);
  return x.json();
 });
}
async function equipFromBackpack(page,item){
 assert.equal((await page.goto(origin+"/inventory?equipment="+item.inv_id,
  {waitUntil:"domcontentloaded",timeout:32000})).status(),200);
 const row=page.locator('[data-functional-inv-id="'+item.inv_id+'"]');
 await row.waitFor({state:"visible",timeout:22000});
 await row.click();
 const action=page.locator("#functional-detail-action");
 await action.waitFor({state:"visible",timeout:20000});
 assert(await action.isEnabled());
 await action.click();
 await page.waitForFunction(id=>document.querySelector(
   '[data-functional-inv-id="'+id+'"]')?.dataset.equipped==="true",
   String(item.inv_id),{timeout:25000});
 const list=await readInventory(page);
 const owned=list.filter(x=>x.equipped===true&&x.slot==="weapon");
 assert.equal(owned.length,1);
 assert.equal(owned[0].item_id,item.id);
 assert(!list.some(x=>x.item_id.startsWith("g018_qa_")&&x.equipped===true
   &&x.item_id!==item.id));
}
async function originalHero(page,item){
 const html=await page.goto(origin+"/hero?g018_qa=1&tab=equipment",
    {waitUntil:"domcontentloaded",timeout:35000});
 assert.equal(html.status(),200);
 assert(await page.locator("#g008-future30-hero-stage").count());
 await page.waitForFunction(itemId=>{
  const p=window.__G018_P022_INPAGE_QA_PROOF__;
  if(!p||p.state!=="ready")return false;
  const main=p.selected.find(x=>x.slot==="MAIN_HAND");
  const off=p.selected.find(x=>x.slot==="OFF_HAND");
  const anchor=p.slots.find(x=>x.slot==="MAIN_HAND");
  const other=p.slots.find(x=>x.slot==="OFF_HAND");
  return document.querySelector("#g008-future30-hero-stage")?.dataset.state==="ready"
    &&main?.server_item_id===itemId&&off?.status==="empty"
    &&anchor?.child_count===1&&other?.child_count===0;
 },item.id,{timeout:65000});
 const rendered=await page.evaluate(async item=>{
  const mod=await import("/js/g008_future30_hero_renderer.js");
  const host=mod.getHeroSharedAttachmentHost();
  const stage=document.querySelector("#g008-future30-hero-stage");
  const canvas=stage.querySelector("canvas");
  const p=window.__G018_P022_INPAGE_QA_PROOF__;
  const main=host.diagnostics().slots.find(x=>x.slot==="MAIN_HAND");
  const off=host.diagnostics().slots.find(x=>x.slot==="OFF_HAND");
  const raw=await fetch("/api/player/inventory",{credentials:"include"})
   .then(r=>r.json());
  return {canvas:!!canvas,canvasWidth:canvas?.width||0,
   gl:!!(canvas?.getContext("webgl2")||canvas?.getContext("webgl")),
   main,off,proof:p,liveEquipped:raw.filter(x=>x.equipped&&x.slot==="weapon")
     .map(x=>x.item_id),
   qaModuleCount:window.__G018_P022_INPAGE_QA_PROOF__?.model_count||0};
 },item);
 assert(rendered.canvas&&rendered.canvasWidth>=200&&rendered.gl);
 assert.equal(rendered.qaModuleCount,13);
 assert.equal(rendered.main.presentation_id,item.qa_id);
 assert.equal(rendered.main.child_count,1);
 assert.equal(rendered.off.child_count,0);
 assert.deepEqual(rendered.liveEquipped,[item.id]);
 assert.equal(rendered.proof.projectile_equip_rejected,true);
 return {code:item.code,id:item.id,sourceSha:item.sha,
   presentationId:rendered.main.presentation_id,
   heroIsOriginal:true,trueWebGL:rendered.gl,mainChildCount:1,
   offChildCount:0,serverAuthoritative:true};
}
const c=await context(cookie);
try{
 const page=await c.newPage();observe(page);
 for(let i=0;i<entries.length;i++){
  const item=entries[i];
  await equipFromBackpack(page,item);
  renders.push(await originalHero(page,item));
  if([0,6,12].includes(i)){
   const fresh=await context(freshCookie);
   try{
    const q=await fresh.newPage();observe(q);
    const result=await originalHero(q,item);
    relogins.push({code:item.code,sourceSha:item.sha,...result});
   }finally{await fresh.close();}
  }
 }
 assert.equal(renders.length,13);
 assert.equal(relogins.length,3);
 // Without QA query, same synthetic owner gets a real Hero but no unreleased
 // P022 model (default Product fail-closed).
 const off=await context(cookie);
 let defaultOff=false;
 try{
  const p=await off.newPage();observe(p);
  assert.equal((await p.goto(origin+"/hero?tab=equipment",
   {waitUntil:"domcontentloaded",timeout:35000})).status(),200);
  await p.waitForFunction(()=>
    document.querySelector("#g008-future30-hero-stage")?.dataset.state==="ready",
    undefined,{timeout:55000});
  const fact=await p.evaluate(async()=>{
   const mod=await import("/js/g008_future30_hero_renderer.js");
   const slots=mod.getHeroSharedAttachmentHost().diagnostics().slots;
   return {P022QA:window.__G018_P022_INPAGE_QA_PROOF__||null,
    eligibleSlot:slots.filter(x=>x.slot==="MAIN_HAND"||x.slot==="OFF_HAND")
      .filter(x=>x.child_count>0||x.presentation_id).length};
  });
  assert.equal(fact.P022QA,null);assert.equal(fact.eligibleSlot,0);
  defaultOff=true;
 }finally{await off.close();}
 assert.equal(writes.filter(x=>x==="/api/player/inventory/equip").length,13);
 assert.equal(writes.filter(x=>x==="/api/shop/buy").length,0);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({verdict:"G018_P022_13_ORIGINAL_HERO_NATIVE_PG_ALL_RELOGIN_PASS",
  realBackpackEquipPOST:13,originalHeroWebGL:13,
  independentFreshSignedSessions:3,defaultOffVerified:defaultOff,
  sourceModels:13,projectilesExcluded:3,
  errors,writes,renders,relogins,formalRelease:false}));
}catch(e){
 console.error("G018_REAL_PG_P022_FAILURE",
  String(e.stack||e).slice(0,3300),
  JSON.stringify({completedRenders:renders,errors,writes}).slice(0,2600));
 process.exitCode=1;
}finally{await c.close();await browser.close();}
