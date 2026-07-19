'use strict';
const assert = require('assert');
const defs = require('../../js/e9/quest_definitions.js');
const evaluator = require('../../js/e9/quest_evaluator.js');
const storeApi = require('../../js/e9/quest_store.js');

assert.strictEqual(defs.validateCatalog(defs.definitions), true);
assert.strictEqual(new Set(defs.definitions.map((q) => q.id)).size, defs.definitions.length);
assert.ok(defs.definitions.every((q) => !Object.keys(q).some((k) => /^reward|claim|grant/i.test(k))));

const first = defs.definitions[0];
let result = evaluator.evaluateQuest(first, { adventure: { maxStars: 0, completedZoneCount: 0 }, dailyChallenge: { userSubmitted: false } });
assert.strictEqual(result.state, 'available');
result = evaluator.evaluateQuest(first, { adventure: { maxStars: 1, completedZoneCount: 0 }, dailyChallenge: { userSubmitted: false } });
assert.strictEqual(result.completed, true);
assert.strictEqual(result.ratio, 1);
assert.strictEqual(evaluator.evaluateQuest(first, {}).state, 'unavailable');
assert.strictEqual(evaluator.evaluateQuest(first, { adventure: { maxStars: -1, completedZoneCount: 0 }, dailyChallenge: { userSubmitted: false } }).state, 'unavailable');
const daily = defs.definitions[3];
assert.strictEqual(evaluator.evaluateQuest(daily, { adventure: { maxStars: 0, completedZoneCount: 0 }, dailyChallenge: { userSubmitted: true } }).completed, true);

let resolveAdventure;
let resolveDaily;
global.E9 = {
  isLifecycleCurrent: () => true,
  Adapters: {
    AdventureState: { fetchAdventureState: () => new Promise((resolve) => { resolveAdventure = resolve; }) },
    ActivityState: { fetchDailyChallenge: () => new Promise((resolve) => { resolveDaily = resolve; }), invalidateActivityState() {} }
  }
};
const store = storeApi.createQuestStore(1);
const pending = store.load();
resolveAdventure({ ok: true, data: { zones: [{ stars: 3, cleared: true }] } });
resolveDaily({ ok: true, data: { submitted: false } });
pending.then((loaded) => {
  assert.strictEqual(loaded.ok, true);
  const evaluated = store.evaluate(defs.definitions, evaluator);
  assert.strictEqual(evaluated[0].completed, true);
  assert.strictEqual(evaluated[0].justCompleted, undefined);
  store.destroy();
  console.log('quest evaluator/store tests passed');
}).catch((err) => { console.error(err); process.exit(1); });
