import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';
let stdin='';
for await(const part of process.stdin)stdin+=part;
const {origin,sessionCookie}=JSON.parse(stdin);
assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_BIN||
  'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
await context.addCookies([{name:'session',value:sessionCookie,url:origin}]);
const page=await context.newPage();
const writes=[],errors=[];
page.on('request',r=>{
 const url=new URL(r.url());
 if(url.origin===origin&&url.pathname.startsWith('/api/')&&r.method()!=='GET')
  writes.push(r.method()+' '+url.pathname);
});
page.on('pageerror',e=>errors.push(String(e)));
try{
 const r=await page.goto(origin+'/community',{waitUntil:'domcontentloaded',timeout:25000});
 assert.equal(r.status(),200);
 const js=await page.request.get(origin+'/g010_m4_quest_leaderboard.js');
 assert.equal(js.status(),200);
 const css=await page.request.get(origin+'/g010_m4_quest_leaderboard.css');
 assert.equal(css.status(),200);
 await page.waitForFunction(()=>document.querySelector('#leaderboard-context')?.dataset.boardContext==='weekly',
  undefined,{timeout:18000});
 const view=await page.evaluate(async()=>{
  const panel=document.querySelector('#g010-m4-quest-panel');
  const res=await fetch('/api/quests/v2',{credentials:'include'});
  return {hidden:panel.hidden,display:getComputedStyle(panel).display,
   claims:panel.querySelectorAll('[data-m4-claim]').length,
   status:res.status,
   board:document.querySelector('#leaderboard-context')?.dataset.boardContext,
   jsLoaded:!!window.G010M4QuestPanel};
 });
 assert.deepEqual({hidden:view.hidden,display:view.display,claims:view.claims,status:view.status},
   {hidden:true,display:'none',claims:0,status:404});
 assert.equal(view.jsLoaded,true);
 assert.deepEqual(writes,[]);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({verdict:'G010_M4_QUEST_OFF_REAL_BROWSER_FAIL_CLOSED_PASS',
  view,writes,errors,production:false}));
}catch(e){
 console.error('G010_M4_OFF_BROWSER_FAILED',String(e.stack||e),JSON.stringify({writes,errors,url:page.url()}));
 process.exitCode=1;
}finally{await context.close();await browser.close();}
