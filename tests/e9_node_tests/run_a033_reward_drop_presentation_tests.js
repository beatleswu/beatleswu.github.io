const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..', '..');
const SOURCE = fs.readFileSync(
  path.join(ROOT, 'js', 'game', 'reward_drop_presentation_v1.js'),
  'utf8',
);

function loadApi() {
  const context = vm.createContext({
    console,
    setTimeout: () => 1,
    clearTimeout: () => {},
    window: { I18n: { getLang: () => 'en' } },
  });
  vm.runInContext(SOURCE, context, { filename: 'reward_drop_presentation_v1.js' });
  return context.window.RewardDropPresentationV1;
}

function main() {
  const api = loadApi();
  assert.equal(api.CONTRACT_VERSION, 'GENERIC_MONSTER_REWARD_PRESENTATION_V1');

  const functional = api.normalize({
    ok: true,
    loot: {
      functional_equipment: true,
      item_id: 'wooden_sword',
      display_name: '木劍',
      display_name_en: 'Wooden Sword',
      slot: 'weapon',
      icon: '/assets/hero/equipment/functional/wooden_sword.svg',
      rarity: 'common',
      inv_id: 41,
    },
  });
  assert.equal(functional.status, api.FUNCTIONAL_EQUIPMENT);
  assert.equal(functional.item_id, 'wooden_sword');
  assert.equal(functional.action, 'VIEW_BACKPACK');
  assert.equal('equip' in functional, false, 'acquisition must not become equip');
  assert.equal('coins' in functional, false, 'Coins are not in the public reward model');

  const cosmetic = api.normalize({
    ok: true,
    appearance_loot: {
      id: 'robe_fox',
      name: '妖狐錦袍',
      name_en: 'Fox Robe',
      emoji: '🧣',
      rarity: 'rare',
    },
  });
  assert.equal(cosmetic.status, api.PURE_COSMETIC);
  assert.equal(cosmetic.pure_cosmetic_no_power, true);
  assert.equal(cosmetic.action, 'NONE');
  assert.equal('combat_power' in cosmetic, false);

  const noDrop = api.normalize({
    ok: true,
    monster: { defeated: true },
    monster_settlement: {
      defeated: true,
      duplicate: false,
      functional_lineage_count: 0,
      wardrobe_lineage_count: 0,
    },
  });
  assert.equal(noDrop.status, api.NO_DROP);
  assert.equal(noDrop.item_id, null);

  assert.equal(
    api.normalize({ ok: true, reward_type: 'COINS', coins: 2 }).status,
    api.UNAVAILABLE,
    'unsupported reward type must fail closed',
  );
  assert.equal(
    api.normalize({ ok: true, loot: { name: 'missing identity' } }).status,
    api.UNAVAILABLE,
    'malformed reward must fail closed',
  );
  assert.equal(
    api.normalize({ ok: true, contract_version: 'WRONG', loot: {} }).status,
    api.UNAVAILABLE,
    'wrong contract must fail closed',
  );
  assert.equal(
    api.normalize({ ok: true, monster_settlement: { defeated: true, duplicate: true } }).status,
    'SKIPPED',
    'duplicate settlement must not render a fabricated no-drop',
  );

console.log('A033 reward drop presentation tests: 8 passed');
}

main();
