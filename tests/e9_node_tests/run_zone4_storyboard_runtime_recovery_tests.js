'use strict';

/**
 * Zone4 cinematic storyboard + installed-PWA parity contract.
 *
 * This is a source/runtime contract harness.  It does not contact Production,
 * open an authenticated browser, or mutate gameplay state.  Physical Safari
 * and installed-PWA UAT remains a separate Owner/device gate.
 */

const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const repoRoot = path.resolve(__dirname, '..', '..');
const indexSource = fs.readFileSync(path.join(repoRoot, 'index.html'), 'utf8');
const swSource = fs.readFileSync(path.join(repoRoot, 'sw.js'), 'utf8');
const manifestSource = fs.readFileSync(path.join(repoRoot, 'manifest.json'), 'utf8');
const e9WorldStageSource = fs.readFileSync(path.join(repoRoot, 'js', 'e9', 'world_stage.js'), 'utf8');
const e9WorldStageCss = fs.readFileSync(path.join(repoRoot, 'css', 'e9', 'world_stage.css'), 'utf8');
const replaySource = fs.readFileSync(path.join(repoRoot, 'js', 'game', 'cinematic_replay.js'), 'utf8');
const zone4Manifest = JSON.parse(fs.readFileSync(path.join(repoRoot, 'ZONE4_RUNTIME_MANIFEST.json'), 'utf8'));
const lordTrialPackage = JSON.parse(fs.readFileSync(path.join(repoRoot, 'assets', 'e10', 'art', 'zone1', 'lord_trial', 'zone1-lord-trial-art-package.json'), 'utf8'));
const adapter = require(path.join(repoRoot, 'js', 'e10', 'zone4_cinematic_content.js'));

const tests = [];
function test(name, fn) { tests.push([name, fn]); }
function fileSha256(relativePath) {
  return crypto.createHash('sha256')
    .update(fs.readFileSync(path.join(repoRoot, relativePath)))
    .digest('hex');
}
function loadReplayFactory() {
  const sandbox = { window: {} };
  vm.createContext(sandbox);
  vm.runInContext(replaySource, sandbox, { filename: 'cinematic_replay.js' });
  return sandbox.window.GoOdysseyCinematicReplay;
}

function resolvedLocale() {
  const api = adapter.create({
    fetchImpl: async () => ({ ok: true, json: async () => zone4Manifest }),
  });
  return api.ready().then(() => api.localeConfig('zh-TW', { filmTitle: '迷霧森林' }));
}

test('complete Zone4 storyboard is ordered and has visual/audio closure', async () => {
  const locale = await resolvedLocale();
  assert.strictEqual(zone4Manifest.tracks.main_story.beats.length, 22);
  assert.strictEqual(locale.fullTimeline.length, 22);
  assert.strictEqual(new Set(locale.fullTimeline.map(item => item.ownerBeatId)).size, 22);
  locale.fullTimeline.forEach((item) => {
    assert.ok(item.imageSrc, item.ownerBeatId + ' image');
    assert.ok(item.beats.length > 0, item.ownerBeatId + ' dialogue');
    item.beats.forEach((beat) => assert.ok(beat.audioSrc, item.ownerBeatId + ' voice'));
  });
  assert.ok(locale.fullTimeline.every(item => item.imageSrc.startsWith('/assets/e10/art/zone4/cinematic/')));
  assert.ok(!locale.fullTimeline.some(item => item.imageSrc.includes('/assets/storyboards/')));
});

test('Zone4 first entry and post-Lord story have explicit locked segmentation', async () => {
  const locale = await resolvedLocale();
  assert.strictEqual(locale.timeline.length, 16);
  assert.strictEqual(locale.preLordTimeline.length, 16);
  assert.strictEqual(locale.postClearTimeline.length, 6);
  assert.strictEqual(locale.preLordTimeline[0].ownerBeatId, 'Z4_S1_01');
  assert.strictEqual(locale.preLordTimeline[15].ownerBeatId, 'Z4_S2_08');
  assert.strictEqual(locale.postClearTimeline[0].ownerBeatId, 'Z4_S3_01');
  assert.strictEqual(locale.postClearTimeline[5].ownerBeatId, 'Z4_S3_06');
  assert.deepStrictEqual(locale.lordBoundary, {
    triggerAfterBeat: 'Z4_S2_08',
    postLordFirstBeat: 'Z4_S3_01',
  });
});

test('generic Replay Story unlocks only the authoritative post-Lord tail after clear', async () => {
  const locale = await resolvedLocale();
  const factory = loadReplayFactory();
  const model = factory.create({
    getSegments: () => ({
      pre_play: locale.preLordTimeline,
      post_clear: locale.postClearTimeline,
    }),
    canEnter: zone => zone.canEnter === true,
    isBossReady: zone => zone.bossReady === true,
    isCleared: zone => zone.cleared === true,
    hasSeen: () => false,
  });
  const beforeLord = { key: 'k11_15', canEnter: true, bossReady: false, cleared: false };
  const afterLord = { key: 'k11_15', canEnter: true, bossReady: false, cleared: true };
  assert.deepStrictEqual(Array.from(model.replaySequence(beforeLord), item => item.phase), ['pre_play']);
  assert.deepStrictEqual(Array.from(model.postVictorySequence(beforeLord)), []);
  assert.deepStrictEqual(Array.from(model.replaySequence(afterLord), item => item.phase), ['pre_play', 'post_clear']);
  assert.deepStrictEqual(Array.from(model.postVictorySequence(afterLord), item => item.phase), ['post_clear']);
});

test('host creates manifest-addressed shot slots and cannot leave voice-only blank beats', () => {
  assert.ok(indexSource.includes('function _ensureIntroFilmShotSlots(timeline = [])'));
  assert.ok(indexSource.includes('for (let shot = 0; shot <= highestShot; shot += 1)'));
  assert.ok(indexSource.includes('const shots = _ensureIntroFilmShotSlots(timeline);'));
  assert.ok(indexSource.includes('const isZone4Presentation = zone?.key === \'k11_15\';'));
  assert.ok(indexSource.includes('shots.forEach((el, idx) => el.classList.toggle(\'active\', idx === item.shot));'));
});

test('first-entry host uses the pre-Lord adapter timeline and clear path owns continuation', () => {
  const start = indexSource.indexOf('async function showStageIntroCinematic');
  const end = indexSource.indexOf('window.startAdventureStage', start);
  assert.ok(start >= 0 && end > start);
  const source = indexSource.slice(start, end);
  assert.ok(source.includes('_ensureZone4CinematicContentReady(zone)'));
  assert.ok(source.includes('await playNewbieVillageIntroFilm(zone, { mode });'));
  assert.ok(indexSource.includes('function _triggerZone4PostClearFromBossWin(zone, options = {})'));
  assert.ok(indexSource.includes("if (!zone4Cleared) return false;"));
  assert.ok(indexSource.includes("_triggerZonePostClearFromBossWin(zone, options)"));
});

test('Replay Story remains presentation-only and reuses the shared E9 card contract', () => {
  assert.ok(indexSource.includes('window.zoneHasReplayableStory = zoneHasReplayableStory;'));
  assert.ok(indexSource.includes('window.playZoneStoryReplay = playZoneStoryReplay;'));
  assert.ok(indexSource.includes('presentationOnly: true'));
  assert.ok(indexSource.includes('function _finishZoneCinematicReplay(zone)'));
  assert.ok(indexSource.includes('window.E9.showAdventureZoneCard(zone.key)'));
  assert.ok(e9WorldStageSource.includes('zoneStoryReplayAvailable'));
  assert.ok(e9WorldStageSource.includes('e10.world_stage.replay_story'));
  assert.ok(e9WorldStageCss.includes('.e9-zone-details__story-replay'));
});

test('Zone4 Lord UI uses dedicated six-asset package and separates first clear from replay', () => {
  const zone4LordDir = path.join(repoRoot, 'assets', 'e10', 'art', 'zone4', 'lord');
  const expected = {
    'Z4-LORD-01.png': '4c452590df1517f7e37f8826251ffc22e2ce8dd1c8d49f7f4d66bad8b5304ed7',
    'Z4-LORD-02.png': '1d5ecd438f1be7864ae8d15f7aa4057834634063b09d9b49e5b49d34b133583f',
    'Z4-LORD-03.png': '16e069fe47760d1a431730b8a5d9a794df4bbd3d6dc4ed58e3b5a3b74556ad1e',
    'Z4-LORD-04.png': '213045fcb3d40aa83628338e4356d21278731c049c0494af9b291d54b52d62f8',
    'Z4-LORD-05.png': '6ae81c0c26d34c0f1ef817b8f221c326dd4204b1db728ff5a5c38ff491cf60a7',
    'Z4-LORD-06.png': '88d7f2ef260ae1604102b36b09e82af4068a3451801a86a3be4c143a609e2152',
  };
  assert.strictEqual(Object.keys(expected).length, 6);
  Object.entries(expected).forEach(([name, sha]) => {
    const relative = path.relative(repoRoot, path.join(zone4LordDir, name));
    assert.strictEqual(fileSha256(relative), sha, name);
    assert.ok(indexSource.includes(`/assets/e10/art/zone4/lord/${name}`), name + ' runtime reference');
  });
  assert.ok(indexSource.includes('function showZone4LordChallengeCard(zone)'));
  assert.ok(indexSource.includes('function showZone4LordResultCard(result, zone)'));
  assert.ok(indexSource.includes("overlay.dataset.zone4Presentation = passed ? (replay ? 'replay_completion' : 'first_clear_success') : 'failure';"));
  assert.ok(indexSource.includes('const firstClear = passed && !replay && result?.firstClear === true;'));
  assert.ok(indexSource.includes('successPortrait.hidden = !firstClear;'));
  assert.ok(indexSource.includes('monster.hidden = true;'));
});

test('historical dedicated Lord Trial WebP package is intact and traceable', () => {
  assert.strictEqual(lordTrialPackage.assets.length, 6);
  lordTrialPackage.assets.forEach((asset) => {
    const runtime = asset.runtime_webp;
    assert.ok(runtime && runtime.path && runtime.sha256, asset.key);
    assert.strictEqual(fileSha256(runtime.path), runtime.sha256, asset.key);
  });
});

test('installed PWA uses the same entry and canonical Adventure surface', () => {
  const manifest = JSON.parse(manifestSource);
  assert.strictEqual(manifest.start_url, '/');
  assert.strictEqual(manifest.display, 'standalone');
  assert.ok(!Object.prototype.hasOwnProperty.call(manifest, 'scope') || manifest.scope === '/');
  assert.ok(indexSource.includes("window.matchMedia('(display-mode: standalone)')"));
  assert.ok(indexSource.includes('window.navigator.standalone === true'));
  assert.ok(indexSource.includes('data-go-display-mode'));
  assert.ok(indexSource.includes('id="e9-adventure-shell"'));
  assert.ok(indexSource.includes('id="e9-bottom-dock-slot"'));
  assert.ok(indexSource.includes('id="adventure-map-panel"'));
  assert.ok(indexSource.includes('id="skill-map"'));
});

test('standalone layout preserves vertical flow, safe area, and one shared renderer', () => {
  assert.ok(indexSource.includes('html[data-go-display-mode="standalone"] body main'));
  assert.ok(indexSource.includes('overflow-y: auto !important'));
  assert.ok(indexSource.includes('env(safe-area-inset-bottom, 0px)'));
  assert.ok(indexSource.includes('html[data-go-display-mode="standalone"] body[data-adventure-shell-active="e9"] #e9-adventure-shell'));
  assert.strictEqual((indexSource.match(/id="e9-adventure-shell"/g) || []).length, 1);
  assert.strictEqual((indexSource.match(/id="adventure-map-panel"/g) || []).length, 1);
});

test('Service Worker update path naturally advances the installed cache namespace', () => {
  assert.ok(swSource.includes("const VERSION     = 'v242-zone4-storyboard-pwa-parity';"));
  assert.ok(swSource.includes("const ASSET_IDENTITY = 'source-v242-zone4-storyboard-pwa-parity';"));
  assert.ok(swSource.includes('self.skipWaiting()'));
  assert.ok(swSource.includes('self.clients.claim()'));
  assert.ok(swSource.includes("if (url.pathname.startsWith('/api/'))"));
  assert.ok(swSource.includes('event.respondWith(networkFirst(request, SHELL_CACHE));'));
  assert.ok(indexSource.includes("navigator.serviceWorker.register('/sw.js', { scope: '/' })"));
});

test('Zone4 Lord presentation is not a gameplay or reward authority', () => {
  const start = indexSource.indexOf('function showZone4LordResultCard');
  const end = indexSource.indexOf('// 2026-08-09', start);
  const source = indexSource.slice(start, end > start ? end : start + 12000);
  assert.ok(source.includes('zone4Presentation'));
  assert.ok(source.includes('result?.firstClear === true'));
  assert.ok(!source.includes("fetch('/api/adventure/boss/start'"));
  assert.ok(!source.includes("fetch('/api/adventure/boss/finish'"));
});

let failed = 0;
(async () => {
  for (const [name, fn] of tests) {
    try {
      await fn();
      console.log('ok   - ' + name);
    } catch (error) {
      failed += 1;
      console.log('FAIL - ' + name);
      console.log('       ' + error.stack);
    }
  }
  console.log('');
  console.log((tests.length - failed) + '/' + tests.length + ' passed');
  process.exit(failed === 0 ? 0 : 1);
})();
