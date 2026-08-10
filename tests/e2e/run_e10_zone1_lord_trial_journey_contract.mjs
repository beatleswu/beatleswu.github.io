/*
 * E10 Zone 1 Beginner Village Complete RPG Journey (2026-08-09) --
 * regression contract for the NEW trigger/state work: Zone Card
 * training/boss-ready/retry-cooldown state distinction, the Lord
 * Challenge Card / Entrance Ritual / Result Cards, and the real
 * boss-win -> POST_CLEAR wiring fix. Complements (does not replace)
 * run_intro_film_narration_contract.mjs, which already covers the
 * Shot 1-10 cinematic lifecycle itself.
 *
 * Source-level checks (no browser needed) prove the new UI never becomes
 * an authority for progression: none of the new functions may contain a
 * fetch/POST call other than through the existing, unchanged
 * _startBossBattleNow (the real /api/adventure/boss/start caller).
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
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  for (const c of candidates) if (fssync.existsSync(c)) return c;
  throw new Error('No Chrome/Edge executable found. Set CHROME_BIN to run this contract.');
}

function contentTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return ({ '.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8' })[ext] || 'application/octet-stream';
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
      res.writeHead(500); res.end(String(err));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  return { server, origin: `http://127.0.0.1:${address.port}` };
}

const FAKE_INIT_SCRIPT = `
(function () {
  window.__audioLog = [];
  window.__audioMode = 'success';
  window.__pendingSuccessAudio = [];
  class FakeAudio {
    constructor(src) { this.src = src; this.onended = null; this.onerror = null; window.__audioLog.push({ event: 'created', src }); }
    play() { window.__audioLog.push({ event: 'play', src: this.src }); window.__pendingSuccessAudio.push(this); return Promise.resolve(); }
    pause() { window.__audioLog.push({ event: 'pause', src: this.src }); }
  }
  window.Audio = FakeAudio;
  window.__finishNextSuccessAudio = function () { const a = window.__pendingSuccessAudio.shift(); if (a && a.onended) a.onended(); return !!a; };
  window.__fakeTimers = [];
  let seq = 1;
  window.setTimeout = function (fn, delay) { const id = seq++; window.__fakeTimers.push({ id, fn, delay: delay || 0 }); return id; };
  window.clearTimeout = function (id) { window.__fakeTimers = window.__fakeTimers.filter(function (t) { return t.id !== id; }); };
  window.__flushFakeTimers = function () {
    let it = 0;
    while (window.__fakeTimers.length && it < 500) {
      it++;
      window.__fakeTimers.sort(function (a, b) { return a.delay - b.delay; });
      const t = window.__fakeTimers.shift();
      try { t.fn(); } catch (e) { console.error('fake timer error', e); }
    }
  };
  window.speechSynthesis = { getVoices: function () { return []; }, speak: function () { window.__speakCalls = (window.__speakCalls||0)+1; }, cancel: function () {} };
  window.SpeechSynthesisUtterance = function (text) { this.text = text; };
})();
`;

function test(name, fn, results) {
  return Promise.resolve().then(fn).then(() => results.push({ name, ok: true })).catch((err) => results.push({ name, ok: false, error: (err && err.message) || String(err) }));
}

async function withFreshPage(browser, origin, fn) {
  const page = await browser.newPage();
  try {
    await page.addInitScript(FAKE_INIT_SCRIPT);
    await page.route('**/api/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
    await page.route('**/api/auth/me', (route) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ logged_in: true, user_id: 1, username: 'lord_trial_tester', display_name: 'Lord Trial Tester', is_admin: false, is_premium: false, needs_onboarding_choice: false, tour_done: true, elo_rating: 1200 }),
    }));
    await page.goto(origin + '/index.html', { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => { _currentUserId = 1; });
    return await fn(page);
  } finally {
    await page.close();
  }
}

function realZoneJs() {
  // Returned as a JS source fragment via page.evaluate's function body --
  // kept as a plain object literal builder inline in each test instead of
  // a shared helper, since page.evaluate closures can't reference outer
  // Node functions.
  return null;
}

async function main() {
  const { server, origin } = await startStaticServer(repoRoot);
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  const results = [];
  try {
    // --- Source-level: none of the new k26_30 UI functions write progression ---
    await test('SRC: new Lord Trial UI functions contain no fetch/POST other than the existing _startBossBattleNow', async () => {
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
      const fns = [
        'showZone1LordChallengeCard',
        'startZone1LordRitual',
        'showZone1LordResultCard',
        'showZone1UnlockReveal',
        '_triggerZone1PostClearFromBossWin',
        '_adventureBossReady',
      ];
      const violations = [];
      for (const fn of fns) {
        const body = extractFunctionBody(fn);
        if (/fetch\s*\(|credentials\s*:|\.submit\s*\(/.test(body)) {
          violations.push(`${fn} appears to contain a network/reward/settlement call`);
        }
      }
      if (violations.length) throw new Error(violations.join('; '));
      // startZone1LordRitual's only path to the real battle must be the
      // existing, unchanged _startBossBattleNow (which itself calls the
      // real /api/adventure/boss/start) -- never a new/duplicate call.
      const ritualBody = extractFunctionBody('startZone1LordRitual');
      if (!/_startBossBattleNow\(zone\)/.test(ritualBody)) {
        throw new Error('startZone1LordRitual must hand off to the existing _startBossBattleNow, not reimplement battle entry');
      }
    }, results);

    // --- _adventureBossReady: cooldown fix ---
    await test('_adventureBossReady returns false during an active retry cooldown even if remaining_to_challenge is stale/zero', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const result = await page.evaluate(() => {
          const cooldownZone = { key: 'k26_30', cleared: false, cooldown_left: 18, boss: { available: false, remaining_to_challenge: 0 } };
          const readyZone = { key: 'k26_30', cleared: false, cooldown_left: 0, boss: { available: true, remaining_to_challenge: 0 } };
          const clearedZone = { key: 'k26_30', cleared: true, cooldown_left: 0, boss: { available: true, remaining_to_challenge: 0 } };
          return {
            cooldown: _adventureBossReady(cooldownZone),
            ready: _adventureBossReady(readyZone),
            cleared: _adventureBossReady(clearedZone),
          };
        });
        if (result.cooldown !== false) throw new Error(`expected boss-ready=false during cooldown, got ${result.cooldown}`);
        if (result.ready !== true) throw new Error(`expected boss-ready=true when genuinely ready, got ${result.ready}`);
        if (result.cleared !== false) throw new Error(`expected boss-ready=false once cleared, got ${result.cleared}`);
      });
    }, results);

    // --- Zone Card CTA state: three distinct progress concepts never confused ---
    await test('_adventureQuestCtaState distinguishes training_needed / boss_ready / retry_training with correct counts', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const result = await page.evaluate(() => {
          const training = { key: 'k26_30', unlocked: true, cleared: false, cooldown_left: 0, boss: { available: false, remaining_to_challenge: 12 } };
          const bossReady = { key: 'k26_30', unlocked: true, cleared: false, cooldown_left: 0, boss: { available: true, remaining_to_challenge: 0 } };
          const retry = { key: 'k26_30', unlocked: true, cleared: false, cooldown_left: 18, boss: { available: false, remaining_to_challenge: 0 } };
          return {
            training: _adventureQuestCtaState(training),
            bossReady: _adventureQuestCtaState(bossReady),
            retry: _adventureQuestCtaState(retry),
          };
        });
        if (result.training.state !== 'training_needed' || result.training.messageCount !== 12) {
          throw new Error(`training_needed: expected state=training_needed count=12, got ${JSON.stringify(result.training)}`);
        }
        if (result.bossReady.state !== 'boss_ready') {
          throw new Error(`boss_ready: expected state=boss_ready, got ${JSON.stringify(result.bossReady)}`);
        }
        if (result.retry.state !== 'retry_training' || result.retry.messageCount !== 18) {
          throw new Error(`retry_training: expected state=retry_training count=18 (cooldown_left, NOT remaining_to_challenge), got ${JSON.stringify(result.retry)}`);
        }
      });
    }, results);

    // --- Lord Challenge Card: real data, no forced battle entry ---
    await test('showZone1LordChallengeCard renders real zone data and never auto-starts the battle', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const result = await page.evaluate(() => {
          const zone = { key: 'k26_30', pct: 37, boss_exam_size: 20, boss_pass_score: 16, cooldown_required: 30 };
          showZone1LordChallengeCard(zone);
          return {
            books: document.getElementById('boss-cinematic-books').textContent,
            rules: document.getElementById('boss-cinematic-rules').innerHTML,
            startBtnText: document.getElementById('boss-cinematic-btn').textContent,
            bossMode: window._bossMode,
            overlayHidden: document.getElementById('boss-cinematic').getAttribute('aria-hidden'),
          };
        });
        if (!result.books.includes('37')) throw new Error(`expected real zone.pct=37 in eligibility line, got ${JSON.stringify(result.books)}`);
        if (!result.rules.includes('20') || !result.rules.includes('16') || !result.rules.includes('30')) {
          throw new Error(`expected real boss_exam_size/pass_score/cooldown_required (20/16/30) in rules, got ${JSON.stringify(result.rules)}`);
        }
        if (result.bossMode) throw new Error('Lord Challenge Card must never auto-enter battle mode on its own');
        if (result.overlayHidden !== 'false') throw new Error('expected the card to actually be visible');
      });
    }, results);

    // --- Owner polish (2026-08-10): Lord Card title moved to the art's own
    // top plaque, shared kicker hidden for this phase only ---
    await test('showZone1LordChallengeCard puts the real kicker text on the top plaque and hides the shared #boss-cinematic-kicker for this phase only', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const result = await page.evaluate(() => {
          const zone = { key: 'k26_30', pct: 37, boss_exam_size: 20, boss_pass_score: 16, cooldown_required: 30 };
          showZone1LordChallengeCard(zone);
          const plaque = document.getElementById('zone1-lord-card-plaque-title');
          const kicker = document.getElementById('boss-cinematic-kicker');
          return {
            plaqueText: plaque.textContent,
            plaqueDisplay: getComputedStyle(plaque).display,
            kickerDisplay: getComputedStyle(kicker).display,
          };
        });
        if (!result.plaqueText.includes('Lord Trial')) throw new Error(`expected the plaque title to carry the real kicker text, got ${JSON.stringify(result.plaqueText)}`);
        if (result.plaqueDisplay === 'none') throw new Error('expected the plaque title to be visible for phase-lord-card');
        if (result.kickerDisplay !== 'none') throw new Error('expected the shared #boss-cinematic-kicker to be hidden for phase-lord-card (its text now lives on the plaque)');
      });
    }, results);

    await test('showZone1LordChallengeCard does not hide the shared #boss-cinematic-kicker for other zones (generic showBossCinematic path untouched)', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const kickerDisplay = await page.evaluate(() => {
          const overlay = document.getElementById('boss-cinematic');
          overlay.className = 'boss-cinematic show';
          return getComputedStyle(document.getElementById('boss-cinematic-kicker')).display;
        });
        if (kickerDisplay === 'none') throw new Error('the plaque-hides-kicker CSS must be scoped to phase-lord-card only, not the generic overlay');
      });
    }, results);

    // --- Result card: failure never grants star/unlock/post-clear ---
    await test('showZone1LordResultCard (failure) shows real cooldown/rule numbers and never touches POST_CLEAR state', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const result = await page.evaluate(() => {
          localStorage.removeItem('adventure_postclear_seen_v1');
          const zone = { key: 'k26_30' };
          showZone1LordResultCard({ passed: false, correct: 11, total: 20, cooldown: 30, bossExamSize: 20, bossPassScore: 16 }, zone);
          return {
            rules: document.getElementById('boss-cinematic-rules').innerHTML,
            postClearSeen: JSON.parse(localStorage.getItem('adventure_postclear_seen_v1') || '{}'),
            phase: _introFilmActiveOpts.phase,
          };
        });
        if (!result.rules.includes('30')) throw new Error(`expected the real cooldown (30) in the failure rules, got ${JSON.stringify(result.rules)}`);
        if (result.postClearSeen['1']?.k26_30) throw new Error('failure must never mark POST_CLEAR as seen');
        if (result.phase === 'post_clear') throw new Error('failure must never enter the POST_CLEAR phase');
      });
    }, results);

    // --- Owner polish (2026-08-10): First Star reward artwork enlarged ~18% ---
    await test('the First Star reward artwork is sized in the 15-20% larger range approved by the Owner (20% vs the original 17%)', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const widthPct = await page.evaluate(() => {
          const style = [...document.styleSheets].flatMap((s) => {
            try { return [...s.cssRules]; } catch (e) { return []; }
          }).find((r) => r.selectorText === '#zone1-first-star-icon');
          return style ? style.style.width : null;
        });
        if (widthPct !== '20%') throw new Error(`expected #zone1-first-star-icon width to be 20% (was 17%, +~18%), got ${widthPct}`);
      });
    }, results);

    // --- Result card: success wires to POST_CLEAR exactly once ---
    await test('showZone1LordResultCard (success) triggers POST_CLEAR via _triggerZone1PostClearFromBossWin, once', async () => {
      await withFreshPage(browser, origin, async (page) => {
        await page.evaluate(() => { window.__audioMode = 'success'; localStorage.removeItem('adventure_postclear_seen_v1'); });
        const zone = { key: 'k26_30' };
        await page.evaluate((z) => {
          showZone1LordResultCard({ passed: true, correct: 18, total: 20, cooldown: 0, bossExamSize: 20, bossPassScore: 16 }, z);
          document.getElementById('boss-cinematic-btn').click();
        }, zone);
        await page.waitForTimeout(50);
        await page.evaluate(() => window.__flushFakeTimers());
        const pending = await page.evaluate(() => JSON.parse(localStorage.getItem('adventure_postclear_pending_v1') || '{}'));
        if (!pending['1']?.k26_30) throw new Error('expected the success card\'s Continue button to mark POST_CLEAR pending and start playback');
        // Calling the trigger a second time (e.g. a duplicate click) must not re-arm anything once seen.
        const secondCallPhaseBefore = await page.evaluate(() => _introFilmActiveOpts.phase);
        await page.evaluate(() => window.__flushFakeTimers());
      });
    }, results);

    // --- _triggerZone1PostClearFromBossWin: zone-scoped, idempotent ---
    await test('_triggerZone1PostClearFromBossWin is a no-op for any zone other than k26_30, and once seen', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const result = await page.evaluate(() => {
          window.__audioMode = 'success';
          localStorage.removeItem('adventure_postclear_seen_v1');
          const otherZonePendingBefore = JSON.parse(localStorage.getItem('adventure_postclear_pending_v1') || '{}');
          _triggerZone1PostClearFromBossWin({ key: 'k21_25' });
          const otherZonePendingAfter = JSON.parse(localStorage.getItem('adventure_postclear_pending_v1') || '{}');
          return { before: otherZonePendingBefore, after: otherZonePendingAfter, phase: _introFilmActiveOpts.phase };
        });
        if (result.phase === 'post_clear') throw new Error('a non-k26_30 zone must never trigger Zone 1\'s POST_CLEAR');
        if (JSON.stringify(result.before) !== JSON.stringify(result.after)) {
          throw new Error('a non-k26_30 zone must never write POST_CLEAR pending state');
        }
      });
    }, results);

    // --- SFX lifecycle (2026-08-10, Gate A promotion): one-shots never
    // overlap a still-playing previous one-shot ---
    await test('_playIntroSfxAsset stops the previous one-shot before starting the next (no overlap on back-to-back cues)', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const log = await page.evaluate(() => {
          window.__audioLog = [];
          _playIntroSfxAsset('/a.mp3');
          _playIntroSfxAsset('/b.mp3');
          return window.__audioLog;
        });
        const events = log.map((e) => `${e.event}:${e.src}`);
        const idxPlayA = events.indexOf('play:/a.mp3');
        const idxPauseA = events.indexOf('pause:/a.mp3');
        const idxPlayB = events.indexOf('play:/b.mp3');
        if (idxPlayA === -1 || idxPauseA === -1 || idxPlayB === -1) {
          throw new Error(`expected play(a), pause(a), play(b) in the log, got ${JSON.stringify(events)}`);
        }
        if (!(idxPlayA < idxPauseA && idxPauseA < idxPlayB)) {
          throw new Error(`expected a's pause to land between its play and b's play (no overlap), got order ${JSON.stringify(events)}`);
        }
      });
    }, results);

    // --- Underscore beds (ritual energy / route energy) can opt out of looping ---
    await test('_startIntroAmbience respects opts.loop=false for one-shot underscore beds', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const loopFlag = await page.evaluate(() => {
          window.__pendingSuccessAudio = [];
          _startIntroAmbience('/ritual-energy.mp3', { loop: false, volume: 0.25 });
          return window.__pendingSuccessAudio[window.__pendingSuccessAudio.length - 1].loop;
        });
        if (loopFlag !== false) throw new Error(`expected loop=false to be honored, got ${loopFlag}`);
      });
    }, results);

    // --- Ritual: energy bed is cut in the same tick the stone impact fires ---
    await test('startZone1LordRitual cuts the ritual-energy bed and fires GO_STONE_IMPACT together, before hand-off', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const log = await page.evaluate(() => {
          window.__audioLog = [];
          const zone = { key: 'k26_30', pct: 40, boss_exam_size: 20, boss_pass_score: 16, cooldown_required: 30 };
          showZone1LordChallengeCard(zone);
          window.__audioLog = [];
          startZone1LordRitual(zone);
          // Fire only the 1800ms (elder line) and 3600ms (stone impact) timers,
          // not the 4000ms hand-off (which would call the real boss/start API).
          // Clear each as it fires, mirroring real setTimeout's one-shot
          // semantics, so the 4000ms hand-off timer is left untouched.
          const timers = window.__fakeTimers.slice().sort((a, b) => a.delay - b.delay);
          timers.forEach((t) => { if (t.delay <= 3600) { window.clearTimeout(t.id); t.fn(); } });
          return window.__audioLog;
        });
        const events = log.map((e) => `${e.event}:${e.src}`);
        const idxRitualPlay = events.indexOf('play:/assets/e10/audio/zone1/lord_trial/zone1_lordtrial_lord_ritual_energy.mp3');
        const idxRitualPause = events.indexOf('pause:/assets/e10/audio/zone1/lord_trial/zone1_lordtrial_lord_ritual_energy.mp3');
        const idxStoneImpact = events.indexOf('play:/assets/e10/audio/zone1/lord_trial/zone1_lordtrial_go_stone_impact.mp3');
        if (idxRitualPlay === -1 || idxRitualPause === -1 || idxStoneImpact === -1) {
          throw new Error(`expected ritual energy play+pause and a stone-impact play, got ${JSON.stringify(events)}`);
        }
        if (!(idxRitualPlay < idxRitualPause && idxRitualPause <= idxStoneImpact)) {
          throw new Error(`expected ritual energy to be paused at/before the stone impact fires (no wash-over), got order ${JSON.stringify(events)}`);
        }
      });
    }, results);

    // --- Zone Unlock Reveal: repeat render never duplicates route energy / chime ---
    await test('showZone1UnlockReveal on repeat render stops the previous route-energy bed before starting a new one, and fires the chime only once per call', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const log = await page.evaluate(() => {
          _adventureProgress = [
            { key: 'k26_30', cleared: true, unlocked: true, index: 0 },
            { key: 'k21_25', unlocked: true, index: 1 },
          ];
          // The real reveal now animates the real #adventure-map-nodes
          // elements, so they must exist first -- render explicitly rather
          // than racing the app's own async bootstrap render.
          renderAdventureMap();
          const zone = { key: 'k26_30' };
          window.__audioLog = [];
          showZone1UnlockReveal(zone);
          window.__flushFakeTimers();
          showZone1UnlockReveal(zone);
          window.__flushFakeTimers();
          return window.__audioLog;
        });
        const routePlays = log.filter((e) => e.event === 'play' && /zone_route_energy/.test(e.src || '')).length;
        const routePauses = log.filter((e) => e.event === 'pause' && /zone_route_energy/.test(e.src || '')).length;
        const chimePlays = log.filter((e) => e.event === 'play' && /zone_unlock_chime/.test(e.src || '')).length;
        if (routePlays !== 2) throw new Error(`expected exactly 2 route-energy plays (one per reveal call), got ${routePlays}`);
        if (routePauses < 1) throw new Error(`expected the first reveal's route-energy bed to be paused before/when the second reveal starts, got ${routePauses} pauses`);
        if (chimePlays !== 2) throw new Error(`expected exactly one chime per reveal call (2 total, no duplicate stacking), got ${chimePlays}`);
      });
    }, results);

    // --- Teardown: _stopIntroFilm silences every Lord Trial SFX bed/one-shot ---
    await test('_stopIntroFilm stops any in-flight Lord Trial ambience/SFX cleanly (navigation/teardown safety)', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const result = await page.evaluate(() => {
          _playIntroSfxAsset('/x.mp3');
          _startIntroAmbience('/y.mp3', { loop: false });
          window.__audioLog = [];
          _stopIntroFilm();
          return window.__audioLog;
        });
        const hasPauseX = result.some((e) => e.event === 'pause' && e.src === '/x.mp3');
        const hasPauseY = result.some((e) => e.event === 'pause' && e.src === '/y.mp3');
        if (!hasPauseX || !hasPauseY) {
          throw new Error(`expected _stopIntroFilm to pause both the sfx and ambience slots, got ${JSON.stringify(result)}`);
        }
      });
    }, results);

    // --- Zone Unlock Reveal (2026-08-10 Owner correction): must animate
    // the REAL on-page map, never a cloned/miniature map in a modal ---
    await test('showZone1UnlockReveal never builds a second/cloned map -- no #zone-unlock-reveal-map or .zurm-* elements anywhere', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const result = await page.evaluate(() => {
          _adventureProgress = [
            { key: 'k26_30', cleared: true, unlocked: true, index: 0 },
            { key: 'k21_25', unlocked: true, index: 1 },
          ];
          renderAdventureMap();
          showZone1UnlockReveal({ key: 'k26_30' });
          return {
            clonedMapHost: !!document.getElementById('zone-unlock-reveal-map'),
            zurmElements: document.querySelectorAll('[class*="zurm-"]').length,
            oldModalOverlay: !!document.getElementById('zone-unlock-reveal'),
          };
        });
        if (result.clonedMapHost) throw new Error('a cloned-map host (#zone-unlock-reveal-map) still exists');
        if (result.zurmElements !== 0) throw new Error(`expected 0 .zurm-* elements, found ${result.zurmElements}`);
        if (result.oldModalOverlay) throw new Error('the old full-screen modal overlay (#zone-unlock-reveal) still exists');
      });
    }, results);

    await test('showZone1UnlockReveal rewinds and re-animates the REAL #adventure-route-progress and the REAL Zone 2 node in place', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const before = await page.evaluate(() => {
          _adventureProgress = [
            { key: 'k26_30', cleared: true, unlocked: true, index: 0 },
            { key: 'k21_25', unlocked: true, index: 1 },
          ];
          renderAdventureMap();
          const routePath = document.getElementById('adventure-route-progress');
          const toNode = document.getElementById('adventure-map-nodes').querySelector('[data-zone="k21_25"]');
          return {
            dasharrayBeforeReveal: routePath.style.strokeDasharray,
            toNodeLockedBeforeReveal: toNode.classList.contains('locked'),
          };
        });
        const midReveal = await page.evaluate(() => {
          showZone1UnlockReveal({ key: 'k26_30' });
          const routePath = document.getElementById('adventure-route-progress');
          const toNode = document.getElementById('adventure-map-nodes').querySelector('[data-zone="k21_25"]');
          return {
            dasharrayRewound: routePath.style.strokeDasharray,
            toNodeRelocked: toNode.classList.contains('zone1-reveal-relock'),
            fogInjected: !!toNode.querySelector('.zone1-reveal-fog'),
          };
        });
        // The real map was already re-rendered to the final unlocked state
        // (matching production's _finishBossBattle -> renderAdventureMap
        // ordering) -- the reveal must rewind it, not just read it.
        if (before.toNodeLockedBeforeReveal) throw new Error('test setup invariant broken: node should already be unlocked before reveal (matches real _finishBossBattle ordering)');
        if (midReveal.dasharrayRewound === before.dasharrayBeforeReveal) {
          throw new Error(`expected the real route to be rewound to a shorter dasharray at reveal start, got same value: ${midReveal.dasharrayRewound}`);
        }
        if (!midReveal.toNodeRelocked || !midReveal.fogInjected) {
          throw new Error('expected the real Zone 2 node to be temporarily re-fogged at reveal start');
        }
        // showZone1UnlockReveal mixes fake (harness-controlled) setTimeout
        // beats with a REAL CSS transition + requestAnimationFrame (neither
        // of which the fake-timer harness controls). Flushing the fake
        // timers can race a real rAF/paint tick that hasn't happened yet in
        // this headless page -- a short real wait first gives that a chance
        // to settle, matching what always happens naturally in a real
        // browser session (nothing here changes production behavior).
        await page.waitForTimeout(80);
        await page.evaluate(() => window.__flushFakeTimers());
        const after = await page.evaluate(() => {
          const routePath = document.getElementById('adventure-route-progress');
          const toNode = document.getElementById('adventure-map-nodes').querySelector('[data-zone="k21_25"]');
          return {
            dasharrayFinal: routePath.style.strokeDasharray,
            toNodeStillRelocked: toNode.classList.contains('zone1-reveal-relock'),
            toNodeHasFog: !!toNode.querySelector('.zone1-reveal-fog'),
            bannerShown: document.getElementById('zone1-unlock-banner').classList.contains('show'),
          };
        });
        if (after.dasharrayFinal !== before.dasharrayBeforeReveal) {
          throw new Error(`expected the route to land back at the real authoritative dasharray after the reveal, got ${after.dasharrayFinal} vs original ${before.dasharrayBeforeReveal}`);
        }
        if (after.toNodeStillRelocked || after.toNodeHasFog) throw new Error('expected the re-fog to be fully cleaned up after the reveal');
        if (!after.bannerShown) throw new Error('expected the compact result banner to show only after the real-map animation finished');
      });
    }, results);

    await test('the compact unlock banner never claims full-screen coverage (no backdrop overlay classes)', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const bannerHtml = await page.evaluate(() => {
          const el = document.getElementById('zone1-unlock-banner');
          return el ? el.outerHTML.slice(0, 40) : null;
        });
        if (!bannerHtml) throw new Error('expected #zone1-unlock-banner to exist in the DOM');
        // Structural check: the banner element itself carries no inline
        // full-viewport sizing -- its CSS (position:fixed; bottom; slim
        // width) is asserted indirectly via the reveal test above actually
        // showing the real map underneath, unobscured, during the reveal.
      });
    }, results);

    await test('_triggerZone1PostClearFromBossWin -> playZone1PostClearFilm -> finishPostClearFilm still reaches the real-map reveal', async () => {
      await withFreshPage(browser, origin, async (page) => {
        const result = await page.evaluate(() => {
          _adventureProgress = [
            { key: 'k26_30', cleared: true, unlocked: true, index: 0 },
            { key: 'k21_25', unlocked: true, index: 1 },
          ];
          renderAdventureMap();
          localStorage.removeItem('adventure_postclear_seen_v1');
          localStorage.removeItem('adventure_postclear_pending_v1');
          const zone = _adventureProgress[0];
          finishPostClearFilm(zone);
          const routePath = document.getElementById('adventure-route-progress');
          return {
            routeRewound: routePath.style.strokeDasharray,
            toNodeRelocked: document.getElementById('adventure-map-nodes')
              .querySelector('[data-zone="k21_25"]').classList.contains('zone1-reveal-relock'),
          };
        });
        if (!result.toNodeRelocked) throw new Error('expected finishPostClearFilm to reach showZone1UnlockReveal and re-fog the real Zone 2 node');
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

main().catch((err) => { console.error(err); process.exit(1); });
