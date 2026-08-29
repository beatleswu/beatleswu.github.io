const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const sourcePath = path.resolve(__dirname, '..', '..', 'js', 'hero_legacy_cache_guard.js');
const source = fs.readFileSync(sourcePath, 'utf8');
const context = { console };
context.globalThis = context;
vm.runInNewContext(source, context, { filename: sourcePath });

const guard = context.GoOdysseyLegacyHeroCache;
assert.ok(guard);
assert.deepStrictEqual(Array.from(guard.FUNCTIONAL_CACHE_FIELDS), [
  'armor', 'cape', 'weapon', 'offhand', 'hat', 'pet', 'aura', 'acc',
]);

const jsonValue = value => JSON.parse(JSON.stringify(value));
assert.deepStrictEqual(jsonValue(guard.parse('')), {});
assert.deepStrictEqual(jsonValue(guard.parse('{not-json')), {});
assert.deepStrictEqual(jsonValue(guard.parse('null')), {});
assert.deepStrictEqual(jsonValue(guard.parse('[]')), {});
assert.strictEqual(
  guard.characterOnly(JSON.stringify({ character: 'rogue', weapon: 'weapon_t10' }),
    ['apprentice', 'rogue']),
  'rogue',
);
assert.strictEqual(
  guard.characterOnly(JSON.stringify({ character: 'unowned' }), ['apprentice', 'rogue']),
  'apprentice',
);

const storage = {
  value: JSON.stringify({
    character: 'rogue',
    armor: 'armor_t10',
    weapon: 'weapon_t10',
    offhand: 'offhand_t10',
    equipped: true,
    wrong_slot: 'unowned_item',
  }),
  setItem(key, value) { this.key = key; this.value = value; },
};
const migrated = guard.discardFunctionalEquipment(
  storage,
  'hero_combat_gear_v1',
  'apprentice',
  ['apprentice', 'rogue'],
);
assert.strictEqual(migrated.character, 'apprentice');
assert.deepStrictEqual(JSON.parse(storage.value), { character: 'apprentice' });
assert.deepStrictEqual(Array.from(migrated.discardedFields), Array.from(guard.FUNCTIONAL_CACHE_FIELDS));

const crossUser = guard.discardFunctionalEquipment(
  storage,
  'hero_combat_gear_v1',
  'mage',
  new Set(['apprentice', 'rogue']),
);
assert.strictEqual(crossUser.character, 'apprentice');
assert.deepStrictEqual(JSON.parse(storage.value), { character: 'apprentice' });

const throwingStorage = { setItem() { throw new Error('storage unavailable'); } };
assert.doesNotThrow(() => guard.discardFunctionalEquipment(
  throwingStorage,
  'hero_combat_gear_v1',
  'apprentice',
  ['apprentice'],
));

assert.ok(!/fetch\(|player_inventory|dmg_bonus|combat_stats/.test(source));
console.log('A040 legacy cache guard tests: 9 passed');
