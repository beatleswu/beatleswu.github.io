'use strict';

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const MODULE_PATH = path.join(ROOT, 'js', 'game', 'battlefield_boss_reward_consumer.js');
const CONTRACT_VERSION = 'F028_BATTLEFIELD_BOSS_MAPPING_A_FIRST_CLEAR_V1';

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
  constructor() {
    this.documentElement = { lang: 'en' };
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
  }

  getElementById(id) {
    return this.elements.get(id) || null;
  }
}

function loadConsumer() {
  const document = new FakeDocument();
  const window = {
    document,
    I18n: { getLang: () => 'en', t: key => key },
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

function routeResponse(itemId, status = 'GRANTED') {
  const hasItem = status !== 'NO_REWARD';
  const item = hasItem ? {
    id: itemId,
    item_id: itemId,
    slot: 'back',
    display_name: '棋具布包',
    name_en: 'Go Kit Pack',
    icon: '🎒',
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
  } : null;
  const reward = {
    coins: 0,
    contract_version: CONTRACT_VERSION,
    status,
    passed: status !== 'NO_REWARD',
    first_clear: status !== 'NO_REWARD',
    replay: status === 'NO_REWARD',
    entitlement_consumed: status !== 'NO_REWARD',
    entitlement_id: 'adventure:first_clear:7:k1_5',
    source_operation_id: 'adventure:first_clear:7:k1_5',
    item_id: hasItem ? itemId : null,
    mapping_a_zone: 'Z6',
    ownership_authority: 'player_wardrobe',
    ownership_persisted: hasItem,
    ownership_row_id: hasItem ? 42 : null,
    auto_equip: false,
    auto_equipped: false,
    compensation: false,
    replacement_reward: false,
    combat_power: 0,
    reward_item: item,
    reason_code: status === 'NO_REWARD' ? 'REPLAY_ALREADY_CLEARED' : null,
  };
  return {
    ok: true,
    passed: reward.passed,
    replay: reward.replay,
    reward,
    reward_item: item,
    adventure_spirit_unlock_results: [{ source: 'D035_D036_ACCEPTED_FIXTURE' }],
  };
}

async function main() {
  const { api, document } = loadConsumer();
  let refreshCalls = 0;
  const granted = await api.present(routeResponse('back_pack'), {
    document,
    lang: 'en',
    refreshOwnership: async () => { refreshCalls += 1; return true; },
  });
  assert.equal(granted.kind, 'granted');
  assert.equal(granted.itemId, 'back_pack');
  assert.equal(granted.refreshStatus, 'refreshed');
  assert.equal(refreshCalls, 1);
  assert.equal(document.getElementById('boss-reward-presentation').hidden, false);
  assert.equal(document.getElementById('boss-reward-presentation-item-name').textContent, 'Go Kit Pack');

  const alreadyOwned = await api.present(routeResponse('back_pack', 'ALREADY_OWNED'), { document, lang: 'en' });
  assert.equal(alreadyOwned.kind, 'already_owned');
  assert.match(document.getElementById('boss-reward-presentation-state').textContent, /unchanged/);

  const replay = await api.present(routeResponse('back_pack', 'NO_REWARD'), {
    document,
    refreshOwnership: async () => { refreshCalls += 1; return true; },
  });
  assert.equal(replay.hasReward, false);
  assert.equal(refreshCalls, 1);
  assert.equal(document.getElementById('boss-reward-presentation').hidden, true);

  process.stdout.write('PASS F030 route-shaped server response integrates with F029 consumer\n');
}

main().catch(error => {
  process.stderr.write(`FAIL F030 route/F029 integration: ${error.stack || error}\n`);
  process.exitCode = 1;
});
