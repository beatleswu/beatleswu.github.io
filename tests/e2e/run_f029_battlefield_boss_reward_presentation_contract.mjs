'use strict';

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const MODULE_PATH = path.join(ROOT, 'js', 'game', 'battlefield_boss_reward_consumer.js');
const INDEX_PATH = path.join(ROOT, 'index.html');
const I18N_PATH = path.join(ROOT, 'i18n.js');
const CONTRACT_VERSION = 'F028_BATTLEFIELD_BOSS_MAPPING_A_FIRST_CLEAR_V1';
const IDS = [
  'back_pack',
  'hat_cloth',
  'hat_bamboo',
  'robe_crane',
  'hat_onihorns',
  'robe_dragon',
  'acc_dragon_pendant',
  'back_cloak',
  'hat_dragon_horn',
  'hat_celestial_crown',
];
const SLOTS = {
  back_pack: 'back',
  hat_cloth: 'hat',
  hat_bamboo: 'hat',
  robe_crane: 'outfit',
  hat_onihorns: 'hat',
  robe_dragon: 'outfit',
  acc_dragon_pendant: 'accessory',
  back_cloak: 'back',
  hat_dragon_horn: 'hat',
  hat_celestial_crown: 'hat',
};

class FakeElement {
  constructor(id) {
    this.id = id;
    this.dataset = {};
    this.hidden = false;
    this.textContent = '';
    this.src = '';
    this.alt = '';
    this.attributes = {};
    this.onload = null;
    this.onerror = null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
}

class FakeDocument {
  constructor(lang = 'zh-TW') {
    this.documentElement = { lang };
    this.elements = new Map();
    [
      'boss-reward-presentation',
      'boss-reward-presentation-kicker',
      'boss-reward-presentation-icon',
      'boss-reward-presentation-image',
      'boss-reward-presentation-fallback',
      'boss-reward-presentation-title',
      'boss-reward-presentation-item-name',
      'boss-reward-presentation-state',
      'boss-reward-presentation-meta',
    ].forEach(id => this.elements.set(id, new FakeElement(id)));
    this.elements.get('boss-reward-presentation').hidden = true;
    this.elements.get('boss-reward-presentation-image').hidden = true;
    this.elements.get('boss-reward-presentation-fallback').hidden = true;
  }

  getElementById(id) {
    return this.elements.get(id) || null;
  }
}

function makeFixture(lang = 'en') {
  const document = new FakeDocument(lang === 'en' ? 'en' : 'zh-TW');
  const window = {
    document,
    I18n: {
      getLang: () => lang,
      t: key => key,
    },
  };
  const context = {
    window,
    globalThis: window,
    document,
    console: { log() {}, info() {}, warn() {}, error() {} },
    Promise,
    Set,
    Object,
    Array,
    String,
    Number,
    Boolean,
    Error,
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(MODULE_PATH, 'utf8'), context, { filename: MODULE_PATH });
  return { api: window.BattlefieldBossRewardConsumer, document };
}

function makeResponse(itemId, status = 'GRANTED', options = {}) {
  const acquired = status !== 'NO_REWARD';
  const item = acquired
    ? {
        id: itemId,
        item_id: itemId,
        slot: SLOTS[itemId],
        display_name: `伺服器名稱 ${itemId}`,
        icon: '🎁',
        presentation: {
          asset: `/assets/hero/items/${itemId}.svg`,
          presentation_only: true,
        },
        ownership_authority: 'player_wardrobe',
        new: status === 'GRANTED',
        already_owned: status === 'ALREADY_OWNED',
        duplicate: false,
        equipped: false,
        auto_equipped: false,
        presentation_only: true,
        combat_power: 0,
      }
    : null;
  const reward = {
    contract_version: CONTRACT_VERSION,
    status,
    passed: options.passed ?? (status !== 'NO_REWARD' || options.replay === true),
    first_clear: acquired,
    replay: options.replay ?? false,
    entitlement_consumed: acquired,
    entitlement_id: `adventure:first_clear:1:k26_30`,
    source_operation_id: `adventure:first_clear:1:k26_30`,
    item_id: acquired ? itemId : null,
    mapping_a_zone: 'Z1',
    ownership_authority: 'player_wardrobe',
    ownership_persisted: acquired,
    ownership_row_id: acquired ? 17 : null,
    auto_equip: false,
    auto_equipped: false,
    compensation: false,
    replacement_reward: false,
    combat_power: 0,
    reward_item: item,
    reason_code: acquired ? null : (options.replay ? 'REPLAY_ALREADY_CLEARED' : 'BOSS_NOT_PASSED'),
  };
  return {
    ok: true,
    reward,
    reward_item: item,
  };
}

function directResponse(itemId) {
  return makeResponse(itemId).reward;
}

function test(name, fn) {
  try {
    fn();
    process.stdout.write(`PASS ${name}\n`);
  } catch (error) {
    process.stderr.write(`FAIL ${name}: ${error.stack || error}\n`);
    process.exitCode = 1;
  }
}

async function asyncTest(name, fn) {
  try {
    await fn();
    process.stdout.write(`PASS ${name}\n`);
  } catch (error) {
    process.stderr.write(`FAIL ${name}: ${error.stack || error}\n`);
    process.exitCode = 1;
  }
}

test('F028 dependency contract and locked ten-item presentation allowlist are explicit', () => {
  const { api } = makeFixture();
  assert.equal(api.CONTRACT_VERSION, CONTRACT_VERSION);
  assert.deepEqual(Object.keys(api.MAPPING_A_PRESENTATION), IDS);
  assert.deepEqual(IDS.map(id => api.MAPPING_A_PRESENTATION[id].slot), IDS.map(id => SLOTS[id]));
});

test('all ten server-authored item identities normalize without client Zone inference', () => {
  const { api } = makeFixture();
  IDS.forEach((itemId, index) => {
    const response = makeResponse(itemId);
    response.reward.mapping_a_zone = `Z${index + 1}`;
    const model = api.normalize(response);
    assert.equal(model.valid, true, itemId);
    assert.equal(model.hasReward, true, itemId);
    assert.equal(model.itemId, itemId, itemId);
    assert.equal(model.slot, SLOTS[itemId], itemId);
  });
});

await asyncTest('first-clear reward renders the server item, refreshes wardrobe, and stays unequipped', async () => {
  const { api, document } = makeFixture('en');
  let refreshCalls = 0;
  const result = await api.present(makeResponse('back_pack'), {
    document,
    lang: 'en',
    refreshOwnership: async () => { refreshCalls += 1; return true; },
  });
  assert.equal(result.kind, 'granted');
  assert.equal(result.refreshStatus, 'refreshed');
  assert.equal(refreshCalls, 1);
  const panel = document.getElementById('boss-reward-presentation');
  assert.equal(panel.hidden, false);
  assert.equal(panel.dataset.itemId, 'back_pack');
  assert.equal(panel.dataset.autoEquip, 'false');
  assert.equal(panel.dataset.combatPower, '0');
  assert.equal(document.getElementById('boss-reward-presentation-title').textContent, 'Reward earned');
  assert.match(document.getElementById('boss-reward-presentation-state').textContent, /wardrobe/);
  assert.equal(document.getElementById('boss-reward-presentation-item-name').textContent, 'Go Kit Pack');
  assert.equal(document.getElementById('boss-reward-presentation-image').src, '/assets/hero/items/back_pack.svg');
  assert.doesNotMatch(document.getElementById('boss-reward-presentation-item-name').textContent, /[\u3400-\u9fff]/);
});

await asyncTest('Chinese first-clear copy is localized and safe', async () => {
  const { api, document } = makeFixture('zh');
  const result = await api.present(makeResponse('hat_celestial_crown'), { document, lang: 'zh' });
  assert.equal(result.kind, 'granted');
  assert.equal(document.getElementById('boss-reward-presentation-kicker').textContent, '戰場領主獎勵');
  assert.equal(document.getElementById('boss-reward-presentation-title').textContent, '獎勵已取得');
  assert.equal(document.getElementById('boss-reward-presentation-item-name').textContent, '伺服器名稱 hat_celestial_crown');
});

await asyncTest('already-owned result is honest and does not claim a second copy or compensation', async () => {
  const { api, document } = makeFixture('en');
  const result = await api.present(makeResponse('acc_dragon_pendant', 'ALREADY_OWNED'), {
    document,
    lang: 'en',
    refreshOwnership: async () => true,
  });
  assert.equal(result.kind, 'already_owned');
  assert.equal(document.getElementById('boss-reward-presentation-title').textContent, 'Already in your wardrobe');
  const state = document.getElementById('boss-reward-presentation-state').textContent;
  assert.match(state, /unchanged/);
  assert.doesNotMatch(state, /received another copy|coins|compensation/i);
});

await asyncTest('replay and failed Boss results hide the reward and never refresh fake ownership', async () => {
  const { api, document } = makeFixture('en');
  let refreshCalls = 0;
  const replay = await api.present(makeResponse('back_pack', 'NO_REWARD', { replay: true }), {
    document,
    refreshOwnership: async () => { refreshCalls += 1; return true; },
  });
  assert.equal(replay.hasReward, false);
  assert.equal(refreshCalls, 0);
  assert.equal(document.getElementById('boss-reward-presentation').hidden, true);
  const failed = await api.present(makeResponse('back_pack', 'NO_REWARD', { passed: false }), {
    document,
    refreshOwnership: async () => { refreshCalls += 1; return true; },
  });
  assert.equal(failed.hasReward, false);
  assert.equal(refreshCalls, 0);
  assert.equal(document.getElementById('boss-reward-presentation').hidden, true);
});

test('missing, malformed, unknown, mismatched, auto-equip, and combat payloads fail closed', () => {
  const { api, document } = makeFixture('en');
  const cases = [
    [null, 'F028_REWARD_RESULT_MISSING'],
    [{ ok: true }, 'F028_REWARD_RESULT_MISSING'],
    [{ ok: false, reward: makeResponse('back_pack').reward }, 'SERVER_REJECTED'],
    [{ reward: { ...makeResponse('back_pack').reward, contract_version: 'wrong' } }, 'F028_CONTRACT_UNSUPPORTED'],
    [{ reward: { ...makeResponse('back_pack').reward, item_id: 'not-a-mapping-item' } }, 'UNKNOWN_MAPPING_A_ITEM'],
    [{ reward: { ...makeResponse('back_pack').reward, auto_equip: true } }, 'PROTECTED_REWARD_FLAG_INVALID'],
    [{ reward: { ...makeResponse('back_pack').reward, combat_power: 1 } }, 'COSMETIC_COMBAT_POWER_INVALID'],
  ];
  cases.forEach(([payload, reason]) => {
    const result = api.normalize(payload);
    assert.equal(result.valid, false, reason);
    assert.equal(result.reasonCode, reason, reason);
    api.render(result, { document });
    assert.equal(document.getElementById('boss-reward-presentation').hidden, true, reason);
  });
});

await asyncTest('ownership refresh failure is recoverable without claiming refreshed ownership', async () => {
  const { api, document } = makeFixture('en');
  const result = await api.present(makeResponse('robe_dragon'), {
    document,
    lang: 'en',
    refreshOwnership: async () => { throw new Error('network'); },
  });
  assert.equal(result.refreshStatus, 'failed');
  assert.match(document.getElementById('boss-reward-presentation-state').textContent, /refresh is unavailable/);
  assert.equal(document.getElementById('boss-reward-presentation').dataset.refreshStatus, 'failed');
});

test('direct F028 service projection is supported for deterministic fixtures without changing transport authority', () => {
  const { api } = makeFixture('en');
  const model = api.normalize(directResponse('hat_cloth'));
  assert.equal(model.valid, true);
  assert.equal(model.itemId, 'hat_cloth');
});

test('consumer source has no reward inference, fetch, or client-only ownership path', () => {
  const source = fs.readFileSync(MODULE_PATH, 'utf8');
  assert.doesNotMatch(source, /selectedZone|localStorage|sessionStorage|fetch\s*\(/);
  assert.match(source, /server has already resolved the item id/);
  assert.match(source, /refreshOwnership/);
});

test('index integration is single-panel, bilingual, responsive, refresh-backed, and app.py-free', () => {
  const index = fs.readFileSync(INDEX_PATH, 'utf8');
  const i18n = fs.readFileSync(I18N_PATH, 'utf8');
  assert.match(index, /battlefield_boss_reward_consumer\.js\?v=f029v1/);
  assert.equal((index.match(/id="boss-reward-presentation"/g) || []).length, 1);
  assert.match(index, /BattlefieldBossRewardConsumer\.present\(data/);
  assert.match(index, /refreshOwnership: async/);
  assert.match(index, /await loadPlayerAvatar\(\)/);
  assert.match(index, /I18n\.t\('index\.boss\.reward\.continue'\)/);
  assert.match(index, /@media \(max-width: 600px\), \(max-height: 700px\)/);
  assert.match(index, /env\(safe-area-inset-bottom/);
  assert.match(index, /min-height: 44px/);
  for (const key of [
    'index.boss.reward.kicker',
    'index.boss.reward.grantedTitle',
    'index.boss.reward.alreadyTitle',
    'index.boss.reward.continue',
    'index.boss.reward.refreshFailed',
  ]) assert.match(i18n, new RegExp(`'${key.replaceAll('.', '\\.')}'`));
});

if (process.exitCode) process.exit(process.exitCode);
