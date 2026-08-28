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
  'A035 must keep one functional wearable renderer',
);
assert(heroSource.includes('data-loadout-effective="off"'));
assert(heroSource.includes('const HERO_LEGACY_LOADOUT_EFFECTIVE = false;'));
assert(heroSource.includes('clearLegacyCombatGearVisuals();'));
assert(heroSource.includes("body[data-loadout-effective=\"off\"] .legacy-loadout-section"));
assert(heroSource.includes('id="hero-equipment-functional-projection-list"'));
assert((heroSource.match(/hero-equipment-functional-projection-list/g) || []).length >= 2);
assert(heroSource.includes("item.functional_equipment === true"));
assert(heroSource.includes("item.equipped === true"));
assert(heroSource.includes('renderAuthoritativeFunctionalEffects();'));
assert(heroSource.includes('refreshAuthoritativeHeroPresentation();'));

const adapterStart = heroSource.indexOf('const FUNCTIONAL_EQUIPMENT_IDS');
const adapterEnd = heroSource.indexOf('const FUNCTIONAL_WEARABLE_ASSET_ROOT', adapterStart);
assert(adapterStart >= 0 && adapterEnd > adapterStart, 'A035 adapter block must remain present');
const context = {};
vm.runInNewContext(
  `${heroSource.slice(adapterStart, adapterEnd)}\nglobalThis.api = { normalizeHeroFunctionalEquipment };`,
  context,
);

const item = (itemId, slot, equipped = true, extra = {}) => ({
  item_id: itemId,
  id: itemId,
  slot,
  equipped,
  functional_equipment: true,
  ...extra,
});
const normalize = context.api.normalizeHeroFunctionalEquipment;

const valid = normalize([
  item('celestial_blade', 'weapon'),
  item('void_mantle', 'armor'),
  item('fox_mask', 'accessory'),
]);
assert.strictEqual(valid.status, 'ready');
assert.strictEqual(
  JSON.stringify(valid.items.map(candidate => candidate.item_id)),
  JSON.stringify(['celestial_blade', 'void_mantle', 'fox_mask']),
);

assert.strictEqual(normalize([
  item('wooden_sword', 'weapon'),
  item('iron_sword', 'weapon'),
]).status, 'unavailable', 'duplicate slot must fail closed');
assert.strictEqual(normalize([item('unknown_item', 'weapon')]).status, 'unavailable');
assert.strictEqual(normalize([item('iron_sword', 'armor')]).status, 'unavailable');
assert.strictEqual(
  JSON.stringify(normalize([item('go_stone_black', 'accessory'), item('iron_sword', 'weapon')]).items
    .map(candidate => candidate.item_id)),
  JSON.stringify(['iron_sword']),
);
assert.strictEqual(
  JSON.stringify(normalize([item('xp_amulet', 'accessory')]).items.map(candidate => candidate.item_id)),
  JSON.stringify(['xp_amulet']),
  'legacy equipped XP Amulet may be displayed for recovery but is not enabled here',
);
assert.strictEqual(JSON.stringify(normalize([item('iron_sword', 'weapon', false)]).items), '[]');

const effectStart = heroSource.indexOf('function renderAuthoritativeFunctionalEffects');
const effectEnd = heroSource.indexOf('function renderCosmeticProjection', effectStart);
const effectBody = heroSource.slice(effectStart, effectEnd);
assert(!effectBody.includes('wardrobeItems'));
assert(effectBody.includes('active_effect_details'));
assert(effectBody.includes('go_stone_black'));

const visualStart = heroSource.indexOf('function applyEquippedVisuals');
const visualEnd = heroSource.indexOf('// ── Inventory slot renderer', visualStart);
const visualBody = heroSource.slice(visualStart, visualEnd);
assert(!visualBody.includes('i.effects'));
assert(visualBody.includes('renderAuthoritativeFunctionalEffects();'));

console.log('A035 Hero equipment presentation tests: 15 passed');
