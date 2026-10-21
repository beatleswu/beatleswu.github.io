// G017: 16 P022 recovered real GLBs -> original G009 shared Hero rig,
// including 13 QA static held objects + 3 arrow PROJECTILE PROP previews.
// Cannot represent two-handed IK, arrow firing, rights admission, inventory.
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {createServer} from "node:http";
import {readFile,writeFile,mkdir} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import path from "node:path";
import {chromium} from "file:///D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core/index.mjs";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../..");
const evidence=path.resolve("D:/go-odyssey-g010-3d-activation-evidence-20261021");
const manifest=JSON.parse(await readFile(path.join(root,
 "docs/handoffs/G017_P022_16_QA_SOURCE_AND_ATTACHMENT_20261021.json"),"utf8"));
const futures=JSON.parse(await readFile(path.join(root,
 "schemas/future30_c005_real_asset_runtime_mapping_manifest.json"),"utf8"));
const heroes=["A1","A3","V1","V2","V3","R1","R3","H1","H2","H3",
 "K1","K2","K3","W1","W2","W3","M1","M2","S1","S2",
 "F1","F2","F3","AR1","AR2","AR3","E1","E2","E3"];
const smoke=process.env.G017_SMOKE==="1";
const keys=smoke?["A1"]:heroes;
const items=smoke?manifest.models.slice(0,3):manifest.models;
const fixture=path.join(root,"tests/e2e/fixtures/g017_p022_16_real_hero_qa.html");
assert.equal(heroes.length,29);assert.equal(new Set(heroes).size,29);
assert.equal(manifest.schema,"G017_P022_16_SOURCED_QA_V1");
assert.equal(manifest.release_status,"NOT_ADMITTED");
assert.equal(manifest.total,16);assert.equal(manifest.nonprojectile_handheld,13);
assert.equal(manifest.projectile_props_only,3);
const allowed=new Set([
 "docs/handoffs/G017_P022_16_QA_SOURCE_AND_ATTACHMENT_20261021.json",
 "js/g009_shared_hero_attachment_host.js",
 "js/hero_equipment_attachment_adapter.js",
 ...manifest.models.map(x=>x.runtime_glb),
 ...futures.visual_models.filter(x=>keys.includes(x.character_id)&&x.variant==="RED").map(x=>x.runtime_glb),
]);
const prefix=["assets/3d_shop/p048/vendor/","assets/3d_shop/p048/hero/",
 "assets/3d_shop/p048/future30/c005/"];
const checks=[],cases=[],errors=[],screens=[],loads=[];
const expectedSHA=new Map();
for(const item of manifest.models){
 assert.equal(item.formal_product_release,"NOT_ADMITTED");
 assert.equal(item.equip_enabled,false);assert.equal(item.shop_enabled,false);
 assert.equal(item.formal_item_id,null);
 const bytes=await readFile(path.join(root,item.runtime_glb));
 assert.equal(bytes.subarray(0,4).toString("utf8"),"glTF");
 assert.equal(createHash("sha256").update(bytes).digest("hex"),item.runtime_sha256);
 assert.equal(bytes.length,item.runtime_bytes);
 expectedSHA.set(item.qa_id,item.runtime_sha256);
 checks.push("source_sha_"+item.code);
}
for(const key of keys){
 const entry=futures.visual_models.find(x=>x.character_id===key&&x.variant==="RED");
 assert(entry,key);
 const bytes=await readFile(path.join(root,entry.runtime_glb));
 assert.equal(createHash("sha256").update(bytes).digest("hex"),entry.runtime_sha256);
}
const server=createServer(async(req,res)=>{
 try{
  const u=new URL(req.url,"http://127.0.0.1");
  const rel=decodeURIComponent(u.pathname).replace(/^\/+/, "");
  const target=rel===""?fixture:
   allowed.has(rel)||prefix.some(x=>rel.startsWith(x))
    ? path.join(root,rel):null;
  if(!target||(!target.startsWith(root+path.sep)&&target!==fixture)){
   res.writeHead(404).end("G017_QA_DEFAULT_DENY");return;
  }
  const blob=await readFile(target);
  if(target.endsWith(".glb"))loads.push(rel);
  const type=target.endsWith(".html")?"text/html; charset=utf-8":
   target.endsWith(".js")?"text/javascript; charset=utf-8":
   target.endsWith(".json")?"application/json":
   target.endsWith(".glb")?"model/gltf-binary":"application/octet-stream";
  res.writeHead(200,{"Content-Type":type,"Cache-Control":"no-store",
   "X-Content-Type-Options":"nosniff"}).end(blob);
 }catch(err){res.writeHead(404).end("unavailable");}
});
let browser,context;
const output={schema:"G017_P022_16_X_29_REAL_WEBGL_STATIC_QA_V1",
 verdict:"HOLD",model_count:16,smoke,
 assertion_checks:checks,cases,errors,screenshot_paths:screens,glb_http_count:0,
 rights:"NOT_ADMITTED",shop_purchase:false,
 server_inventory_equip:false,two_hand_IK:false,projectile_firing:false};
try{
 await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
 const url="http://127.0.0.1:"+server.address().port;
 browser=await chromium.launch({headless:true,
  executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",
  args:["--use-gl=angle","--use-angle=swiftshader","--enable-webgl",
   "--enable-unsafe-swiftshader"]});
 context=await browser.newContext({viewport:{width:740,height:800},serviceWorkers:"block"});
 const page=await context.newPage();
 page.on("pageerror",e=>errors.push(String(e)));
 assert.equal((await page.goto(url+"/?g017_qa=1",{waitUntil:"domcontentloaded"})).status(),200);
 await page.waitForFunction(()=>window.__g017P022Ready===true,undefined,{timeout:30000});
 const catalog=await page.evaluate(()=>window.__g017P022QA);
 assert.equal(catalog.activeCount,16);assert.equal(catalog.projectileProps,3);
 assert.equal(catalog.formalRelease,false);
 checks.push("16_nonrelease_glb_shas_and_strict_qa_gate");
 for(const key of keys){
  const hero=futures.visual_models.find(x=>x.character_id===key&&x.variant==="RED");
  const info=await page.evaluate(x=>window.startHero(x),
    {characterKey:key,heroPath:"/"+hero.runtime_glb});
  assert.equal(info.liveRenderers,1);assert.equal(info.maxRenderers,1);
  const poses=smoke?["DEFAULT"]:key==="A1"?["DEFAULT","A1_CORRECT_MID"]:
    key==="A3"?["DEFAULT","A3_RAISED_ARM"]:["DEFAULT"];
  for(const pose of poses){
   await page.evaluate(x=>window.setGripPose(x),pose);
   for(const item of items){
    const actual=await page.evaluate(assetId=>window.attachG017Main({assetId}),
      item.qa_id);
    assert.equal(actual.mainCount,1);
    assert.equal(actual.offCount,0);
    assert.equal(actual.liveRenderers,1);
    assert.equal(actual.maxRenderers,1);
    const m=actual.metric;
    assert.equal(m.asset_id,item.qa_id);
    assert.equal(m.functional_class,item.functional_class);
    assert.equal(m.actualSha,expectedSHA.get(item.qa_id));
    assert.equal(m.attachStatus,"attached");
    assert.equal(m.childCount,1);
    assert.match(m.anchorSource,/^HAND_BONE:/);
    assert(m.boneMatrixDelta<1e-3,
      key+"/"+pose+"/"+item.code+":hand drift "+m.boneMatrixDelta);
    assert(!m.boundEmpty);
    assert(m.centerHandRatio<0.38,
      key+"/"+pose+"/"+item.code+":distance "+m.centerHandRatio);
    assert(m.maxDimensionRatio>0.025&&m.maxDimensionRatio<0.65,
      key+"/"+pose+"/"+item.code+":dimension "+m.maxDimensionRatio);
    cases.push({key,pose,code:item.code,qa_id:item.qa_id,
      functional_class:item.functional_class,skinned:item.skinned,metric:m});
    if((key==="A1"&&pose==="DEFAULT"&&item.code==="H-W1B")||
      (key==="A3"&&pose==="A3_RAISED_ARM"&&item.code==="AR-W5R")||
      (key==="K1"&&pose==="DEFAULT"&&item.code==="AR-W6B")){
       const target=path.join(evidence,"G017_"+key+"_"+item.code+"_REAL_HERO_20261021.png");
       await page.locator("canvas").screenshot({path:target});
       screens.push(target);
    }
   }
   checks.push(key+"_"+pose+"_static_glb_models_"+items.length);
  }
 }
 assert.deepEqual(errors,[]);
 const after=await page.evaluate(()=>window.closeGripScene());
 assert.equal(after.liveRenderers,0);assert.equal(after.maxRenderers,1);
 checks.push("renderer_disposed_one_owner");
 assert.equal(cases.length,smoke?3:496);
 assert(loads.length>= (smoke?3:16));
 output.glb_http_count=loads.length;
 output.hero_count=keys.length;
 output.pose_count=smoke?1:31;
 output.case_count=cases.length;
 output.handheld_cases=cases.filter(x=>x.functional_class==="MAIN_HAND_STATIC_QA").length;
 output.projectile_prop_cases=cases.filter(x=>x.functional_class==="PROJECTILE_PROP_ONLY").length;
 output.max_renderers=after.maxRenderers;
 output.verdict="G017_P022_16_REAL_SHARED_HERO_STATIC_WEBGL_QA_PASS";
}catch(err){
 output.failure=String(err.stack||err).slice(0,2500);
 process.exitCode=1;
}finally{
 await context?.close();await browser?.close();
 await new Promise(resolve=>server.close(resolve));
 await mkdir(evidence,{recursive:true});
 const target=path.join(evidence,smoke?
  "G017_P022_16_SMOKE_REAL_HERO_20261021.json":
  "G017_P022_16_ALL29_REAL_HERO_WEBGL_20261021.json");
 await writeFile(target,JSON.stringify(output,null,2));
 console.log(JSON.stringify({verdict:output.verdict,
  cases:cases.length,checks:checks.length,screens:screens.length,
  error:output.failure||null,raw:target}));
}
