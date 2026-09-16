'use strict';

/**
 * P0 Lane A -- Zone4 intro cinematic wiring regression.
 *
 * This harness executes the real mapping functions extracted from
 * js/e9/world_stage.js. It intentionally does not pass when the source is
 * only changed textually: the asserted values are the functions' runtime
 * results.
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const repoRoot = path.resolve(__dirname, '..', '..');
const worldStagePath = path.join(repoRoot, 'js', 'e9', 'world_stage.js');
const source = fs.readFileSync(worldStagePath, 'utf8');

function extract(pattern, label) {
  const match = source.match(pattern);
  assert.ok(match, 'could not extract ' + label + ' from world_stage.js');
  return match[0];
}

// world_stage.js is a browser IIFE. These two pure mapping functions and
// their constants can be executed in a small VM without booting a browser or
// replacing any application state.
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

function test(name, fn) {
  tests.push([name, fn]);
}

test('Zone4 resolves to its approved cinematic key', () => {
  assert.strictEqual(introCinematicKeyForZone('k11_15'), 'e10_zone4_intro_v1');
});

test('Zone4 resolves to a dedicated in-flight guard', () => {
  assert.strictEqual(introEntryInFlightKey('k11_15'), 'zone4EntryInFlight');
  assert.notStrictEqual(
    introEntryInFlightKey('k11_15'),
    introEntryInFlightKey('k21_25')
  );
});

test('Zones 1-3 retain their existing mappings', () => {
  const expected = [
    ['k26_30', 'e10_zone1_intro_v1', 'zone1EntryInFlight'],
    ['k21_25', 'e10_zone2_intro_v1', 'zone2EntryInFlight'],
    ['k16_20', 'e10_zone3_intro_v1', 'zone3EntryInFlight'],
  ];
  expected.forEach(([zoneKey, cinematicKey, guardKey]) => {
    assert.strictEqual(introCinematicKeyForZone(zoneKey), cinematicKey, zoneKey);
    assert.strictEqual(introEntryInFlightKey(zoneKey), guardKey, zoneKey);
  });
});

test('all wired zones have distinct cinematic keys and guards', () => {
  const wired = [
    ['k26_30', 'e10_zone1_intro_v1', 'zone1EntryInFlight'],
    ['k21_25', 'e10_zone2_intro_v1', 'zone2EntryInFlight'],
    ['k16_20', 'e10_zone3_intro_v1', 'zone3EntryInFlight'],
    ['k11_15', 'e10_zone4_intro_v1', 'zone4EntryInFlight'],
  ];
  const cinematicKeys = new Set();
  const guardKeys = new Set();
  wired.forEach(([zoneKey, cinematicKey, guardKey]) => {
    assert.strictEqual(introCinematicKeyForZone(zoneKey), cinematicKey, zoneKey);
    assert.strictEqual(introEntryInFlightKey(zoneKey), guardKey, zoneKey);
    cinematicKeys.add(cinematicKey);
    guardKeys.add(guardKey);
  });
  assert.strictEqual(cinematicKeys.size, wired.length);
  assert.strictEqual(guardKeys.size, wired.length);
});

test('Zone5 and later remain deliberately unwired', () => {
  ['k6_10', 'k1_5', 'd1_2', 'd3_4'].forEach((zoneKey) => {
    assert.strictEqual(introCinematicKeyForZone(zoneKey), null, zoneKey);
  });
});

test('unknown zone keys remain unwired', () => {
  [undefined, '', 'not_a_zone'].forEach((zoneKey) => {
    assert.strictEqual(introCinematicKeyForZone(zoneKey), null, String(zoneKey));
  });
});

let failed = 0;
tests.forEach(([name, fn]) => {
  try {
    fn();
    console.log('ok   - ' + name);
  } catch (error) {
    failed += 1;
    console.log('FAIL - ' + name);
    console.log('       ' + error.message);
  }
});
console.log('');
console.log((tests.length - failed) + '/' + tests.length + ' passed');
process.exit(failed === 0 ? 0 : 1);
