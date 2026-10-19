// Real WEBGL/GLB pixel and pointer acceptance. Local READ-ONLY fixture only.
// API identity here is synthetic, not authenticated Test02 or production.
// Runtime authenticates actual owner-approved C005 + Formal18 asset bytes.
import assert from 'node:assert/strict';
import { statSync, createReadStream } from 'node:fs';
import { readFile as readAsync } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { chromium } from 'playwright-core';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const manifestBytes = await readAsync(path.join(root, 'schemas/future30_c005_real_asset_runtime_mapping_manifest.json'));
const manifest = JSON.parse(manifestBytes.toString('utf8'));
const manifestHash = createHash('sha256').update(manifestBytes).digest('hex');
const heroKey = 'A1';
const entries = manifest.roster.map(logical => {
  const visuals = manifest.visual_models.filter(v => v.character_id === logical.character_id);
  const red = visuals.find(v => v.variant === 'RED');
  assert(red);
  return {
    ...red, character_key: logical.character_id,
    visual_models: visuals, owned: true, is_applied: logical.character_id === heroKey,
    acquisition_source: 'ACCEPTANCE_TEST',
  };
});
const entry = entries.find(x => x.character_key === heroKey);
const catalog = {
  entries, logical_count: 30, visual_count: 33,
  c005_manifest_sha256: manifestHash, blue_optional: ['AR1', 'AR2', 'AR3'],
};
const appearance = {
  character_key: heroKey,
  character_key_source: 'player_appearance.character_key',
  character_key_authority: 'player_appearance.character_key',
  character_entitled: true,
  character_runtime: {...entry, default_variant: 'RED', c005_manifest_sha256: manifestHash},
};
const pet = {pet_key: 'ink_drop_kelpie', level: 9, nickname: '3D test only'};
const documentHtml = `<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<script type="importmap">{"imports":{"three":"/assets/3d_shop/p048/vendor/three.module.js"}}</script>
<link rel="stylesheet" href="/css/g009_hero_hub_batch_a.css">
<style>
body{margin:0;background:#0e172d;color:#fff;font:14px sans-serif;display:grid;grid-template-columns:340px 400px;gap:20px;padding:15px}
#char-avatar{position:relative;width:320px;height:460px}
#g008-future30-hero-stage{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#g008-future30-hero-stage canvas{width:100%;height:100%;display:block}
.g009-stage-host{position:relative;width:340px;height:530px}
.g009-companion-3d-viewport{width:390px;height:280px}
.g009-companion-3d-shell{min-height:350px}
.g009-turntable-controls{margin:6px}
</style></head>
<body data-g009-hero-hub="batch-a" data-g009-hero-tab="pet">
<div id="g009-stage-host" class="g009-stage-host">
<div id="char-avatar">
<div id="g008-future30-hero-stage" class="g008-future30-hero-stage" data-state="inactive"></div>
</div>
<div id="g009-hero-rotate-controls" class="g009-turntable-controls" data-turntable-ready="false">
<span class="g009-turntable-hint">3D 角色 · 360°</span>
<div class="g009-turntable-buttons">
<button type="button" data-turntable-action="left" disabled>左</button>
<button type="button" data-turntable-action="reset" disabled>正面</button>
<button type="button" data-turntable-action="right" disabled>右</button>
</div>
</div>
</div>
<section id="g009-panel-companion">
<div id="g009-companion-3d-shell" class="g009-companion-3d-shell" data-preview-state="inactive">
<div id="g009-companion-3d-viewport" class="g009-companion-3d-viewport"></div>
<div id="g009-companion-3d-status" class="g009-companion-3d-status"></div>
<div id="g009-companion-rotate-controls" class="g009-turntable-controls" data-turntable-ready="false">
<span class="g009-turntable-hint">3D 棋靈 · 360°</span>
<div class="g009-turntable-buttons">
<button type="button" data-turntable-action="left" disabled>左</button>
<button type="button" data-turntable-action="reset" disabled>正面</button>
<button type="button" data-turntable-action="right" disabled>右</button>
</div>
</div>
</div>
</section>
<script type="module" src="/js/g008_future30_hero_renderer.js"></script>
<script type="module" src="/js/g009_companion_360_viewer.mjs"></script>
</body></html>`;
const mime = {
  '.js':'text/javascript', '.mjs':'text/javascript', '.json':'application/json',
  '.glb':'model/gltf-binary', '.css':'text/css', '.png':'image/png',
  '.jpg':'image/jpeg', '.webp':'image/webp',
};
const assetRequests=[];
const server = createServer((request,response) => {
  const uri = new URL(request.url,'http://127.0.0.1');
  const name = uri.pathname;
  if (name === '/__360_real_glb_test') {
    response.writeHead(200, {'Content-Type':'text/html; charset=utf-8'});
    response.end(documentHtml);return;
  }
  const api = {
    '/api/player/character-catalog':catalog,
    '/api/player/appearance':appearance,
    '/api/pet/status':{pet},
  }[name];
  if (api) {
    response.writeHead(200, {'Content-Type':'application/json'});
    response.end(JSON.stringify(api));return;
  }
  if (!name.startsWith('/assets/') && !name.startsWith('/js/') && !name.startsWith('/css/')) {
    response.writeHead(404); response.end('not registered');return;
  }
  const local = path.resolve(root,'.'+decodeURIComponent(name));
  if (!local.startsWith(root+path.sep) || !statSync(local,{throwIfNoEntry:false})?.isFile()) {
    response.writeHead(404);response.end('unavailable');return;
  }
  if (name.endsWith('.glb')) assetRequests.push(name);
  response.writeHead(200, {'Content-Type':mime[path.extname(local)] || 'application/octet-stream'});
  createReadStream(local).pipe(response);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base='http://127.0.0.1:'+server.address().port;
const browser=await chromium.launch({
  headless:true,
  executablePath:process.env.CHROME_BIN || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--enable-webgl','--ignore-gpu-blocklist'],
});
const page=await browser.newPage({viewport:{width:840,height:760},deviceScaleFactor:1});
const errors=[];
page.on('pageerror',e=>errors.push(String(e)));
const results=[];
async function check(label,fn) {const result=await fn();results.push({label,verdict:'PASS',...result});}
function angle(selector) {return page.locator(selector).getAttribute('data-rotation-degrees').then(x=>Number(x));}
try {
  await page.goto(base+'/__360_real_glb_test',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(() =>
    window.__G008_HERO_RENDER_STATE__?.state==='ready'
    && window.__G009_COMPANION_360_STATE__?.state==='ready',null,{timeout:30000});
  const heroCanvas='#g008-future30-hero-stage canvas';
  const petCanvas='#g009-companion-3d-viewport canvas';
  await check('real_verified_GLBS_hero_and_companion',async()=>{
    const states=await page.evaluate(()=>({
      hero:window.__G008_HERO_RENDER_STATE__,
      pet:window.__G009_COMPANION_360_STATE__,
      canvasCount:document.querySelectorAll('canvas').length,
      heroPointer:getComputedStyle(document.querySelector('#g008-future30-hero-stage')).pointerEvents,
    }));
    assert.equal(states.hero.state,'ready');
    assert.equal(states.pet.state,'ready');
    assert(states.hero.mesh_count>=1);
    assert(states.pet.meshes>=1);
    assert.equal(states.pet.canvas_count,1);
    assert.equal(states.canvasCount,2);
    assert.equal(states.heroPointer,'auto');
    assert(assetRequests.includes('/' + entry.runtime_glb), 'expected the canonical role GLB: ' + JSON.stringify(assetRequests));
    assert(assetRequests.some(x=>x.includes('/companion/formal_18/ink_drop_kelpie/stage_i.glb')));
    return {heroModel:states.hero.runtime_glb,petSha:states.pet.asset_sha256,
      meshCount:states.hero.mesh_count,petMeshes:states.pet.meshes,canvases:states.canvasCount};
  });
  await check('hero_mouse_drag_rotates_mesh_and_changes_rendered_pixels',async()=>{
    const canvas=page.locator(heroCanvas);
    const start=await canvas.screenshot();
    const rect=await canvas.boundingBox();
    assert(rect);
    await page.mouse.move(rect.x+rect.width*.4,rect.y+rect.height*.5);
    await page.mouse.down();
    await page.mouse.move(rect.x+rect.width*.8,rect.y+rect.height*.5,{steps:18});
    await page.mouse.up();
    const end=await canvas.screenshot();
    const degrees=await angle(heroCanvas);
    assert(degrees>10 && degrees<350);
    assert.notEqual(createHash('sha256').update(start).digest('hex'),
      createHash('sha256').update(end).digest('hex'),'true model canvas pixels must change');
    await page.locator('#g009-hero-rotate-controls [data-turntable-action="reset"]').click();
    assert.equal(await angle(heroCanvas),0);
    return {dragAngle:degrees,pixelsChanged:true,resetAngle:0};
  });
  await check('companion_mouse_drag_rotates_real_3d_mesh',async()=>{
    const canvas=page.locator(petCanvas);
    const start=await canvas.screenshot();
    const rect=await canvas.boundingBox();
    assert(rect);
    await page.mouse.move(rect.x+rect.width*.3,rect.y+rect.height*.5);
    await page.mouse.down();
    await page.mouse.move(rect.x+rect.width*.77,rect.y+rect.height*.5,{steps:16});
    await page.mouse.up();
    const end=await canvas.screenshot();
    assert.notEqual(createHash('sha256').update(start).digest('hex'),
      createHash('sha256').update(end).digest('hex'));
    const degrees=await angle(petCanvas);
    assert(degrees>10 && degrees<350);
    await page.locator('#g009-companion-rotate-controls [data-turntable-action="right"]').click();
    assert.notEqual(await angle(petCanvas),degrees);
    await page.locator('#g009-companion-rotate-controls [data-turntable-action="reset"]').click();
    assert.equal(await angle(petCanvas),0);
    return {dragAngle:degrees,pixelsChanged:true,buttonsAndReset:true};
  });
  await check('keyboard_and_touch_pointer_contract',async()=>{
    await page.locator(heroCanvas).focus();
    await page.keyboard.press('ArrowRight');
    assert.equal(await angle(heroCanvas),23);
    await page.keyboard.press('Home');
    assert.equal(await angle(heroCanvas),0);
    await page.locator(petCanvas).dispatchEvent('pointerdown',{pointerId:25,pointerType:'touch',clientX:90,button:0});
    await page.locator(petCanvas).dispatchEvent('pointermove',{pointerId:25,pointerType:'touch',clientX:245});
    await page.locator(petCanvas).dispatchEvent('pointerup',{pointerId:25,pointerType:'touch',clientX:245});
    assert((await angle(petCanvas))>5);
    await page.locator('#g009-companion-rotate-controls [data-turntable-action="reset"]').click();
    return {heroKeyboard:true,petTouchPointer:true};
  });
  await check('tab_hide_releases_second_webgl_and_tab_return_restores_it',async()=>{
    await page.evaluate(()=>{document.body.dataset.g009HeroTab='hero';});
    await page.waitForFunction(()=>document.querySelectorAll('#g009-companion-3d-viewport canvas').length===0,null,{timeout:8000});
    assert.equal(await page.locator(heroCanvas).count(),1);
    await page.evaluate(()=>{document.body.dataset.g009HeroTab='pet';});
    await page.waitForFunction(()=>window.__G009_COMPANION_360_STATE__?.state==='ready'
      && document.querySelectorAll('#g009-companion-3d-viewport canvas').length===1,null,{timeout:20000});
    const state=await page.evaluate(()=>window.__G009_COMPANION_360_STATE__);
    assert.equal(state.pet_key,'ink_drop_kelpie');
    assert.equal(await page.locator('canvas').count(),2);
    return {companionRestored:true,maxCanvases:2};
  });
  await check('all_18_approved_3d_companion_stage_models_rotate_as_real_geometry', async()=>{
    const keys=[
      'ink_drop_kelpie','whispering_void_kit','star_shell_hatchling',
      'starpath_antlerling','fatty','obsidian_bastion',
    ];
    let confirmed=0;
    for (const petKey of keys) {
      for (const [level,stage] of [[9,'I'],[10,'II'],[25,'III']]) {
        pet.pet_key=petKey;
        pet.level=level;
        await page.evaluate(()=>window.dispatchEvent(new Event('g009:companion-status')));
        await page.waitForFunction(([key,want])=>
          window.__G009_COMPANION_360_STATE__?.state==='ready'
          && window.__G009_COMPANION_360_STATE__?.pet_key===key
          && window.__G009_COMPANION_360_STATE__?.stage===want,
          [petKey,stage],{timeout:30000});
        const state=await page.evaluate(()=>window.__G009_COMPANION_360_STATE__);
        assert(state.meshes>=1);
        assert.equal(await page.locator(petCanvas).count(),1);
        const before=await page.locator(petCanvas).screenshot();
        await page.locator('#g009-companion-rotate-controls [data-turntable-action="right"]').click();
        assert.equal(await angle(petCanvas),45);
        const after=await page.locator(petCanvas).screenshot();
        assert.notEqual(createHash('sha256').update(before).digest('hex'),
          createHash('sha256').update(after).digest('hex'),
          'real model pixels must change: '+petKey+':'+stage);
        confirmed++;
      }
    }
    // Return to original fixture identity for the integrity-rejection test.
    pet.pet_key='ink_drop_kelpie';pet.level=9;
    await page.evaluate(()=>window.dispatchEvent(new Event('g009:companion-status')));
    await page.waitForFunction(()=>window.__G009_COMPANION_360_STATE__?.state==='ready'
      && window.__G009_COMPANION_360_STATE__?.pet_key==='ink_drop_kelpie'
      && window.__G009_COMPANION_360_STATE__?.stage==='I',null,{timeout:30000});
    assert.equal(confirmed,18);
    assert.equal(await page.locator('canvas').count(),2);
    return {realModelVariants:confirmed,canonicalPets:keys.length,
      actual3dPixelsChangeForEveryVariant:true};
  });

  await check('tampered_companion_glb_fails_closed_without_fake_3d', async()=>{
    const negative=await browser.newPage({viewport:{width:840,height:760}});
    const negativeErrors=[];
    negative.on('pageerror',err=>negativeErrors.push(String(err)));
    try {
      await negative.route('**/companion/formal_18/ink_drop_kelpie/stage_i.glb',
        route=>route.fulfill({status:200,contentType:'model/gltf-binary',
          body:'TEST_ONLY_TAMPERED_MODEL_BYTES'}));
      await negative.goto(base+'/__360_real_glb_test',{waitUntil:'domcontentloaded'});
      await negative.waitForFunction(() =>
        window.__G009_COMPANION_360_STATE__?.state==='unavailable'
        && window.__G008_HERO_RENDER_STATE__?.state==='ready',
        null,{timeout:30000});
      const result=await negative.evaluate(()=>({
        reason:window.__G009_COMPANION_360_STATE__.reason,
        canvases:document.querySelectorAll('#g009-companion-3d-viewport canvas').length,
        controls:document.getElementById('g009-companion-rotate-controls').dataset.turntableReady,
      }));
      assert.equal(result.canvases,0);
      assert.equal(result.controls,'false');
      assert.match(result.reason,/COMPANION_MODEL_SHA_OR_SIZE_MISMATCH/);
      assert.deepEqual(negativeErrors,[]);
      return {tamperedModelRejected:true,false360NeverDisplayed:true};
    } finally {await negative.close();}
  });

  assert.deepEqual(errors,[],'browser JS errors');
  const receipt={schema:'GO_ODYSSEY_REAL_GLB_360_BROWSER_20261019_V1',
    verdict:'LOCAL_REAL_3D_GLB_WEBGL_360_PASS_NOT_PRODUCTION_OR_REAL_IPAD',
    checks:results,passed:results.length,failed:0,
    page_errors:errors,model_requests:assetRequests,
    authentic_prod_Test02:false,real_iPad:false,release_authorized:false};
  console.log(JSON.stringify(receipt,null,2));
  if(process.env.G009_360_RECEIPT_PATH){
    const {writeFile}=await import('node:fs/promises');
    await writeFile(process.env.G009_360_RECEIPT_PATH,JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
  }
}catch(e){
  console.error('REAL_GLB_360_BROWSER_FAILED',e.stack||String(e));
  console.error('PAGE_ERRORS',errors);
  process.exitCode=1;
}finally{
  await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
