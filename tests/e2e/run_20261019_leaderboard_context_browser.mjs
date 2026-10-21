// G Master: actual community.html Chrome DOM rendering with local fixture API.
// Does not authenticate Test02, load production data or issue any reward.
import assert from 'node:assert/strict';
import {createReadStream, statSync} from 'node:fs';
import {createServer} from 'node:http';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {chromium} from 'playwright-core';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const user=(rank,username,score,is_you=false,display_name=username)=>({
  rank, username, score, is_you, display_name, rank_level: 'LV15',
  character_key:'apprentice', total_correct: score, max_combo: 5,
});
const fixture={
  weekly:[user(1,'Test',160),user(2,'Test02',150,true),user(3,'rival',140,false,
    '<img src=x onerror=window.__leaderboardInjected=1>')],
  monthly:[user(1,'winner',155),user(2,'Test',150),user(3,'Test02',149,true)],
  alltime:[user(1,'Test',3000),user(2,'Test02',2900,true)],
  rank:[user(1,'Test',3000),user(2,'Test02',2900,true)],
  combo:[user(1,'Test',10),user(2,'Test02',9,true)],
  friends:[user(1,'Test02',2900,true),user(2,'Test',2100)],
};
const mime={'.js':'application/javascript','.html':'text/html; charset=utf-8',
  '.css':'text/css','.json':'application/json','.webp':'image/webp',
  '.png':'image/png','.svg':'image/svg+xml'};
const server=createServer((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  const name=url.pathname;
  const responses={
    '/api/community/leaderboard':fixture,
    '/api/auth/me':{username:'Test02',nickname:'Test02'},
    '/api/community/reviews':{items:[]},
    '/api/community/challenges':{items:[]},
    '/api/friends':{friends:[],requests:[]},
    '/api/community/leaderboard/reward-notifications':{ok:true,notifications:[]},
    '/api/community/leaderboard/reward-rules':{ok:true,rules:{}},
  };
  if(name.startsWith('/api/')){
    res.writeHead(200,{'content-type':'application/json'});
    res.end(JSON.stringify(responses[name] ?? {items:[],friends:[],challenges:[],requests:[]}));
    return;
  }
  if(name==='/') {
    res.writeHead(302,{location:'/community.html'});res.end();return;
  }
  if(name!=='/community.html' && !name.startsWith('/assets/') && !/^\/[a-zA-Z0-9_.\/-]+$/.test(name)){
    res.writeHead(404);res.end();return;
  }
  const full=path.resolve(root,'.'+decodeURIComponent(name));
  if(!full.startsWith(root+path.sep)||!statSync(full,{throwIfNoEntry:false})?.isFile()){
    res.writeHead(404);res.end();return;
  }
  res.writeHead(200,{'content-type':mime[path.extname(full)]||'application/octet-stream'});
  createReadStream(full).pipe(res);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
const browser=await chromium.launch({
  headless:true,executablePath:process.env.CHROME_BIN||'C:/Program Files/Google/Chrome/Application/chrome.exe',
});
const page=await browser.newPage({viewport:{width:820,height:1180}});
const results=[], browserErrors=[], browserResponses=[];
page.on('pageerror',e=>browserErrors.push(String(e)));
page.on('response',r=>{ if(r.url().includes('/api/')) browserResponses.push([r.status(),new URL(r.url()).pathname]); });
async function check(label,fn){await fn();results.push({label,status:'PASS'});}
const context=()=>page.locator('#leaderboard-context').innerText();
try {
  await page.route('https://fonts.googleapis.com/**',route=>route.abort());
  await page.goto(origin+'/community.html',{waitUntil:'domcontentloaded',timeout:20000});
  await page.waitForFunction(()=>document.querySelector('#leaderboard-context')?.dataset.boardContext==='weekly'
    && document.querySelector('#leaderboard-context')?.textContent.includes('150'),null,{timeout:15000});
  await check('weekly_real_dom_uses_server_is_you_not_nickname',async()=>{
    const text=await context();
    assert.match(text,/11/);
    assert.match(text,/150/);
    assert.match(text,/每週一|Monday/);
    assert.equal(await page.locator('#leaderboard-table tbody tr.me').count(),1);
    const me=page.locator('#leaderboard-table tbody tr.me .name');
    assert.match(await me.innerText(),/Test02/);
    assert.equal(await page.evaluate(()=>window.__leaderboardInjected??false),false);
    assert.equal(await page.locator('#leaderboard-table img[onerror]').count(),0);
  });
  await check('monthly_tab_rule_and_strict_above_score_gap',async()=>{
    await page.locator('[data-lb="monthly"]').click();
    const text=await context();
    assert.match(text,/每月 1 日|1st of each month/);
    assert.match(await page.locator('#view-leaderboard .panel-title').innerText(),/本月|This Month/);
    assert.match(text,/至少再多 2|at least \+2/);
    assert.match(text,/上榜不等於|eligibility is separate/);
    assert.equal(await page.locator('#leaderboard-context').getAttribute('data-board-context'),'monthly');
    assert.equal(await page.locator('#leaderboard-table tbody tr.me').count(),1);
  });
  await check('rank_is_explicitly_character_LV_not_go_dan_kyu',async()=>{
    await page.locator('[data-lb="rank"]').click();
    const text=await context();
    assert.match(text,/角色 LV|Character LV/);
    assert.match(await page.locator('[data-lb="rank"]').innerText(),/角色 LV|Character LV/);
    assert.match(await page.locator('#view-leaderboard .panel-title').innerText(),/角色 LV|Character LV/);
    assert.match(text,/圍棋段級位|Go rank/);
    assert.match(text,/總 XP|Lifetime XP/);
  });
  await check('combo_best_saved_streak_no_current_combo_claim',async()=>{
    await page.locator('[data-lb="combo"]').click();
    const text=await context();
    assert.match(text,/最高連續答對|Best answer streak/);
    assert.match(text,/保存的最高|saved longest/);
    assert.match(text,/至少再多 2|at least \+2/);
  });
  await check('friend_board_and_self_authorship',async()=>{
    await page.locator('[data-lb="friends"]').click();
    const text=await context();
    assert.match(text,/好友|Friends/);
    assert.match(text,/第 1 名|#1/);
  });
  await check('top50_truncation_never_invents_player_position',async()=>{
    await page.evaluate(()=>{state.leaderboard.monthly=[
      {rank:1,username:'Test',display_name:'Test',score:150,is_you:false},
    ];state.lbKey='monthly';renderLeaderboard();});
    const text=await context();
    assert.match(text,/前 50 名|top 50/);
    assert.match(text,/不推測|no rank or gap/);
    assert.equal(await page.locator('#leaderboard-context').getAttribute('data-has-own-row'),'false');
  });
  await check('empty_board_explains_no_records',async()=>{
    await page.evaluate(()=>{state.leaderboard.monthly=[];renderLeaderboard();});
    assert.match(await context(),/沒有可顯示的紀錄|No ranking records/);
  });
  await check('switch_back_rehydrates_current_authoritative_rows',async()=>{
    await page.evaluate(()=>{state.leaderboard.monthly=[
      {rank:1,username:'winner',display_name:'Winner',score:155,is_you:false},
      {rank:2,username:'Test02',display_name:'Test02',score:149,is_you:true},
    ];renderLeaderboard();});
    assert.match(await context(),/至少再多 7|at least \+7/);
    assert.equal(await page.locator('#leaderboard-table tbody tr.me').count(),1);
  });
  const output={schema:'GO_G_MASTER_LB_R02_R06_BROWSER_R1',verdict:'LOCAL_REAL_CHROME_DOM_API_FIXTURE_PASS_NOT_PRODUCTION',
    passed:results.length,checks:results,prod_Test02_login:false,real_iPad:false,production_mutation:false};
  console.log(JSON.stringify(output,null,2));
} catch(e){console.error('LEADERBOARD_DOM_E2E_FAILED',e.stack||String(e));process.exitCode=1;}
finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
