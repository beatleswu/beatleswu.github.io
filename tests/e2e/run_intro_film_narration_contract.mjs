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
 * 4-shot timeline with audioSrc on every shot. The production zones now use
 * their real 10-shot bilingual timelines (including intentional silent
 * shots), so the generic engine tests inject this deterministic 4-shot
 * fixture instead of coupling pacing assertions to a content timeline.
 * Test J below covers Zone 1's own contract (10 shots, silence shots, zero
 * TTS/audio calls) directly.
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
  window.__audioPolicy = 'unrestricted';
  window.__dialogueAudioElementCount = 0;
  window.__pendingSuccessAudio = [];
  class FakeAudio {
    constructor(src) {
      this.src = src || '';
      this.onended = null;
      this.onerror = null;
      this._dialogueElementNumber = 0;
      window.__audioLog.push({ event: 'created', src: this.src });
    }
    play() {
      const mode = window.__audioMode;
      if (this.src.includes('/dialogue/') && !this._dialogueElementNumber) {
        this._dialogueElementNumber = ++window.__dialogueAudioElementCount;
      }
      const blockedByMediaPolicy = window.__audioPolicy === 'ipad-single-narration-element'
        && this.src.includes('/dialogue/')
        && this._dialogueElementNumber > 3;
      if (blockedByMediaPolicy) {
        window.__audioLog.push({ event: 'play-rejected-policy', src: this.src, dialogueElementNumber: this._dialogueElementNumber });
        if (this.onerror) this.onerror(new Event('error'));
        return Promise.resolve();
      }
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
    load() {}
  }
  window.Audio = FakeAudio;
  window.__finishNextSuccessAudio = function () {
    let a;
    while ((a = window.__pendingSuccessAudio.shift())) {
      // BGM/ambience/SFX fakes are intentionally allowed to share the
      // queue, but only the narration element has an onended callback that
      // advances the cinematic.  Consume decorative beds without letting
      // them steal a deterministic narration step.
      if (a.onended) {
        a.onended();
        return true;
      }
    }
    return false;
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
    // Set deterministically rather than relying on window.onload's async
    // getMe() to have resolved by 'domcontentloaded' (a real race -- account-
    // scoped storage, e.g. adventurePostClearSeen/Pending, reads this).
    // Matches the mocked /api/auth/me response above, so this doesn't fight
    // the real bootstrap even if it completes later.
    await page.evaluate(() => { _currentUserId = 1; });
    return await fn(page);
  } finally {
    await page.close();
  }
}

const GENERIC_AUDIO_TIMELINE = [0, 1, 2, 3].map((shot) => ({
  shot,
  caption: `Generic shot ${shot + 1}`,
  text: `Generic narration ${shot + 1}`,
  audioSrc: `/tests/e2e/fixtures/generic-narration-${shot + 1}.mp3`,
  imageSrc: `/assets/storyboards/e10_z2_shot0${shot + 1}.webp`,
  imageAlt: `Generic narration shot ${shot + 1}`
}));

async function runFilm(page, zoneKey, mode = null, timeline = null) {
  await page.evaluate(({ key, playMode, timeline }) => {
    window.__filmDone = false;
    // Mirror what showStageIntroCinematic does in production: stamp the
    // active zone onto the overlay so getCurrentIntroZone() (used by
    // replayIntroFilm/skipIntroFilm) resolves back to the SAME zone under
    // test, instead of silently falling back to ADVENTURE_ZONES[0].
    const overlay = document.getElementById('boss-cinematic');
    if (overlay) overlay.dataset.zoneKey = key;
    const opts = { ...(playMode ? { mode: playMode } : {}), ...(timeline ? { timeline } : {}) };
    playNewbieVillageIntroFilm({ key }, opts).then(() => { window.__filmDone = true; });
  }, { key: zoneKey, playMode: mode, timeline });
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
        await runFilm(page, 'k21_25', null, GENERIC_AUDIO_TIMELINE);
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
        await runFilm(page, 'k21_25', null, GENERIC_AUDIO_TIMELINE);
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
        await runFilm(page, 'k21_25', null, GENERIC_AUDIO_TIMELINE);
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
        await runFilm(page, 'k21_25', null, GENERIC_AUDIO_TIMELINE);
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
        await runFilm(page, 'k21_25', null, GENERIC_AUDIO_TIMELINE);
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
        await runFilm(page, 'k21_25', null, GENERIC_AUDIO_TIMELINE);
        await page.waitForTimeout(20);
        const delaysBeforeReplay = await page.evaluate(() => window.__pendingTimerDelays());
        if (!delaysBeforeReplay.some((d) => d >= 4000)) throw new Error(`expected a pending >=4000ms silent-hold timer before replay, got ${JSON.stringify(delaysBeforeReplay)}`);
        // Replaying through the same sequencer after _stopIntroFilm() must
        // clear that stale hold timer.  Inject the deterministic fixture into
        // the fresh run so a real Zone 2 silent shot cannot be mistaken for
        // the stale callback this test is targeting.
        await page.evaluate((timeline) => {
          window.__audioMode = 'success';
          _stopIntroFilm();
          playNewbieVillageIntroFilm({ key: 'k21_25' }, { timeline, mode: 'manual_replay' });
        }, GENERIC_AUDIO_TIMELINE);
        const delaysAfterReplay = await page.evaluate(() => window.__pendingTimerDelays());
        if (delaysAfterReplay.some((d) => d >= 4000)) throw new Error(`stale silent-hold timer survived replay: ${JSON.stringify(delaysAfterReplay)}`);
      });
    }, results);

    // --- H. TTS prohibition, explicit ---
    await test('H: narration failure path never calls playBrowserVoice/speechSynthesis', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await page.evaluate(() => { window.__audioMode = 'error'; });
        await runFilm(page, 'k21_25', null, GENERIC_AUDIO_TIMELINE);
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
    // 2026-08-09 update (E10-Z1-AUDIO-PRODUCTION-001): Zone 1 now has real
    // audioSrc on every non-silent beat (the "zero audioSrc" assumption
    // these tests were originally written under, see the file header, no
    // longer holds). A beat with audioSrc waits on Audio.onended -- i.e. on
    // window.__pendingSuccessAudio, drained via __finishNextSuccessAudio()
    // -- not on a fake timer; a beats:[] silence shot (S3/S5/S7/S9) still
    // waits on a pure fake timer, unchanged. Drain whichever is ready,
    // audio first (matches production: the audio object already exists by
    // the time its "slot" is checked), recording state after every step.
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
        while (iterations < 1000) {
          iterations++;
          if (window.__pendingSuccessAudio.length) {
            window.__finishNextSuccessAudio();
            record();
            continue;
          }
          if (window.__fakeTimers.length) {
            window.__fakeTimers.sort((a, b) => a.delay - b.delay);
            const t = window.__fakeTimers.shift();
            t.fn();
            record();
            continue;
          }
          break;
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

    // Drives BOSS_READY (Shots 7-8) directly, bypassing the
    // _adventureBossReady()-gated trigger -- for testing the cinematic
    // PLAYBACK mechanics in isolation. The gating itself (autoplay-once,
    // authoritative-condition-only, no-force-battle) has its own dedicated
    // tests further below, driven through updateMapProgress() with
    // synthetic zone data instead.
    async function runBossReadyFilm(page, zoneKey) {
      await page.evaluate((key) => {
        const overlay = document.getElementById('boss-cinematic');
        if (overlay) overlay.dataset.zoneKey = key;
        playZone1BossReadyFilm({ key });
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
    // 2026-08-09 (E10-Z1-CINEMATIC-TRIGGER-REALIGNMENT): ZONE_ENTRY is now
    // Shots 1-6 only (Shots 7-8 moved to the separate BOSS_READY
    // announcement, see the "BR:" tests below) -- title/shot-count updated
    // to match; the never-9/10 and audio/TTS assertions are unchanged.
    await test('J: Zone 1 ZONE_ENTRY plays exactly Shots 1-6, never 7/8/9/10, real narration audio, zero TTS calls', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const log = await recordFilmRun(page, (p) => runFilm(p, 'k26_30'));
        const seenShots = new Set(log.map((entry) => entry.activeIdx).filter((idx) => idx >= 0));
        if (seenShots.size !== 6) throw new Error(`expected exactly Shots 1-6 (6 distinct indices) to play, got ${JSON.stringify([...seenShots].sort((a, b) => a - b))} from log ${JSON.stringify(log)}`);
        if (seenShots.has(6) || seenShots.has(7) || seenShots.has(8) || seenShots.has(9)) throw new Error(`ZONE_ENTRY must never activate Shot 7/8/9/10 (indices 6-9), saw ${JSON.stringify([...seenShots])}`);
        const overlayReady = await page.evaluate(() => document.getElementById('boss-cinematic').classList.contains('ready'));
        if (!overlayReady) throw new Error('expected Zone 1 ZONE_ENTRY to reach ready state after Shot 6');
        const showsTitleCard = await page.evaluate(() => document.getElementById('intro-film-stage').classList.contains('show-title-card'));
        if (showsTitleCard) throw new Error('Zone 1 PRE_PLAY hand-off must not show the legacy title card (Fix 2)');
        // 2026-08-09: Zone 1 now has real recorded narration (audioSrc) on
        // every non-silent beat -- window.Audio construction is now
        // EXPECTED (dialogue narration + the main-theme BGM/ambience beds),
        // unlike the old "no recorded narration yet" assumption. TTS must
        // still never be used now that real recordings exist.
        const audioCreated = await page.evaluate(() => window.__audioLog.some((e) => e.event === 'created'));
        if (!audioCreated) throw new Error('expected window.Audio to be constructed for Zone 1 PRE_PLAY narration/BGM now that real assets exist');
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

    // --- L. S2/S4/S6 multi-beat order is exact canonical text, not a flattened/prefixed string ---
    // 2026-08-09 (E10-Z1-CINEMATIC-TRIGGER-REALIGNMENT): S8 moved out of
    // ZONE_ENTRY into the separate BOSS_READY announcement -- see the "BR:"
    // tests below for S7/S8 coverage. Exercises BOTH locales explicitly
    // (zh-TW is the page's ambient default; en is set via I18n.setLang
    // before kickoff) -- the whole point of this Zone 1 work is a correct
    // bilingual contract, so this must not silently only ever check
    // whichever locale happens to be ambient.
    const L_EXPECTED_BY_LOCALE = {
      zh: {
        1: ['孩子，天亮了。', '早啊，小水。'], // S2
        3: ['你看，那片雲。', '它已經停在那裡三天了。', '而且……每天都更近一點。'], // S4
        5: ['我不知道自己行不行……', '但我想去看看。'], // S6
      },
      en: {
        1: ['Morning, child.', 'Morning, Shui.'], // S2
        3: ["Look at that cloud.", "It's been sitting there for three days.", 'And... every day, it gets a little closer.'], // S4
        5: ["I don't know if I can do this...", 'But I want to go see for myself.'], // S6
      },
    };
    for (const [localeLabel, expected] of Object.entries(L_EXPECTED_BY_LOCALE)) {
      await test(`L (${localeLabel}): Zone 1 ZONE_ENTRY multi-beat shots (S2/S4/S6) play beats in exact canonical order`, async () => {
        await withFreshPage(browser, origin, async (page) => {
          if (localeLabel === 'en') {
            await page.evaluate(() => { if (window.I18n && window.I18n.setLang) window.I18n.setLang('en'); });
          }
          const log = await recordFilmRun(page, (p) => runFilm(p, 'k26_30'));
          const mismatches = [];
          for (const [shotIdx, expectedBeats] of Object.entries(expected)) {
            const actualFull = beatsForShot(log, Number(shotIdx));
            // 2026-08-09: for the LAST ZONE_ENTRY shot (S6, index 5), natural
            // completion synchronously updates #boss-cinematic-line to the
            // new post-training "ready state" copy (section 8) as part of
            // the same recordFilmRun step that reaches it -- a real,
            // intentional UI update, not a spoken beat. Compare only the
            // canonical spoken-beat prefix; anything appended after that
            // is post-completion chrome, not part of this shot's dialogue.
            const actual = actualFull.slice(0, expectedBeats.length);
            if (JSON.stringify(actual) !== JSON.stringify(expectedBeats)) {
              mismatches.push({ shot: shotIdx, expected: expectedBeats, actual: actualFull });
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
    }

    // --- IPAD. iPad/Safari-like narration media-session boundary ---
    // A real iPad acceptance run kept subtitles/BGM/timeline alive but lost
    // voice beginning at S4-B1 ("你看，那片雲"). The production assets are
    // present; the platform-sensitive boundary is the fourth fresh dialogue
    // Audio element. This policy fake models that failure while requiring the
    // production fix to reuse one narration element across every beat. BGM,
    // ambience, and SFX remain separate beds and are not covered by this
    // policy.
    const IPAD_EXPECTED_ZH_DIALOGUE = [
      '/assets/e10/audio/zone1/dialogue/zone1_final_shot01_beat01_zh_anna.mp3',
      '/assets/e10/audio/zone1/dialogue/zone1_final_shot02_beat01_zh_elder.mp3',
      '/assets/e10/audio/zone1/dialogue/zone1_final_shot02_beat02_zh_hero.mp3',
      '/assets/e10/audio/zone1/dialogue/zone1_final_shot04_beat01_zh_elder.mp3',
      '/assets/e10/audio/zone1/dialogue/zone1_final_shot04_beat02_zh_elder.mp3',
      '/assets/e10/audio/zone1/dialogue/zone1_final_shot04_beat03_zh_elder.mp3',
      '/assets/e10/audio/zone1/dialogue/zone1_final_shot06_beat01_zh_hero.mp3',
      '/assets/e10/audio/zone1/dialogue/zone1_final_shot06_beat02_zh_hero.mp3',
    ];
    async function dialoguePlaySources(page) {
      return page.evaluate(() => window.__audioLog
        .filter((entry) => entry.event === 'play' && entry.src.includes('/dialogue/'))
        .map((entry) => entry.src));
    }
    async function policyRejections(page) {
      return page.evaluate(() => window.__audioLog
        .filter((entry) => entry.event === 'play-rejected-policy')
        .map((entry) => entry.src));
    }
    await test('IPAD: iPad-like media policy preserves S4-B1 and all later Zone 1 narration in first-entry and replay', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await page.evaluate(() => {
          window.__audioPolicy = 'ipad-single-narration-element';
          window.__dialogueAudioElementCount = 0;
        });
        await recordFilmRun(page, (p) => runFilm(p, 'k26_30', 'first_entry'));
        const firstEntrySources = await dialoguePlaySources(page);
        const firstEntryRejected = await policyRejections(page);
        if (JSON.stringify(firstEntrySources) !== JSON.stringify(IPAD_EXPECTED_ZH_DIALOGUE)) {
          throw new Error(`first-entry narration cue sequence mismatch: ${JSON.stringify(firstEntrySources)}`);
        }
        if (firstEntryRejected.length) {
          throw new Error(`first-entry narration hit the iPad-like fresh-element policy: ${JSON.stringify(firstEntryRejected)}`);
        }
        const firstEntryBgmCount = await page.evaluate(() => window.__audioLog
          .filter((entry) => entry.event === 'play' && entry.src.includes('/zone1/bgm/zone1_bgm_main_theme.mp3')).length);
        if (firstEntryBgmCount !== 1) throw new Error(`expected one continuous main BGM start for first-entry, got ${firstEntryBgmCount}`);

        const replaySources = await recordFilmRun(page, (p) => p.evaluate(() => {
          window.__audioPolicy = 'ipad-single-narration-element';
          window.__dialogueAudioElementCount = 0;
          window.__audioLog = [];
          replayIntroFilm();
        }));
        const replayDialogueSources = await dialoguePlaySources(page);
        const replayRejected = await policyRejections(page);
        if (JSON.stringify(replayDialogueSources) !== JSON.stringify(IPAD_EXPECTED_ZH_DIALOGUE)) {
          throw new Error(`replay narration cue sequence mismatch: ${JSON.stringify(replayDialogueSources)}`);
        }
        if (replayRejected.length) {
          throw new Error(`replay narration hit the iPad-like fresh-element policy: ${JSON.stringify(replayRejected)}`);
        }
        if (!replaySources.some((entry) => entry.activeIdx === 5 && entry.lineText === '但我想去看看。')) {
          throw new Error('replay did not reach the final Zone 1 spoken cue');
        }
      });
    }, results);

    // --- BR. BOSS_READY (Shots 7-8) playback mechanics: silent S7 then canonical S8 dialogue ---
    await test('BR: BOSS_READY plays exactly Shot 7 (silent) then Shot 8 (canonical DL-01 dialogue), never other shots', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const log = await recordFilmRun(page, (p) => runBossReadyFilm(p, 'k26_30'));
        const order = [];
        for (const entry of log) {
          if (entry.activeIdx >= 0 && order[order.length - 1] !== entry.activeIdx) order.push(entry.activeIdx);
        }
        if (JSON.stringify(order) !== JSON.stringify([6, 7])) {
          throw new Error(`expected BOSS_READY shot order [6,7] (Shot 7 then Shot 8), got ${JSON.stringify(order)}`);
        }
        const shot7Beats = beatsForShot(log, 6).filter((t) => t !== '');
        if (shot7Beats.length) throw new Error(`expected Shot 7 (S7) to be silent, saw subtitle text: ${JSON.stringify(shot7Beats)}`);
        const shot8Beats = beatsForShot(log, 7);
        const expected = ['想出村，就先陪我下一局。', '別急。', '看清楚，再落子。'];
        if (JSON.stringify(shot8Beats) !== JSON.stringify(expected)) {
          throw new Error(`Shot 8 (DL-01) beat mismatch: expected ${JSON.stringify(expected)}, got ${JSON.stringify(shot8Beats)}`);
        }
      });
    }, results);

    await test('BR: BOSS_READY does not force battle entry -- completion just closes the overlay', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await recordFilmRun(page, (p) => runBossReadyFilm(p, 'k26_30'));
        const overlayHidden = await page.evaluate(() => document.getElementById('boss-cinematic').getAttribute('aria-hidden'));
        if (overlayHidden !== 'true') throw new Error(`expected BOSS_READY completion to close the overlay (aria-hidden=true), got ${overlayHidden}`);
        // No boss-battle-only DOM signal (phase-seal class, etc.) may be present.
        const overlayClass = await page.evaluate(() => document.getElementById('boss-cinematic').className);
        if (/phase-seal/.test(overlayClass)) throw new Error(`expected no battle-entry class after BOSS_READY completion, got ${overlayClass}`);
      });
    }, results);

    // --- M. Structural proof: getIntroFilmLocaleConfig itself separates PRE_PLAY from POST_CLEAR ---
    // 2026-08-09 (E10-Z1-CINEMATIC-TRIGGER-REALIGNMENT): the three-array
    // structure now matches the three-act model exactly: `timeline`
    // (ZONE_ENTRY, Shots 1-6) / `bossReadyTimeline` (BOSS_READY, Shots 7-8)
    // / `postClearTimeline` (POST_CLEAR, Shots 9-10).
    await test('M: Zone 1 config has exactly 6 ZONE_ENTRY (0-5), 2 BOSS_READY (6-7), 2 POST_CLEAR (8-9) shots, both locales', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const result = await page.evaluate(() => {
          const zh = getIntroFilmLocaleConfig({ key: 'k26_30' });
          if (window.I18n && window.I18n.setLang) window.I18n.setLang('en');
          const en = getIntroFilmLocaleConfig({ key: 'k26_30' });
          const shotList = (tl) => (tl || []).map((s) => s.shot);
          const beatCounts = (tl) => (tl || []).map((s) => (s.beats || []).length);
          return {
            zhTimelineShots: shotList(zh.timeline), zhBossReadyShots: shotList(zh.bossReadyTimeline), zhPostClearShots: shotList(zh.postClearTimeline),
            enTimelineShots: shotList(en.timeline), enBossReadyShots: shotList(en.bossReadyTimeline), enPostClearShots: shotList(en.postClearTimeline),
            zhBeatCounts: beatCounts(zh.timeline).concat(beatCounts(zh.bossReadyTimeline)).concat(beatCounts(zh.postClearTimeline)),
            enBeatCounts: beatCounts(en.timeline).concat(beatCounts(en.bossReadyTimeline)).concat(beatCounts(en.postClearTimeline)),
            zhHasFinalCaption: 'finalCaption' in zh, zhHasFinalLine: 'finalLine' in zh,
            enHasFinalCaption: 'finalCaption' in en, enHasFinalLine: 'finalLine' in en,
            zhHasBgmMainTheme: typeof zh.bgmMainTheme === 'string' && zh.bgmMainTheme.length > 0,
            zhHasBgmPostClear: typeof zh.bgmPostClearUrgency === 'string' && zh.bgmPostClearUrgency.length > 0,
            zhHasAmbience: typeof zh.ambienceVillageDawn === 'string' && zh.ambienceVillageDawn.length > 0,
          };
        });
        const expectedTimeline = [0, 1, 2, 3, 4, 5];
        const expectedBossReady = [6, 7];
        const expectedPostClear = [8, 9];
        const expectedBeatCounts = [1, 2, 0, 3, 0, 2, 0, 3, 0, 3]; // S1..S10, unchanged overall
        for (const [label, actual, expected] of [
          ['zh timeline', result.zhTimelineShots, expectedTimeline],
          ['zh bossReady', result.zhBossReadyShots, expectedBossReady],
          ['zh postClear', result.zhPostClearShots, expectedPostClear],
          ['en timeline', result.enTimelineShots, expectedTimeline],
          ['en bossReady', result.enBossReadyShots, expectedBossReady],
          ['en postClear', result.enPostClearShots, expectedPostClear],
          ['zh beat counts', result.zhBeatCounts, expectedBeatCounts],
          ['en beat counts', result.enBeatCounts, expectedBeatCounts],
        ]) {
          if (JSON.stringify(actual) !== JSON.stringify(expected)) {
            throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
          }
        }
        if (!result.zhHasBgmMainTheme || !result.zhHasBgmPostClear || !result.zhHasAmbience) {
          throw new Error(`expected bgmMainTheme/bgmPostClearUrgency/ambienceVillageDawn to remain defined: ${JSON.stringify(result)}`);
        }
        // Fix 2: no legacy finalCaption/finalLine exposition anywhere in Zone 1's config.
        if (result.zhHasFinalCaption || result.zhHasFinalLine || result.enHasFinalCaption || result.enHasFinalLine) {
          throw new Error(`Zone 1 config must not define finalCaption/finalLine: ${JSON.stringify(result)}`);
        }
      });
    }, results);

    // --- BG. BOSS_READY gating: reuses the authoritative _adventureBossReady() predicate, autoplay-once ---
    function notReadyZone() {
      return { key: 'k26_30', cleared: false, boss: { available: false, remaining_to_challenge: 5 } };
    }
    function readyZone() {
      return { key: 'k26_30', cleared: false, boss: { available: true, remaining_to_challenge: 0 } };
    }

    await test('BG: BOSS_READY never triggers while _adventureBossReady(zone) is false', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await page.evaluate((zone) => { updateMapProgress({ zones: [zone] }); }, notReadyZone());
        const phase = await page.evaluate(() => _introFilmActiveOpts.phase);
        const overlayHidden = await page.evaluate(() => document.getElementById('boss-cinematic').getAttribute('aria-hidden'));
        if (phase === 'boss_ready') throw new Error('BOSS_READY must not trigger while boss is not ready');
        if (overlayHidden === 'false') throw new Error('cinematic overlay must not open while boss is not ready');
      });
    }, results);

    await test('BG: BOSS_READY triggers exactly once on the authoritative ready state, not again on repeat renders', async () => {
      await withFreshPage(browser, origin, async (page) => {
        // Not ready yet -- no-op.
        await page.evaluate((zone) => { updateMapProgress({ zones: [zone] }); }, notReadyZone());
        // Now ready -- must trigger BOSS_READY (Shots 7-8) automatically.
        await page.evaluate((zone) => { updateMapProgress({ zones: [zone] }); }, readyZone());
        const phaseAfterFirstReady = await page.evaluate(() => _introFilmActiveOpts.phase);
        if (phaseAfterFirstReady !== 'boss_ready') throw new Error(`expected the first ready transition to trigger BOSS_READY, phase was ${JSON.stringify(phaseAfterFirstReady)}`);
        await drainAllFakeTimers(page);
        const overlayHiddenAfterComplete = await page.evaluate(() => document.getElementById('boss-cinematic').getAttribute('aria-hidden'));
        if (overlayHiddenAfterComplete !== 'true') throw new Error('expected BOSS_READY to close the overlay after completion');
        const audioCountAfterFirst = await page.evaluate(() => window.__audioLog.filter((e) => e.event === 'created').length);
        // Re-render with the SAME ready state again (e.g. a second progress
        // poll) -- must be a no-op: no re-trigger, no new audio.
        await page.evaluate((zone) => { updateMapProgress({ zones: [zone] }); }, readyZone());
        const overlayHiddenAfterRepeat = await page.evaluate(() => document.getElementById('boss-cinematic').getAttribute('aria-hidden'));
        const audioCountAfterRepeat = await page.evaluate(() => window.__audioLog.filter((e) => e.event === 'created').length);
        if (overlayHiddenAfterRepeat !== 'true') throw new Error('expected a repeat ready render NOT to reopen the cinematic overlay');
        if (audioCountAfterRepeat !== audioCountAfterFirst) throw new Error(`expected no new audio on a repeat ready render, had ${audioCountAfterFirst} then ${audioCountAfterRepeat}`);
      });
    }, results);

    await test('BG: BOSS_READY does not fire again after the boss is later defeated (zone.cleared)', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await page.evaluate((zone) => { updateMapProgress({ zones: [zone] }); }, readyZone());
        await drainAllFakeTimers(page);
        const clearedZone = { key: 'k26_30', cleared: true, boss: { available: true, remaining_to_challenge: 0 } };
        await page.evaluate((zone) => { updateMapProgress({ zones: [zone] }); }, clearedZone);
        const overlayHidden = await page.evaluate(() => document.getElementById('boss-cinematic').getAttribute('aria-hidden'));
        if (overlayHidden !== 'true') throw new Error('expected no BOSS_READY re-trigger once the zone is cleared');
      });
    }, results);

    await test('BG: RELOAD_AFTER_BOSS_READY_SEEN -- a real page reload does not replay the announcement again', async () => {
      // Unlike POST_CLEAR, BOSS_READY has no "pending" flag to recover --
      // it's a stable re-derivable state, so "seen" alone (persisted in
      // localStorage, which genuinely survives a real reload) is enough to
      // prove reload-safety end to end.
      const page = await browser.newPage();
      await page.addInitScript(FAKE_INIT_SCRIPT);
      await page.route('**/api/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
      await page.route('**/api/auth/me', (route) => route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ logged_in: true, user_id: 1, username: 'bossready_reload_tester', display_name: 'Boss Ready Reload Tester', is_admin: false, is_premium: false, needs_onboarding_choice: false, tour_done: true, elo_rating: 1200 })
      }));
      try {
        await page.goto(origin + '/index.html', { waitUntil: 'domcontentloaded' });
        await page.evaluate(() => { window.__audioMode = 'success'; _currentUserId = 1; });
        await page.evaluate((zone) => { updateMapProgress({ zones: [zone] }); }, readyZone());
        await drainAllFakeTimers(page);
        const seenBeforeReload = await page.evaluate(() => JSON.parse(localStorage.getItem('adventure_bossready_seen_v1') || '{}'));
        if (!seenBeforeReload['1']?.k26_30) throw new Error('test setup invalid: expected boss-ready seen to be set before reload');
        // A real reload: in-memory JS state is genuinely gone, only localStorage survives.
        await page.goto(origin + '/index.html', { waitUntil: 'domcontentloaded' });
        await page.evaluate(() => { window.__audioMode = 'success'; _currentUserId = 1; });
        await page.evaluate((zone) => { updateMapProgress({ zones: [zone] }); }, readyZone());
        const phaseAfterReload = await page.evaluate(() => _introFilmActiveOpts.phase);
        const overlayHiddenAfterReload = await page.evaluate(() => document.getElementById('boss-cinematic').getAttribute('aria-hidden'));
        if (phaseAfterReload === 'boss_ready') throw new Error('expected reload NOT to replay BOSS_READY once already seen');
        if (overlayHiddenAfterReload === 'false') throw new Error('expected the cinematic overlay to stay closed after reload once BOSS_READY was already seen');
      } finally {
        await page.close();
      }
    }, results);

    // --- N & O. GENUINE_CLEAR = S9 THEN S10 / S10 multi-beat order exact / zero audio/TTS ---
    await test('N: Zone 1 POST_CLEAR plays exactly Shot 9 then Shot 10, real narration audio, zero TTS calls', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const log = await recordFilmRun(page, (p) => runPostClearFilm(p, 'k26_30'));
        const order = [];
        for (const entry of log) {
          if (entry.activeIdx >= 0 && order[order.length - 1] !== entry.activeIdx) order.push(entry.activeIdx);
        }
        if (JSON.stringify(order) !== JSON.stringify([8, 9])) {
          throw new Error(`expected POST_CLEAR shot order [8,9] (Shot 9 then Shot 10), got ${JSON.stringify(order)} from log ${JSON.stringify(log)}`);
        }
        // 2026-08-09: Shot 10 now has real recorded narration + a BGM/SFX
        // cue; Shot 9 stays silent by design (no beats, no BGM). Audio
        // construction is expected overall; TTS must still never fire.
        const audioCreated = await page.evaluate(() => window.__audioLog.some((e) => e.event === 'created'));
        if (!audioCreated) throw new Error('expected window.Audio to be constructed for Shot 10 narration/BGM/SFX now that real assets exist');
        const speakCalls = await page.evaluate(() => window.__speakCalls);
        if (speakCalls !== 0) throw new Error(`expected 0 TTS calls across Zone 1 POST_CLEAR, got ${speakCalls}`);
      });
    }, results);

    const O_EXPECTED_SHOT10_BY_LOCALE = {
      zh: ['村長！', '史萊姆平原的商隊……', '三天了，還沒回來！'],
      en: ['Elder!', 'The caravan from the Slime Plains...', "It's been three days, and they still haven't come back!"],
    };
    for (const [localeLabel, expected] of Object.entries(O_EXPECTED_SHOT10_BY_LOCALE)) {
      await test(`O (${localeLabel}): Zone 1 POST_CLEAR Shot 9 is silent, Shot 10 plays exact canonical 3-beat order, no extra line after`, async () => {
        await withFreshPage(browser, origin, async (page) => {
          if (localeLabel === 'en') {
            await page.evaluate(() => { if (window.I18n && window.I18n.setLang) window.I18n.setLang('en'); });
          }
          const log = await recordFilmRun(page, (p) => runPostClearFilm(p, 'k26_30'));
          const shot9Beats = beatsForShot(log, 8).filter((t) => t !== '');
          if (shot9Beats.length) throw new Error(`expected Shot 9 (S9) to be silent, saw subtitle text: ${JSON.stringify(shot9Beats)}`);
          const shot10Beats = beatsForShot(log, 9);
          if (JSON.stringify(shot10Beats) !== JSON.stringify(expected)) {
            throw new Error(`Shot 10 beat mismatch: expected ${JSON.stringify(expected)}, got ${JSON.stringify(shot10Beats)}`);
          }
          // Fix 2: nothing (no Hero response, no thesis line) may play after
          // Shot 10's last beat. Read this off the drain loop's own last
          // recorded entry rather than a separate page.evaluate() round-trip
          // -- with Shot 10 now driven by real audio-completion steps (not
          // just fake timers), a later separate evaluate() introduces an
          // async gap where the harness's own microtask/IPC timing can be
          // observed mid-flight; the log's last entry is captured at the
          // same synchronous point production code settles on.
          const finalLineAfterComplete = log[log.length - 1]?.lineText || '';
          if (finalLineAfterComplete !== expected[expected.length - 1]) {
            throw new Error(`expected the subtitle to still read Shot 10's own last line after completion, got ${JSON.stringify(finalLineAfterComplete)}`);
          }
        });
      }, results);
    }

    // --- P. finishPostClearFilm marks seen and closes the overlay (no reward/settlement call, visual-only) ---
    await test('P: Zone 1 POST_CLEAR completion marks postClearSeen and closes the overlay', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await recordFilmRun(page, (p) => runPostClearFilm(p, 'k26_30'));
        const seen = await page.evaluate(() => {
          const raw = localStorage.getItem('adventure_postclear_seen_v1');
          return raw ? JSON.parse(raw) : {};
        });
        // Account-scoped storage: adventure_postclear_seen_v1 is now nested
        // {[userId]: {[zoneKey]: timestamp}} -- withFreshPage's default
        // mocked /api/auth/me resolves _currentUserId to 1.
        if (!seen['1']?.k26_30) throw new Error(`expected adventure_postclear_seen_v1['1'].k26_30 to be set after completion, got ${JSON.stringify(seen)}`);
        const overlayHidden = await page.evaluate(() => document.getElementById('boss-cinematic').getAttribute('aria-hidden'));
        if (overlayHidden !== 'true') throw new Error(`expected the overlay to close (aria-hidden=true) after POST_CLEAR completes, got ${overlayHidden}`);
      });
    }, results);

    // --- Q. authoritative Lord success trigger fires once, is a no-op once already seen ---
    await test('Q: _triggerZone1PostClearFromBossWin is idempotent (fires once per zone)', async () => {
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
          // level); the authoritative Lord-success trigger uses the explicit
          // ADVENTURE_ZONES.find(...) when it's empty, so no override needed.
          _triggerZone1PostClearFromBossWin({ key: 'k26_30' });
          return document.getElementById('boss-cinematic').className;
        });
        if (!/intro-film/.test(firstRun)) throw new Error(`expected first trigger to open the POST_CLEAR film, overlay class was ${JSON.stringify(firstRun)}`);
        // window.__flushFakeTimers() only drains fake timers -- Shot 10 now
        // also needs pending audio completions drained (real narration/BGM/
        // SFX). drainAllFakeTimers (defined below, hoisted) does both.
        await drainAllFakeTimers(page);
        const seenAfterFirst = await page.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_seen_v1') || '{}'));
        if (!seenAfterFirst['1']?.k26_30) throw new Error('expected postClearSeen to be set (account-scoped under user "1") after the first trigger completes');
        const secondRunClass = await page.evaluate(() => {
          const before = document.getElementById('boss-cinematic').className;
          _triggerZone1PostClearFromBossWin({ key: 'k26_30' });
          const after = document.getElementById('boss-cinematic').className;
          return { before, after };
        });
        if (secondRunClass.before !== secondRunClass.after) {
          throw new Error(`expected a second trigger (already seen) to be a no-op, overlay class changed from ${JSON.stringify(secondRunClass.before)} to ${JSON.stringify(secondRunClass.after)}`);
        }
      });
    }, results);

    // --- R. Source-level: no reward/settlement authority in cinematic code; only Lord success can trigger ---
    await test('R: Zone 1 lifecycle functions contain no reward/settlement calls; ordinary Map Battle cannot trigger POST_CLEAR', async () => {
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
      const cinematicFns = ['playZone1PostClearFilm', 'finishPostClearFilm', '_resumeZone1PostClearIfPending', 'replayIntroFilm', 'skipIntroFilm'];
      const violations = [];
      for (const fn of cinematicFns) {
        const body = extractFunctionBody(fn);
        if (/fetch\s*\(|credentials\s*:|\.submit\s*\(|\/api\//.test(body)) {
          violations.push(`${fn} appears to contain a network/reward/settlement call`);
        }
      }
      if (violations.length) throw new Error(violations.join('; '));
      // Ordinary Map Battle monster_defeated is presentation-only. It must
      // never reach the Zone POST_CLEAR trigger, pending/seen storage, or the
      // next-zone reveal path.
      const monsterDefeatedBranch = source.match(/if \(response\.next_action === 'monster_defeated'\) \{[\s\S]*?\n\s{16}\}/);
      if (!monsterDefeatedBranch) {
        throw new Error("monster_defeated branch not found in _submitMapBattleV1IfActive");
      }
      const ordinaryForbidden = /_triggerZone1PostClearFromBossWin|playZone1PostClearFilm|markAdventurePostClearPending|markAdventurePostClearSeen|showZone1UnlockReveal/;
      if (ordinaryForbidden.test(monsterDefeatedBranch[0])) {
        throw new Error('ordinary monster_defeated branch contains a Zone POST_CLEAR/reveal authority call');
      }
      const lordResultCard = source.match(/function showZone1LordResultCard\([\s\S]*?\n\}/);
      if (!lordResultCard || !lordResultCard[0].includes('_triggerZone1PostClearFromBossWin(zone)')) {
        throw new Error('authoritative Lord result card does not wire success to Zone POST_CLEAR');
      }
      const callOnly = source.match(/(?<!function )_triggerZone1PostClearFromBossWin\(zone\)/g) || [];
      if (callOnly.length !== 1) {
        throw new Error(`expected exactly 1 gameplay call site of _triggerZone1PostClearFromBossWin(zone), found ${callOnly.length}`);
      }
      // Structural proof postClearTimeline is never reachable from the
      // PRE_PLAY entry path (showStageIntroCinematic never references it).
      const showStageBody = extractFunctionBody('showStageIntroCinematic');
      if (showStageBody.includes('postClearTimeline')) {
        throw new Error('showStageIntroCinematic must never reference postClearTimeline -- S9/S10 must be structurally unreachable before a genuine clear');
      }
    }, results);

    // --- S & T. Reload/close resilience: a genuine clear left pending mid-S9/S10 must recover ---
    // The real trigger (_triggerZone1PostClearFromBossWin) marks pending BEFORE
    // playback starts and only clears it in finishPostClearFilm (normal
    // completion/skip). Simulate "reload" with a REAL page.goto() re-
    // navigation on the SAME page/context, so localStorage genuinely
    // persists across it exactly as a browser reload would -- this is not
    // simulated via a fresh isolated context (withFreshPage's newPage()
    // would NOT share localStorage).
    // 2026-08-09: one "step" now means either finishing one pending audio
    // (audio-backed beats, e.g. Zone 1's Shot 10 dialogue) or firing one
    // fake timer (silence shots / post-audio hold delays) -- audio first,
    // matching recordFilmRun's same priority. See that function's comment
    // for why Zone 1 no longer drives purely off fake timers.
    async function drainOneFakeTimer(page) {
      await page.evaluate(() => {
        if (window.__pendingSuccessAudio.length) {
          window.__finishNextSuccessAudio();
          return;
        }
        window.__fakeTimers.sort((a, b) => a.delay - b.delay);
        const t = window.__fakeTimers.shift();
        if (t) t.fn();
      });
    }
    async function drainAllFakeTimers(page) {
      let iterations = 0;
      while (
        (await page.evaluate(() => window.__fakeTimers.length || window.__pendingSuccessAudio.length))
        && iterations < 500
      ) {
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
        // Set deterministically rather than relying on window.onload's
        // async getMe() to have resolved by the time this runs (a real
        // race against 'domcontentloaded' -- see gotoAsUser's identical
        // reasoning below). The value matches the mocked /api/auth/me
        // response above, so this doesn't fight the real bootstrap even if
        // it does complete later.
        _currentUserId = 1;
        _adventureActiveQuestions = [{ topic: 'Beginner Village' }];
        _triggerZone1PostClearFromBossWin({ key: 'k26_30' });
      });
      for (let i = 0; i < drainsBeforeReload; i++) await drainOneFakeTimer(page1);
      const pendingBeforeReload = await page1.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_pending_v1') || '{}'));
      const seenBeforeReload = await page1.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_seen_v1') || '{}'));
      // Account-scoped storage: nested {[userId]: {[zoneKey]: timestamp}} --
      // this helper's mocked /api/auth/me resolves _currentUserId to 1.
      if (!pendingBeforeReload['1']?.k26_30) throw new Error('test setup invalid: expected pending to be set before reload');
      if (seenBeforeReload['1']?.k26_30) throw new Error('test setup invalid: expected NOT seen before reload (reload happened too late)');
      // A real reload: re-navigate the same page/context. FAKE_INIT_SCRIPT
      // re-applies via addInitScript on every navigation, so fakes are back
      // in place, but all in-memory JS state (_introFilmActiveOpts, the
      // overlay's DOM, etc.) is genuinely gone -- only localStorage survives.
      await page1.goto(origin + '/index.html', { waitUntil: 'domcontentloaded' });
      await page1.evaluate(() => { window.__audioMode = 'success'; _currentUserId = 1; });
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
        if (!seenAfter['1']?.k26_30) throw new Error('expected seen to be set after the resumed playback completes');
        const pendingAfter = await page.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_pending_v1') || '{}'));
        if (pendingAfter['1']?.k26_30) throw new Error('expected pending to be cleared after completion');
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
        if (!seenAfter['1']?.k26_30) throw new Error('expected seen to be set after the resumed playback completes');
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

    // --- V-Y. Account-scoped POST_CLEAR state (Owner final review) ---
    // adventure_postclear_seen_v1/pending_v1 are now nested by the
    // authenticated user's id (_currentUserId, same convention as the
    // pre-existing _dailyLimitStorageKey() elsewhere in index.html), not
    // just by zone.key -- otherwise a shared browser lets one account's
    // POST_CLEAR state leak into another's. gotoAsUser() mocks
    // /api/auth/me to return a given user_id AND directly sets
    // _currentUserId to the same value immediately after navigation, so
    // these tests don't depend on timing between that assignment and
    // window.onload's async getMe() completing.
    async function gotoAsUser(page, userId) {
      await page.unroute('**/api/auth/me').catch(() => {});
      await page.route('**/api/auth/me', (route) => route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ logged_in: true, user_id: userId, username: `user_${userId}`, display_name: `User ${userId}`, is_admin: false, is_premium: false, needs_onboarding_choice: false, tour_done: true, elo_rating: 1200 })
      }));
      await page.goto(origin + '/index.html', { waitUntil: 'domcontentloaded' });
      await page.evaluate((uid) => {
        window.__audioMode = 'success';
        _currentUserId = uid;
      }, userId);
    }
    async function newSharedBrowserPage() {
      const page = await browser.newPage();
      await page.addInitScript(FAKE_INIT_SCRIPT);
      await page.route('**/api/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
      return page;
    }
    async function triggerGenuineClearForCurrentUser(page) {
      await page.evaluate(() => {
        _adventureActiveQuestions = [{ topic: 'Beginner Village' }];
        _triggerZone1PostClearFromBossWin({ key: 'k26_30' });
      });
    }

    await test('V: USER_A_CLEAR -> RELOAD_MID_S9 = User A resumes their own POST_CLEAR', async () => {
      const page = await newSharedBrowserPage();
      try {
        await gotoAsUser(page, 'userA');
        await triggerGenuineClearForCurrentUser(page);
        await drainOneFakeTimer(page); // mid-S9
        await gotoAsUser(page, 'userA'); // reload as the SAME user
        await page.evaluate(() => { updateMapProgress({ zones: [] }); });
        const resumedPhase = await page.evaluate(() => _introFilmActiveOpts.phase);
        if (resumedPhase !== 'post_clear') throw new Error(`expected User A's reload to resume their own POST_CLEAR, got ${JSON.stringify(resumedPhase)}`);
      } finally {
        await page.close();
      }
    }, results);

    await test('W: USER_A_PENDING -> SWITCH_TO_USER_B = User B does not inherit User A\'s pending POST_CLEAR', async () => {
      const page = await newSharedBrowserPage();
      try {
        await gotoAsUser(page, 'userA');
        await triggerGenuineClearForCurrentUser(page);
        await drainOneFakeTimer(page); // User A mid-S9, pending[userA] = true
        await gotoAsUser(page, 'userB'); // same browser/context, different account
        await page.evaluate(() => { updateMapProgress({ zones: [] }); });
        const phaseAfterSwitch = await page.evaluate(() => _introFilmActiveOpts.phase);
        if (phaseAfterSwitch === 'post_clear') throw new Error("User B must not inherit/resume User A's pending POST_CLEAR");
        const seenAfterSwitch = await page.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_seen_v1') || '{}'));
        if (seenAfterSwitch.userB?.k26_30) throw new Error("User B's seen flag must not be set just from User A's pending state existing");
      } finally {
        await page.close();
      }
    }, results);

    await test('X: USER_A_SEEN -> USER_B_GENUINE_CLEAR = User B still receives their own S9-S10', async () => {
      const page = await newSharedBrowserPage();
      try {
        await gotoAsUser(page, 'userA');
        await triggerGenuineClearForCurrentUser(page);
        await drainAllFakeTimers(page); // User A completes: seen[userA] = true
        const seenA = await page.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_seen_v1') || '{}'));
        if (!seenA.userA?.k26_30) throw new Error('test setup invalid: expected User A to be seen before User B logs in');
        await gotoAsUser(page, 'userB');
        const triggeredForB = await page.evaluate(() => {
          _adventureActiveQuestions = [{ topic: 'Beginner Village' }];
          _triggerZone1PostClearFromBossWin({ key: 'k26_30' });
          return _introFilmActiveOpts.phase;
        });
        if (triggeredForB !== 'post_clear') throw new Error(`expected User B's own genuine clear to trigger POST_CLEAR despite User A already seen theirs, got ${JSON.stringify(triggeredForB)}`);
      } finally {
        await page.close();
      }
    }, results);

    await test('Y: switching back to User A restores their own pending state correctly', async () => {
      const page = await newSharedBrowserPage();
      try {
        await gotoAsUser(page, 'userA');
        await triggerGenuineClearForCurrentUser(page);
        await drainOneFakeTimer(page); // User A mid-S9, pending[userA] = true
        await gotoAsUser(page, 'userB'); // User B logs in, does nothing Zone-1-related
        await gotoAsUser(page, 'userA'); // back to User A
        await page.evaluate(() => { updateMapProgress({ zones: [] }); });
        const resumedPhase = await page.evaluate(() => _introFilmActiveOpts.phase);
        if (resumedPhase !== 'post_clear') throw new Error(`expected User A to recover their own pending POST_CLEAR after switching back, got ${JSON.stringify(resumedPhase)}`);
        await drainAllFakeTimers(page);
        const seenAfter = await page.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_seen_v1') || '{}'));
        if (!seenAfter.userA?.k26_30) throw new Error('expected User A seen to be set after their resumed playback completes');
        // 2026-08-09: real narration/BGM/SFX audio is now expected across a
        // full POST_CLEAR resume (audioCreated=true is correct, not a
        // reward/settlement leak) -- the invariant that actually matters is
        // TTS never firing, which remains true regardless of real audio.
        const audioCreated = await page.evaluate(() => window.__audioLog.some((e) => e.event === 'created'));
        const speakCalls = await page.evaluate(() => window.__speakCalls);
        if (!audioCreated) throw new Error('expected window.Audio to be constructed for User A\'s resumed POST_CLEAR playback');
        if (speakCalls !== 0) throw new Error(`expected 0 TTS calls across the whole account-switch/resume path, got speakCalls=${speakCalls}`);
      } finally {
        await page.close();
      }
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
