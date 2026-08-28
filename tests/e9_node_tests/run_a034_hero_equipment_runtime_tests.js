const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const heroSource = fs.readFileSync(
  path.join(__dirname, '..', '..', 'hero.html'),
  'utf8',
);

assert.strictEqual(
  (heroSource.match(/function renderFunctionalWearableProjection\s*\(/g) || []).length,
  1,
  'Hero must have one functional wearable projection implementation',
);

const adapterStart = heroSource.indexOf('const FUNCTIONAL_FULL_BODY_EQUIPMENT_IDS');
const adapterEnd = heroSource.indexOf('const FUNCTIONAL_WEARABLE_ASSET_ROOT', adapterStart);
assert(adapterStart >= 0 && adapterEnd > adapterStart, 'Hero adapter block must remain present');
const context = {};
vm.runInNewContext(
  `${heroSource.slice(adapterStart, adapterEnd)}\nglobalThis.api = { normalizeHeroFunctionalEquipment };`,
  context,
);

const item = (itemId, slot, equipped = true) => ({
  item_id: itemId,
  id: itemId,
  slot,
  equipped,
  functional_equipment: true,
});
const normalize = context.api.normalizeHeroFunctionalEquipment;

const valid = normalize([
  item('iron_sword', 'weapon'),
  item('dragon_scale', 'armor'),
  item('dragon_eye', 'accessory'),
]);
assert.strictEqual(valid.status, 'ready');
assert.strictEqual(
  JSON.stringify(valid.items.map(candidate => candidate.item_id)),
  JSON.stringify(['iron_sword', 'dragon_scale', 'dragon_eye']),
);

const duplicateSlot = normalize([
  item('wooden_sword', 'weapon'),
  item('iron_sword', 'weapon'),
]);
assert.strictEqual(duplicateSlot.status, 'unavailable');
assert.strictEqual(duplicateSlot.items.length, 0);

const wrongSlot = normalize([item('iron_sword', 'armor')]);
assert.strictEqual(wrongSlot.status, 'unavailable');
assert.strictEqual(wrongSlot.items.length, 0);

const unknown = normalize([item('unreleased_sword', 'weapon')]);
assert.strictEqual(unknown.status, 'unavailable');
assert.strictEqual(unknown.items.length, 0);

const trophy = normalize([
  item('go_stone_black', 'accessory'),
  item('iron_sword', 'weapon'),
]);
assert.strictEqual(trophy.status, 'ready');
assert.strictEqual(
  JSON.stringify(trophy.items.map(candidate => candidate.item_id)),
  JSON.stringify(['iron_sword']),
);

const legacyHold = normalize([item('xp_amulet', 'accessory')]);
assert.strictEqual(legacyHold.status, 'ready');
assert.strictEqual(
  JSON.stringify(legacyHold.items.map(candidate => candidate.item_id)),
  JSON.stringify(['xp_amulet']),
);

const unequipped = normalize([item('iron_sword', 'weapon', false)]);
assert.strictEqual(unequipped.status, 'ready');
assert.strictEqual(unequipped.items.length, 0);

console.log('A034 Hero equipment runtime tests: 7 passed');
