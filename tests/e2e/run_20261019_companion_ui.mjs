// Offline execution of hero.html functions. No browser, network, or player data.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const html = readFileSync(new URL('../../hero.html', import.meta.url), 'utf8');
const section = (start, end) => html.slice(html.indexOf(start), html.indexOf(end, html.indexOf(start)));
const feedSource = section('let _petFeedInFlight =', 'async function interactPet(');
const renderSource = section('function renderPetCompanion()', 'function petBurst(');
const idSource = section('function newCompanionOperationId(', 'function notifyActiveSpiritSelection(');
const reply = (data = {ok: true}, status = 200) => ({ok: status < 400, status, json: async () => data});
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; };

function harness(fetch) {
  const buttons = ['candy', 'fruit', 'empty'].map(key => ({
    dataset: {petFeed: key}, disabled: key === 'empty',
    setAttribute(name, value) { this[name] = value; },
  }));
  const root = {innerHTML: '', querySelector: () => null};
  const messages = [];
  const c = vm.createContext({
    fetch, crypto: globalThis.crypto, Date, Math, Promise,
    _petState: {pet: {pet_key: 'ink_drop_kelpie', fullness: 100, affection: 10},
      inventory: [{key: 'candy', qty: 3}, {key: 'fruit', qty: 1}, {key: 'empty', qty: 0}]},
    _petPendingLine: null,
    document: {querySelectorAll: () => buttons, getElementById: () => root},
    isEn: () => true, showToast: msg => messages.push(msg),
    petSay: () => 'fed', petMilestoneToast: () => 'milestone',
    loadPetStatus: async () => {},
    petFrameKey: () => '', petMood: () => ({key: 'happy'}), petSituation: () => 'idle',
    escapeHTML: v => String(v ?? ''), petLocal: () => '', petAnimatedImage: () => '',
    petRosterHTML: () => '', petStatHTML: () => '', petEvolutionHTML: () => '',
    petBonusHTML: () => '', petFoodHelpHTML: () => '', petActionRowHTML: () => '',
    startPetIdle: () => {}, startPetCooldownTicker: () => {},
    startPetExpeditionTicker: () => {}, petTypewriter: () => {},
  });
  vm.runInContext(idSource + feedSource + renderSource, c);
  return {c, buttons, root, messages, run: code => vm.runInContext(code, c)};
}

test('all inline classic scripts parse', () => {
  let count = 0;
  for (const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    if (/\bsrc\s*=|type\s*=\s*["'](?:module|importmap|application\/)/.test(match[1])) continue;
    new vm.Script(match[2]);
    count++;
  }
  assert(count > 0);
});

test('double click and different-food click share one flight and disable every food through refresh', async () => {
  const request = deferred(), refresh = deferred();
  const calls = [];
  const h = harness(async (url, options) => { calls.push({url, options}); return request.promise; });
  h.c.loadPetStatus = async () => { h.run('renderPetCompanion()'); await refresh.promise; };
  const first = h.run("feedPet('candy')");
  assert.equal(first, h.run("feedPet('candy')"));
  assert.equal(first, h.run("feedPet('fruit')"));
  assert(h.buttons.every(b => b.disabled));
  await Promise.resolve();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/pet/feed');
  const payload = JSON.parse(calls[0].options.body);
  assert.equal(payload.spirit_id, 'ink_drop_kelpie');
  assert.equal(payload.item_key, 'candy');
  assert.match(payload.operation_id, /^companion:feed:.+/);
  assert.equal(calls[0].options.credentials, 'include');
  request.resolve(reply());
  for (let i = 0; i < 8; i++) await Promise.resolve();
  assert(h.buttons.every(b => b.disabled));
  const markup = [...h.root.innerHTML.matchAll(/<button[^>]*data-pet-feed[^>]*>/g)];
  assert.equal(markup.length, 3);
  assert(markup.every(m => /disabled/.test(m[0])));
  refresh.resolve(); await first;
  assert.deepEqual(h.buttons.map(b => b.disabled), [false, false, true]);
});

test('lost committed response retries identical bytes and consumes once in a durable-authority simulation', async () => {
  const ledger = new Set(), bodies = []; let consumed = 0;
  const h = harness(async (_, options) => {
    bodies.push(options.body);
    const p = JSON.parse(options.body);
    if (!ledger.has(p.operation_id)) { ledger.add(p.operation_id); consumed++; throw new Error('response lost'); }
    return reply();
  });
  await h.run("feedPet('candy')");
  assert.equal(bodies.length, 2);
  assert.equal(bodies[0], bodies[1]);
  assert.equal(consumed, 1);
  await h.run("feedPet('candy')");
  assert.equal(consumed, 2);
  assert.notEqual(bodies[0], bodies[2]);
});

test('exhausted transport retries retain identity across later clicks and reject a different target', async () => {
  const bodies = []; let fail = true;
  const h = harness(async (_, options) => { bodies.push(options.body); if (fail) throw new Error('offline'); return reply(); });
  await h.run("feedPet('candy')");
  assert.equal(bodies.length, 2);
  assert.deepEqual(h.buttons.map(b => b.disabled), [false, true, true]);
  await h.run("feedPet('fruit')");
  h.c._petState.pet.pet_key = 'whispering_void_kit';
  await h.run("feedPet('candy')");
  assert.equal(bodies.length, 2);
  h.c._petState.pet.pet_key = 'ink_drop_kelpie';
  h.c._petState.inventory[0].qty = 0;
  h.run('syncPetFeedButtons()');
  assert.equal(h.buttons[0].disabled, false, 'allow replay even if status shows the consumed last food');
  fail = false;
  await h.run("feedPet('candy')");
  assert.equal(bodies[0], bodies[2]);
  assert.equal(h.buttons[0].disabled, true);
});

test('unreadable response retries with same identity', async () => {
  const bodies = [];
  const h = harness(async (_, options) => {
    bodies.push(options.body);
    return bodies.length === 1 ? {ok: true, status: 200, json: async () => { throw new Error('truncated'); }} : reply();
  });
  await h.run("feedPet('candy')");
  assert.equal(bodies.length, 2); assert.equal(bodies[0], bodies[1]);
});

test('explicit rejection releases flight without success animation or automatic mutation retry', async () => {
  let calls = 0;
  const h = harness(async () => { calls++; return reply({ok: false, error: 'ACTIVE_SPIRIT_CHANGED'}, 409); });
  await h.run("feedPet('candy')");
  assert.equal(calls, 1);
  assert.equal(h.c._petPendingLine, null);
  assert.equal(h.messages.at(-1), 'ACTIVE_SPIRIT_CHANGED');
  assert.deepEqual(h.buttons.map(b => b.disabled), [false, false, true]);
  assert.equal(h.run('_petFeedPending'), null);
});

test('server failure keeps retry identity and never celebrates ok:false', async () => {
  const bodies = [];
  const h = harness(async (_, options) => { bodies.push(options.body); return reply({ok: false, error: 'unavailable'}, 503); });
  await h.run("feedPet('candy')"); await h.run("feedPet('candy')");
  assert.equal(bodies.length, 2); assert.equal(bodies[0], bodies[1]);
  assert.equal(h.c._petPendingLine, null);
  assert.match(h.messages.at(-1), /unconfirmed/);
});

test('legacy explicit HTTP rejection without ok is definitive and is not retried', async () => {
  let calls = 0;
  const h = harness(async () => { calls++; return reply({error: 'not authenticated'}, 401); });
  await h.run("feedPet('candy')");
  assert.equal(calls, 1);
  assert.equal(h.run('_petFeedPending'), null);
  assert.equal(h.messages.at(-1), 'not authenticated');
});

test('active spirit change during flight does not retarget the request or animate the new spirit', async () => {
  const request = deferred(), bodies = [];
  const h = harness(async (_, options) => { bodies.push(options.body); return request.promise; });
  const flight = h.run("feedPet('candy')");
  h.c._petState.pet.pet_key = 'whispering_void_kit';
  request.resolve(reply());
  await flight;
  assert.equal(JSON.parse(bodies[0]).spirit_id, 'ink_drop_kelpie');
  assert.equal(h.c._petState.pet.pet_key, 'whispering_void_kit');
  assert.equal(h.c._petPendingLine, null);
});

test('refresh failure releases lock after confirmed operation and keeps depleted food disabled', async () => {
  const h = harness(async () => reply());
  h.c.loadPetStatus = async () => { h.c._petState.inventory[0].qty = 0; throw new Error('refresh unavailable'); };
  await h.run("feedPet('candy')");
  assert.equal(h.run('_petFeedInFlight'), null);
  assert.equal(h.run('_petFeedPending'), null);
  assert.deepEqual(h.buttons.map(b => b.disabled), [true, false, true]);
});

test('missing active companion never sends a request', async () => {
  const h = harness(async () => { assert.fail('unexpected request'); });
  h.c._petState.pet = null;
  await h.run("feedPet('candy')");
});

test('fullness saturation explains consumption, XP and capped affection in both languages without disabling food', () => {
  const h = harness(async () => reply());
  h.run('renderPetCompanion()');
  assert.match(h.root.innerHTML, /consumes one food even at full fullness/);
  assert.match(h.root.innerHTML, /still grants XP and Bond \(Bond caps at 100\)/);
  assert.match(h.root.innerHTML, /data-pet-feed="candy"[^>]*onclick="feedPet\('candy'\)" >/);
  h.c.isEn = () => false;
  h.run('renderPetCompanion()');
  assert.match(h.root.innerHTML, /每次消耗 1 份食物/);
  assert.match(h.root.innerHTML, /仍獲得 XP 與親密度（親密度上限 100）/);
});
