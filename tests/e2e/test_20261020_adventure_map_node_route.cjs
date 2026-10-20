'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', '..', 'index.html'), 'utf8');
function extract(signature) {
  const start = source.indexOf(signature);
  assert.ok(start >= 0, 'missing production function: ' + signature);
  const end = source.indexOf('\n}', start);
  assert.ok(end > start, 'missing function terminator');
  return source.slice(start, end + 2);
}
const actualClick = extract('async function onAdventureMapNodeClick(zoneKey)');
const actualHandler = extract('function _handleAdventureMapNodeActivation(event)');

function harness({ unlocked = true, bossReady = false } = {}) {
  const calls = [];
  let node = {
    dataset: { zone: 'k21_25' },
    classList: { contains: name => (name === 'locked' && !unlocked) || (name === 'boss-ready' && bossReady) },
  };
  const host = { dataset: {}, contains: candidate => candidate === node };
  const zone = { key: 'k21_25', unlocked, boss_ready: bossReady };
  const sandbox = {
    document: { getElementById: id => id === 'adventure-map-nodes' ? host : null },
    _adventureProgress: [zone],
    ADVENTURE_ZONES: [zone],
    _adventureCanEnter: candidate => candidate.unlocked === true,
    selectAdventureStage: key => calls.push('select:' + key),
    startAdventureStage: async key => { calls.push('train:' + key); },
    startBossBattle: key => { calls.push('UNEXPECTED_BOSS:' + key); },
    playAdventureMapSound: sound => calls.push('sound:' + sound),
    setMsg: () => calls.push('message'),
    _adventureText: key => key,
    Date,
  };
  vm.runInNewContext(actualClick + '\n' + actualHandler, sandbox, { filename: 'index.html-map-route' });
  function fire() {
    const consumed = [];
    const event = {
      target: { closest: () => node },
      preventDefault: () => consumed.push('default'),
      stopPropagation: () => consumed.push('bubble'),
      stopImmediatePropagation: () => consumed.push('immediate'),
    };
    sandbox._handleAdventureMapNodeActivation(event);
    return consumed;
  }
  function replaceNode() {
    node = { ...node, dataset: { zone: 'k21_25' } };
  }
  return { calls, fire, replaceNode };
}

test('unlocked zone 2 map entry selects before training', async () => {
  const h = harness();
  assert.deepEqual(h.fire(), ['default', 'bubble', 'immediate']);
  await Promise.resolve();
  assert.deepEqual(h.calls, ['select:k21_25', 'train:k21_25']);
});

test('boss-ready map node does not bypass explicit Lord CTA', async () => {
  const h = harness({ bossReady: true });
  h.fire();
  await Promise.resolve();
  assert.deepEqual(h.calls, ['select:k21_25', 'train:k21_25']);
});

test('pointerup followed by click is consumed but not double-entered', async () => {
  const h = harness();
  assert.deepEqual(h.fire(), ['default', 'bubble', 'immediate']);
  assert.deepEqual(h.fire(), ['default', 'bubble', 'immediate']);
  await Promise.resolve();
  assert.deepEqual(h.calls, ['select:k21_25', 'train:k21_25']);
});

test('duplicate event after map re-render cannot enter a second time', async () => {
  const h = harness();
  h.fire();
  h.replaceNode();
  assert.deepEqual(h.fire(), ['default', 'bubble', 'immediate']);
  await Promise.resolve();
  assert.deepEqual(h.calls, ['select:k21_25', 'train:k21_25']);
});

test('locked node cannot enter any stage', async () => {
  const h = harness({ unlocked: false });
  assert.deepEqual(h.fire(), ['default', 'bubble', 'immediate']);
  await Promise.resolve();
  assert.deepEqual(h.calls, []);
});
