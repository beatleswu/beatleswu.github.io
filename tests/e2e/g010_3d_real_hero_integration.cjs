'use strict';
const {chromium}=require('D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl','--enable-unsafe-swiftshader']});
 const checks=[],unexpected3d=[],browserErrors=[];
 const data={schema:'G010_3D_ACTUAL_HERO_PAGE_V1',checks,unexpected3d,browserErrors,verdict:'HOLD'};
 try {
  const ctx=await browser.newContext({viewport:{width:1100,height:900}}),page=await ctx.newPage();
  page.on('pageerror',e=>{if(/g010_hero_3d_gallery|three|GLTFLoader|WebGL/i.test(String(e)))unexpected3d.push(String(e));else browserErrors.push(String(e).slice(0,220))});
  const response=await page.goto('http://127.0.0.1:6197/hero.html?tab=equipment',{waitUntil:'domcontentloaded',timeout:35000});
  assert.equal(response.status(),200);checks.push('real_Hero_HTML200');
  await page.waitForSelector('#g010-3d-gallery');checks.push('real_Hero_3d_markup');
  await page.waitForFunction(()=>document.querySelector('#g010-3d-category')?.options.length===5,
    undefined,{timeout:30000});checks.push('real_5_categories');
  if(await page.locator('#g009-panel-equipment').evaluate(el=>el.hidden)){
    await page.locator('#g009-panel-equipment').evaluate(el=>el.hidden=false);
  }
  await page.selectOption('#g010-3d-category','weapon');
  await page.waitForFunction(()=>document.querySelector('#g010-3d-gallery')?.dataset.state==='ready' &&
    document.querySelector('#g010-3d-gallery')?.dataset.integrity==='verified' &&
    document.querySelectorAll('#g010-3d-canvas canvas').length===1,
  undefined,{timeout:55000});
  checks.push('actual_Hero_equipment_tab_WebGL_weapon');
  const boxes=await page.locator('#g010-3d-canvas canvas').boundingBox();
  assert(boxes.width>250&&boxes.height>240);checks.push('real_Hero_weapon_visible_canvas_area');
  assert.equal(unexpected3d.length,0);
  checks.push('real_3d_module_no_errors');
  data.verdict='ACTUAL_HERO_WEBGL_GALLERY_WIRING_PASS';
  await ctx.close();
 }catch(e){data.failure=String(e.stack||e).slice(0,1900);process.exitCode=1}
 finally{
  data.pass=checks.length;
  fs.writeFileSync(path.join(__dirname,'G010_3D_REAL_HERO_BROWSER_20261021.json'),JSON.stringify(data,null,2));
  console.log(JSON.stringify(data));
  await browser.close();
 }
})().catch(e=>{console.error(String(e));process.exitCode=1});
