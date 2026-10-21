// G013 QA: real P038 8 mainhand + 4 offhand GLBs simultaneously attached
// through current G009/G008 Hero rig, 3 real character GLBs / animated poses.
// NOT player entitlement, Shop identity, release admission or real iPad UAT.
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {createServer} from "node:http";
import {readFile,writeFile,mkdir} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import path from "node:path";
import {chromium} from "file:///D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core/index.mjs";

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"../..");
const evidence=path.resolve("D:/go-odyssey-g010-3d-activation-evidence-20261021");
const candidate=JSON.parse(await readFile(path.join(root,"docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json"),"utf8"));
const future=JSON.parse(await readFile(path.join(root,"schemas/future30_c005_real_asset_runtime_mapping_manifest.json"),"utf8"));
const fixture=path.join(root,"tests/e2e/fixtures/g013_p038_dual_hand_qa.html");
const smoke=process.env.G013_SMOKE==="1";
const full29=process.env.G013_ALL29==="1";
const P038_ACTIVE29=Object.freeze(["A1","A3","V1","V2","V3","R1","R3","H1","H2","H3","K1","K2","K3","W1","W2","W3","M1","M2","S1","S2","F1","F2","F3","AR1","AR2","AR3","E1","E2","E3"]);
const targetKeys=full29?P038_ACTIVE29:["A1","A3","K1"];
assert.equal(P038_ACTIVE29.length,29);
assert.equal(new Set(P038_ACTIVE29).size,29);
assert.equal(candidate.models.length,12);
assert.equal(candidate.release_status,"NOT_ADMITTED");
const mains=candidate.models.filter(x=>x.slot==="MAIN_HAND");
const offs=candidate.models.filter(x=>x.slot==="OFF_HAND");
assert.equal(mains.length,8);assert.equal(offs.length,4);
const allPaths=new Set([
 "docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json",
 "js/g009_shared_hero_attachment_host.js",
 "js/hero_equipment_attachment_adapter.js",
 ...candidate.models.map(x=>x.runtime_glb),
 ...future.visual_models.filter(x=>targetKeys.includes(x.character_id)
    && x.variant==="RED").map(x=>x.runtime_glb),
]);
const prefixes=[
 "assets/3d_shop/p048/vendor/",
 "assets/3d_shop/p048/hero/",
 "assets/3d_shop/p048/future30/c005/",
];
const allExpected=new Map(candidate.models.map(x=>[x.qa_id,x.runtime_sha256]));
const checks=[],cases=[],screens=[],errors=[],assetLoads=[];
for(const c of candidate.models){
  const fp=path.join(root,c.runtime_glb);
  const bytes=await readFile(fp);
  assert.equal(bytes.subarray(0,4).toString("utf8"),"glTF");
  assert.equal(createHash("sha256").update(bytes).digest("hex"),c.runtime_sha256);
  checks.push("p038_model_sha_"+c.qa_id);
}
for(const key of targetKeys){
  const v=future.visual_models.find(x=>x.character_id===key&&x.variant==="RED");
  assert(v);const bytes=await readFile(path.join(root,v.runtime_glb));
  assert.equal(createHash("sha256").update(bytes).digest("hex"),v.runtime_sha256);
  checks.push("hero_sha_"+key);
}
const server=createServer(async(req,res)=>{
 try{
  const uri=new URL(req.url,"http://127.0.0.1/");
  const rel=decodeURIComponent(uri.pathname).replace(/^\/+/, "");
  const requested=rel===""?fixture:
    allPaths.has(rel) || prefixes.some(pre=>rel.startsWith(pre))
      ? path.join(root,rel):null;
  if(!requested||(!requested.startsWith(root+path.sep)&&requested!==fixture)){
    res.writeHead(404).end("no");return;
  }
  const bytes=await readFile(requested);
  const ct=requested.endsWith(".html")?"text/html; charset=utf-8":
     requested.endsWith(".js")?"text/javascript; charset=utf-8":
     requested.endsWith(".json")?"application/json":requested.endsWith(".glb")?
     "model/gltf-binary":"application/octet-stream";
  if(requested.endsWith(".glb"))assetLoads.push(rel);
  res.writeHead(200,{"Content-Type":ct,"Cache-Control":"no-store",
     "X-Content-Type-Options":"nosniff"}).end(bytes);
 }catch(e){res.writeHead(404).end("missing "+e.message);}
});
let browser;let context;
const out={schema:"G013_P038_12_X_3_REAL_HERO_DUAL_WEBGL_V1",
 status:"HOLD",smoke,claims:{product_release:false,player_equip:false,
  synthetic_hero_only:true,glb_sha_verified:true},
 checks,cases,screen_paths:screens,browser_errors:errors,assetLoads:0};
try{
 await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
 const origin="http://127.0.0.1:"+server.address().port;
 browser=await chromium.launch({headless:true,
  executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe",
  args:["--use-gl=angle","--use-angle=swiftshader","--enable-webgl",
    "--enable-unsafe-swiftshader"]});
 context=await browser.newContext({viewport:{width:740,height:800},deviceScaleFactor:1});
 const page=await context.newPage();
 page.on("pageerror",e=>errors.push(String(e)));
 const doc=await page.goto(origin+"/?g013_qa=1",{waitUntil:"domcontentloaded",timeout:35000});
 assert.equal(doc.status(),200);
 await page.waitForFunction(()=>window.__g013P038DualReady===true,undefined,{timeout:24000});
 checks.push("qa_manifest_fail_closed_opt_in_and_module_loaded");
 const checked=await page.evaluate(()=>window.__g013P038QACatalog);
 assert.equal(checked.activeCount,12);assert.equal(checked.releaseAdmitted,false);
 checks.push("manifest_all12_not_admitted");
 const chars=smoke?["A1"]:targetKeys;
 const mainList=smoke?mains.slice(0,2):mains;
 const offList=smoke?offs.slice(0,2):offs;
 for(const key of chars){
  const model=future.visual_models.find(x=>x.character_id===key&&x.variant==="RED");
  const info=await page.evaluate(x=>window.startHero(x),
     {characterKey:key,heroPath:"/"+model.runtime_glb});
  assert.equal(info.liveRenderers,1);assert.equal(info.maxRenderers,1);
  checks.push("real_three_renderer_"+key);
  const poses=key==="A1"?["DEFAULT","A1_CORRECT_MID"]:
    key==="A3"?["DEFAULT","A3_RAISED_ARM"]:["DEFAULT"];
  for(const pose of (smoke?["DEFAULT"]:poses)){
   await page.evaluate(p=>window.setGripPose(p),pose);
   for(const m of mainList) for(const o of offList){
    const v=await page.evaluate(ids=>window.attachP038Dual(ids),
      {mainId:m.qa_id,offId:o.qa_id});
    assert.equal(v.mainCount,1);assert.equal(v.offCount,1);
    assert.equal(v.liveRenderers,1);assert.equal(v.maxRenderers,1);
    assert.equal(v.realGeometry,true);
    assert.equal(v.metrics.length,2);
    for(const met of v.metrics){
     assert.equal(met.attachStatus,"attached");
     assert.equal(met.childCount,1);
     assert.match(met.anchorSource,/^HAND_BONE:/);
     assert(met.boneMatrixDelta<1e-3,
       key+"/"+pose+"/"+met.asset_id+" hand bone drift "+met.boneMatrixDelta);
     assert.equal(met.actualSha,allExpected.get(met.asset_id));
     assert(met.maxDimensionRatio>0.025 && met.maxDimensionRatio<0.65,
       key+"/"+pose+"/"+met.asset_id+" size ratio "+met.maxDimensionRatio);
     assert(met.centerHandRatio<0.38,
       key+"/"+pose+"/"+met.asset_id+" detached equipment "+met.centerHandRatio);
     assert.equal(met.boundEmpty,false);
    }
    cases.push({key,pose,mainId:m.qa_id,offId:o.qa_id,
      main:v.metrics[0],off:v.metrics[1]});
    if((m.qa_id===mains[0].qa_id)&&(o.qa_id===offs[0].qa_id)&&
       ["A1","A3","K1"].includes(key)&&
       (pose==="DEFAULT"||pose==="A3_RAISED_ARM")){
      const screenshot=path.join(evidence,
         "G013_"+key+"_"+pose+"_P038_SWORD_AND_SHIELD_20261021.png");
      await page.locator("canvas").screenshot({path:screenshot});
      screens.push(screenshot);
    }
   }
   checks.push("real_3d_both_hands_"+key+"_"+pose+"_"+mainList.length*offList.length);
  }
 }
 assert.equal(errors.length,0,errors.join(" | "));
 checks.push("real_webgl_browser_no_exceptions");
 const closed=await page.evaluate(()=>window.closeGripScene());
 assert.equal(closed.liveRenderers,0);assert.equal(closed.maxRenderers,1);
 checks.push("gpu_renderer_disposed_and_single_owned");
 const expected=smoke?4:full29?992:160;
 assert.equal(cases.length,expected);
 assert(assetLoads.length>=(smoke?2:12),
  "all true GLBs must be requested by real browser");
 out.assetLoads=assetLoads.length;
 out.status="G013_P038_12_REAL_DUAL_HANDS_HERO_WEBGL_PASS";
 out.case_count=cases.length;
 out.hero_characters=chars;
 out.real_pose_count=smoke?1:full29?31:5;
 out.model_sha_count=12;
 out.one_renderer_max=closed.maxRenderers;
}catch(e){
 out.failure=String(e.stack||e).slice(0,1900);
 process.exitCode=1;
}finally{
 await context?.close();await browser?.close();
 await new Promise(resolve=>server.close(resolve));
 out.check_count=checks.length;
 const target=path.join(evidence,smoke?
    "G013_P038_DUAL_HAND_SMOKE_20261021.json":
    full29?"G013_P038_ALL29_DUAL_HAND_20261021.json":
    "G013_P038_DUAL_HAND_FULL_20261021.json");
 await mkdir(evidence,{recursive:true});
 await writeFile(target,JSON.stringify(out,null,2));
 console.log(JSON.stringify({verdict:out.status,cases:cases.length,
  checks:checks.length,glbFetches:out.assetLoads,screens:screens.length,
  failure:out.failure||null,evidence:target}));
}
