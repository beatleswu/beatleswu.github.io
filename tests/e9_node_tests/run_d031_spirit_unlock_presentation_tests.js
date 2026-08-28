'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const MODULE_PATH = path.join(REPO_ROOT, 'js', 'e9', 'adventure_spirit_unlock_presentation.js');
const moduleSource = fs.readFileSync(MODULE_PATH, 'utf8');
const presentation = require(MODULE_PATH);

const MILESTONES = [
  { zone_number: 4, zone_key: 'k11_15', spirit_id: 'starpath_antlerling' },
  { zone_number: 6, zone_key: 'k1_5', spirit_id: 'fatty' },
  { zone_number: 8, zone_key: 'd3_4', spirit_id: 'obsidian_bastion' },
];

let passCount = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passCount += 1;
  } catch (error) {
    failures.push({ name, error: error && error.stack ? error.stack : String(error) });
  }
}

function resultFor(definition, status = 'UNLOCKED', overrides = {}) {
  const eligible = status !== 'NOT_ELIGIBLE';
  const replayed = status === 'REPLAY';
  const mutation = status === 'UNLOCKED' ? 1 : 0;
  const result = {
    contract_version: 'ADVENTURE_SPIRIT_UNLOCK_RESULT_TRANSPORT_V1',
    user_id: 43102,
    zone_number: definition.zone_number,
    zone_key: definition.zone_key,
    spirit_id: definition.spirit_id,
    operation_id: `adventure:spirit_unlock:43102:${definition.zone_key}`,
    source_authority: 'ADVENTURE_ZONE_MILESTONE',
    source_fact: 'adventure_boss_progress.cleared=1',
    source_reference: `adventure_boss_progress:43102:${definition.zone_key}`,
    cleared: eligible,
    eligible,
    operation_type: 'SPIRIT_UNLOCK',
    ownership_store: 'pet_collection',
    compensation_count: 0,
    replacement_count: 0,
    client_completion_authority: false,
    status,
    result_state: status === 'REPLAY' ? 'NO_OP' : status,
    ownership_created: status === 'UNLOCKED',
    already_owned: status === 'NOT_ELIGIBLE' ? null : status !== 'UNLOCKED',
    historical_catchup: null,
    replay: replayed,
    reason_code: status === 'UNLOCKED' ? 'MILESTONE_UNLOCKED'
      : status === 'NO_OP' ? 'MILESTONE_ALREADY_OWNED'
      : status === 'REPLAY' ? 'MILESTONE_REPLAY'
      : 'MILESTONE_NOT_ELIGIBLE',
    replayed,
    ownership_mutation_count: mutation,
    new_unlock_count: mutation,
  };
  if (eligible) result.operation_status = 'COMPLETED';
  return Object.assign(result, overrides);
}

class FakeNode {
  constructor(tagName, document) {
    this.tagName = tagName.toUpperCase();
    this.document = document;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.hidden = false;
    this._textContent = '';
    this.className = '';
    this.id = '';
  }

  set textContent(value) {
    this._textContent = String(value == null ? '' : value);
    if (this._textContent === '') this.children = [];
  }

  get textContent() {
    return this._textContent;
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === 'id') this.id = String(value);
  }

  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name)
      ? this.attributes[name]
      : null;
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  addEventListener(name, handler) {
    (this.listeners[name] || (this.listeners[name] = [])).push(handler);
  }

  dispatchEvent(event) {
    (this.listeners[event.type] || []).slice().forEach((handler) => handler(event));
  }

  click() {
    this.dispatchEvent({ type: 'click' });
  }

  focus() {}

  querySelectorAll(selector) {
    const found = [];
    const walk = (node) => {
      node.children.forEach((child) => {
        if (selector === 'button' && child.tagName === 'BUTTON') found.push(child);
        if (selector === 'img' && child.tagName === 'IMG') found.push(child);
        walk(child);
      });
    };
    walk(this);
    return found;
  }
}

class FakeDocument {
  constructor() {
    this.documentElement = { lang: 'en' };
    this.body = new FakeNode('body', this);
  }

  createElement(tagName) {
    return new FakeNode(tagName, this);
  }

  getElementById(id) {
    let found = null;
    const walk = (node) => {
      if (found) return;
      if (node.id === id) {
        found = node;
        return;
      }
      node.children.forEach(walk);
    };
    walk(this.body);
    return found;
  }
}

function allText(node) {
  return node._textContent + node.children.map(allText).join('');
}

test('contract exposes exactly three supported presentation states', () => {
  assert.deepStrictEqual(Object.values(presentation.STATES), [
    'NEW_SPIRIT_UNLOCK',
    'ALREADY_OWNED_NO_OP',
    'NO_MILESTONE_UNLOCK',
  ]);
  assert.strictEqual(presentation.CONTRACT_VERSION, 'ADVENTURE_SPIRIT_UNLOCK_RESULT_V1');
});

test('all three locked milestone mappings normalize to new unlock', () => {
  MILESTONES.forEach((definition) => {
    const normalized = presentation.normalizeResult(resultFor(definition));
    assert.strictEqual(normalized.state, 'NEW_SPIRIT_UNLOCK');
    assert.strictEqual(normalized.zoneNumber, definition.zone_number);
    assert.strictEqual(normalized.spiritId, definition.spirit_id);
  });
});

test('NO_OP normalizes to already-owned no-op', () => {
  const normalized = presentation.normalizeResult(resultFor(MILESTONES[1], 'NO_OP'));
  assert.strictEqual(normalized.state, 'ALREADY_OWNED_NO_OP');
  assert.strictEqual(normalized.replayed, false);
});

test('REPLAY normalizes to already-owned no-op without new ownership', () => {
  const normalized = presentation.normalizeResult(resultFor(MILESTONES[2], 'REPLAY'));
  assert.strictEqual(normalized.state, 'ALREADY_OWNED_NO_OP');
  assert.strictEqual(normalized.replayed, true);
});

test('NOT_ELIGIBLE normalizes to no milestone unlock', () => {
  const normalized = presentation.normalizeResult(resultFor(MILESTONES[0], 'NOT_ELIGIBLE'));
  assert.strictEqual(normalized.state, 'NO_MILESTONE_UNLOCK');
});

test('server identity mismatch fails closed', () => {
  assert.strictEqual(
    presentation.normalizeResult(resultFor(MILESTONES[0], 'UNLOCKED', { spirit_id: 'fatty' })),
    null,
  );
  assert.strictEqual(
    presentation.normalizeResult(resultFor(MILESTONES[0], 'UNLOCKED', { zone_key: 'unknown' })),
    null,
  );
});

test('provenance and sink markers are required', () => {
  const base = resultFor(MILESTONES[0]);
  ['source_authority', 'source_fact', 'operation_type', 'ownership_store', 'source_reference', 'operation_id']
    .forEach((field) => {
      const invalid = Object.assign({}, base);
      delete invalid[field];
      assert.strictEqual(presentation.normalizeResult(invalid), null, field);
    });
  assert.strictEqual(
    presentation.normalizeResult(Object.assign({}, base, { client_completion_authority: true })),
    null,
  );
});

test('unlock counts and compensation markers cannot be forged', () => {
  const base = resultFor(MILESTONES[0]);
  assert.strictEqual(presentation.normalizeResult(Object.assign({}, base, { new_unlock_count: 0 })), null);
  assert.strictEqual(presentation.normalizeResult(Object.assign({}, base, { compensation_count: 1 })), null);
  assert.strictEqual(presentation.normalizeResult(Object.assign({}, base, { replacement_count: 1 })), null);
  assert.strictEqual(presentation.normalizeResult(Object.assign({}, base, { replayed: true })), null);
});

test('unknown status fails closed', () => {
  assert.strictEqual(
    presentation.normalizeResult(resultFor(MILESTONES[0], 'SUCCESS')),
    null,
  );
});

test('array normalization is deterministic and sorted by locked zone number', () => {
  const normalized = presentation.normalizeResults([
    resultFor(MILESTONES[2]),
    resultFor(MILESTONES[0]),
    resultFor(MILESTONES[1]),
  ]);
  assert.deepStrictEqual(normalized.map((item) => item.zoneNumber), [4, 6, 8]);
});

test('duplicate or contradictory server batches fail closed', () => {
  const valid = resultFor(MILESTONES[0]);
  assert.strictEqual(presentation.normalizeResults([valid, resultFor(MILESTONES[0])]), null);
  assert.strictEqual(
    presentation.normalizeResult(Object.assign({}, valid, {
      result_state: 'NO_OP',
      ownership_created: false,
    })),
    null,
  );
});

test('mixed catch-up results present actionable results and omit ineligible noise', () => {
  const states = presentation.present([
    resultFor(MILESTONES[2], 'NOT_ELIGIBLE'),
    resultFor(MILESTONES[0], 'UNLOCKED'),
    resultFor(MILESTONES[1], 'NO_OP'),
  ]);
  assert.deepStrictEqual(states, ['NEW_SPIRIT_UNLOCK', 'ALREADY_OWNED_NO_OP']);
});

test('invalid or empty transport produces no presentation', () => {
  assert.deepStrictEqual(presentation.present([]), []);
  assert.deepStrictEqual(presentation.present({ status: 'UNLOCKED' }), []);
});

test('DOM presentation exposes new unlock state and trusted mapped art', () => {
  const oldDocument = global.document;
  const document = new FakeDocument();
  global.document = document;
  try {
    presentation.present(resultFor(MILESTONES[0]));
    const root = document.getElementById('d031-adventure-spirit-result');
    assert.ok(root);
    assert.strictEqual(root.hidden, false);
    assert.strictEqual(root.getAttribute('data-d031-presentation-state'), 'NEW_SPIRIT_UNLOCK');
    assert.strictEqual(root.getAttribute('data-zone-key'), 'k11_15');
    assert.strictEqual(root.getAttribute('data-spirit-id'), 'starpath_antlerling');
    assert.ok(allText(root).includes('Starpath Antlerling'));
    assert.ok(allText(root).includes('Misty Forest'));
    assert.strictEqual(root.querySelectorAll('button').length, 2);
  } finally {
    global.document = oldDocument;
    presentation.clear();
  }
});

test('no-op presentation contains no acquisition language', () => {
  const oldDocument = global.document;
  const document = new FakeDocument();
  global.document = document;
  try {
    presentation.present(resultFor(MILESTONES[1], 'NO_OP'));
    const root = document.getElementById('d031-adventure-spirit-result');
    assert.strictEqual(root.getAttribute('data-d031-presentation-state'), 'ALREADY_OWNED_NO_OP');
    assert.ok(allText(root).includes('already in your collection'));
    assert.ok(!allText(root).includes('new Spirit joins'));
  } finally {
    global.document = oldDocument;
    presentation.clear();
  }
});

test('non-eligible result produces no presentation', () => {
  const oldDocument = global.document;
  const document = new FakeDocument();
  global.document = document;
  try {
    assert.deepStrictEqual(presentation.present(resultFor(MILESTONES[0], 'NOT_ELIGIBLE')), []);
    const root = document.getElementById('d031-adventure-spirit-result');
    assert.strictEqual(root, null);
  } finally {
    global.document = oldDocument;
    presentation.clear();
  }
});

test('neutral result clears any stale visible presentation', () => {
  const oldDocument = global.document;
  const document = new FakeDocument();
  global.document = document;
  try {
    presentation.present(resultFor(MILESTONES[0]));
    const root = document.getElementById('d031-adventure-spirit-result');
    assert.strictEqual(root.hidden, false);
    presentation.present(resultFor(MILESTONES[0], 'NOT_ELIGIBLE'));
    assert.strictEqual(root.hidden, true);
  } finally {
    global.document = oldDocument;
    presentation.clear();
  }
});

test('continue closes the final result without an unlock action', () => {
  const oldDocument = global.document;
  const document = new FakeDocument();
  global.document = document;
  try {
    presentation.present(resultFor(MILESTONES[0]));
    const root = document.getElementById('d031-adventure-spirit-result');
    assert.strictEqual(root.querySelectorAll('button')[0].getAttribute('aria-label'), 'Dismiss');
    root.querySelectorAll('button')[1].click();
    assert.strictEqual(root.hidden, true);
  } finally {
    global.document = oldDocument;
    presentation.clear();
  }
});

test('Escape dismisses the final result and emits one completion hint', () => {
  const oldDocument = global.document;
  const oldCustomEvent = global.CustomEvent;
  const oldDispatchEvent = global.dispatchEvent;
  const document = new FakeDocument();
  const events = [];
  global.document = document;
  global.CustomEvent = function CustomEvent(type) { this.type = type; };
  global.dispatchEvent = (event) => events.push(event.type);
  try {
    presentation.present(resultFor(MILESTONES[0]));
    const root = document.getElementById('d031-adventure-spirit-result');
    let prevented = false;
    root.dispatchEvent({ type: 'keydown', key: 'Escape', preventDefault: () => { prevented = true; } });
    assert.strictEqual(prevented, true);
    assert.strictEqual(root.hidden, true);
    assert.deepStrictEqual(events, [presentation.COMPLETION_EVENT]);
  } finally {
    global.document = oldDocument;
    global.CustomEvent = oldCustomEvent;
    global.dispatchEvent = oldDispatchEvent;
    presentation.clear();
  }
});

test('completion broadcasts a refresh hint without carrying ownership state', () => {
  const oldDocument = global.document;
  const oldCustomEvent = global.CustomEvent;
  const oldDispatchEvent = global.dispatchEvent;
  const oldBroadcastChannel = global.BroadcastChannel;
  const document = new FakeDocument();
  const messages = [];
  const channels = [];
  function FakeBroadcastChannel(name) {
    this.name = name;
    this.listeners = [];
    channels.push(this);
  }
  FakeBroadcastChannel.prototype.addEventListener = function (type, listener) {
    if (type === 'message') this.listeners.push(listener);
  };
  FakeBroadcastChannel.prototype.postMessage = function (message) {
    channels.forEach((channel) => {
      if (channel !== this) channel.listeners.forEach((listener) => listener({ data: message }));
    });
  };
  FakeBroadcastChannel.prototype.close = function () {};
  global.document = document;
  global.CustomEvent = function CustomEvent(type) { this.type = type; };
  global.dispatchEvent = () => {};
  global.BroadcastChannel = FakeBroadcastChannel;
  try {
    const observer = new global.BroadcastChannel(presentation.SYNC_CHANNEL_NAME);
    observer.addEventListener('message', (event) => messages.push(event.data));
    presentation.present(resultFor(MILESTONES[0]));
    document.getElementById('d031-adventure-spirit-result').querySelectorAll('button')[1].click();
    assert.deepStrictEqual(messages, [{ type: presentation.COMPLETION_EVENT }]);
  } finally {
    global.document = oldDocument;
    global.CustomEvent = oldCustomEvent;
    global.dispatchEvent = oldDispatchEvent;
    global.BroadcastChannel = oldBroadcastChannel;
    presentation.clear();
  }
});

test('presentation ignores unrelated client-shaped fields', () => {
  const raw = resultFor(MILESTONES[2]);
  raw.selectedZone = 'k11_15';
  raw.monster = { defeated: true };
  raw.quest = { completed: true };
  raw.client_unlock = true;
  const normalized = presentation.normalizeResult(raw);
  assert.strictEqual(normalized.state, 'NEW_SPIRIT_UNLOCK');
  assert.strictEqual(normalized.zoneKey, 'd3_4');
  assert.strictEqual(normalized.spiritId, 'obsidian_bastion');
});

test('asset mapping is canonical and raw asset identity is ignored', () => {
  const raw = resultFor(MILESTONES[1], 'UNLOCKED', { asset: '/client/forged.webp' });
  const normalized = presentation.normalizeResult(raw);
  assert.strictEqual(normalized.asset, '/assets/pets/pet_fatty_stage1.webp');
});

test('module has no API, storage, or mutation hook', () => {
  assert.ok(!/\bfetch\s*\(/.test(moduleSource));
  assert.ok(!/XMLHttpRequest|localStorage|sessionStorage/.test(moduleSource));
  assert.ok(!/INSERT|UPDATE|DELETE|commit\s*\(/i.test(moduleSource));
});

test('module does not expose a state-changing unlock control', () => {
  assert.ok(!/unlock\s*\(/i.test(moduleSource));
  assert.ok(!/window\.location|location\.href/.test(moduleSource));
});

if (failures.length) {
  failures.forEach((failure) => {
    process.stderr.write(`FAIL ${failure.name}\n${failure.error}\n`);
  });
  process.exitCode = 1;
} else {
  process.stdout.write(`D031 presentation tests: ${passCount} passed\n`);
}
