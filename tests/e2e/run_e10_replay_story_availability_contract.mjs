/**
 * Executable contract for the shared Replay Story availability predicate
 * (E10_REPLAY_STORY_CROSS_SURFACE_IPAD_HOTFIX_002A).
 *
 * The Owner's product rule, verbatim:
 *
 *   zoneReplayStoryAvailable(zoneKey, zoneRecord) must require
 *     1. zoneRecord is authoritative
 *     2. zoneRecord.locked != true
 *     3. zoneRecord.cleared == true
 *     4. canonical replayable unlocked segment count > 0
 *
 * This runs the real function out of js/e9/world_stage.js against synthetic
 * authoritative records, so the four conditions are asserted by execution
 * rather than by matching source text. It covers the combinations a seeded
 * fixture cannot always produce -- notably "cleared zone that declares no
 * replayable segments", which no current zone is.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..', '..');
const SOURCE = readFileSync(resolve(ROOT, 'js', 'e9', 'world_stage.js'), 'utf8');

function block(startMarker, endMarker) {
  const start = SOURCE.indexOf(startMarker);
  const end = SOURCE.indexOf(endMarker, start);
  if (start < 0 || end < 0) throw new Error(`source block not found: ${startMarker}`);
  return SOURCE.slice(start, end);
}

const logic = block(
  'function zoneStoryReplayAvailable(zoneKey, zoneRecord) {',
  '  // Replays every legitimately unlocked segment'
);

// Segment truth is the canonical model's job, so it is stubbed here to a
// simple set: this contract is about the predicate's own four conditions.
const REPLAYABLE = new Set(['k26_30', 'k21_25']);

function makeSandbox({ withModel = true, throwing = false } = {}) {
  const sandbox = {
    console,
    window: {
      E10Cinematic: withModel
        ? {
            hasReplayableStory(zoneKey) {
              if (throwing) throw new Error('model exploded');
              return REPLAYABLE.has(zoneKey);
            },
          }
        : undefined,
    },
  };
  vm.createContext(sandbox);
  new vm.Script(logic).runInContext(sandbox);
  return sandbox;
}

const checks = [];
function check(name, actual, expected) {
  const pass = actual === expected;
  checks.push({ name, actual, expected, pass });
}

const box = makeSandbox();
const call = (key, record) => box.zoneStoryReplayAvailable(key, record);

const cleared = (key) => ({ key, locked: false, cleared: true });
const unlockedNotCleared = (key) => ({ key, locked: false, cleared: false });
const locked = (key) => ({ key, locked: true, cleared: false });
// A locked zone that is somehow also flagged cleared must still be refused:
// rule 2 is not subordinate to rule 3.
const lockedButCleared = (key) => ({ key, locked: true, cleared: true });

// ---- positive: all four conditions satisfied --------------------------------
check('zone1 cleared + replayable', call('k26_30', cleared('k26_30')), true);
check('zone2 cleared + replayable', call('k21_25', cleared('k21_25')), true);

// ---- rule 3: cleared is REQUIRED -------------------------------------------
check('unlocked but not cleared is refused',
  call('k26_30', unlockedNotCleared('k26_30')), false);
check('missing cleared field is refused',
  call('k26_30', { key: 'k26_30', locked: false }), false);
check('cleared must be strictly true, not truthy',
  call('k26_30', { key: 'k26_30', locked: false, cleared: 1 }), false);

// ---- rule 2: locked is refused --------------------------------------------
check('locked zone is refused', call('k16_20', locked('k16_20')), false);
check('locked wins over cleared', call('k26_30', lockedButCleared('k26_30')), false);

// ---- rule 4: canonical replayable segments required ------------------------
check('cleared zone with no replayable segments is refused',
  call('k16_20', cleared('k16_20')), false);

// ---- rule 1: an authoritative record is required (fail closed) -------------
check('no record and no resolvable state is refused', call('k26_30', null), false);
check('undefined record is refused', call('k26_30', undefined), false);
check('empty zone key is refused', call('', cleared('k26_30')), false);

// ---- fail closed when the question cannot be answered ----------------------
const noModel = makeSandbox({ withModel: false });
check('no cinematic model is refused (no identity guessing)',
  noModel.zoneStoryReplayAvailable('k26_30', cleared('k26_30')), false);

const throwing = makeSandbox({ throwing: true });
check('throwing model is refused',
  throwing.zoneStoryReplayAvailable('k26_30', cleared('k26_30')), false);

// ---- the predicate must not be keyed on zone identity ----------------------
// A synthetic zone key that no allowlist could know about still works when it
// satisfies all four conditions.
REPLAYABLE.add('zone_that_did_not_exist_before');
check('unknown-but-eligible zone is allowed (no allowlist)',
  call('zone_that_did_not_exist_before', cleared('zone_that_did_not_exist_before')), true);

const failures = checks.filter((entry) => !entry.pass);
for (const entry of failures) {
  console.error(`FAIL ${entry.name}: expected ${entry.expected}, got ${entry.actual}`);
}
console.log(JSON.stringify({
  status: failures.length ? 'FAIL' : 'PASS',
  checks: checks.length,
  failures: failures.length,
  detail: checks,
}, null, 2));
process.exit(failures.length ? 1 : 0);
