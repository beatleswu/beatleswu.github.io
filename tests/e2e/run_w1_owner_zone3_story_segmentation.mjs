/*
 * W1-OWNER-POSTDEPLOY-ACCEPTANCE-CORRECTIVE-FINAL-001, Issue B.
 *
 * Behavioral harness for the Zone 3 story lifecycle gate. It evaluates the
 * REAL showZone3EntrySafeFallback / _continueZone3SafeEntry bodies extracted
 * from index.html against stubbed presentation and authority surfaces, so the
 * Owner's acceptance matrix is answered by running the shipped code rather
 * than by reading it.
 *
 * Nothing here talks to a server: every authority fact (seen markers, cleared,
 * Lord-ready) is injected, which is exactly the point -- the gate must be a
 * pure function of authoritative facts plus the entry mode.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const indexSource = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');

function extractFunction(source, name) {
  const marker = `function ${name}(`;
  const at = source.indexOf(marker);
  assert.notEqual(at, -1, `missing ${name}`);
  // Keep an `async` prefix, or an extracted body's `await` will not parse.
  const lineStart = source.lastIndexOf('\n', at) + 1;
  const start = source.slice(lineStart, at).trim() === 'async' ? lineStart : at;
  // Skip the parameter list before looking for the body brace: a default such
  // as `options = {}` would otherwise be mistaken for a zero-length body.
  let parenDepth = 0;
  let signatureEnd = source.indexOf('(', at);
  for (let index = signatureEnd; index < source.length; index += 1) {
    if (source[index] === '(') parenDepth += 1;
    else if (source[index] === ')') {
      parenDepth -= 1;
      if (parenDepth === 0) { signatureEnd = index; break; }
    }
  }
  const opening = source.indexOf('{', signatureEnd);
  let depth = 0;
  let quote = null;
  let escaped = false;
  let comment = null; // 'line' | 'block'
  for (let index = opening; index < source.length; index += 1) {
    const char = source[index];
    if (comment === 'line') {
      if (char === '\n') comment = null;
      continue;
    }
    if (comment === 'block') {
      if (char === '*' && source[index + 1] === '/') { comment = null; index += 1; }
      continue;
    }
    if (quote) {
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === quote) quote = null;
      continue;
    }
    // Comments must be skipped, not scanned: an ordinary English apostrophe in
    // a prose comment would otherwise open a string and desynchronise the brace
    // depth, silently returning a body that runs past its own closing brace.
    if (char === '/' && source[index + 1] === '/') { comment = 'line'; index += 1; continue; }
    if (char === '/' && source[index + 1] === '*') { comment = 'block'; index += 1; continue; }
    if (char === "'" || char === '"' || char === '`') quote = char;
    else if (char === '{') depth += 1;
    else if (char === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  throw new Error(`unterminated ${name}`);
}

const ZONE3 = 'k16_20';

/**
 * One entry attempt. `facts` are the authoritative inputs; the result records
 * every observable effect the gate can have.
 */
async function enterZone3({ mode = 'legacy', seen = {}, cleared = false, manifestShots = 10, firstEntryShots = 5 } = {}) {
  const trace = [];
  const elements = new Map();
  const makeEl = id => ({
    id,
    dataset: {},
    className: '',
    style: {},
    hidden: false,
    textContent: '',
    innerHTML: '',
    disabled: false,
    onclick: null,
    classList: {
      _set: new Set(),
      add(...c) { c.forEach(x => this._set.add(x)); },
      remove(...c) { c.forEach(x => this._set.delete(x)); },
      contains(c) { return this._set.has(c); },
    },
    setAttribute(name, value) { this[`attr:${name}`] = value; },
  });
  for (const id of [
    'boss-cinematic', 'boss-cinematic-kicker', 'boss-cinematic-monster',
    'boss-cinematic-title', 'boss-cinematic-books', 'boss-cinematic-line',
    'boss-cinematic-rules', 'boss-cinematic-btn', 'boss-cinematic-progress',
    'boss-cinematic-cancel-btn', 'intro-film-stage',
  ]) elements.set(id, makeEl(id));

  const shots = Array.from({ length: manifestShots }, (_, i) => ({
    shotNumber: i + 1,
    phase: i < 5 ? 'FIRST_ENTRY' : i < 7 ? 'BOSS_READY' : 'POST_CLEAR',
  }));

  const sandbox = {
    console,
    setTimeout,
    clearTimeout,
    document: {
      getElementById: id => elements.get(id) || null,
      documentElement: { dataset: {} },
    },
    window: {
      location: { href: '' },
      E9: { showAdventureZoneCard: key => trace.push('ZONE_CARD:' + key) },
    },
    I18n: { t: key => key, getLang: () => 'zh' },
    trace,
  };
  sandbox.globalThis = sandbox;

  const prelude = `
    const zone = { key: ${JSON.stringify(ZONE3)}, cleared: ${cleared === true} };
    const SEEN = ${JSON.stringify(seen)};
    let _pendingBossZone = null;
    let _activeBossZone = null;
    let _zoneCinematicPresentationOnly = false;
    const _shots = ${JSON.stringify(shots)};
    const _firstEntryLength = ${Number(firstEntryShots)};

    function adventureCinematicPhaseSeen(z, phase) { return SEEN[phase] === true; }
    function adventureIntroSeen(z) { return adventureCinematicPhaseSeen(z, 'intro'); }
    async function markAdventureIntroSeen(z) { trace.push('MARK_INTRO_SEEN'); SEEN.intro = true; return true; }

    function hideBossCinematic() { trace.push('HIDE_OVERLAY'); }
    function _stopIntroFilm() {}
    function _registerZone3PresentationLifecycleCleanup() {}
    function _zone3ReturnToMap() { trace.push('RETURN_TO_MAP'); }
    function _failZone3PresentationOnly() { trace.push('PRESENTATION_FAILSAFE'); return true; }
    function _finishZoneCinematicReplay(z) { trace.push('REPLAY_TERMINATOR'); }
    function _finishZone3EntryManifest(z, mode) { trace.push('HANDOFF_CTA:' + mode); }
    function emitZone3JourneyEvent(name) { trace.push('EVENT:' + name); }
    function firstQuestionHref() { return '/question'; }
    function _zone3CinematicPresentation() {
      return { responsiveManifestReconciled: true, shots: _shots };
    }
    function _zone3CinematicTimeline(phase) {
      const picked = _shots.filter(s => s.phase === phase);
      // FIRST_ENTRY length is injectable so the harness can prove the manifest
      // path REFUSES a slice that is not exactly five shots.
      return phase === 'FIRST_ENTRY' ? picked.slice(0, _firstEntryLength) : picked;
    }
    async function playNewbieVillageIntroFilm(z, opts) {
      trace.push('PLAY:' + opts.phase + ':' + opts.timeline.length + ':' + opts.mode);
      return true;
    }
    async function enterAdventureZoneInPage(z) { trace.push('GAMEPLAY_ENTERED'); return true; }
  `;

  const body = [
    extractFunction(indexSource, '_continueZone3SafeEntry'),
    extractFunction(indexSource, 'showZone3EntrySafeFallback'),
  ].join('\n');

  vm.runInNewContext(
    `${prelude}\n${body}\nglobalThis.__run = () => showZone3EntrySafeFallback(zone, { mode: ${JSON.stringify(mode)} });`,
    sandbox,
    { filename: 'index.html:zone3-entry' },
  );

  const returned = await sandbox.__run();
  const played = trace.filter(t => t.startsWith('PLAY:'));
  return {
    returned,
    trace,
    playedPhases: played,
    autoplayed: played.length > 0,
    enteredGameplay: trace.includes('GAMEPLAY_ENTERED'),
    markedSeen: trace.includes('MARK_INTRO_SEEN'),
    returnedToZoneCard: trace.some(t => t.startsWith('ZONE_CARD:')),
  };
}

const failures = [];
const sequencing = { whileSegmentAShowing: null, whenSurfaceFree: null, postClearRecovery: null };
const check = (name, fn) => {
  try {
    const result = fn();
    // A check whose body returns a promise would otherwise report PASS while
    // its assertions rejected unobserved.
    if (result && typeof result.then === 'function') {
      throw new Error('check() bodies must be synchronous; await before calling it');
    }
  } catch (error) { failures.push(`${name}: ${error.message}`); }
};

// --- Point 1: first-ever entry autoplays Segment A, and only Segment A ------
const firstEntry = await enterZone3({ mode: 'first_entry', seen: {} });
check('P1 first entry autoplays Segment A', () => {
  assert.equal(firstEntry.autoplayed, true, 'first entry must autoplay');
  assert.deepEqual(firstEntry.playedPhases, ['PLAY:pre_play:5:first_entry']);
});
check('P1 first entry never plays shots 6-10', () => {
  assert.ok(!firstEntry.trace.some(t => t.startsWith('PLAY:') && !t.includes(':5:')),
    'Segment A must be five shots, never the whole ten-shot manifest');
});

// --- Point 2: repeat entry does not autoplay -------------------------------
const repeatEntry = await enterZone3({ mode: 'legacy', seen: { intro: true } });
check('P2 repeat entry does not autoplay', () => {
  assert.equal(repeatEntry.autoplayed, false, 'a seen opening must not replay');
  assert.equal(repeatEntry.enteredGameplay, true, 'repeat entry must hand straight to gameplay');
  assert.equal(repeatEntry.returned, true);
});

// --- Point 2c: a seen MAP-NODE entry stops at the Zone Card ---------------
// showStageIntroCinematic enforces this for every other zone: node entry and
// the Zone Card's training CTA are distinct product actions, so a seen account
// must not be dropped straight into a battle by selecting the node.
const seenNodeEntry = await enterZone3({ mode: 'first_entry', seen: { intro: true } });
check('P2c seen first_entry returns to the Zone Card, does not start gameplay', () => {
  assert.equal(seenNodeEntry.autoplayed, false);
  assert.equal(seenNodeEntry.returnedToZoneCard, true, 'must hand back to the Zone Card');
  assert.equal(seenNodeEntry.enteredGameplay, false, 'node entry must not auto-start a battle');
});

// The legacy map CTA IS the "start training" action, so it may enter directly.
const seenLegacyEntry = await enterZone3({ mode: 'legacy', seen: { intro: true } });
check('P2c legacy CTA still enters gameplay directly', () => {
  assert.equal(seenLegacyEntry.autoplayed, false);
  assert.equal(seenLegacyEntry.enteredGameplay, true);
});

// --- Point 7: cleared re-entry autoplays nothing ---------------------------
const clearedEntries = [];
for (const seen of [{}, { intro: true }]) {
  const clearedEntry = await enterZone3({ mode: 'legacy', cleared: true, seen });
  clearedEntries.push(clearedEntry);
  check(`P7 cleared re-entry autoplays nothing (seen=${JSON.stringify(seen)})`, () => {
    assert.equal(clearedEntry.autoplayed, false);
    assert.equal(clearedEntry.enteredGameplay, true);
  });
}

// --- Point 8: manual replay bypasses the gate and still plays --------------
const replay = await enterZone3({ mode: 'manual_replay', seen: { intro: true }, cleared: true });
check('P8 manual replay still plays for a seen, cleared zone', () => {
  assert.equal(replay.autoplayed, true, 'replay must not be blocked by the seen gate');
  assert.deepEqual(replay.playedPhases, ['PLAY:pre_play:5:manual_replay']);
});

// --- Point 9: manual replay writes no seen state --------------------------
check('P9 manual replay writes nothing', () => {
  assert.equal(replay.markedSeen, false, 'replay must not write the seen marker');
  assert.equal(replay.enteredGameplay, false, 'replay must not start gameplay');
});

// --- Point 2b: the entry flow does record "seen", or the gate never latches -
const continued = await enterZone3({ mode: 'legacy', seen: {} });
check('P2b an unseen entry does autoplay, so the gate is the only thing stopping it', () => {
  assert.equal(continued.autoplayed, true);
});

// The CTA handoff is what reaches _continueZone3SafeEntry; drive it directly.
{
  const trace = [];
  const overlay = { dataset: {}, classList: { add() {}, remove() {} }, setAttribute() {} };
  const sandbox = {
    console,
    document: { getElementById: id => (id === 'boss-cinematic' ? overlay : null) },
    window: { location: { href: '' } },
    trace,
    __overlay: overlay,
  };
  sandbox.globalThis = sandbox;
  vm.runInNewContext(`
    const overlay = globalThis.__overlay;
    const zone = { key: ${JSON.stringify(ZONE3)} };
    async function markAdventureIntroSeen() { trace.push('MARK_INTRO_SEEN'); return true; }
    async function enterAdventureZoneInPage() { trace.push('GAMEPLAY_ENTERED'); return true; }
    function firstQuestionHref() { return '/question'; }
    function _finishZoneCinematicReplay() { trace.push('REPLAY_TERMINATOR'); }
    function emitZone3JourneyEvent(name) { trace.push('EVENT:' + name); }
    ${extractFunction(indexSource, '_continueZone3SafeEntry')}
    globalThis.__continue = mode => {
      overlay.dataset.zone3Replay = mode === 'manual_replay' ? 'true' : 'false';
      delete overlay.dataset.zone3EntryCompleted;
      return _continueZone3SafeEntry(zone, mode === 'manual_replay' ? 'replay' : 'continue');
    };
  `, sandbox, { filename: 'index.html:zone3-continue' });

  trace.length = 0;
  await sandbox.__continue('legacy');
  check('P2b continuation marks seen and enters gameplay', () => {
    assert.ok(trace.includes('MARK_INTRO_SEEN'), 'entry must record Segment A as seen');
    assert.ok(trace.includes('GAMEPLAY_ENTERED'));
  });

  trace.length = 0;
  await sandbox.__continue('manual_replay');
  check('P9 replay continuation writes nothing and starts no gameplay', () => {
    assert.ok(!trace.includes('MARK_INTRO_SEEN'), 'replay must not record seen');
    assert.ok(!trace.includes('GAMEPLAY_ENTERED'), 'replay must not start gameplay');
    assert.ok(trace.includes('REPLAY_TERMINATOR'));
  });
}

// --- The ten-shot regression the Owner actually reported -------------------
const degenerate = await enterZone3({ mode: 'first_entry', seen: {}, firstEntryShots: 10 });
check('Segment A refuses a ten-shot slice', () => {
  assert.ok(
    !degenerate.playedPhases.some(p => p.includes(':10:')),
    'a FIRST_ENTRY slice that is not exactly five shots must not reach the manifest player',
  );
});

// --- Segments B and C must not be spliced onto whatever is already showing --
// This is the second half of the Owner's "Shots 1-10 as one movie" report: an
// account that is ALREADY Lord-ready when it first enters Zone 3 satisfies the
// readiness condition while Segment A is still on screen, and updateMapProgress
// re-derives readiness on every bootstrap.
{
  const runs = [];
  const overlay = { classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, contains(c) { return this._s.has(c); } } };
  const sandbox = {
    console,
    document: { getElementById: id => (id === 'boss-cinematic' ? overlay : null) },
    runs,
    __overlay: overlay,
  };
  sandbox.globalThis = sandbox;
  vm.runInNewContext(`
    const overlay = globalThis.__overlay;
    let _introFilmActiveOpts = { phase: 'pre_play' };
    let _adventureProgress = [];
    let SEEN_BOSS_READY = false;
    let SEEN_POST_CLEAR = false;
    let PENDING = true;
    const ADVENTURE_ZONES = [{ key: ${JSON.stringify(ZONE3)} }];
    // Readiness mirrors the real _adventureBossReady, which returns false once
    // the zone is cleared -- so "cleared AND boss-ready" is never modelled here,
    // because production cannot produce it.
    function _adventureBossReady(z) { return !(z && z.cleared); }
    function adventureBossReadyFilmSeen() { return SEEN_BOSS_READY; }
    function adventurePostClearSeen() { return SEEN_POST_CLEAR; }
    function adventurePostClearPending() { return PENDING; }
    // The stubs record "seen" where the real terminators do
    // (markAdventureBossReadyFilmSeen at onStarted, finishPostClearFilm at the
    // end of playback) AND take the cinematic surface the way
    // _startZone3CinematicWithGesture does -- it sets the overlay's show class
    // synchronously on both its branches. Without that, this harness would model
    // a world where starting a segment does not occupy the surface, which is
    // precisely the thing under test.
    function playZone3BossReadyFilm() { runs.push('SEGMENT_B'); SEEN_BOSS_READY = true; overlay.classList.add('show'); }
    function playZone3PostClearFilm() { runs.push('SEGMENT_C'); SEEN_POST_CLEAR = true; overlay.classList.add('show'); }
    ${extractFunction(indexSource, '_zone3CinematicSurfaceBusy')}
    ${extractFunction(indexSource, '_maybeTriggerZone3BossReadyFilm')}
    ${extractFunction(indexSource, '_resumeZone3PostClearIfPending')}
    globalThis.__bootstrap = (zones, showing) => {
      if (showing) overlay.classList.add('show'); else overlay.classList.remove('show');
      _adventureProgress = zones;
      // Same order as updateMapProgress: _resumeZone3PostClearIfPending runs
      // BEFORE _maybeTriggerZone3BossReadyFilm. Modelling it the other way
      // round would make this harness prove a sequence production never runs.
      _resumeZone3PostClearIfPending();
      _maybeTriggerZone3BossReadyFilm(zones);
    };
    globalThis.__runs = runs;
  `, sandbox, { filename: 'index.html:zone3-triggers' });

  // The Owner's reported scenario: Lord-ready (therefore not cleared) on the
  // very first Zone 3 entry, with Segment A still on screen.
  const readyZones = [{ key: ZONE3, cleared: false }];

  runs.length = 0;
  sandbox.__bootstrap(readyZones, true);
  sequencing.whileSegmentAShowing = [...runs];
  check('PB1 Segment B does not splice onto a showing Segment A', () => {
    assert.deepEqual(runs, [], `expected nothing to start, got ${JSON.stringify(runs)}`);
  });

  // Segment A ends, the surface frees: Segment B plays, and a second bootstrap
  // must not replay it.
  runs.length = 0;
  sandbox.__bootstrap(readyZones, false);
  sandbox.__bootstrap(readyZones, false);
  sequencing.whenSurfaceFree = [...runs];
  check('PB2 Segment B plays exactly once once the surface is free', () => {
    assert.deepEqual(runs, ['SEGMENT_B'],
      `two bootstraps must not replay Segment B, got ${JSON.stringify(runs)}`);
  });

  // Segment C's own recovery path: cleared, pending, unseen. Because a cleared
  // zone is never Lord-ready, C is the only segment in play here.
  runs.length = 0;
  overlay.classList.remove('show');
  const clearedZones = [{ key: ZONE3, cleared: true }];
  sandbox.__bootstrap(clearedZones, false);
  sandbox.__bootstrap(clearedZones, false);
  sequencing.postClearRecovery = [...runs];
  check('PB3 Segment C resumes exactly once and takes the surface', () => {
    assert.deepEqual(runs, ['SEGMENT_C'],
      `pending recovery must not replay Segment C, got ${JSON.stringify(runs)}`);
  });
}

const report = {
  runner: 'run_w1_owner_zone3_story_segmentation',
  status: failures.length ? 'FAIL' : 'PASS',
  failures,
  evidence: {
    ZONE3_FIRST_ENTRY: firstEntry.playedPhases,
    ZONE3_SEGMENT_A_REPEAT_AUTOPLAY: repeatEntry.autoplayed ? 'YES' : 'NO',
    ZONE3_CLEARED_REENTRY_AUTOPLAY: clearedEntries.some(e => e.autoplayed) ? 'YES' : 'NO',
    ZONE3_MANUAL_REPLAY_PLAYS: replay.autoplayed ? 'YES' : 'NO',
    ZONE3_MANUAL_REPLAY_WRITES_STATE: replay.markedSeen ? 'YES' : 'NO',
    ZONE3_SEGMENT_B_SPLICED_ONTO_SEGMENT_A: sequencing.whileSegmentAShowing?.length ? 'YES' : 'NO',
    ZONE3_SEGMENT_B_ONCE_WHEN_SURFACE_FREE: sequencing.whenSurfaceFree,
    ZONE3_SEGMENT_C_ONCE_ON_PENDING_RECOVERY: sequencing.postClearRecovery,
  },
};
console.log(JSON.stringify(report, null, 2));
if (failures.length) process.exit(1);
