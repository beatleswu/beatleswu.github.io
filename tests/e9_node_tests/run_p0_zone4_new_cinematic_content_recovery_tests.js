'use strict';

/**
 * P0 Lane -- Zone4 Owner-final cinematic content recovery.
 *
 * This harness validates the real manifest adapter, byte closure, and the
 * existing bounded Zone4 host wiring without booting the full browser app.
 */

const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..');
const manifestPath = path.join(repoRoot, 'ZONE4_RUNTIME_MANIFEST.json');
const staticPackPath = path.join(repoRoot, 'deploy', 'canonical-e10-zone4-static-pack-manifest.json');
const inventoryPath = path.join(repoRoot, 'deploy', 'live-static-asset-inventory.json');
const indexPath = path.join(repoRoot, 'index.html');
const adapter = require(path.join(repoRoot, 'js', 'e10', 'zone4_cinematic_content.js'));
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const staticPack = JSON.parse(fs.readFileSync(staticPackPath, 'utf8'));
const inventory = JSON.parse(fs.readFileSync(inventoryPath, 'utf8'));
const indexSource = fs.readFileSync(indexPath, 'utf8');
const worldStageSource = fs.readFileSync(path.join(repoRoot, 'js', 'e9', 'world_stage.js'), 'utf8');

const tests = [];
function test(name, fn) { tests.push([name, fn]); }

function fileSha256(relativePath) {
  const bytes = fs.readFileSync(path.join(repoRoot, relativePath));
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function allRuntimePaths() {
  const paths = new Set();
  (manifest.visual_assets || []).forEach(asset => paths.add(asset.path));
  (manifest.audio_assets || []).forEach(asset => paths.add(asset.path));
  return paths;
}

test('Owner-final Zone4 manifest validates and keeps Lord review separate', () => {
  assert.strictEqual(manifest.schema, 'GO_ODYSSEY_ZONE4_OWNER_FINAL_STORY_RUNTIME_INTEGRATION_V1');
  const validated = adapter.validateManifest(manifest);
  assert.strictEqual(validated.tracks.main_story.beats.length, 22);
  assert.strictEqual(validated.tracks.lord_review.beats.length, 6);
  assert.strictEqual(validated.tracks.lord_review.autoplay_allowed, false);
});

test('Zone4 adapter resolves the new main-story runtime with all 22 shots', async () => {
  const api = adapter.create({
    fetchImpl: async (requestPath, options) => {
      assert.strictEqual(requestPath, '/ZONE4_RUNTIME_MANIFEST.json');
      assert.strictEqual(options.credentials, 'same-origin');
      assert.strictEqual(options.cache, 'no-store');
      return { ok: true, json: async () => manifest };
    },
  });
  assert.strictEqual(api.isReady(), false);
  assert.strictEqual(await api.ready(), true);
  assert.strictEqual(api.isReady(), true);
  const locale = api.localeConfig('en', { filmTitle: 'Misty Forest: Phantoms and True Form' });
  assert.strictEqual(locale.track, 'main_story');
  assert.strictEqual(locale.timeline.length, 22);
  assert.ok(locale.bgmMainTheme.startsWith('/assets/e10/audio/zone4/'));
  assert.ok(locale.ambienceVillageDawn.startsWith('/assets/e10/audio/zone4/'));
  assert.ok(locale.timeline.every(item => item.imageSrc.startsWith('/assets/e10/art/zone4/cinematic/')));
  assert.ok(locale.timeline.every(item => item.bgmSrc.startsWith('/assets/e10/audio/zone4/')));
  const voiceSources = locale.timeline.flatMap(item => item.beats.map(beat => beat.audioSrc));
  assert.ok(voiceSources.length > 0);
  assert.ok(voiceSources.every(source => source.startsWith('/assets/e10/audio/zone4/')));
  assert.ok(locale.timeline.every(item => item.beats.every(beat => beat.allowTtsFallback === false)));
  assert.ok(locale.timeline.every(item => !item.imageSrc.includes('/assets/storyboards/')));
});

test('Every Owner-final Zone4 runtime asset exists and matches its declared SHA', () => {
  const assets = [...(manifest.visual_assets || []), ...(manifest.audio_assets || [])];
  assert.strictEqual(assets.length, 139);
  assets.forEach(asset => {
    assert.ok(asset.path && !asset.path.includes('..'), asset.asset_id);
    assert.strictEqual(fileSha256(asset.path), asset.sha256, asset.path);
  });
});

test('Static Zone4 pack and live inventory close every new runtime asset', () => {
  const packPaths = new Set((staticPack.files || []).map(entry => entry.path));
  allRuntimePaths().forEach(assetPath => assert.ok(packPaths.has(assetPath), assetPath));
  const required = new Set((inventory.required_in_generation && inventory.required_in_generation.entries) || []);
  assert.ok(required.has('ZONE4_RUNTIME_MANIFEST.json'));
  const eligible = new Set((inventory.eligible_files && inventory.eligible_files.entries) || []);
  assert.ok(eligible.has('js/e10/zone4_cinematic_content.js'));
  const subtree = ((inventory.required_subtrees && inventory.required_subtrees.entries) || [])
    .find(item => item.manifest === 'deploy/canonical-e10-zone4-static-pack-manifest.json');
  assert.ok(subtree, 'assets/e10/ closure');
  assert.strictEqual(subtree.manifest, 'deploy/canonical-e10-zone4-static-pack-manifest.json');
});

test('Zone4 runtime contains no legacy storyboard URL and preserves other zone wiring', () => {
  assert.ok(indexSource.includes('/js/e10/zone4_cinematic_content.js'));
  assert.ok(indexSource.includes('Zone4CinematicContent'));
  assert.ok(indexSource.includes('_ensureZone4CinematicContentReady'));
  assert.ok(worldStageSource.includes("e10_zone2_intro_v1"));
  assert.ok(worldStageSource.includes("zone4EntryInFlight"));
  assert.ok(!indexSource.includes('go_misty_forest_'));
  assert.ok(!indexSource.includes('/assets/storyboards/go_misty_forest'));
});

test('Manifest failure is fail-closed and never exposes a legacy fallback timeline', async () => {
  const api = adapter.create({
    fetchImpl: async () => ({ ok: false, json: async () => ({}) }),
  });
  assert.strictEqual(await api.ready(), false);
  assert.strictEqual(api.isReady(), false);
  assert.ok(api.failure());
});

(async () => {
  let failed = 0;
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
