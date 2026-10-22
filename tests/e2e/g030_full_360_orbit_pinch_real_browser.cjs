'use strict';
const {chromium}=require('D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core');
const assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const origin='http://127.0.0.1:6197';
async function scenario(browser,device,opts){
 const context=await browser.newContext(opts);
 const errors=[],httpFail=[],checks=[];
 const page=await context.newPage();
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('response',r=>{if(r.status()>=400&&r.url().startsWith(origin))httpFail.push(r.status()+':'+r.url())});
 const {g010GalleryDiagnostics:diagnostics}=await(async()=>{
  const res=await page.goto(origin+'/tests/e2e/g010_3d_activation_fixture.html',{waitUntil:'domcontentloaded',timeout:40000});
  assert.equal(res.status(),200);
  await page.waitForFunction(()=>document.querySelector('#g010-3d-gallery')?.dataset.integrity==='verified',{timeout:60000});
  return {g010GalleryDiagnostics:()=>null};
 })();
 // Live same ES module instance as the page (not a second renderer).
 const diag=async()=>page.evaluate(async()=>(
   await import('/js/g010_hero_3d_gallery.mjs')).g010GalleryDiagnostics());
 const start=await diag();
 assert.equal(start.controls,'unrestricted_360_two_axes_with_pinch_wheel_zoom_and_reset');
 assert.equal(start.catalog_size,71);
 const cameraDefault=start.camera_distance;
 const identity=(q)=>Math.abs(q[0])<0.0004&&Math.abs(q[1])<0.0004&&Math.abs(q[2])<0.0004&&Math.abs(Math.abs(q[3])-1)<0.0004;
 assert(identity(start.rotation_quaternion));
 checks.push('real_webgl_sha_verified_canvas_and_initial_identity');
 const turn=async(axis)=>{
  await page.evaluate(async(axis)=>{
   const c=document.querySelector('#g010-3d-canvas canvas');
   const event=(t,id,x,y)=>c.dispatchEvent(new PointerEvent(t,{pointerId:id,pointerType:'touch',
      clientX:x,clientY:y,bubbles:true,cancelable:true,isPrimary:true,buttons:1,button:0}));
   event('pointerdown',17,110,120);
   const checkpoints=[];
   for(let k=1;k<=4;k++){
    event('pointermove',17,axis==='horizontal'?110+180*k:110,axis==='vertical'?120+180*k:120);
    checkpoints.push((await import('/js/g010_hero_3d_gallery.mjs')).g010GalleryDiagnostics().rotation_quaternion);
   }
   event('pointerup',17,axis==='horizontal'?830:110,axis==='vertical'?840:120);
   window.__g030Last360=checkpoints;
  },axis);
  const result=await page.evaluate(()=>window.__g030Last360);
  assert.equal(result.length,4);
  const qmid=result[1],qfinal=result[3];
  assert(Math.abs(qmid[3])<0.002,'180 degree midpoint must face back or bottom');
  assert(identity(qfinal),'unrestricted '+axis+' completed full 360 and returned to original quaternion');
  assert.equal((await diag()).pointer_contacts,0);
  checks.push(axis+'_360_unrestricted_full_quaternion_turn');
 };
 // Capture genuine WebGL image change for a quarter turn before testing full turns.
 const canvas=page.locator('#g010-3d-canvas canvas');
 const initial=crypto.createHash('sha256').update(await canvas.screenshot()).digest('hex');
 await page.evaluate(()=>{
  const c=document.querySelector('#g010-3d-canvas canvas');
  const f=(t,x,y)=>c.dispatchEvent(new PointerEvent(t,{pointerId:22,pointerType:'touch',clientX:x,clientY:y,bubbles:true,cancelable:true,buttons:1,button:0}));
  f('pointerdown',100,100);f('pointermove',280,100);f('pointerup',280,100);
 });
 await page.waitForTimeout(150);
 const spun=crypto.createHash('sha256').update(await canvas.screenshot()).digest('hex');
 assert.notEqual(initial,spun,'true rendered pixels must change after 90 degree turn');
 checks.push('real_webgl_pixels_change_on_quarter_turn');
 await page.click('#g010-3d-reset');
 assert(identity((await diag()).rotation_quaternion));
 await turn('horizontal');
 await turn('vertical');
 // Detect portrait flip through mid-cycle (not a 40deg pitch clamp).
 checks.push('pitch_midcycle_180_proves_no_vertical_clamp');
 const zoom0=(await diag()).camera_distance;
 await page.click('#g010-3d-zoom-in');
 const zoom1=(await diag()).camera_distance;
 assert(zoom1<zoom0);
 await page.click('#g010-3d-zoom-out');
 const zoom2=(await diag()).camera_distance;
 assert(zoom2>zoom1);
 checks.push('zoom_buttons_bidirectional');
 const wheelPrevented=await page.evaluate(()=>{
  const c=document.querySelector('#g010-3d-canvas canvas');
  return !c.dispatchEvent(new WheelEvent('wheel',{deltaY:-240,cancelable:true,bubbles:true}));
 });
 assert(wheelPrevented,'wheel must prevent page scrolling over canvas');
 const zoom3=(await diag()).camera_distance;
 assert(zoom3<zoom2);
 checks.push('mouse_wheel_zoom_prevents_page_scroll');
 const pinchBefore=(await diag()).camera_distance;
 await page.evaluate(()=>{
  const c=document.querySelector('#g010-3d-canvas canvas');
  const event=(t,id,x,y)=>c.dispatchEvent(new PointerEvent(t,{pointerId:id,pointerType:'touch',
    clientX:x,clientY:y,bubbles:true,cancelable:true,buttons:1,button:0}));
  event('pointerdown',11,110,160);event('pointerdown',12,210,160);
  event('pointermove',12,260,160);
  event('pointerup',12,260,160);event('pointerup',11,110,160);
 });
 const pinchAfter=(await diag()).camera_distance;
 assert(pinchAfter<pinchBefore,'two-finger spread must zoom in');
 checks.push('two_touch_pointer_pinch_zooms_in');
 // Clamp near and far without leaving frustum range.
 await page.evaluate(()=>{
  const c=document.querySelector('#g010-3d-canvas canvas');
  for(let i=0;i<60;i++)c.dispatchEvent(new WheelEvent('wheel',{deltaY:-500,cancelable:true,bubbles:true}));
 });
 assert((await diag()).camera_distance>=3-.001);
 await page.evaluate(()=>{
  const c=document.querySelector('#g010-3d-canvas canvas');
  for(let i=0;i<60;i++)c.dispatchEvent(new WheelEvent('wheel',{deltaY:500,cancelable:true,bubbles:true}));
 });
 assert((await diag()).camera_distance<=22+.001);
 checks.push('bounded_zoom_prevents_clipping');
 await page.click('#g010-3d-reset');
 const reset=await diag();
 assert(identity(reset.rotation_quaternion));
 assert(Math.abs(reset.camera_distance-cameraDefault)<.002);
 checks.push('one_tap_restores_orientation_and_zoom');
 // Model switch must also restore view (no leaked transforms).
 await page.click('#g010-3d-zoom-in');
 await page.selectOption('#g010-3d-category','weapon');
 await page.waitForFunction(()=>document.querySelector('#g010-3d-gallery')?.dataset.integrity==='verified'
   && document.querySelector('#g010-3d-gallery')?.dataset.assetId===document.querySelector('#g010-3d-model')?.value,{timeout:60000});
 const swapped=await diag();
 assert(identity(swapped.rotation_quaternion));
 assert(Math.abs(swapped.camera_distance-cameraDefault)<.002);
 checks.push('model_swap_restores_full_camera_and_orientation');
 assert.deepEqual(errors,[]);
 assert.deepEqual(httpFail,[]);
 checks.push('no_http_or_js_errors');
 await context.close();
 return {device,checks,cameraDefault,zoom_range:[3,22],errors,httpFail};
}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
 args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl','--enable-unsafe-swiftshader']});
 const report={schema:'G030_GALLERY_TRUE_UNRESTRICTED_TWO_AXIS_360_INTERACTION_V1',
 github_pr:437,production_writes:0,not_real_ipad_safari:true,scenarios:[],verdict:'HOLD'};
 try{
  report.scenarios.push(await scenario(browser,'desktop_chrome',{viewport:{width:1050,height:850},deviceScaleFactor:1}));
  report.scenarios.push(await scenario(browser,'touch_emulated_chrome',{viewport:{width:820,height:1180},deviceScaleFactor:2,isMobile:true,hasTouch:true}));
  report.pass=report.scenarios.reduce((n,s)=>n+s.checks.length,0);
  report.verdict='G030_TWO_AXIS_360_FULL_ROTATION_PINCH_WHEEL_RESET_REAL_WEBGL_PASS';
 }catch(e){report.failure=String(e.stack||e).slice(0,1800);process.exitCode=1}
 finally{
  fs.mkdirSync('D:/go-odyssey-g030-evidence-20261022',{recursive:true});
  fs.writeFileSync('D:/go-odyssey-g030-evidence-20261022/G030_TWO_AXIS_360_REAL_WEBGL_BROWSER_20261022.json',JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));await browser.close();
 }
})().catch(e=>{console.error(String(e.stack||e));process.exitCode=1});
