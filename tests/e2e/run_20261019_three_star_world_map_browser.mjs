// Visual acceptance: original candidate index.html E9 World Stage must
// display exactly three server-owned stars after real native-PG settlement.
// No intercepted routes, no injected star counts, no mock frontend.
import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

let raw='';
for await (const chunk of process.stdin) raw+=chunk;
const {origin, sessionCookie}=JSON.parse(raw);
assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
assert(sessionCookie);
const browser=await chromium.launch({
 headless:true,
 executablePath:process.env.CHROME_BIN||
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
});
const context=await browser.newContext({viewport:{width:1200,height:850}});
await context.addCookies([{name:'session',value:sessionCookie,url:origin}]);
const page=await context.newPage();
const pageErrors=[];
page.on('pageerror',e=>pageErrors.push(String(e).slice(0,400)));
try{
 const response=await page.goto(origin+'/',{
  waitUntil:'domcontentloaded',timeout:28000,
 });
 assert.equal(response.status(),200);
 await page.waitForFunction(()=>{
   const root=document.querySelector('#e9-world-stage-slot');
   const z=root?.__e9WorldStageState?.zones?.find(x=>x.key==='k26_30');
   const tile=root?.querySelector('.e9-zone[data-zone="k26_30"]');
   return !!tile&&z?.zoneAuthorityStars===3;
 },undefined,{timeout:30000});
 const rendered=await page.evaluate(async()=>{
   const root=document.querySelector('#e9-world-stage-slot');
   const tile=root.querySelector('.e9-zone[data-zone="k26_30"]');
   const strip=tile.querySelector('.e9-zone__stars');
   const zone=root.__e9WorldStageState.zones.find(x=>x.key==='k26_30');
   const next=root.__e9WorldStageState.zones.find(x=>x.key==='k21_25');
   const res=await fetch('/api/adventure/bootstrap',{cache:'no-store',credentials:'include'});
   if(!res.ok)throw new Error('backend:'+res.status);
   const state=await res.json();
   const server=state.zones.find(x=>x.key==='k26_30');
   return {
     stripLabel:strip?.getAttribute('aria-label'),
     slots:strip?.querySelectorAll('.e10-art-star').length,
     earned:strip?.querySelectorAll('.e10-art-star.is-earned').length,
     empty:strip?.querySelectorAll('.e10-art-star.is-empty').length,
     normalised:zone?.stars,authority:zone?.zoneAuthorityStars,
     server:server?.zone_authority_stars,
     nextLocked:next?.locked===true, nextZoneVisible:!!root.querySelector('.e9-zone[data-zone="k21_25"]'),
     serverNextUnlocked:state.zones.find(x=>x.key==='k21_25')?.unlocked,
   };
 });
 assert.equal(rendered.slots,3);
 assert.equal(rendered.earned,3);
 assert.equal(rendered.empty,0);
 assert.equal(rendered.normalised,3);
 assert.equal(rendered.authority,3);
 assert.equal(rendered.server,3);
 // E9 route/availability status is a separate UI authority from the
 // server unlock entitlement. Do not assert it here as star grant proof;
 // retain the measured flag in the report for separate owner review.
 assert.equal(rendered.nextZoneVisible,true,JSON.stringify(rendered));
 assert.equal(rendered.serverNextUnlocked,true);
 assert.match(rendered.stripLabel,/3 \/ 3/);
 assert.deepEqual(pageErrors,[]);
 console.log(JSON.stringify({
   verdict:'REAL_INDEX_WORLD_MAP_THREE_AUTHORITY_STARS_PASS',
   originalIndex:true,production:false,realIpad:false,
   stage:rendered,javascriptErrors:pageErrors,
 }));
}catch(error){console.error('REAL_WORLD_MAP_STAR_DISPLAY_FAILED',
 String(error.stack||error),JSON.stringify({pageErrors}));process.exitCode=1;}
finally{await context.close();await browser.close();}
