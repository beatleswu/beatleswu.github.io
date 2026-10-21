'use strict';
const {chromium}=require('D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl','--enable-unsafe-swiftshader']});
 const report={schema:'G011_DEFAULT_PUBLIC_CATALOG_GATE_V1',pass:[],error:[],verdict:'HOLD'};
 const c=await b.newContext({viewport:{width:1100,height:880}}),page=await c.newPage();
 try{
  page.on('pageerror',e=>report.error.push(String(e)));
  const r=await page.goto('http://127.0.0.1:6197/tests/e2e/g010_3d_activation_fixture.html',{waitUntil:'domcontentloaded'});
  assert.equal(r.status(),200);report.pass.push('fixture_200');
  await page.waitForFunction(()=>document.querySelector('#g010-3d-category')?.options.length===5,{timeout:24000});
  report.pass.push('public_catalog_still_only_five_categories');
  const opts=await page.locator('#g010-3d-category option').evaluateAll(a=>a.map(x=>x.value));
  assert(!opts.includes('p038_qa'));report.pass.push('QA_legacy_28_hidden_by_default');
  await page.selectOption('#g010-3d-category','weapon');
  assert.equal(await page.locator('#g010-3d-model option').count(),4);
  report.pass.push('formal_weapon_catalog_still_exact_four');
  await page.waitForFunction(()=>document.getElementById('g010-3d-gallery')?.dataset.integrity==='verified',{timeout:40000});
  report.pass.push('formal_glb_still_SHA_valid');
  assert.equal(report.error.length,0);report.pass.push('no_browser_errors');
  report.verdict='G011_28_QA_MODE_FAIL_CLOSED_DEFAULT_PASS';
 }catch(e){report.failure=String(e.stack||e);process.exitCode=1}
 finally{
  fs.writeFileSync(path.join(__dirname,'G011_QA_DEFAULT_OFF_BROWSER_20261021.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));await c.close();await b.close();
 }
})().catch(e=>{console.error(String(e.stack||e));process.exitCode=1});
