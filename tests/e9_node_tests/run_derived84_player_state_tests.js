/* Real execution tests for Future30 -> finalized Derived84 presentation mapping. */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const PlayerState = require(path.join(ROOT, 'js', 'e9', 'adapters', 'player_state.js'));
const runtimeManifest = JSON.parse(fs.readFileSync(
  path.join(ROOT, 'assets', 'world-map-identity', 'runtime_manifest.json'), 'utf8'));

function fakeFetch(responses) {
  let index = 0;
  return function fetchImpl() {
    const response = responses[index++];
    if (!response) throw new Error('fakeFetch: no canned response');
    return Promise.resolve({
      ok: response.ok,
      status: response.status || 200,
      json: () => Promise.resolve(response.body),
    });
  };
}

async function main() {
  const visual = runtimeManifest.entries.find(
    entry => entry.asset_role === 'AVATAR' && entry.visual_model_id === 'FUTURE30_MODEL_A1_RED');
  const standing = runtimeManifest.entries.find(
    entry => entry.asset_role === 'STANDING' && entry.visual_model_id === 'FUTURE30_MODEL_A1_RED');
  assert(visual && standing, 'A1 Derived84 rows must be present');
  const appearance = {
    character_key: 'A1',
    character_key_source: 'player_appearance.character_key',
    character_runtime: { visual_model_id: 'FUTURE30_MODEL_A1_RED' },
  };
  const result = await PlayerState.fetchAvatarPresentation(fakeFetch([
    { ok: true, body: appearance },
    { ok: true, body: runtimeManifest },
  ]));
  assert.strictEqual(result.ok, true);
  assert.strictEqual(result.data.presentationType, 'future30-derived84');
  assert.strictEqual(result.data.asset, `/${visual.target_runtime_path}`);
  assert.strictEqual(result.data.standingAsset, `/${standing.target_runtime_path}`);
  assert.strictEqual(result.data.fallbackAsset, '');

  const full = await PlayerState.fetchPlayerState(fakeFetch([
    { ok: true, body: { display_name: 'player', rank_level: 'LV8' } },
    { ok: true, body: { coins: 0 } },
    { ok: true, body: appearance },
    { ok: true, body: runtimeManifest },
  ]));
  assert.strictEqual(full.ok, true);
  assert.strictEqual(full.data.avatarSrc, `/${visual.target_runtime_path}`);
  assert.strictEqual(full.data.avatarPresentation.standingAsset, `/${standing.target_runtime_path}`);

  const unmapped = await PlayerState.fetchAvatarPresentation(fakeFetch([
    { ok: true, body: {
      character_key: 'A1',
      character_runtime: { visual_model_id: 'FUTURE30_MODEL_NOT_ACCEPTED' },
    } },
    { ok: true, body: runtimeManifest },
  ]));
  assert.strictEqual(unmapped.ok, false, 'unmapped Future30 identity must fail closed');
  console.log('Derived84 player-state tests passed');
}

main().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
