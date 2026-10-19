// Browser proof: run the shipped map_battle_v1_adapter.js and real Flask+PG
// API via local fixture page. Fixture controls are NOT the production map UI.
import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';

const input = await new Promise((resolve,reject)=>{
  let s='';process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk=>s+=chunk);
  process.stdin.on('end',()=>{try{resolve(JSON.parse(s))}catch(e){reject(e)}});
});
assert.match(input.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
assert(input.sessionCookie && typeof input.sessionCookie==='string');

const browser=await chromium.launch({
  headless:true,
  executablePath:process.env.CHROME_BIN || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--disable-gpu-sandbox'],
});
const context=await browser.newContext({viewport:{width:850,height:660}});
await context.addCookies([{name:'session',value:input.sessionCookie,url:input.origin}]);
const page=await context.newPage();
const errors=[],results=[];
page.on('pageerror',e=>errors.push(String(e)));
async function check(label,fn){await fn();results.push({name:label,status:'PASS'})}
try{
  await page.goto(input.origin+'/__p1_adventure_browser',{waitUntil:'domcontentloaded',timeout:20000});
  await page.waitForFunction(()=>typeof window.MapBattleV1?.legacy?.prepare === 'function');
  await check('actual_shipped_adventure_adapter_loaded_in_chrome',async()=>{
    assert.equal(await page.evaluate(()=>window.MapBattleV1.legacy.runtimeService),
      'map-battle-v1-runtime');
    assert.equal(await page.locator('#stage').innerText(),'LOCAL_READY');
  });
  await check('user_click_enters_zone_real_flask_issues_attempt',async()=>{
    await page.getByRole('button',{name:'進入冒險'}).click();
    await page.waitForFunction(()=>document.querySelector('#stage')?.textContent==='ATTEMPT_ISSUED');
    assert.match(await page.locator('#attempt').innerText(),/^battle=/);
  });
  await check('user_click_correct_move_settles_real_sgf_judge_xp_and_map',async()=>{
    await page.getByRole('button',{name:'在 D4 下棋'}).click();
    await page.waitForFunction(()=>document.querySelector('#stage')?.textContent==='ANSWER_CORRECT');
    const result=await page.locator('#result').innerText();
    assert.match(result,/CORRECT/);
    assert.equal(await page.locator('#level').innerText(),'LV2');
    assert.equal(await page.locator('#xp').innerText(),'134 XP');
    assert.equal(await page.locator('#zone').innerText(),'k26_30 correct=1');
  });
  await check('browser_repeat_click_is_server_replay_no_extra_xp',async()=>{
    await page.getByRole('button',{name:'重送相同答案'}).click();
    await page.waitForFunction(()=>document.querySelector('#stage')?.textContent==='DUPLICATE_IGNORED');
    assert.equal(await page.locator('#xp').innerText(),'134 XP');
    assert.equal(await page.locator('#zone').innerText(),'k26_30 correct=1');
  });
  await check('reloading_read_only_player_projection_is_durable',async()=>{
    await page.reload({waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.querySelector('#stage')?.textContent==='RELOADED_PLAYER_STATE');
    assert.equal(await page.locator('#level').innerText(),'LV2');
    assert.equal(await page.locator('#xp').innerText(),'134 XP');
    assert.equal(await page.locator('#zone').innerText(),'k26_30 correct=1');
  });
  assert.deepEqual(errors,[],'browser page errors');
  console.log(JSON.stringify({
    schema:'GO_P1_REAL_ADVENTURE_BROWSER_TO_PG_R1',
    verdict:'LOCAL_REAL_CHROME_SHIPPED_MAP_ADAPTER_REAL_FLASK_PG_PASS',
    passed:results.length,checks:results,
    product_adventure_view_used:false,
    production_player_login:false,
    real_iPad:false,
    source:'js/map_battle_v1_adapter.js'
  },null,2));
}catch(e){console.error('BROWSER_REAL_JOURNEY_FAILED',e.stack||String(e));process.exitCode=1;}
finally{await context.close();await browser.close();}
