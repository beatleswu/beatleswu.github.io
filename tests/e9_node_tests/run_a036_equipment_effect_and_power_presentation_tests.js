const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.join(__dirname, '..', '..');
const heroSource = fs.readFileSync(path.join(root, 'hero.html'), 'utf8');
const inventorySource = fs.readFileSync(path.join(root, 'inventory.html'), 'utf8');

assert(inventorySource.includes('const FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED = false;'));
assert(inventorySource.includes("const FUNCTIONAL_INVENTORY_ONLY_IDS = new Set(['go_stone_black']);"));
assert(inventorySource.includes('declared_value_label'));
assert(inventorySource.includes('action.disabled = blockedNewEquip;'));
assert(inventorySource.includes('action === \'equip\' && !FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED'));
assert(inventorySource.includes('No combat power'));
assert(inventorySource.includes('不提供戰鬥能力'));
assert(heroSource.includes('server-defined equipment'));
assert(heroSource.includes('hero-functional-projection-state'));
assert(heroSource.includes('overflow-wrap:anywhere'));
assert(inventorySource.includes('.functional-detail-row > span:first-child'));
assert(heroSource.includes('Not currently effective'));
assert(heroSource.includes('尚未啟用'));

for (const rawKey of ['dmg_bonus', 'player_dmg_reduce', 'negate_counter', 'first_question_ace']) {
  assert(!inventorySource.includes(rawKey), `raw effect key leaked into Backpack: ${rawKey}`);
  assert(!heroSource.includes(rawKey), `raw effect key leaked into Hero: ${rawKey}`);
}

const start = inventorySource.indexOf('const FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED');
const end = inventorySource.indexOf('function renderFunctionalEquipmentFilters', start);
assert(start >= 0 && end > start);
const context = {
  I18n: { getLang: () => 'zh' },
};
vm.runInNewContext(
  `${inventorySource.slice(start, end)}\nglobalThis.api = { functionalEffectDetails, functionalUnsupportedEffects, functionalEffectValue, functionalEquipmentCardHTML };`,
  context,
);

const xp = {
  item_id: 'xp_amulet', inv_id: 1, display_name: 'XP 護符', name_en: 'XP Amulet',
  rarity: 'rare', slot: 'accessory', equipped: false, owned_quantity: 1,
  active_effect_details: [],
  unsupported_effects: [{
    key: 'xp_bonus', label: 'XP 加成', label_en: 'XP bonus',
    declared_value: 0.2, declared_value_label: '+20%', declared_value_label_en: '+20%',
    status: 'NOT_CURRENTLY_EFFECTIVE',
  }],
};
assert.strictEqual(context.api.functionalEffectDetails(xp).length, 0);
assert.strictEqual(context.api.functionalUnsupportedEffects(xp).length, 1);
assert.strictEqual(context.api.functionalEffectValue(xp.unsupported_effects[0]), '+20%');
assert(context.api.functionalEquipmentCardHTML(xp).includes('+20%'));
assert(context.api.functionalEquipmentCardHTML(xp).includes('尚未啟用'));

const stone = {
  item_id: 'go_stone_black', inv_id: 2, display_name: '先手黑石', name_en: 'First-Move Black Stone',
  rarity: 'legendary', slot: 'accessory', equipped: false, owned_quantity: 1,
  active_effect_details: [],
  unsupported_effects: [{
    key: 'first_question_ace', label: '第一題保證高分', label_en: 'First-question guarantee',
    declared_value: true, declared_value_label: '啟用', declared_value_label_en: 'Enabled',
    status: 'NOT_CURRENTLY_EFFECTIVE',
  }],
};
assert.strictEqual(context.api.functionalEffectDetails(stone).length, 0);
assert.strictEqual(context.api.functionalUnsupportedEffects(stone).length, 0);
const stoneCard = context.api.functionalEquipmentCardHTML(stone);
assert(stoneCard.includes('收藏品'));
assert(stoneCard.includes('不提供戰鬥能力'));
assert(!stoneCard.includes('first_question_ace'));

const malformed = {
  item_id: 'iron_sword', inv_id: 3, display_name: '鐵劍', name_en: 'Iron Sword',
  rarity: 'uncommon', slot: 'weapon', equipped: true, owned_quantity: 1,
  active_effect_details: [null, { key: 'dmg_bonus', value: 0.12 }],
  unsupported_effects: [],
};
const malformedCard = context.api.functionalEquipmentCardHTML(malformed);
assert(!malformedCard.includes('dmg_bonus'));
assert(!malformedCard.includes('0.12'));
assert(malformedCard.includes('已定義效果'));

const projectionStart = heroSource.indexOf('function functionalProjectionEffectDetails');
const projectionEnd = heroSource.indexOf('function functionalProjectionItemHTML', projectionStart);
assert(projectionStart >= 0 && projectionEnd > projectionStart);
const projectionContext = { isEn: () => false };
vm.runInNewContext(
  `${heroSource.slice(projectionStart, projectionEnd)}\nglobalThis.api = { functionalProjectionEffectText };`,
  projectionContext,
);
const malformedProjection = projectionContext.api.functionalProjectionEffectText({
  active_effect_details: [null, { key: 'dmg_bonus', value: 0.12 }],
  unsupported_effects: [],
});
assert.strictEqual(malformedProjection, '已定義效果');

const summaryStart = heroSource.indexOf('function renderHeroOverview()');
const summaryEnd = heroSource.indexOf('async function hydrateAuthoritativeHeroPresentation', summaryStart);
assert(summaryStart >= 0 && summaryEnd > summaryStart);
assert(!heroSource.slice(summaryStart, summaryEnd).includes('active_effect_details'));

console.log('A036 equipment effect and power presentation tests: 15 passed');
