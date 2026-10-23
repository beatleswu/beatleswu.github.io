// Local fixture only. Uses actual candidate UI + HTTP + existing SGF engine.
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium} from 'file:///D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core/index.mjs';
const root=new URL('../../',import.meta.url);
const output=new URL('artifacts/g066/',root);await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const results=[], errors=[];
async function check(name,fn){await fn();results.push({name,status:'PASS'});}
try {
  await check('OFF: embed preserves existing Quest Board DOM and sends no writes',async()=>{
    const page=await browser.newPage();let writes=0;
    page.on('request',r=>{if(r.method()==='POST')writes++;});
    await page.route('**/api/course-v1/summary',r=>r.fulfill({status:404,contentType:'application/json',body:'{"error":"course_feature_off"}'}));
    await page.goto('http://127.0.0.1:5066/fixture-host');
    await page.waitForLoadState('networkidle');
    assert.equal(await page.locator('#quest-board').count(),1);
    assert.equal(await page.locator('#g066-tabs').count(),0);
    assert.equal(await page.locator('iframe').count(),0);assert.equal(writes,0);await page.close();
  });
  const context=await browser.newContext({viewport:{width:1280,height:900}});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await check('ON fixture: tabs preserve same Quest Board node and keyboard navigation',async()=>{
    await page.goto('http://127.0.0.1:5066/fixture-host');
    await page.waitForSelector('#g066-course-tab');
    await page.evaluate(()=>{window.originalQuest=document.getElementById('quest-board');});
    await page.getByRole('tab',{name:'啟蒙班 20 課'}).click();
    await page.getByRole('tab',{name:'啟蒙班 20 課'}).press('ArrowLeft');
    assert.equal(await page.locator('#quest-board').isVisible(),true);
    assert.equal(await page.evaluate(()=>window.originalQuest===document.getElementById('quest-board')),true);
    await page.getByRole('tab',{name:'啟蒙班 20 課'}).click();
  });
  const frame=page.frameLocator('iframe');
  await check('20 lessons / 4 weeks, pending media, next lesson locked',async()=>{
    await frame.locator('[data-lesson="1"]').click();
    assert.equal(await frame.locator('#lessons h2').count(),4);
    assert.equal(await frame.locator('[data-lesson]').count(),20);
    assert.equal(await frame.locator('[data-lesson="2"]').isDisabled(),true);
    await frame.locator('#start').click();await frame.locator('#board button').first().waitFor();
    assert.match(await frame.locator('#media-status').innerText(),/Owner/);
    assert.equal(await frame.locator('#board button').count(),81);
  });
  await check('real SGF wrong answer + replacement retry cannot inflate first score',async()=>{
    await frame.getByRole('button',{name:'5,5',exact:true}).click();await frame.locator('#submit').click();
    await frame.locator('#replace').waitFor({state:'visible'});await frame.locator('#replace').click();
    await frame.getByRole('button',{name:'1,2',exact:true}).click();await frame.locator('#submit').click();
    await frame.locator('#score').filter({hasText:'答對了'}).waitFor();
    assert.match(await frame.locator('#score').innerText(),/首次答對 0\/8/);
    await frame.locator('#next').click();
  });
  await check('remaining seven first answers unlock lesson 2',async()=>{
    for(let slot=1;slot<8;slot++) {
      await frame.locator('#question-title').filter({hasText:`練習 ${slot+1} / 8`}).waitFor();
      await frame.getByRole('button',{name:'1,2',exact:true}).click();await frame.locator('#submit').click();
      await frame.locator('#score').filter({hasText:`已作答 ${slot+1}/8`}).waitFor();
      if(slot<7)await frame.locator('#next').click();
    }
    await frame.locator('[data-lesson="2"]:not(:disabled)').waitFor();
    await page.screenshot({path:new URL('ui-desktop.png',output).pathname.replace(/^\/(\w:)/,'$1'),fullPage:true});
  });
  await check('separate browser context resumes persisted progress',async()=>{
    const other=await browser.newContext();const p=await other.newPage();
    await p.goto('http://127.0.0.1:5066/course-v1/');await p.locator('[data-lesson="2"]:not(:disabled)').waitFor();
    await p.locator('[data-lesson="1"]').click();await p.locator('#start').click();
    await p.locator('#course-status').filter({hasText:'本課已完成'}).waitFor();await other.close();
  });
  await check('375px and 768px responsive UI has no horizontal overflow',async()=>{
    for(const width of [375,768]) {
      const p=await browser.newPage({viewport:{width,height:900}});p.on('pageerror',e=>errors.push(e.message));
      await p.goto('http://127.0.0.1:5066/course-v1/');await p.locator('[data-lesson="2"]').click();
      await p.locator('#start').click();await p.locator('#board button').first().waitFor();
      assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      await p.screenshot({path:new URL(`ui-${width}.png`,output).pathname.replace(/^\/(\w:)/,'$1'),fullPage:true});await p.close();
    }
  });
  assert.deepEqual(errors,[]);
  results.push({name:'browser page errors',status:'PASS',errors});
} catch(error) {results.push({name:'browser execution',status:'FAIL',error:String(error.stack)});process.exitCode=1;}
finally {await browser.close();await writeFile(new URL('browser-results.json',output),JSON.stringify({scope:'OFFLINE_FIXTURE_ONLY',results},null,2));console.log(JSON.stringify(results,null,2));}
