// G020 one signed synthetic native-PG player; AFTER a real G010 boss/Quest
// reward and real G019 original Shop+Backpack buy/equip. All GET, zero writes.
import assert from "node:assert/strict";
import {chromium} from "file:///D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core/index.mjs";
let input="";for await(const x of process.stdin)input+=x;
const {origin,sessionCookie,reloginCookie,expectedXp,expectedCoins,expectedEquipment}=JSON.parse(input);
assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const browser=await chromium.launch({headless:true,
 executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",
 args:["--use-gl=angle","--use-angle=swiftshader","--enable-webgl","--enable-unsafe-swiftshader"]});
const touch=process.env.GO_G020_TOUCH==="1";
const errors=[],http500=[],writes=[],checks=[],snapshots={};
const check=(name,expr)=>{assert.ok(expr,name);checks.push(name)};
async function session(cookie){
 const cx=await browser.newContext({
   viewport:touch?{width:820,height:1180}:{width:1280,height:900},
   hasTouch:touch,isMobile:touch,deviceScaleFactor:touch?2:1,
   serviceWorkers:"block"});
 await cx.addCookies([{name:"session",value:cookie,url:origin}]);
 const page=await cx.newPage();
 page.on("pageerror",e=>errors.push(String(e).slice(0,350)));
 page.on("response",r=>{
  if(new URL(r.url()).origin===origin && r.status()>=500)
   http500.push(r.status()+": "+new URL(r.url()).pathname);
 });
 page.on("request",r=>{
  if(new URL(r.url()).origin===origin && r.method()!=="GET"
    && r.method()!=="HEAD" && r.method()!=="OPTIONS")
   writes.push(r.method()+" "+new URL(r.url()).pathname);
 });
 return {cx,page};
}
async function api(page,path){
 const r=await page.evaluate(async u=>{
  const result=await fetch(u,{credentials:"include",cache:"no-store"});
  let value;try{value=await result.json()}catch{value=null}
  return {status:result.status,value};
 },path);
 check(path+" HTTP 200",r.status===200);
 return r.value;
}
async function page200(page,path){
 const r=await page.goto(origin+path,{waitUntil:"domcontentloaded",timeout:36000});
 check(path+" original Product page",r?.status()===200);
 await page.waitForTimeout(900);
 const len=(await page.locator("body").innerText()).length;
 check(path+" content rendered",len>120);
}
const a=await session(sessionCookie);
const b=await session(reloginCookie);
try{
 await page200(a.page,"/curriculum");
 await a.page.locator("#quest-board").waitFor({state:"attached",timeout:13000});
 check("Curriculum commission panel exists",await a.page.locator("#quest-board").count()===1);
 const summary=await api(a.page,"/api/curriculum/summary");
 check("Curriculum summary JSON object",!!summary&&typeof summary==="object"&&!Array.isArray(summary));
 const board=await api(a.page,"/api/quest-board");
 check("Quest-board JSON object",!!board&&typeof board==="object"&&!Array.isArray(board));
 snapshots.curriculum={summary:!!summary,board:!!board};
 await page200(a.page,"/community");
 const tabs=a.page.locator("button[data-tab]");
 check("Tavern four tabs",await tabs.count()===4);
 for(const name of ["challenges","reviews","friends","leaderboard"]){
  await a.page.locator('button[data-tab="'+name+'"]').click();
  check("Tavern "+name+" tab active",
    await a.page.locator('button[data-tab="'+name+'"]').evaluate(el=>el.classList.contains("active")));
 }
 const standings=await api(a.page,"/api/community/leaderboard");
 const alltime=standings?.alltime?.find(x=>x.is_you===true);
 check("Tavern all-time ranking equals player XP",Number(alltime?.score)===expectedXp);
 const quests=await api(a.page,"/api/quests/v2");
 check("Quest daily reward claimed and persisted",quests?.quests?.find(x=>
  x.quest_id==="daily:streak_correct")?.claimed===true);
 snapshots.tavern={alltime:Number(alltime.score),questClaimed:true,tabCount:4};
 await page200(a.page,"/hero?tab=equipment");
 await a.page.waitForFunction(()=>
  document.querySelector("#g008-future30-hero-stage")?.dataset.state==="ready",
  undefined,{timeout:45000});
 const hero=await a.page.evaluate(async()=>{
  const canvas=document.querySelector("#g008-future30-hero-stage canvas");
  const inv=await fetch("/api/player/inventory",{credentials:"include"}).then(r=>r.json());
  return {hasCanvas:!!canvas,width:canvas?.width||0,
    equipped:inv.filter(x=>x.equipped===true).map(x=>({slot:x.slot,item_id:x.item_id})),
    QAmodel:!!(window.__G018_P022_INPAGE_QA_PROOF__||window.__G015_P038_INPAGE_QA_PROOF__)};
 });
 check("Hero original G008 real canvas",hero.hasCanvas&&hero.width>100);
 check("Hero server weapon equipped",hero.equipped.some(x=>x.item_id===expectedEquipment&&x.slot==="weapon"));
 check("Hero no unadmitted QA hook",!hero.QAmodel);
 snapshots.hero=hero;
 await page200(a.page,"/inventory");
 const inv=await api(a.page,"/api/player/inventory");
 check("Backpack owns equip row",inv.some(x=>x.item_id===expectedEquipment&&x.equipped===true));
 const xp=await api(a.page,"/api/xp/status");
 check("XP after quest unchanged in readback",xp?.xp===expectedXp);
 const shop=await api(a.page,"/api/shop/catalog");
 check("Shop coins after purchase retained",shop?.coins===expectedCoins);
 check("Shop 9 canonical server offers",shop?.equipment_offers?.length===9);
 check("Shop UI flag server-approved",shop?.approved_equipment_purchase_ui_enabled===true);
 snapshots.wallet={xp:xp.xp,coins:shop.coins,equipped:expectedEquipment};
 await page200(b.page,"/curriculum");
 await page200(b.page,"/community");
 const otherRank=await api(b.page,"/api/community/leaderboard");
 check("New signed session tavern score persistent",Number(otherRank?.alltime?.find(x=>x.is_you)?.score)===expectedXp);
 const otherInventory=await api(b.page,"/api/player/inventory");
 check("New signed session equipment persistent",otherInventory.some(x=>x.item_id===expectedEquipment&&x.equipped));
 const otherShop=await api(b.page,"/api/shop/catalog");
 check("New signed session Coins persistent",otherShop?.coins===expectedCoins);
 const otherXp=await api(b.page,"/api/xp/status");
 check("New signed session XP persistent",otherXp?.xp===expectedXp);
 check("Read-only navigation zero mutations",writes.length===0);
 check("No HTTP 500",http500.length===0);
 check("No JS page errors",errors.length===0);
 console.log(JSON.stringify({verdict:"G020_FULL_ORIGINAL_PRODUCT_PLAYER_SAME_SESSION_READBACK_PASS",
  checks:checks.length,checkNames:checks,snapshots,writes,errors,http500,
  differentSignedSession:true,originalHtml:true,production:false,
  mode:touch?"chrome_tablet_touch":"desktop_mouse"}));
}catch(e){
 console.error("G020_ONE_PLAYER_ORIGINAL_PRODUCT_READBACK_FAIL",
  String(e.stack||e).slice(0,2200),JSON.stringify({checks,writes,errors,http500,snapshots}).slice(0,3500));
 process.exitCode=1;
}finally{await a.cx.close();await b.cx.close();await browser.close();}
