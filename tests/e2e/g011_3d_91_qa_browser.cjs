'use strict';
const { chromium } = require('D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl','--enable-unsafe-swiftshader']});
  const report={schema:'G010_TRUE_3D_GALLERY_BROWSER_V1',checks:[],errors:[],httpFail:[],
    selected:[],verdict:'HOLD'};
  let context;
  try{
    context=await browser.newContext({viewport:{width:1000,height:850},deviceScaleFactor:1});
    const page=await context.newPage();
    page.on('pageerror',e=>report.errors.push(String(e)));
    page.on('response',res=>{if(res.status()>=400&&new URL(res.url()).origin==='http://127.0.0.1:6197')report.httpFail.push(res.status()+':'+new URL(res.url()).pathname)});
    const url='http://127.0.0.1:6197/tests/e2e/g010_3d_activation_fixture.html?g011_qa=1';
    const r=await page.goto(url,{waitUntil:'domcontentloaded',timeout:35000});
    assert.equal(r.status(),200);report.checks.push('authentic_static_fixture_page');
    await page.waitForFunction(()=>document.querySelector('#g010-3d-model').options.length===33,{timeout:25000});
    const cat=await page.locator('#g010-3d-category option').allTextContents();
    assert.deepEqual(cat.length,6);report.checks.push('five_owner_authorized_categories');
    async function selectedCount(category,expected){
      await page.selectOption('#g010-3d-category',category);
      await page.waitForFunction(expected=>document.querySelector('#g010-3d-model').options.length===expected,expected,{timeout:10000});
      report.checks.push('catalog_'+category+'_'+expected);
      return await page.locator('#g010-3d-model option').evaluateAll(os=>os.map(o=>o.value));
    }
    const counts={character:33,spirit:18,accessory:6,weapon:4,bonus:2,p038_qa:28};
    const catalog={};
    for(const [kind,count] of Object.entries(counts)){catalog[kind]=await selectedCount(kind,count)}
    const targets=Object.entries(counts).flatMap(([category])=>catalog[category].map(id=>({category,id})));
    if(targets.length!==91)throw Error('catalog_len_expected_63');
    for(const [index,model] of targets.entries()){
      await page.selectOption('#g010-3d-category',model.category);
      await page.selectOption('#g010-3d-model',model.id);
      await page.waitForFunction(id=>{const root=document.getElementById('g010-3d-gallery');
        return root.dataset.assetId===id && root.dataset.integrity==='verified'&&root.dataset.state==='ready';},
        model.id,{timeout:90000});
      const actual=await page.locator('#g010-3d-canvas canvas').count();
      assert.equal(actual,1,'real WebGL renderer only one');
      report.selected.push({id:model.id,category:model.category,shaVerified:true,realCanvas:true});
      report.checks.push('rendered_sha_verified_'+model.category+'_'+index);
      if((index+1)%10===0) console.log('G010_3D_REAL_WEBGL_'+(index+1)+'_OF_91');
      if(index===2){
        const canvas=page.locator('#g010-3d-canvas canvas'),box=await canvas.boundingBox();
        const first=crypto.createHash('sha256').update(await canvas.screenshot()).digest('hex');
        await page.mouse.move(box.x+box.width*0.5,box.y+box.height*0.5);
        await page.mouse.down();await page.mouse.move(box.x+box.width*0.85,box.y+box.height*0.5,{steps:7});await page.mouse.up();
        await page.waitForTimeout(250);
        const second=crypto.createHash('sha256').update(await canvas.screenshot()).digest('hex');
        assert.notEqual(first,second,'3d rotation changes genuine pixels');
        report.checks.push('genuine_webgl_rotation_pixel_delta');
        await page.click('#g010-3d-reset');report.checks.push('reset_view_click');
      }
    }
    await page.locator('#g009-panel-equipment').evaluate(el=>el.hidden=true);
    await page.waitForFunction(()=>document.querySelectorAll('#g010-3d-canvas canvas').length===0,{timeout:15000});
    report.checks.push('gpu_canvas_disposed_when_tab_hidden');
    await page.locator('#g009-panel-equipment').evaluate(el=>el.hidden=false);
    await page.waitForFunction(()=>document.querySelectorAll('#g010-3d-canvas canvas').length===1
      && document.querySelector('#g010-3d-gallery').dataset.integrity==='verified',{timeout:60000});
    report.checks.push('recreated_on_tab_return');
    assert.equal(report.errors.length,0,report.errors.slice(0,5).join('|'));
    assert.equal(report.httpFail.length,0,report.httpFail.slice(0,6).join('|'));
    report.checks.push('no_uncaught_browser_errors');
    report.checks.push('no_http_fails');
    report.verdict='G011_91_REAL_GLBS_QA_ONLY_PASS';
  }catch(e){report.failure=String(e.stack||e).slice(0,1800);process.exitCode=1}
  finally{
    report.pass=report.checks.length;
    const file=path.join(__dirname,'G011_3D_QA_91_REAL_WEBGL_BROWSER_20261021.json');
    fs.writeFileSync(file,JSON.stringify(report,null,2));
    console.log(JSON.stringify({verdict:report.verdict,pass:report.pass,rendered:report.selected.length,
      errors:report.errors.slice(0,4),httpFail:report.httpFail.slice(0,4),failure:report.failure}));
    await context?.close();await browser.close();
  }
})().catch(e=>{console.error(String(e.stack||e));process.exitCode=1});
