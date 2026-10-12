/* R12 successor: explicit-but-unmapped Future30 identity fails closed; legacy art and A1 default are kept. */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const PlayerState = require(path.join(ROOT, 'js', 'e9', 'adapters', 'player_state.js'));
const manifest = JSON.parse(fs.readFileSync(
  path.join(ROOT, 'assets', 'world-map-identity', 'runtime_manifest.json'), 'utf8'));
const A1 = 'FUTURE30_MODEL_A1_RED';
const avatar = manifest.entries.find(e => e.asset_role === 'AVATAR' && e.visual_model_id === A1);
const UNMAPPED = { character_key: 'A1', character_runtime: { visual_model_id: 'FUTURE30_MODEL_NOT_ACCEPTED' } };

function fake(canned) {
  return function fetchImpl(url) {
    const r = url === '/assets/world-map-identity/runtime_manifest.json' ? canned.manifest
      : url === '/api/player/appearance' ? canned.appearance
        : url === '/api/skills/profile' ? { ok: true, body: { display_name: 'p', rank_level: 'LV3' } }
          : { ok: true, body: { coins: 7 } };
    if (!r) throw new Error('uncanned ' + url);
    return Promise.resolve({ ok: r.ok, status: r.status || 200, json: () => Promise.resolve(r.body) });
  };
}
const okBody = body => ({ ok: true, body });
const noA1Claim = p => {
  assert.notStrictEqual(p.visualModelId, A1);
  assert.strictEqual(p.asset, '');
  assert.strictEqual(p.avatarAsset, '');
  assert.strictEqual(p.standingAsset, '');
  assert.strictEqual(p.fallback, undefined);
};

async function main() {
  // 0. Manifest unavailable still fails closed (map provider and HUD). Runs first: a successful load is cached by the adapter.
  let r = await PlayerState.fetchAvatarPresentation(fake({ appearance: okBody(UNMAPPED), manifest: { ok: false, status: 503 } }));
  assert.strictEqual(r.ok, false);
  r = await PlayerState.fetchPlayerState(fake({ appearance: okBody(UNMAPPED), manifest: { ok: false, status: 503 } }));
  assert.strictEqual(r.ok, false);

  // 1. Unmapped explicit identity: map provider fails closed.
  r = await PlayerState.fetchAvatarPresentation(fake({ appearance: okBody(UNMAPPED), manifest: okBody(manifest) }));
  assert.strictEqual(r.ok, false, 'unmapped Future30 identity must fail closed');

  // 2. Same identity in the HUD: name/level/coins survive, avatar stays neutral and is never A1.
  r = await PlayerState.fetchPlayerState(fake({ appearance: okBody(UNMAPPED), manifest: okBody(manifest) }));
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.data.name, 'p');
  assert.strictEqual(r.data.avatarSrc, '');
  assert.strictEqual(r.data.avatarPresentation.unmappedIdentity, true);
  noA1Claim(r.data.avatarPresentation);

  // 3. Synchronous resolver does not claim A1 for an explicit foreign identity.
  noA1Claim(PlayerState.resolveCurrentPlayerAvatarPresentation(UNMAPPED));

  // 5. No Future30 identity at all (new player / unknown key) keeps the approved A1 default.
  for (const body of [null, {}, { character_key: 'not-a-key' }]) {
    r = await PlayerState.fetchAvatarPresentation(fake({ appearance: okBody(body), manifest: okBody(manifest) }));
    assert.strictEqual(r.ok, true);
    assert.strictEqual(r.fallback, true);
    assert.strictEqual(r.data.asset, `/${avatar.target_runtime_path}`);
  }

  // 6. A mapped Future30 identity resolves normally.
  r = await PlayerState.fetchAvatarPresentation(fake({
    appearance: okBody({ character_key: 'A1', character_runtime: { visual_model_id: A1 } }), manifest: okBody(manifest) }));
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.fallback, false);

  // 7. A deliberately chosen legacy character keeps its shipped art and needs no manifest.
  r = await PlayerState.fetchAvatarPresentation(fake({ appearance: okBody({ character_key: 'mage' }), manifest: { ok: false, status: 503 } }));
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.data.asset, '/assets/hero/characters/chibi_mage_normalized.webp');
  assert.strictEqual(r.fallback, false);

  console.log('R12 Future30 fail-closed successor: PASS cases=9');
}

main().catch(error => { console.error(error.stack || error); process.exitCode = 1; });
