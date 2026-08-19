'use strict';

// Executable contract for the Zone 1-10 generic cinematic replay model
// (E10_ZONE_GENERIC_CINEMATIC_REPLAY_001).
//
// Exercises js/game/cinematic_replay.js directly, with no DOM and no zone
// identity anywhere in the module under test: every zone here is a plain
// fixture that declares segments and authoritative state. The Zone 1 / Zone 2
// cases and the synthetic five-phase future zone all run through the same code
// path -- that is the point of the proof.

import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const MODULE_SOURCE = await fs.readFile(path.join(ROOT, 'js', 'game', 'cinematic_replay.js'), 'utf8');

function loadModule() {
  const window = {};
  const context = vm.createContext({
    window,
    console,
    Object,
    Array,
    Number,
    String,
    Boolean,
    JSON,
    Error,
    TypeError,
    Set,
    Map,
    Math,
  });
  vm.runInContext(MODULE_SOURCE, context);
  return window.GoOdysseyCinematicReplay;
}

const CinematicReplay = loadModule();

const shots = (n, tag) => Array.from({ length: n }, (_, i) => ({ shot: `${tag}${i + 1}` }));

// Zone 1 / Zone 2 shaped: FIRST_ENTRY -> BOSS_READY -> POST_CLEAR.
const THREE_ACT = {
  pre_play: shots(6, 'entry'),
  boss_ready: shots(2, 'boss'),
  post_clear: shots(2, 'post'),
};

// A future zone whose lifecycle is deliberately NOT three acts.
const FIVE_PHASE = {
  pre_play: shots(3, 'entry'),
  mid_play: shots(2, 'mid'),
  boss_ready: shots(2, 'boss'),
  post_clear: shots(3, 'post'),
  ending: shots(2, 'end'),
};

function modelFor(segmentsByZone, seenByZone = {}) {
  return CinematicReplay.create({
    getSegments: zone => segmentsByZone[zone.key] || {},
    isCleared: zone => zone.cleared === true,
    isBossReady: zone => zone.bossReady === true,
    canEnter: zone => zone.canEnter === true,
    hasSeen: (zone, phase) => !!(seenByZone[zone.key] || {})[phase],
  });
}

// Array.from() rebuilds in THIS realm: the module runs inside a vm context,
// so its arrays carry that context's Array prototype and would fail a strict
// deepEqual against a host-realm literal for reasons unrelated to the model.
const phasesOf = segments => Array.from(segments, segment => segment.phase);

const checks = [];
function check(name, fn) {
  checks.push({ name, fn });
}

check('canonical order is lifecycle order, not declaration order', () => {
  const model = modelFor({
    z: {
      ending: shots(1, 'end'),
      pre_play: shots(1, 'entry'),
      post_clear: shots(1, 'post'),
      boss_ready: shots(1, 'boss'),
      mid_play: shots(1, 'mid'),
    },
  });
  const zone = { key: 'z', cleared: true, canEnter: true };
  assert.deepEqual(phasesOf(model.replaySequence(zone)), [
    'pre_play',
    'mid_play',
    'boss_ready',
    'post_clear',
    'ending',
  ]);
});

check('zone declaring no segments has no replayable story', () => {
  const model = modelFor({});
  const zone = { key: 'k16_20', canEnter: true, cleared: true };
  assert.equal(model.hasReplayableStory(zone), false);
  assert.equal(model.replaySequence(zone).length, 0);
  assert.equal(model.postVictorySequence(zone).length, 0);
});

check('empty timelines are not segments', () => {
  const model = modelFor({ z: { pre_play: [], post_clear: shots(1, 'post') } });
  const zone = { key: 'z', canEnter: true, cleared: true };
  assert.deepEqual(phasesOf(model.replaySequence(zone)), ['post_clear']);
});

check('intro-only player replays FIRST_ENTRY only', () => {
  const model = modelFor({ z: THREE_ACT });
  const zone = { key: 'z', canEnter: true, bossReady: false, cleared: false };
  assert.deepEqual(phasesOf(model.replaySequence(zone)), ['pre_play']);
  assert.equal(model.postVictorySequence(zone).length, 0);
});

check('boss-ready but uncleared player replays FIRST_ENTRY + BOSS_READY only', () => {
  const model = modelFor({ z: THREE_ACT });
  const zone = { key: 'z', canEnter: true, bossReady: true, cleared: false };
  assert.deepEqual(phasesOf(model.replaySequence(zone)), ['pre_play', 'boss_ready']);
  assert.equal(model.postVictorySequence(zone).length, 0);
});

check('cleared player replays the whole unlocked timeline', () => {
  const model = modelFor({ z: THREE_ACT });
  const zone = { key: 'z', canEnter: true, bossReady: false, cleared: true };
  assert.deepEqual(phasesOf(model.replaySequence(zone)), ['pre_play', 'boss_ready', 'post_clear']);
});

check('clearing a zone does not revoke BOSS_READY even though isBossReady goes false', () => {
  // The real _adventureBossReady returns false once a zone is cleared. A
  // cleared player has necessarily passed boss-ready, so the segment must stay
  // unlocked -- this is the regression that would silently shorten every
  // cleared zone's replay.
  const model = modelFor({ z: THREE_ACT });
  const cleared = { key: 'z', canEnter: false, bossReady: false, cleared: true };
  assert.ok(phasesOf(model.replaySequence(cleared)).includes('boss_ready'));
  assert.ok(phasesOf(model.replaySequence(cleared)).includes('pre_play'));
});

check('POST_CLEAR never unlocks from a seen marker alone', () => {
  // A rolled-back / wiped clear must not leave the ending reachable.
  const model = modelFor({ z: THREE_ACT }, { z: { post_clear: true, ending: true } });
  const zone = { key: 'z', canEnter: true, bossReady: true, cleared: false };
  assert.deepEqual(phasesOf(model.replaySequence(zone)), ['pre_play', 'boss_ready']);
});

check('client cannot self-declare a clear', () => {
  // isCleared reads the server field; a client-shaped hint is ignored.
  const model = CinematicReplay.create({
    getSegments: () => THREE_ACT,
    isCleared: zone => zone.cleared === true,
    isBossReady: () => false,
    canEnter: () => true,
    hasSeen: () => false,
  });
  const lying = { key: 'z', cleared: false, replay: true, post_clear_allowed: true, client_cleared: true };
  assert.deepEqual(phasesOf(model.replaySequence(lying)), ['pre_play']);
});

check('five-phase future zone needs no zone-specific branch', () => {
  const model = modelFor({ future: FIVE_PHASE });
  const intro = { key: 'future', canEnter: true, bossReady: false, cleared: false };
  const mid = { key: 'future', canEnter: true, bossReady: false, cleared: false };
  const ready = { key: 'future', canEnter: true, bossReady: true, cleared: false };
  const cleared = { key: 'future', canEnter: true, bossReady: false, cleared: true };

  assert.deepEqual(phasesOf(model.replaySequence(intro)), ['pre_play']);
  assert.deepEqual(phasesOf(model.replaySequence(ready)), ['pre_play', 'mid_play', 'boss_ready']);
  assert.deepEqual(phasesOf(model.replaySequence(cleared)), [
    'pre_play',
    'mid_play',
    'boss_ready',
    'post_clear',
    'ending',
  ]);
  // MID_PLAY is replayable purely as cinematic once legitimately reached.
  const seenMid = modelFor({ future: FIVE_PHASE }, { future: { mid_play: true } });
  assert.deepEqual(phasesOf(seenMid.replaySequence(mid)), ['pre_play', 'mid_play']);
});

check('post-victory tail is POST_CLEAR onward, including later phases', () => {
  const model = modelFor({ future: FIVE_PHASE });
  const cleared = { key: 'future', canEnter: true, cleared: true };
  assert.deepEqual(phasesOf(model.postVictorySequence(cleared)), ['post_clear', 'ending']);
  // and never leaks a pre-victory phase
  const tail = Array.from(model.postVictorySequence(cleared));
  const postClearIndex = Array.from(CinematicReplay.SEGMENT_ORDER).indexOf('post_clear');
  assert.ok(tail.every(segment => segment.order >= postClearIndex));
});

check('a segment may declare its own unlock condition', () => {
  const model = CinematicReplay.create({
    getSegments: () => ({
      pre_play: shots(1, 'entry'),
      mid_play: { timeline: shots(1, 'mid'), unlock: zone => zone.chapter >= 2 },
    }),
    isCleared: () => false,
    isBossReady: () => false,
    canEnter: () => true,
    hasSeen: () => false,
  });
  assert.deepEqual(phasesOf(model.replaySequence({ key: 'z', chapter: 1 })), ['pre_play']);
  assert.deepEqual(phasesOf(model.replaySequence({ key: 'z', chapter: 2 })), ['pre_play', 'mid_play']);
});

check('a segment may opt out of replay while staying unlocked', () => {
  const model = CinematicReplay.create({
    getSegments: () => ({
      pre_play: shots(1, 'entry'),
      post_clear: { timeline: shots(1, 'post'), replayEligible: false },
    }),
    isCleared: () => true,
    isBossReady: () => false,
    canEnter: () => true,
    hasSeen: () => false,
  });
  const zone = { key: 'z' };
  assert.deepEqual(phasesOf(model.unlockedSegments(zone)), ['pre_play', 'post_clear']);
  assert.deepEqual(phasesOf(model.replaySequence(zone)), ['pre_play']);
});

check('throwing dependencies fail closed rather than unlocking', () => {
  const model = CinematicReplay.create({
    getSegments: () => THREE_ACT,
    isCleared: () => { throw new Error('boom'); },
    isBossReady: () => { throw new Error('boom'); },
    canEnter: () => { throw new Error('boom'); },
    hasSeen: () => { throw new Error('boom'); },
  });
  assert.equal(model.replaySequence({ key: 'z' }).length, 0);
});

check('segment descriptors expose identity, order and lifecycle phase', () => {
  const model = modelFor({ z: THREE_ACT });
  const segments = Array.from(model.segmentsForZone({ key: 'z', canEnter: true, cleared: true }));
  const post = segments.find(segment => segment.phase === 'post_clear');
  assert.equal(post.id, 'post_clear');
  assert.equal(post.lifecycle, 'POST_CLEAR');
  assert.equal(post.order, Array.from(CinematicReplay.SEGMENT_ORDER).indexOf('post_clear'));
  assert.equal(post.unlocked, true);
  assert.equal(post.replayEligible, true);
  assert.equal(post.timeline.length, 2);
});

const results = [];
let failures = 0;
for (const { name, fn } of checks) {
  try {
    fn();
    results.push({ name, status: 'PASS' });
  } catch (error) {
    failures += 1;
    results.push({ name, status: 'FAIL', error: String(error && error.message ? error.message : error) });
    console.error(`FAIL: ${name}\n${error && error.stack ? error.stack : error}`);
  }
}

const report = {
  task: 'E10_ZONE_GENERIC_CINEMATIC_REPLAY_001',
  checks: results.length,
  failures,
  results,
  status: failures === 0 ? 'PASS' : 'FAIL',
};
console.log(JSON.stringify(report, null, 2));
if (failures > 0) process.exit(1);
