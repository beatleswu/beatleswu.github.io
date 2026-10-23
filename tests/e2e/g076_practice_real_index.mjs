import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.G076_PLAYWRIGHT_CORE || 'D:/go-website/tests/e2e/node_modules/playwright-core');
const [url,cookie,out]=process.argv.slice(2);
const checks=[];
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,
  args:['--no-proxy-server','--disable-background-networking','--disable-component-update','--disable-sync']});
try {
  const context=await browser.newContext({viewport:{width:1200,height:1000},serviceWorkers:'block'});
  await context.addCookies([{name:'session',value:cookie,url}]);
  // Keep actual index.html, every gameplay script, QuestionLoader, renderer
  // and loadQuestion. Only unrelated login/onboarding auto-boot is suppressed.
  await context.addInitScript(()=>{Object.defineProperty(window,'onload',{configurable:true,get:()=>null,set:()=>{}});});
  await context.route('**/*',async route=>{
    const req=route.request(), u=new URL(req.url());
    if(u.origin!==new URL(url).origin) return route.abort();
    if(u.pathname.startsWith('/api/') && !u.pathname.startsWith('/api/g076/') &&
        !u.pathname.startsWith('/api/srs/practice/') && !u.pathname.startsWith('/api/question/') &&
        u.pathname!='/api/curriculum/summary' && u.pathname!='/api/srs/all') {
      return route.fulfill({json:{},status:200});
    }
    return route.continue();
  });
  const page=await context.newPage();
  const errors=[],pageErrors=[];page.on('pageerror',e=>{pageErrors.push(e.message);errors.push(e.message);console.error('PAGEERROR',e.stack);});
  page.on('console',msg=>{if(msg.type()==='error') errors.push(msg.text());});
  const responses=[];page.on('response',r=>{if(r.url().includes('/api/g076/nonmap/')) responses.push(r);});
  await page.goto(url,{waitUntil:'networkidle'});
  async function load() {
    return page.evaluate(async()=>{
      _currentUserId=101; _isPremiumUser=true;
      const q=await (await fetch('/api/question/701')).json();
      allQuestions=[q];
      return await loadQuestion(q);
    });
  }
  async function snapshot(){return page.evaluate(()=>({
    active:!!_g076Practice,solved,answering,failed:_questionBoardFailedClosed,
    msg:document.getElementById('msg-box').textContent,
    board:logicBoard,tree:currentProblem?.tree, interval:document.getElementById('q-interval').textContent,
    marks:board?.obj_arr, content:currentQ?.content,
  }));}
  assert.equal(await load(),true,JSON.stringify({state:await snapshot(),errors}));
  assert.equal((await snapshot()).active,true);checks.push('actual index loadQuestion activates Practice');
  assert.ok(await page.locator('#board-canvas-wrap canvas').count());checks.push('actual WGo canvas');
  assert.equal((await snapshot()).content.includes(';B['),false);checks.push('initial board has no answer tree');
  async function click(x,y){
    const point=await page.evaluate(([x,y])=>{
      const canvas=document.querySelector('#board-canvas-wrap canvas');
      const r=canvas.getBoundingClientRect();
      return {x:r.left+board.getX(_bx(x))/(board.pixelRatio || 1),
              y:r.top+board.getY(_by(y))/(board.pixelRatio || 1)};
    },[x,y]);
    await page.mouse.click(point.x,point.y);
    await page.waitForFunction(()=>!answering);
  }
  await click(0,0);
  await page.waitForFunction(()=>logicBoard[1]?.[1]==='W');
  assert.equal((await snapshot()).solved,false);checks.push('physical canvas click -> server CONTINUE and opponent reply');
  await page.reload({waitUntil:'networkidle'});assert.equal(await load(),true);
  assert.equal((await snapshot()).board[0][0],'B');assert.equal((await snapshot()).board[1][1],'W');
  checks.push('reload restores committed prefix');
  // Drop only the first terminal HTTP response AFTER the actual server commit.
  let dropped=false;
  await page.route('**/api/g076/nonmap/steps',async route=>{
    if(!dropped){dropped=true;await route.fetch();return route.abort('failed');}
    return route.continue();
  });
  await click(2,2);
  await page.waitForFunction(()=>!!_g076PracticePending && !answering);
  assert.equal((await snapshot()).board[2][2],null);checks.push('lost response does not paint or grade locally');
  await click(3,0);assert.equal((await snapshot()).board[3][0],null);
  await click(2,2);
  await page.waitForFunction(()=>solved && document.getElementById('msg-box').textContent.includes('XP +0'));
  const final=await snapshot();assert.equal(final.board[2][2],'B');assert.ok(final.interval);
  assert.equal(await page.locator('#today-count').textContent(),'1');
  assert.equal(await page.locator('#today-correct').textContent(),'1');
  assert.equal(await page.locator('#today-acc').textContent(),'100%');
  checks.push('committed daily score recovered after response loss');
  const marked=await page.evaluate(()=>board.obj_arr[_bx(2)][_by(2)].some(x=>x.type==='CR'));
  assert.ok(marked);checks.push('same request retry displays server correct, result mark and SRS interval');
  assert.ok(final.msg.includes('XP +0'));checks.push('Practice awards zero XP');
  const curriculum=await page.evaluate(async()=>(await fetch('/api/curriculum/summary')).json());
  assert.equal(curriculum.units[0].practiced,1);checks.push('existing school progress read model');
  await page.screenshot({path:path.join(out,'correct-index.png'),fullPage:true});
  await page.reload({waitUntil:'networkidle'});assert.equal(await load(),true);
  assert.equal((await snapshot()).solved,true);checks.push('terminal reload recovers recorded result');
  assert.equal(await page.locator('#today-count').textContent(),'1');
  await context.clearCookies();
  // Second real authenticated fixture player exercises the wrong terminal.
  // Cookie supplied separately by runner, never forge identity in application.
  await context.addCookies([{name:'session',value:process.env.G076_SECOND_COOKIE,url}]);
  await page.reload({waitUntil:'networkidle'});assert.equal(await load(),true);
  await click(3,0);await page.waitForFunction(()=>solved);
  assert.ok((await snapshot()).msg.includes('XP +0'));
  assert.equal(await page.locator('#today-correct').textContent(),'0');
  assert.equal(await page.locator('#today-acc').textContent(),'0%');
  assert.ok(await page.evaluate(()=>board.obj_arr[_bx(3)][_by(0)].some(x=>x.type==='MA')));
  checks.push('wrong terminal displays real cross mark and no XP');
  await page.screenshot({path:path.join(out,'wrong-index.png'),fullPage:true});
  await page.route('**/api/g076/practice/steps/capability',route=>route.fulfill({json:{
    protocol:'g076-practice-steps-v1',enabled:false,privacy_enforced:true}}));
  assert.equal(await load(),false);
  assert.ok(await page.evaluate(()=>_g076PracticeHold && !_g076Practice));
  checks.push('partial activation explicitly HOLDs without local grading fallback');
  assert.deepEqual(pageErrors,[],'uncaught browser script errors');
  fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify({status:'PASS',checks,errors,
    scope:'unmodified index.html; unrelated account onboarding onload suppressed; actual Practice loadQuestion and WGo mouse clicks'},null,2));
  console.log('PASS',checks.length);
} catch(error) {
  console.error(error); process.exitCode=1;
} finally {await browser.close();}
