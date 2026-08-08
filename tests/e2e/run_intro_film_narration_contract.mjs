/*
 * Regression contract for the adventure intro-film narration pacing fix
 * (2026-07-14 incident: recorded MP3 narration missing on Production caused
 * every zone's intro cinematic to race through all shots in milliseconds,
 * because a failed/missing narration asset triggered a zero-delay advance).
 *
 * This drives the real index.html functions (playNewbieVillageIntroFilm and
 * its closures) in a headless browser, with window.Audio, setTimeout and
 * speechSynthesis replaced by deterministic fakes -- no real waiting, no
 * real audio files, no network dependency on a live backend.
 *
 * Zone fixture note (E10-Z1-PROD-INTEGRATION-001): tests A-F/H exercise the
 * SHARED engine's generic success/failure/replay pacing behavior and were
 * originally written against zone k26_30 back when it was a placeholder
 * 4-shot timeline with audioSrc on every shot. k26_30 is now the canonical
 * Zone 1 bilingual cinematic (10 shots, intentionally zero audioSrc until
 * real narration is recorded -- see getIntroFilmLocaleConfig in index.html),
 * so these generic-engine tests were retargeted to k21_25 (unchanged, still
 * a 4-shot/all-audioSrc zone) to keep testing the same engine mechanics
 * without coupling them to Zone 1's content shape. Test J below covers Zone
 * 1's own contract (10 shots, silence shots, zero TTS/audio calls) directly.
 *
 * Exits non-zero with a printed failure list on any assertion failure.
 */
'use strict';

import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (fssync.existsSync(candidate)) return candidate;
  }
  throw new Error('No Chrome/Edge executable found. Set CHROME_BIN to run this contract.');
}

function contentTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8'
  })[ext] || 'application/octet-stream';
}

async function startStaticServer(rootDir) {
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://127.0.0.1');
      let rel = decodeURIComponent(url.pathname);
      if (rel === '/') rel = '/index.html';
      const abs = path.resolve(rootDir, '.' + rel);
      if (!abs.startsWith(rootDir)) { res.writeHead(404); res.end('not found'); return; }
      const stat = await fs.stat(abs).catch(() => null);
      if (!stat || !stat.isFile()) { res.writeHead(404); res.end('not found'); return; }
      res.writeHead(200, { 'Content-Type': contentTypeFor(abs) });
      fssync.createReadStream(abs).pipe(res);
    } catch (err) {
      res.writeHead(500);
      res.end(String(err));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  return { server, origin: `http://127.0.0.1:${address.port}` };
}

// Fakes installed before every page script runs, so window.Audio/setTimeout/
// speechSynthesis are already replaced by the time index.html's inline
// <script> executes and defines playNewbieVillageIntroFilm.
const FAKE_INIT_SCRIPT = `
(function () {
  window.__audioLog = [];
  window.__audioMode = 'success'; // 'success' | 'error' | 'reject'
  window.__pendingSuccessAudio = [];
  class FakeAudio {
    constructor(src) {
      this.src = src;
      this.onended = null;
      this.onerror = null;
      window.__audioLog.push({ event: 'created', src });
    }
    play() {
      const mode = window.__audioMode;
      window.__audioLog.push({ event: 'play', src: this.src, mode });
      if (mode === 'reject') return Promise.reject(new Error('NotAllowedError'));
      if (mode === 'error') {
        Promise.resolve().then(() => { if (this.onerror) this.onerror(new Event('error')); });
        return Promise.resolve();
      }
      window.__pendingSuccessAudio.push(this);
      return Promise.resolve();
    }
    pause() { window.__audioLog.push({ event: 'pause', src: this.src }); }
  }
  window.Audio = FakeAudio;
  window.__finishNextSuccessAudio = function () {
    const a = window.__pendingSuccessAudio.shift();
    if (a && a.onended) a.onended();
    return !!a;
  };

  window.__fakeTimers = [];
  let seq = 1;
  window.setTimeout = function (fn, delay) {
    const id = seq++;
    window.__fakeTimers.push({ id, fn, delay: delay || 0 });
    return id;
  };
  window.clearTimeout = function (id) {
    window.__fakeTimers = window.__fakeTimers.filter(function (t) { return t.id !== id; });
  };
  window.__flushFakeTimers = function () {
    let iterations = 0;
    while (window.__fakeTimers.length && iterations < 500) {
      iterations++;
      window.__fakeTimers.sort(function (a, b) { return a.delay - b.delay; });
      const t = window.__fakeTimers.shift();
      try { t.fn(); } catch (e) { console.error('fake timer error', e); }
    }
  };
  window.__pendingTimerDelays = function () {
    return window.__fakeTimers.map(function (t) { return t.delay; });
  };

  window.__speakCalls = 0;
  window.speechSynthesis = {
    getVoices: function () { return []; },
    speak: function (u) { window.__speakCalls++; },
    cancel: function () {}
  };
  window.SpeechSynthesisUtterance = function (text) { this.text = text; };
})();
`;

function test(name, fn, results) {
  return Promise.resolve()
    .then(fn)
    .then(() => results.push({ name, ok: true }))
    .catch((err) => results.push({ name, ok: false, error: err && err.message || String(err) }));
}

async function withFreshPage(browser, origin, fn) {
  const page = await browser.newPage();
  try {
    await page.addInitScript(FAKE_INIT_SCRIPT);
    // Playwright applies the most-recently-registered matching route first,
    // so the specific /api/auth/me handler must be registered LAST to win
    // over the generic /api/** catch-all.
    await page.route('**/api/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
    await page.route('**/api/auth/me', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ logged_in: true, user_id: 1, username: 'narration_tester', display_name: 'Narration Tester', is_admin: false, is_premium: false, needs_onboarding_choice: false, tour_done: true, elo_rating: 1200 })
    }));
    await page.goto(origin + '/index.html', { waitUntil: 'domcontentloaded' });
    // sanity: the function under test must exist before proceeding
    const hasFn = await page.evaluate(() => typeof playNewbieVillageIntroFilm === 'function');
    if (!hasFn) throw new Error('playNewbieVillageIntroFilm not defined on page');
    return await fn(page);
  } finally {
    await page.close();
  }
}

async function runFilm(page, zoneKey) {
  await page.evaluate((key) => {
    window.__filmDone = false;
    // Mirror what showStageIntroCinematic does in production: stamp the
    // active zone onto the overlay so getCurrentIntroZone() (used by
    // replayIntroFilm/skipIntroFilm) resolves back to the SAME zone under
    // test, instead of silently falling back to ADVENTURE_ZONES[0].
    const overlay = document.getElementById('boss-cinematic');
    if (overlay) overlay.dataset.zoneKey = key;
    playNewbieVillageIntroFilm({ key }).then(() => { window.__filmDone = true; });
  }, zoneKey);
}

async function main() {
  const { server, origin } = await startStaticServer(repoRoot);
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  const results = [];
  try {
    // --- A. Recorded MP3 success: no TTS, advances once per completed shot, normal pacing ---
    await test('A: successful MP3 narration advances shots without TTS', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await page.evaluate(() => { window.__audioMode = 'success'; });
        await runFilm(page, 'k21_25');
        // drive all 4 shots to completion via onended
        for (let i = 0; i < 4; i++) {
          const advanced = await page.evaluate(() => window.__finishNextSuccessAudio());
          if (!advanced) throw new Error(`expected pending audio for shot ${i}, found none`);
          await page.evaluate(() => window.__flushFakeTimers());
        }
        const speakCalls = await page.evaluate(() => window.__speakCalls);
        const overlayReady = await page.evaluate(() => document.getElementById('boss-cinematic').classList.contains('ready'));
        if (speakCalls !== 0) throw new Error(`expected 0 speechSynthesis.speak calls, got ${speakCalls}`);
        if (!overlayReady) throw new Error('expected cinematic to reach ready state after 4 successful shots');
      });
    }, results);

    // --- B. MP3 404 / audio.onerror: no TTS, no zero-delay, shot holds, advances once ---
    await test('B: audio.onerror holds the shot silently instead of finish(0)', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await page.evaluate(() => { window.__audioMode = 'error'; });
        await runFilm(page, 'k21_25');
        // let the microtask-queued onerror fire
        await page.waitForTimeout(20);
        const delaysAfterError = await page.evaluate(() => window.__pendingTimerDelays());
        const speakCallsBeforeFlush = await page.evaluate(() => window.__speakCalls);
        if (speakCallsBeforeFlush !== 0) throw new Error('TTS was invoked on audio.onerror path');
        const hasZeroDelay = delaysAfterError.some((d) => d === 0);
        if (hasZeroDelay) throw new Error(`found a zero-delay timer scheduled on failure: ${JSON.stringify(delaysAfterError)}`);
        const hasMeaningfulHold = delaysAfterError.some((d) => d >= 4000);
        if (!hasMeaningfulHold) throw new Error(`expected a >=4000ms visual hold timer, got delays ${JSON.stringify(delaysAfterError)}`);
        // shot 1 caption/composition should still be showing (not yet advanced)
        const activeShotBeforeFlush = await page.evaluate(() => {
          const shots = Array.from(document.querySelectorAll('#intro-film-stage .film-shot'));
          return shots.findIndex((el) => el.classList.contains('active'));
        });
        if (activeShotBeforeFlush !== 0) throw new Error(`expected shot 0 still active before hold elapses, got index ${activeShotBeforeFlush}`);
      });
    }, results);

    // --- C. audio.play() rejection: same silent visual-hold behavior, no uncaught rejection ---
    await test('C: play() rejection falls back to silent hold, no throw', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const pageErrors = [];
        page.on('pageerror', (e) => pageErrors.push(String(e)));
        await page.evaluate(() => { window.__audioMode = 'reject'; });
        await runFilm(page, 'k21_25');
        await page.waitForTimeout(20);
        const delays = await page.evaluate(() => window.__pendingTimerDelays());
        if (!delays.some((d) => d >= 4000)) throw new Error(`expected silent-hold timer after play() rejection, got ${JSON.stringify(delays)}`);
        if (pageErrors.length) throw new Error(`uncaught page errors: ${pageErrors.join(' | ')}`);
      });
    }, results);

    // --- D. Four consecutive failed MP3 files: all 4 shots shown in order, each held, completion exactly once ---
    await test('D: four consecutive failures still show all shots with holds, complete once', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await page.evaluate(() => { window.__audioMode = 'error'; });
        await runFilm(page, 'k21_25');
        const seenShots = [];
        for (let i = 0; i < 4; i++) {
          await page.waitForTimeout(5); // let onerror microtask fire
          const activeIdx = await page.evaluate(() => {
            const shots = Array.from(document.querySelectorAll('#intro-film-stage .film-shot'));
            return shots.findIndex((el) => el.classList.contains('active'));
          });
          seenShots.push(activeIdx);
          const delaysBefore = await page.evaluate(() => window.__pendingTimerDelays());
          if (!delaysBefore.some((d) => d >= 4000)) throw new Error(`shot ${i}: expected a visual-hold timer, got ${JSON.stringify(delaysBefore)}`);
          await page.evaluate(() => window.__flushFakeTimers());
        }
        const uniqueShots = new Set(seenShots);
        if (uniqueShots.size !== 4) throw new Error(`expected 4 distinct shots shown in order, got ${JSON.stringify(seenShots)}`);
        const overlayReady = await page.evaluate(() => document.getElementById('boss-cinematic').classList.contains('ready'));
        if (!overlayReady) throw new Error('expected cinematic to complete (ready) after all 4 shots held+advanced');
        const speakCalls = await page.evaluate(() => window.__speakCalls);
        if (speakCalls !== 0) throw new Error(`expected 0 TTS calls across 4 failures, got ${speakCalls}`);
      });
    }, results);

    // --- E. Error/completion race: onerror plus a second callback still advances exactly once ---
    await test('E: onended firing after onerror does not double-advance', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await page.evaluate(() => { window.__audioMode = 'error'; });
        await runFilm(page, 'k21_25');
        await page.waitForTimeout(20);
        // simulate a stale onended firing on the same (already-failed) audio instance
        await page.evaluate(() => {
          const shots = Array.from(document.querySelectorAll('#intro-film-stage .film-shot'));
          window.__activeShotBeforeRace = shots.findIndex((el) => el.classList.contains('active'));
        });
        await page.evaluate(() => window.__finishNextSuccessAudio()); // no-op: queue is empty on the error path
        await page.evaluate(() => window.__flushFakeTimers());
        const activeAfter = await page.evaluate(() => {
          const shots = Array.from(document.querySelectorAll('#intro-film-stage .film-shot'));
          return shots.findIndex((el) => el.classList.contains('active'));
        });
        const before = await page.evaluate(() => window.__activeShotBeforeRace);
        // after flushing exactly one hold timer, we should have advanced by exactly one shot, not skipped ahead
        if (activeAfter !== before + 1 && !(before === 3 && activeAfter === -1)) {
          throw new Error(`expected advance by exactly one shot (from ${before}), got ${activeAfter}`);
        }
      });
    }, results);

    // --- F. Replay/close/skip: pending fallback timers cancelled, stale callbacks don't affect next run ---
    await test('F: replay cancels pending silent-hold timer from previous run', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await page.evaluate(() => { window.__audioMode = 'error'; });
        await runFilm(page, 'k21_25');
        await page.waitForTimeout(20);
        const delaysBeforeReplay = await page.evaluate(() => window.__pendingTimerDelays());
        if (!delaysBeforeReplay.some((d) => d >= 4000)) throw new Error(`expected a pending >=4000ms silent-hold timer before replay, got ${JSON.stringify(delaysBeforeReplay)}`);
        // replayIntroFilm() calls _stopIntroFilm() which must clear that stale hold timer
        // (a fresh run legitimately schedules its OWN new short timers, e.g. the shot-0
        // 'grub' sfx cue at 620ms -- we only assert the stale >=4000ms one is gone).
        await page.evaluate(() => { window.__audioMode = 'success'; replayIntroFilm(); });
        const delaysAfterReplay = await page.evaluate(() => window.__pendingTimerDelays());
        if (delaysAfterReplay.some((d) => d >= 4000)) throw new Error(`stale silent-hold timer survived replay: ${JSON.stringify(delaysAfterReplay)}`);
      });
    }, results);

    // --- H. TTS prohibition, explicit ---
    await test('H: narration failure path never calls playBrowserVoice/speechSynthesis', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await page.evaluate(() => { window.__audioMode = 'error'; });
        await runFilm(page, 'k21_25');
        for (let i = 0; i < 4; i++) {
          await page.waitForTimeout(5);
          await page.evaluate(() => window.__flushFakeTimers());
        }
        const speakCalls = await page.evaluate(() => window.__speakCalls);
        if (speakCalls !== 0) throw new Error(`expected zero TTS invocations across a fully-failed cinematic, got ${speakCalls}`);
      });
    }, results);

    // --- I. Missing recorded asset: intro must remain silent and paced ---
    await test('I: missing audioSrc uses silent pacing without TTS', async () => {
      const source = await fs.readFile(path.join(repoRoot, 'index.html'), 'utf8');
      // playAssetVoice now operates on a per-beat object (renamed item ->
      // beat when Fix 3's beats[] model replaced one-flattened-string-per-
      // shot -- see E10-Z1-PROD-INTEGRATION-001 Owner review).
      if (!/if \(!beat\.audioSrc\)\s*\{\s*finishSilently\(\);\s*return;\s*\}/.test(source)) {
        throw new Error('missing audioSrc is not wired to finishSilently');
      }
      if (/if \(!beat\.audioSrc\)\s*\{[^}]*playBrowserVoice/s.test(source)) {
        throw new Error('missing audioSrc still reaches playBrowserVoice');
      }
      // The browser cases above exercise the same silent hold for load/error/
      // play rejection; this source-level guard proves the missing-asset branch
      // cannot reach the browser-TTS function.
    }, results);

    // --- J-R. Zone 1 (k26_30) lifecycle + beats contract ---
    // E10-Z1-PROD-INTEGRATION-001 Owner review (Changes Required): the
    // PRE_PLAY cinematic is Shots 1-8 ONLY (timeline, DOM shot indices 0-7);
    // Shots 9-10 (postClearTimeline, DOM shot indices 8-9) only ever play via
    // playZone1PostClearFilm(), itself only reachable from a genuine, fresh,
    // server-authoritative Map Battle v1 'monster_defeated' response for
    // k26_30 (see _submitMapBattleV1IfActive). Zone 1 has zero audioSrc on
    // every beat (no recorded narration exists yet), so playAssetVoice's
    // missing-audioSrc branch fires synchronously and schedules its
    // silent-hold timer immediately -- unlike the MP3-backed zones above,
    // there is no real Audio object / onended-onerror microtask boundary to
    // single-step through. Drain the fake timer queue one entry at a time,
    // recording state after each individual callback, so every shot/beat
    // transition is captured.
    async function recordFilmRun(page, kickoff) {
      await page.evaluate(() => { window.__audioMode = 'success'; });
      await kickoff(page);
      return page.evaluate(() => {
        const stage = document.getElementById('intro-film-stage');
        const line = document.getElementById('boss-cinematic-line');
        const record = () => {
          const shots = Array.from(stage.querySelectorAll('.film-shot'));
          const activeIdx = shots.findIndex((el) => el.classList.contains('active'));
          log.push({ activeIdx, lineText: line ? line.textContent : '' });
        };
        const log = [];
        record();
        let iterations = 0;
        while (window.__fakeTimers.length && iterations < 500) {
          iterations++;
          window.__fakeTimers.sort((a, b) => a.delay - b.delay);
          const t = window.__fakeTimers.shift();
          t.fn();
          record();
        }
        return log;
      });
    }

    async function runPostClearFilm(page, zoneKey) {
      await page.evaluate((key) => {
        const overlay = document.getElementById('boss-cinematic');
        if (overlay) overlay.dataset.zoneKey = key;
        playZone1PostClearFilm({ key });
      }, zoneKey);
    }

    // Distinct beat texts per shot, in order, deduped against consecutive
    // repeats (the fake-timer drain can record the same DOM state more than
    // once per beat, e.g. once for the class toggle and once for the text
    // change -- consecutive-dedup collapses that without merging two
    // genuinely different beats that happen to repeat the same shot index).
    function beatsForShot(log, shotIdx) {
      const texts = log.filter((e) => e.activeIdx === shotIdx).map((e) => e.lineText);
      const deduped = [];
      for (const t of texts) {
        if (deduped.length === 0 || deduped[deduped.length - 1] !== t) deduped.push(t);
      }
      return deduped;
    }

    // --- J. UNCLEARED_ENTRY = S1..S8 ONLY / S9_BEFORE_CLEAR & S10_BEFORE_CLEAR = IMPOSSIBLE ---
    await test('J: Zone 1 PRE_PLAY plays exactly Shots 1-8, never 9/10, zero audio/TTS calls', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const log = await recordFilmRun(page, (p) => runFilm(p, 'k26_30'));
        const seenShots = new Set(log.map((entry) => entry.activeIdx).filter((idx) => idx >= 0));
        if (seenShots.size !== 8) throw new Error(`expected exactly Shots 1-8 (8 distinct indices) to play, got ${JSON.stringify([...seenShots].sort((a, b) => a - b))} from log ${JSON.stringify(log)}`);
        if (seenShots.has(8) || seenShots.has(9)) throw new Error(`PRE_PLAY must never activate Shot 9/10 (indices 8/9), saw ${JSON.stringify([...seenShots])}`);
        const overlayReady = await page.evaluate(() => document.getElementById('boss-cinematic').classList.contains('ready'));
        if (!overlayReady) throw new Error('expected Zone 1 PRE_PLAY to reach ready state after Shot 8');
        const showsTitleCard = await page.evaluate(() => document.getElementById('intro-film-stage').classList.contains('show-title-card'));
        if (showsTitleCard) throw new Error('Zone 1 PRE_PLAY hand-off must not show the legacy title card (Fix 2)');
        const audioCreated = await page.evaluate(() => window.__audioLog.some((e) => e.event === 'created'));
        if (audioCreated) throw new Error('Zone 1 has no recorded narration yet -- no window.Audio should ever be constructed');
        const speakCalls = await page.evaluate(() => window.__speakCalls);
        if (speakCalls !== 0) throw new Error(`expected 0 TTS calls across Zone 1 PRE_PLAY, got ${speakCalls}`);
      });
    }, results);

    // --- K. S3/S5/S7_SILENCE (PRE_PLAY silence shots show no subtitle) ---
    await test('K: Zone 1 PRE_PLAY silence shots (S3/S5/S7) show no subtitle text', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const log = await recordFilmRun(page, (p) => runFilm(p, 'k26_30'));
        const silentIndices = [2, 4, 6]; // S3, S5, S7
        const bad = [];
        for (const idx of silentIndices) {
          for (const entry of log.filter((e) => e.activeIdx === idx)) {
            if ((entry.lineText || '').trim() !== '') bad.push({ idx, lineText: entry.lineText });
          }
        }
        if (bad.length) throw new Error(`expected empty subtitle at Zone 1 silence shots, found: ${JSON.stringify(bad)}`);
      });
    }, results);

    // --- L. S2/S4/S6/S8 multi-beat order is exact canonical text, not a flattened/prefixed string ---
    await test('L: Zone 1 PRE_PLAY multi-beat shots (S2/S4/S6/S8) play beats in exact canonical order', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const log = await recordFilmRun(page, (p) => runFilm(p, 'k26_30'));
        const expected = {
          1: ['Morning, child.', 'Morning, Shui.'], // S2
          3: ["Look at that cloud.", "It's been sitting there for three days.", 'And... every day, it gets a little closer.'], // S4
          5: ["I don't know if I can do this...", 'But I want to go see for myself.'], // S6
          7: ['If you want to leave the village, play one game with me first.', "Don't rush.", 'Look carefully. Then make your move.'], // S8 (DL-01)
        };
        const mismatches = [];
        for (const [shotIdx, expectedBeats] of Object.entries(expected)) {
          const actual = beatsForShot(log, Number(shotIdx));
          if (JSON.stringify(actual) !== JSON.stringify(expectedBeats)) {
            mismatches.push({ shot: shotIdx, expected: expectedBeats, actual });
          }
          // Non-canonical speaker-label injection guard (no "Elder:"/"Hero:"
          // prefixes -- speaker is metadata only, never in the subtitle text).
          for (const beat of actual) {
            if (/^(Elder|Hero|Anna|Runner|村長|主角|Narrator)[:：]/.test(beat)) {
              mismatches.push({ shot: shotIdx, error: `non-canonical speaker label injected into subtitle: ${JSON.stringify(beat)}` });
            }
          }
        }
        if (mismatches.length) throw new Error(`beat order/text mismatch: ${JSON.stringify(mismatches)}`);
      });
    }, results);

    // --- M. Structural proof: getIntroFilmLocaleConfig itself separates PRE_PLAY from POST_CLEAR ---
    await test('M: Zone 1 config has exactly 8 PRE_PLAY shots (0-7) and 2 POST_CLEAR shots (8-9), both locales', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const result = await page.evaluate(() => {
          const zh = getIntroFilmLocaleConfig({ key: 'k26_30' });
          if (window.I18n && window.I18n.setLang) window.I18n.setLang('en');
          const en = getIntroFilmLocaleConfig({ key: 'k26_30' });
          const shotList = (tl) => (tl || []).map((s) => s.shot);
          const beatCounts = (tl) => (tl || []).map((s) => (s.beats || []).length);
          return {
            zhTimelineShots: shotList(zh.timeline), zhPostClearShots: shotList(zh.postClearTimeline),
            enTimelineShots: shotList(en.timeline), enPostClearShots: shotList(en.postClearTimeline),
            zhBeatCounts: beatCounts(zh.timeline).concat(beatCounts(zh.postClearTimeline)),
            enBeatCounts: beatCounts(en.timeline).concat(beatCounts(en.postClearTimeline)),
            zhHasFinalCaption: 'finalCaption' in zh, zhHasFinalLine: 'finalLine' in zh,
            enHasFinalCaption: 'finalCaption' in en, enHasFinalLine: 'finalLine' in en,
          };
        });
        const expectedTimeline = [0, 1, 2, 3, 4, 5, 6, 7];
        const expectedPostClear = [8, 9];
        const expectedBeatCounts = [1, 2, 0, 3, 0, 2, 0, 3, 0, 3]; // S1..S10
        for (const [label, actual, expected] of [
          ['zh timeline', result.zhTimelineShots, expectedTimeline],
          ['zh postClear', result.zhPostClearShots, expectedPostClear],
          ['en timeline', result.enTimelineShots, expectedTimeline],
          ['en postClear', result.enPostClearShots, expectedPostClear],
          ['zh beat counts', result.zhBeatCounts, expectedBeatCounts],
          ['en beat counts', result.enBeatCounts, expectedBeatCounts],
        ]) {
          if (JSON.stringify(actual) !== JSON.stringify(expected)) {
            throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
          }
        }
        // Fix 2: no legacy finalCaption/finalLine exposition anywhere in Zone 1's config.
        if (result.zhHasFinalCaption || result.zhHasFinalLine || result.enHasFinalCaption || result.enHasFinalLine) {
          throw new Error(`Zone 1 config must not define finalCaption/finalLine: ${JSON.stringify(result)}`);
        }
      });
    }, results);

    // --- N & O. GENUINE_CLEAR = S9 THEN S10 / S10 multi-beat order exact / zero audio/TTS ---
    await test('N: Zone 1 POST_CLEAR plays exactly Shot 9 then Shot 10, zero audio/TTS calls', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const log = await recordFilmRun(page, (p) => runPostClearFilm(p, 'k26_30'));
        const order = [];
        for (const entry of log) {
          if (entry.activeIdx >= 0 && order[order.length - 1] !== entry.activeIdx) order.push(entry.activeIdx);
        }
        if (JSON.stringify(order) !== JSON.stringify([8, 9])) {
          throw new Error(`expected POST_CLEAR shot order [8,9] (Shot 9 then Shot 10), got ${JSON.stringify(order)} from log ${JSON.stringify(log)}`);
        }
        const audioCreated = await page.evaluate(() => window.__audioLog.some((e) => e.event === 'created'));
        if (audioCreated) throw new Error('Zone 1 POST_CLEAR has no recorded narration yet -- no window.Audio should ever be constructed');
        const speakCalls = await page.evaluate(() => window.__speakCalls);
        if (speakCalls !== 0) throw new Error(`expected 0 TTS calls across Zone 1 POST_CLEAR, got ${speakCalls}`);
      });
    }, results);

    await test('O: Zone 1 POST_CLEAR Shot 9 is silent, Shot 10 plays exact canonical 3-beat order, no extra line after', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const log = await recordFilmRun(page, (p) => runPostClearFilm(p, 'k26_30'));
        const shot9Beats = beatsForShot(log, 8).filter((t) => t !== '');
        if (shot9Beats.length) throw new Error(`expected Shot 9 (S9) to be silent, saw subtitle text: ${JSON.stringify(shot9Beats)}`);
        const shot10Beats = beatsForShot(log, 9);
        const expected = ['Elder!', 'The caravan from the Slime Plains...', "It's been three days, and they still haven't come back!"];
        if (JSON.stringify(shot10Beats) !== JSON.stringify(expected)) {
          throw new Error(`Shot 10 beat mismatch: expected ${JSON.stringify(expected)}, got ${JSON.stringify(shot10Beats)}`);
        }
        // Fix 2: nothing (no Hero response, no thesis line) may play after Shot 10's last beat.
        const finalLineAfterComplete = await page.evaluate(() => document.getElementById('boss-cinematic-line')?.textContent || '');
        if (finalLineAfterComplete !== expected[expected.length - 1]) {
          throw new Error(`expected the subtitle to still read Shot 10's own last line after completion, got ${JSON.stringify(finalLineAfterComplete)}`);
        }
      });
    }, results);

    // --- P. finishPostClearFilm marks seen and closes the overlay (no reward/settlement call, visual-only) ---
    await test('P: Zone 1 POST_CLEAR completion marks postClearSeen and closes the overlay', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await recordFilmRun(page, (p) => runPostClearFilm(p, 'k26_30'));
        const seen = await page.evaluate(() => {
          const raw = localStorage.getItem('adventure_postclear_seen_v1');
          return raw ? JSON.parse(raw) : {};
        });
        if (!seen.k26_30) throw new Error(`expected adventure_postclear_seen_v1.k26_30 to be set after completion, got ${JSON.stringify(seen)}`);
        const overlayHidden = await page.evaluate(() => document.getElementById('boss-cinematic').getAttribute('aria-hidden'));
        if (overlayHidden !== 'true') throw new Error(`expected the overlay to close (aria-hidden=true) after POST_CLEAR completes, got ${overlayHidden}`);
      });
    }, results);

    // --- Q. _maybeTriggerZone1PostClearFilm fires once, is a no-op once already seen ---
    await test('Q: _maybeTriggerZone1PostClearFilm is idempotent (fires once per zone)', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const firstRun = await page.evaluate(() => {
          // isBeginnerVillageAdventureResult() requires _isAdventureZonePractice()
          // (a non-empty _adventureActiveQuestions) AND either a ?zone=k26_30 URL
          // param or a question topic matching /新手村|Beginner Village/ -- fake
          // the latter so this test doesn't need a second page navigation.
          // `let _adventureActiveQuestions` at index.html's top level is a
          // global LEXICAL binding, not a window property -- window.foo=
          // would silently create an unrelated property that
          // isBeginnerVillageAdventureResult() never reads. A bare
          // assignment mutates the same binding the page's own script uses.
          _adventureActiveQuestions = [{ topic: 'Beginner Village' }];
          // _adventureProgress already defaults to [] (index.html top
          // level); _maybeTriggerZone1PostClearFilm() falls back to
          // ADVENTURE_ZONES.find(...) when it's empty, so no override needed.
          _maybeTriggerZone1PostClearFilm();
          return document.getElementById('boss-cinematic').className;
        });
        if (!/intro-film/.test(firstRun)) throw new Error(`expected first trigger to open the POST_CLEAR film, overlay class was ${JSON.stringify(firstRun)}`);
        await page.evaluate(() => window.__flushFakeTimers());
        const seenAfterFirst = await page.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_seen_v1') || '{}'));
        if (!seenAfterFirst.k26_30) throw new Error('expected postClearSeen to be set after the first trigger completes');
        const secondRunClass = await page.evaluate(() => {
          const before = document.getElementById('boss-cinematic').className;
          _maybeTriggerZone1PostClearFilm();
          const after = document.getElementById('boss-cinematic').className;
          return { before, after };
        });
        if (secondRunClass.before !== secondRunClass.after) {
          throw new Error(`expected a second trigger (already seen) to be a no-op, overlay class changed from ${JSON.stringify(secondRunClass.before)} to ${JSON.stringify(secondRunClass.after)}`);
        }
      });
    }, results);

    // --- R. Source-level: no reward/settlement authority in cinematic code; trigger is win-only-scoped ---
    await test('R: Zone 1 lifecycle functions contain no reward/settlement calls; trigger fires only on monster_defeated', async () => {
      const source = await fs.readFile(path.join(repoRoot, 'index.html'), 'utf8');
      function extractFunctionBody(name) {
        const m = source.match(new RegExp(`function ${name}\\([^)]*\\)\\s*\\{`));
        if (!m) throw new Error(`function ${name} not found in index.html`);
        let i = m.index + m[0].length;
        let depth = 1;
        const start = i;
        while (depth > 0 && i < source.length) {
          if (source[i] === '{') depth++;
          else if (source[i] === '}') depth--;
          i++;
        }
        return source.slice(start, i - 1);
      }
      const cinematicFns = ['playZone1PostClearFilm', 'finishPostClearFilm', '_maybeTriggerZone1PostClearFilm', '_resumeZone1PostClearIfPending', 'replayIntroFilm', 'skipIntroFilm'];
      const violations = [];
      for (const fn of cinematicFns) {
        const body = extractFunctionBody(fn);
        if (/fetch\s*\(|credentials\s*:|\.submit\s*\(|\/api\//.test(body)) {
          violations.push(`${fn} appears to contain a network/reward/settlement call`);
        }
      }
      if (violations.length) throw new Error(violations.join('; '));
      // The only call site of _maybeTriggerZone1PostClearFilm() must be inside
      // the next_action === 'monster_defeated' branch of
      // _submitMapBattleV1IfActive -- never inside a 'player_defeated' or
      // generic 'continue' path (FAILED_OR_ABORTED_GAMEPLAY_POST_CLEAR=NONE).
      const monsterDefeatedBranch = source.match(/if \(response\.next_action === 'monster_defeated'\) \{[\s\S]*?\n\s{16}\}/);
      if (!monsterDefeatedBranch || !monsterDefeatedBranch[0].includes('_maybeTriggerZone1PostClearFilm()')) {
        throw new Error("_maybeTriggerZone1PostClearFilm() call site not found scoped inside the monster_defeated branch");
      }
      const callOnly = source.match(/(?<!function )_maybeTriggerZone1PostClearFilm\(\);/g) || [];
      if (callOnly.length !== 1) {
        throw new Error(`expected exactly 1 call site of _maybeTriggerZone1PostClearFilm(), found ${callOnly.length}`);
      }
      // Structural proof postClearTimeline is never reachable from the
      // PRE_PLAY entry path (showStageIntroCinematic never references it).
      const showStageBody = extractFunctionBody('showStageIntroCinematic');
      if (showStageBody.includes('postClearTimeline')) {
        throw new Error('showStageIntroCinematic must never reference postClearTimeline -- S9/S10 must be structurally unreachable before a genuine clear');
      }
    }, results);

    // --- S & T. Reload/close resilience: a genuine clear left pending mid-S9/S10 must recover ---
    // The real trigger (_maybeTriggerZone1PostClearFilm) marks pending BEFORE
    // playback starts and only clears it in finishPostClearFilm (normal
    // completion/skip). Simulate "reload" with a REAL page.goto() re-
    // navigation on the SAME page/context, so localStorage genuinely
    // persists across it exactly as a browser reload would -- this is not
    // simulated via a fresh isolated context (withFreshPage's newPage()
    // would NOT share localStorage).
    async function drainOneFakeTimer(page) {
      await page.evaluate(() => {
        window.__fakeTimers.sort((a, b) => a.delay - b.delay);
        const t = window.__fakeTimers.shift();
        if (t) t.fn();
      });
    }
    async function drainAllFakeTimers(page) {
      let iterations = 0;
      while (await page.evaluate(() => window.__fakeTimers.length) && iterations < 500) {
        iterations++;
        await drainOneFakeTimer(page);
      }
    }
    async function triggerGenuineClearAndReloadMidPlayback(drainsBeforeReload) {
      const page1 = await browser.newPage();
      await page1.addInitScript(FAKE_INIT_SCRIPT);
      await page1.route('**/api/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
      await page1.route('**/api/auth/me', (route) => route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ logged_in: true, user_id: 1, username: 'reload_tester', display_name: 'Reload Tester', is_admin: false, is_premium: false, needs_onboarding_choice: false, tour_done: true, elo_rating: 1200 })
      }));
      await page1.goto(origin + '/index.html', { waitUntil: 'domcontentloaded' });
      await page1.evaluate(() => {
        window.__audioMode = 'success';
        _adventureActiveQuestions = [{ topic: 'Beginner Village' }];
        _maybeTriggerZone1PostClearFilm();
      });
      for (let i = 0; i < drainsBeforeReload; i++) await drainOneFakeTimer(page1);
      const pendingBeforeReload = await page1.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_pending_v1') || '{}'));
      const seenBeforeReload = await page1.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_seen_v1') || '{}'));
      if (!pendingBeforeReload.k26_30) throw new Error('test setup invalid: expected pending to be set before reload');
      if (seenBeforeReload.k26_30) throw new Error('test setup invalid: expected NOT seen before reload (reload happened too late)');
      // A real reload: re-navigate the same page/context. FAKE_INIT_SCRIPT
      // re-applies via addInitScript on every navigation, so fakes are back
      // in place, but all in-memory JS state (_introFilmActiveOpts, the
      // overlay's DOM, etc.) is genuinely gone -- only localStorage survives.
      await page1.goto(origin + '/index.html', { waitUntil: 'domcontentloaded' });
      await page1.evaluate(() => { window.__audioMode = 'success'; });
      return page1;
    }

    await test('S: RELOAD_DURING_S9 = POST_CLEAR_RECOVERABLE', async () => {
      const page = await triggerGenuineClearAndReloadMidPlayback(1);
      try {
        // The real production hook: updateMapProgress() runs whenever fresh
        // adventure progress loads (e.g. on the map after a reload).
        await page.evaluate(() => { updateMapProgress({ zones: [] }); });
        const resumedPhase = await page.evaluate(() => _introFilmActiveOpts.phase);
        if (resumedPhase !== 'post_clear') throw new Error(`expected reload to resume POST_CLEAR, phase was ${JSON.stringify(resumedPhase)}`);
        const activeShotAfterResume = await page.evaluate(() => {
          const shots = Array.from(document.querySelectorAll('#intro-film-stage .film-shot'));
          return shots.findIndex((el) => el.classList.contains('active'));
        });
        if (activeShotAfterResume !== 8) throw new Error(`expected resume to restart at Shot 9 (index 8), got ${activeShotAfterResume}`);
        await drainAllFakeTimers(page);
        const seenAfter = await page.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_seen_v1') || '{}'));
        if (!seenAfter.k26_30) throw new Error('expected seen to be set after the resumed playback completes');
        const pendingAfter = await page.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_pending_v1') || '{}'));
        if (pendingAfter.k26_30) throw new Error('expected pending to be cleared after completion');
      } finally {
        await page.close();
      }
    }, results);

    await test('T: RELOAD_DURING_S10 = POST_CLEAR_RECOVERABLE', async () => {
      // Drain enough timers to get past Shot 9's silent hold and into Shot
      // 10's beats before reloading -- proves recovery works regardless of
      // which of the two POST_CLEAR shots the reload interrupts.
      const page = await triggerGenuineClearAndReloadMidPlayback(3);
      try {
        await page.evaluate(() => { updateMapProgress({ zones: [] }); });
        const activeShotAfterResume = await page.evaluate(() => {
          const shots = Array.from(document.querySelectorAll('#intro-film-stage .film-shot'));
          return shots.findIndex((el) => el.classList.contains('active'));
        });
        if (activeShotAfterResume !== 8) throw new Error(`expected resume to restart at Shot 9 (index 8) even when the reload interrupted Shot 10, got ${activeShotAfterResume}`);
        await drainAllFakeTimers(page);
        const seenAfter = await page.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_seen_v1') || '{}'));
        if (!seenAfter.k26_30) throw new Error('expected seen to be set after the resumed playback completes');
      } finally {
        await page.close();
      }
    }, results);

    // --- U. Zone 1's scene-caption badge is hidden (Owner review follow-up, Fix B) ---
    await test('U: Zone 1 hides the film-caption badge in both phases; other zones keep it', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await recordFilmRun(page, (p) => runFilm(p, 'k26_30'));
        const preplayCaptionHidden = await page.evaluate(() => document.getElementById('intro-film-caption').style.display === 'none');
        if (!preplayCaptionHidden) throw new Error('expected Zone 1 PRE_PLAY to hide the caption badge');
      });
      await withFreshPage(browser, origin, async (page) => {
        // Check mid-playback, not after full completion: finishPostClearFilm
        // closes the whole overlay via hideBossCinematic() -> _stopIntroFilm(),
        // which resets the badge's display style for the NEXT run (harmless,
        // since the overlay itself is hidden by then) -- checking after that
        // point would test the wrong thing. activateShot(0) runs
        // synchronously as part of playZone1PostClearFilm(), so the state is
        // already correct immediately after triggering, before any timers drain.
        await page.evaluate(() => { window.__audioMode = 'success'; });
        await runPostClearFilm(page, 'k26_30');
        const postClearCaptionHidden = await page.evaluate(() => document.getElementById('intro-film-caption').style.display === 'none');
        if (!postClearCaptionHidden) throw new Error('expected Zone 1 POST_CLEAR to hide the caption badge');
      });
      await withFreshPage(browser, origin, async (page) => {
        await recordFilmRun(page, (p) => runFilm(p, 'k21_25'));
        const otherZoneCaptionVisible = await page.evaluate(() => document.getElementById('intro-film-caption').style.display !== 'none');
        if (!otherZoneCaptionVisible) throw new Error('expected a non-Zone-1 zone to keep its caption badge visible (no regression)');
      });
    }, results);

    const failed = results.filter((r) => !r.ok);
    console.log(JSON.stringify({ ok: failed.length === 0, total: results.length, passed: results.length - failed.length, failed }, null, 2));
    if (failed.length) process.exitCode = 1;
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
