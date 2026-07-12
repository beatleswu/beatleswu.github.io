/*
 * RELEASE-FIX-B -- real Node execution of js/e9/i18n_fallback.js (the
 * shared E9 missing-key fallback helper), not source-level regex matching.
 * Exits non-zero with a printed failure list on any assertion failure, so
 * pytest can shell out to `node` and treat a non-zero exit as a real
 * test failure.
 */
'use strict';

const path = require('path');
const assert = require('assert');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const I18nFallback = require(path.join(REPO_ROOT, 'js', 'e9', 'i18n_fallback.js'));

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

// Minimal fake global.I18n objects standing in for the real i18n.js
// runtime, mirroring its actual documented behavior: t(key) returns the
// key itself when missing, the translated string otherwise.
function fakeI18nWithDict(dict) {
  return {
    t: function (key) {
      return Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : key;
    },
  };
}

// --- 1. real translation is returned unchanged -----------------------------
test('returns the real translated value when the key exists', () => {
  global.I18n = fakeI18nWithDict({ 'e9.top_hud.error': 'Player status unavailable' });
  const r = I18nFallback.t('e9.top_hud.error', 'FALLBACK');
  assert.strictEqual(r, 'Player status unavailable');
});

// --- 2. missing key (I18n.t returns the key itself) falls through ----------
test('missing key (I18n.t returns key) falls back, never the raw key', () => {
  global.I18n = fakeI18nWithDict({}); // dictionary empty -- t() returns key
  const r = I18nFallback.t('e9.top_hud.error', 'Player status unavailable');
  assert.strictEqual(r, 'Player status unavailable');
  assert.notStrictEqual(r, 'e9.top_hud.error');
});

// --- 3. empty/null/undefined result falls back ------------------------------
test('empty string result falls back', () => {
  global.I18n = fakeI18nWithDict({ 'k': '' });
  assert.strictEqual(I18nFallback.t('k', 'FB'), 'FB');
});
test('null result falls back', () => {
  global.I18n = { t: function () { return null; } };
  assert.strictEqual(I18nFallback.t('k', 'FB'), 'FB');
});
test('undefined result falls back', () => {
  global.I18n = { t: function () { return undefined; } };
  assert.strictEqual(I18nFallback.t('k', 'FB'), 'FB');
});

// --- 4. I18n unavailable falls back -----------------------------------------
test('window.I18n missing entirely falls back', () => {
  global.I18n = undefined;
  assert.strictEqual(I18nFallback.t('k', 'FB'), 'FB');
});
test('window.I18n.t not a function falls back', () => {
  global.I18n = { t: 'not-a-function' };
  assert.strictEqual(I18nFallback.t('k', 'FB'), 'FB');
});

// --- 5. I18n.t() throwing falls back safely, never an uncaught error -------
test('I18n.t() throwing is caught and falls back', () => {
  global.I18n = { t: function () { throw new Error('boom'); } };
  assert.doesNotThrow(() => {
    assert.strictEqual(I18nFallback.t('k', 'FB'), 'FB');
  });
});

// --- 6. valid "0"-like / falsy-but-real text is NOT treated as missing -----
test('a real translated value of "0" is returned, not treated as missing', () => {
  global.I18n = fakeI18nWithDict({ 'e9.right_cards.srs_due_count': '0' });
  assert.strictEqual(I18nFallback.t('e9.right_cards.srs_due_count', 'FB'), '0');
});

// --- 7. translated text that happens to equal the fallback text is valid --
test('translated text coincidentally equal to fallback is still returned as translated', () => {
  global.I18n = fakeI18nWithDict({ 'e9.right_cards.error': 'Unavailable' });
  assert.strictEqual(I18nFallback.t('e9.right_cards.error', 'Unavailable'), 'Unavailable');
});

// --- Raw-key-prevention: every real E9 call site pattern, forced missing --
const REAL_E9_CALL_SITES = [
  ['e9.top_hud.error', 'Player status unavailable'],
  ['e9.top_hud.unauthorized', 'Please log in again'],
  ['e9.right_cards.error', 'Unavailable'],
  ['e9.right_cards.unauthorized', 'Please log in again'],
  ['e9.right_cards.empty', 'No data yet'],
  ['e9.right_cards.daily_challenge_done', 'Completed today'],
  ['e9.right_cards.daily_challenge_available', 'Available now'],
  ['index.adv.summary', '{n} / {t} areas cleared'],
  ['index.adv.zone_locked', 'This area is still sealed by mist.'],
  ['index.adv.boss_ready', 'Seal broken'],
  ['e9.shell.critical_error', 'A critical error occurred. Returning to Adventure Map.'],
];
REAL_E9_CALL_SITES.forEach(([key, fallback]) => {
  test(`raw-key-prevention: "${key}" missing never leaks the key itself`, () => {
    global.I18n = fakeI18nWithDict({}); // simulate every key missing
    const r = I18nFallback.t(key, fallback);
    assert.strictEqual(r, fallback);
    assert.notStrictEqual(r, key);
  });
});

// --- interpolation contract: fallback text keeps {n}/{t} placeholders for
// the caller's own .replace() chaining (right_cards.js / world_stage.js) --
test('fallback text preserves {n}/{t} placeholders for caller-side .replace()', () => {
  global.I18n = fakeI18nWithDict({});
  const r = I18nFallback.t('index.adv.summary', '{n} / {t} areas cleared').replace('{n}', 3).replace('{t}', 8);
  assert.strictEqual(r, '3 / 8 areas cleared');
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
