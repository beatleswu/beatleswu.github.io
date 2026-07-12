/*
 * E9.1B adapter tests -- real Node execution of the actual adapter files
 * (js/e9/adapters/*.js), not source-level regex matching. Exits non-zero
 * with a printed failure list on any assertion failure, so pytest can
 * shell out to `node` and treat a non-zero exit as a real test failure.
 */
'use strict';

const path = require('path');
const assert = require('assert');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const PlayerState = require(path.join(REPO_ROOT, 'js', 'e9', 'adapters', 'player_state.js'));
const AdventureState = require(path.join(REPO_ROOT, 'js', 'e9', 'adapters', 'adventure_state.js'));
const ActivityState = require(path.join(REPO_ROOT, 'js', 'e9', 'adapters', 'activity_state.js'));

let failures = [];
let passCount = 0;

function test(name, fn) {
  try {
    fn();
    passCount++;
  } catch (err) {
    failures.push({ name: name, error: err.message || String(err) });
  }
}

function fakeFetch(responses) {
  // responses: array of {ok, status, body} consumed in call order
  let i = 0;
  return function fetchImpl() {
    if (i >= responses.length) throw new Error('fakeFetch: no more canned responses');
    const r = responses[i++];
    return Promise.resolve({
      ok: r.ok,
      status: r.status,
      json: function () { return Promise.resolve(r.body); },
    });
  };
}

async function testAsync(name, fn) {
  try {
    await fn();
    passCount++;
  } catch (err) {
    failures.push({ name: name, error: err.message || String(err) });
  }
}

// --- PlayerState.normalizeProfile -----------------------------------------
test('normalizeProfile: valid data', () => {
  const r = PlayerState.normalizeProfile({ display_name: 'test01', rank_level: 'LV12' });
  assert.strictEqual(r.name, 'test01');
  assert.strictEqual(r.level, 12);
});
test('normalizeProfile: missing display_name', () => {
  const r = PlayerState.normalizeProfile({ rank_level: 'LV5' });
  assert.strictEqual(r.name, null);
  assert.strictEqual(r.level, 5);
});
test('normalizeProfile: malformed rank_level (no digits)', () => {
  const r = PlayerState.normalizeProfile({ display_name: 'x', rank_level: 'LVabc' });
  assert.strictEqual(r.level, null);
});
test('normalizeProfile: negative level rejected', () => {
  const r = PlayerState.normalizeProfile({ display_name: 'x', rank_level: -5 });
  assert.strictEqual(r.level, null);
});
test('normalizeProfile: throws on non-object', () => {
  assert.throws(() => PlayerState.normalizeProfile(null));
  assert.throws(() => PlayerState.normalizeProfile('nope'));
});

// --- PlayerState.normalizeCoins --------------------------------------------
test('normalizeCoins: zero is valid data, not missing', () => {
  const r = PlayerState.normalizeCoins({ coins: 0 });
  assert.strictEqual(r.coins, 0);
});
test('normalizeCoins: missing coins distinguished from zero', () => {
  const r = PlayerState.normalizeCoins({});
  assert.strictEqual(r.coins, null);
});
test('normalizeCoins: negative rejected', () => {
  const r = PlayerState.normalizeCoins({ coins: -1 });
  assert.strictEqual(r.coins, null);
});
test('normalizeCoins: NaN rejected', () => {
  const r = PlayerState.normalizeCoins({ coins: NaN });
  assert.strictEqual(r.coins, null);
});
test('normalizeCoins: string coerced value rejected (must be real number type)', () => {
  const r = PlayerState.normalizeCoins({ coins: '500' });
  assert.strictEqual(r.coins, null);
});

// --- AdventureState.normalizeZone -------------------------------------------
test('normalizeZone: valid locked zone', () => {
  const z = AdventureState.normalizeZone({ key: 'k1', name: 'Zone 1', status: 'locked', stars: 0 });
  assert.strictEqual(z.locked, true);
  assert.strictEqual(z.cleared, false);
  assert.strictEqual(z.stars, 0);
});
test('normalizeZone: cleared zone with full stars', () => {
  const z = AdventureState.normalizeZone({ key: 'k1', name: 'Zone 1', status: 'completed', stars: 3, boss: { available: false } });
  assert.strictEqual(z.cleared, true);
  assert.strictEqual(z.stars, 3);
});
test('normalizeZone: stars clamped above range', () => {
  const z = AdventureState.normalizeZone({ key: 'k1', name: 'Z', status: 'unlocked', stars: 99 });
  assert.strictEqual(z.stars, 3);
});
test('normalizeZone: stars clamped below range (negative)', () => {
  const z = AdventureState.normalizeZone({ key: 'k1', name: 'Z', status: 'unlocked', stars: -5 });
  assert.strictEqual(z.stars, 0);
});
test('normalizeZone: invalid status dropped (returns null)', () => {
  const z = AdventureState.normalizeZone({ key: 'k1', name: 'Z', status: 'made_up_status' });
  assert.strictEqual(z, null);
});
test('normalizeZone: missing key dropped', () => {
  assert.strictEqual(AdventureState.normalizeZone({ name: 'Z', status: 'locked' }), null);
});
test('normalizeZone: missing name dropped', () => {
  assert.strictEqual(AdventureState.normalizeZone({ key: 'k1', status: 'locked' }), null);
});
test('normalizeZone: boss.available missing defaults to false, never fabricated true', () => {
  const z = AdventureState.normalizeZone({ key: 'k1', name: 'Z', status: 'unlocked' });
  assert.strictEqual(z.bossAvailable, false);
});
test('normalizeZones: drops invalid entries, keeps valid ones', () => {
  const r = AdventureState.normalizeZones({
    zones: [
      { key: 'k1', name: 'Good', status: 'locked' },
      { key: 'bad', name: 'Bad', status: 'nonsense' },
      { key: 'k2', name: 'Good2', status: 'completed', stars: 3 },
    ],
  });
  assert.strictEqual(r.zones.length, 2);
});
test('normalizeZones: throws on missing zones array', () => {
  assert.throws(() => AdventureState.normalizeZones({}));
});
test('normalizeZones: empty zones array is valid shape (caller decides criticality)', () => {
  const r = AdventureState.normalizeZones({ zones: [] });
  assert.strictEqual(r.zones.length, 0);
});

// --- ActivityState -----------------------------------------------------------
test('normalizeDailyChallenge: not submitted', () => {
  const r = ActivityState.normalizeDailyChallenge({ user_submitted: false });
  assert.strictEqual(r.submitted, false);
  assert.strictEqual(r.correct, null);
});
test('normalizeDailyChallenge: submitted and correct', () => {
  const r = ActivityState.normalizeDailyChallenge({ user_submitted: true, user_correct: true });
  assert.strictEqual(r.submitted, true);
  assert.strictEqual(r.correct, true);
});
test('normalizeBossProgress: counts completed zones', () => {
  const r = ActivityState.normalizeBossProgress({
    zones: [{ status: 'completed' }, { status: 'locked' }, { status: 'completed' }],
  });
  assert.strictEqual(r.cleared, 2);
  assert.strictEqual(r.total, 3);
});
test('normalizeSrsDue: zero is valid', () => {
  const r = ActivityState.normalizeSrsDue({ count: 0, due: [] });
  assert.strictEqual(r.count, 0);
});
test('normalizeSrsDue: missing distinguished from zero', () => {
  const r = ActivityState.normalizeSrsDue({});
  assert.strictEqual(r.count, null);
});
test('normalizeMistakes: zero is valid', () => {
  const r = ActivityState.normalizeMistakes({ total: 0 });
  assert.strictEqual(r.total, 0);
});
test('normalizeMistakes: negative rejected', () => {
  const r = ActivityState.normalizeMistakes({ total: -3 });
  assert.strictEqual(r.total, null);
});

// --- fetch-layer HTTP status classification (401/403/500/network) ---------
async function run() {
  await testAsync('fetchPlayerState: 401 classified as unauthorized', async () => {
    const fetchImpl = fakeFetch([{ ok: false, status: 401 }, { ok: true, status: 200, body: { coins: 0 } }]);
    const r = await PlayerState.fetchPlayerState(fetchImpl);
    assert.strictEqual(r.ok, false);
    assert.strictEqual(r.kind, 'unauthorized');
  });
  await testAsync('fetchPlayerState: 403 classified as unauthorized', async () => {
    const fetchImpl = fakeFetch([{ ok: false, status: 403 }, { ok: true, status: 200, body: { coins: 0 } }]);
    const r = await PlayerState.fetchPlayerState(fetchImpl);
    assert.strictEqual(r.kind, 'unauthorized');
  });
  await testAsync('fetchPlayerState: 500 classified as error', async () => {
    const fetchImpl = fakeFetch([{ ok: false, status: 500 }, { ok: true, status: 200, body: { coins: 0 } }]);
    const r = await PlayerState.fetchPlayerState(fetchImpl);
    assert.strictEqual(r.kind, 'error');
  });
  await testAsync('fetchPlayerState: success combines profile + coins', async () => {
    const fetchImpl = fakeFetch([
      { ok: true, status: 200, body: { display_name: 'test01', rank_level: 'LV8' } },
      { ok: true, status: 200, body: { coins: 250 } },
    ]);
    const r = await PlayerState.fetchPlayerState(fetchImpl);
    assert.strictEqual(r.ok, true);
    assert.strictEqual(r.data.name, 'test01');
    assert.strictEqual(r.data.level, 8);
    assert.strictEqual(r.data.coins, 250);
  });
  await testAsync('fetchAdventureState: network failure classified as network', async () => {
    const fetchImpl = function () { return Promise.reject(new Error('boom')); };
    const r = await AdventureState.fetchAdventureState(fetchImpl);
    assert.strictEqual(r.ok, false);
    assert.strictEqual(r.kind, 'network');
  });
  await testAsync('fetchAdventureState: malformed JSON body (missing zones) yields error result, not throw', async () => {
    const fetchImpl = fakeFetch([{ ok: true, status: 200, body: { not_zones: [] } }]);
    const r = await AdventureState.fetchAdventureState(fetchImpl);
    assert.strictEqual(r.ok, false);
    assert.strictEqual(r.kind, 'network'); // normalize() throw is caught by the outer .catch
  });
  await testAsync('fetchDailyChallenge: 401 unauthorized', async () => {
    const fetchImpl = fakeFetch([{ ok: false, status: 401 }]);
    const r = await ActivityState.fetchDailyChallenge(fetchImpl);
    assert.strictEqual(r.kind, 'unauthorized');
  });

  if (failures.length) {
    console.error('FAILURES:');
    failures.forEach(f => console.error(`  - ${f.name}: ${f.error}`));
    console.error(`\n${passCount} passed, ${failures.length} failed`);
    process.exit(1);
  } else {
    console.log(`${passCount} passed, 0 failed`);
    process.exit(0);
  }
}

run();
