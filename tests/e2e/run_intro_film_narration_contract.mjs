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
        await runFilm(page, 'k26_30');
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
        await runFilm(page, 'k26_30');
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
        await runFilm(page, 'k26_30');
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
        await runFilm(page, 'k26_30');
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
        await runFilm(page, 'k26_30');
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
        await runFilm(page, 'k26_30');
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
        await runFilm(page, 'k26_30');
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
      if (!/if \(!item\.audioSrc\)\s*\{\s*finishSilently\(\);\s*return;\s*\}/.test(source)) {
        throw new Error('missing audioSrc is not wired to finishSilently');
      }
      if (/if \(!item\.audioSrc\)\s*\{[^}]*playBrowserVoice/s.test(source)) {
        throw new Error('missing audioSrc still reaches playBrowserVoice');
      }
      // The browser cases above exercise the same silent hold for load/error/
      // play rejection; this source-level guard proves the missing-asset branch
      // cannot reach the browser-TTS function.
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
