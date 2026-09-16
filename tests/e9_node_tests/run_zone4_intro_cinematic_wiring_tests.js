'use strict';

/**
 * POST007C_008 Lane A — Zone4 intro cinematic wiring regression.
 *
 * Background: the Owner UAT reported that Zone4's intro cinematic never plays.
 * The cause was in js/e9/world_stage.js: introCinematicKeyForZone() mapped only
 * Zones 1-3, so Zone4 ('k11_15') fell through to null and the journey never
 * asked the cinematic host to mount anything. Production telemetry confirmed
 * e10_zone4_intro_v1 had never fired for any account.
 *
 * These tests execute the real functions extracted from world_stage.js rather
 * than substring-matching the source, so they assert behaviour and not spelling.
 *
 * FAILS against the pre-hotfix baseline on two independent assertions:
 *   1. introCinematicKeyForZone('k11_15') returned null.
 *   2. introEntryInFlightKey('k11_15') returned 'zone2EntryInFlight' via the
 *      trailing fallback, colliding with Zone2's re-entrancy guard.
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const WORLD_STAGE_JS = path.join(REPO_ROOT, 'js', 'e9', 'world_stage.js');

const source = fs.readFileSync(WORLD_STAGE_JS, 'utf8');

function extract(pattern, label) {
  const match = source.match(pattern);
  assert.ok(match, `could not extract ${label} from world_stage.js`);
  return match[0];
}

// Pull the two functions and the constants they close over into an isolated
// sandbox. world_stage.js as a whole needs a browser; these functions do not.
const sandboxSource = [
  extract(/var ACTIVE_INTRO_ZONE_KEY = '[^']*';/, 'ACTIVE_INTRO_ZONE_KEY'),
  extract(/var ACTIVE_INTRO_CINEMATIC_KEY = '[^']*';/, 'ACTIVE_INTRO_CINEMATIC_KEY'),
  extract(/function introCinematicKeyForZone\(zoneKey\) \{[\s\S]*?\n  \}/, 'introCinematicKeyForZone'),
  extract(/function introEntryInFlightKey\(zoneKey\) \{[\s\S]*?\n  \}/, 'introEntryInFlightKey'),
].join('\n');

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(sandboxSource, sandbox);

const introCinematicKeyForZone = sandbox.introCinematicKeyForZone;
const introEntryInFlightKey = sandbox.introEntryInFlightKey;

const tests = [];
function test(name, fn) { tests.push([name, fn]); }

// The zones that are player-reachable and have a wired first-entry cinematic.
const WIRED_ZONES = [
  ['k26_30', 'e10_zone1_intro_v1', 'zone1EntryInFlight'],
  ['k21_25', 'e10_zone2_intro_v1', 'zone2EntryInFlight'],
  ['k16_20', 'e10_zone3_intro_v1', 'zone3EntryInFlight'],
  ['k11_15', 'e10_zone4_intro_v1', 'zone4EntryInFlight'],
];

test('Zone4 resolves to its own intro cinematic key', () => {
  // The regression the Owner UAT caught. Pre-hotfix this was null.
  assert.strictEqual(introCinematicKeyForZone('k11_15'), 'e10_zone4_intro_v1');
});

test('Zone4 has a dedicated in-flight guard, not Zone2\'s fallback', () => {
  // introEntryInFlightKey's trailing fallback returns 'zone2EntryInFlight'.
  // If Zone4 gained a cinematic key but not an in-flight key, Zone2 and Zone4
  // would share one re-entrancy guard and suppress each other's first entry.
  assert.strictEqual(introEntryInFlightKey('k11_15'), 'zone4EntryInFlight');
  assert.notStrictEqual(introEntryInFlightKey('k11_15'), introEntryInFlightKey('k21_25'));
});

test('Zones 1-3 intro wiring is unchanged', () => {
  for (const [zoneKey, cinematicKey, inFlightKey] of WIRED_ZONES.slice(0, 3)) {
    assert.strictEqual(introCinematicKeyForZone(zoneKey), cinematicKey, zoneKey);
    assert.strictEqual(introEntryInFlightKey(zoneKey), inFlightKey, zoneKey);
  }
});

test('every wired zone has a distinct cinematic key and in-flight guard', () => {
  const cinematicKeys = new Set();
  const inFlightKeys = new Set();
  for (const [zoneKey, cinematicKey, inFlightKey] of WIRED_ZONES) {
    assert.strictEqual(introCinematicKeyForZone(zoneKey), cinematicKey, zoneKey);
    assert.strictEqual(introEntryInFlightKey(zoneKey), inFlightKey, zoneKey);
    cinematicKeys.add(cinematicKey);
    inFlightKeys.add(inFlightKey);
  }
  assert.strictEqual(cinematicKeys.size, WIRED_ZONES.length, 'duplicate cinematic key');
  assert.strictEqual(inFlightKeys.size, WIRED_ZONES.length, 'duplicate in-flight guard');
});

test('Zone5 and beyond remain deliberately unwired', () => {
  // POST007C_008 is a bounded Zone4 hotfix: Zone5 must stay untouched. This is
  // why the mapping was NOT replaced with a generic `e10_zone${n}_intro_v1`
  // derivation -- that would silently enable Zones 5-10 whose assets and story
  // locks have not been accepted.
  for (const zoneKey of ['k6_10', 'k1_5', 'd1_2', 'd3_4']) {
    assert.strictEqual(introCinematicKeyForZone(zoneKey), null, zoneKey);
  }
});

test('an unknown zone key does not resolve to a cinematic', () => {
  assert.strictEqual(introCinematicKeyForZone('not_a_zone'), null);
  assert.strictEqual(introCinematicKeyForZone(''), null);
  assert.strictEqual(introCinematicKeyForZone(undefined), null);
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log(`ok   - ${name}`);
  } catch (err) {
    failed += 1;
    console.log(`FAIL - ${name}`);
    console.log(`       ${err.message}`);
  }
}
console.log(`\n${tests.length - failed}/${tests.length} passed`);
process.exit(failed === 0 ? 0 : 1);
