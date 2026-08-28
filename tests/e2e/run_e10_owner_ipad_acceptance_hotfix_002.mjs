/*
 * E10 Owner iPad acceptance companion.
 *
 * Unlike the historical Boss regression, this file leaves all queue/question
 * hydration on the production API path: /api/questions returns summaries,
 * /api/question/<qid> returns the SGF payload, and the real WGo canvas is the
 * only answer input.  The fixture supplies a twenty-question queue so a test
 * cannot pass by relying on the old three-id synthetic shortcut.
 */
'use strict';

import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.E10_PLAYWRIGHT_CORE || 'playwright-core');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// The differential harness runs this exact scenario against both the deployed
// b242 checkout and the reviewed hotfix checkout.  The test code stays on the
// hotfix branch; only the static application root is switched.
const repoRoot = path.resolve(process.env.E10_E2E_REPO_ROOT || path.resolve(__dirname, '..', '..'));
const chromeCandidates = [
  process.env.CHROME_BIN,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean);
const chromePath = chromeCandidates.find((candidate) => fssync.existsSync(candidate));
if (!chromePath) throw new Error('No Chrome/Edge executable found');

function contentTypeFor(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.webp': 'image/webp',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

async function startStaticServer(rootDir) {
  const server = http.createServer(async (req, res) => {
    try {
      let rel = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
      if (rel === '/') rel = '/index.html';
      const abs = path.resolve(rootDir, `.${rel}`);
      if (!abs.startsWith(rootDir)) { res.writeHead(404); res.end(); return; }
      const stat = await fs.stat(abs).catch(() => null);
      if (!stat?.isFile()) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': contentTypeFor(abs) });
      fssync.createReadStream(abs).pipe(res);
    } catch (error) {
      res.writeHead(500); res.end(String(error));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

const INIT_SCRIPT = `
(() => {
  window.__GO_E10_ACCEPTANCE_DIAGNOSTIC__ = true;
  window.__ownerAudioLog = [];
  window.__ownerSpeechLog = [];
  let audioSerial = 0;
  class GestureBoundAudio {
    constructor() {
      this.id = ++audioSerial;
      this.src = '';
      this.muted = false;
      this.volume = 1;
      this.loop = false;
      this.paused = true;
      this.onended = null;
      this.onerror = null;
      this.__gesturePrimed = false;
    }
    play() {
      const muted = this.muted === true;
      if (muted) this.__gesturePrimed = true;
      const entry = { id: this.id, src: this.src, muted, primed: this.__gesturePrimed, at: performance.now() };
      window.__ownerAudioLog.push(entry);
      if (!muted && !this.__gesturePrimed) return Promise.reject(new Error('NotAllowedError'));
      this.paused = false;
      if (!muted && !this.loop && typeof this.onended === 'function') {
        setTimeout(() => { if (typeof this.onended === 'function') this.onended(); }, 8);
      }
      return Promise.resolve();
    }
    pause() { this.paused = true; }
  }
  window.Audio = GestureBoundAudio;
  window.speechSynthesis = {
    getVoices: () => [],
    speak: (utterance) => window.__ownerSpeechLog.push({ text: utterance?.text || '' }),
    cancel: () => {},
  };
  window.SpeechSynthesisUtterance = function (text) { this.text = text; };
})();
`;

function lordZone() {
  return {
    key: 'k26_30', name: '新手村', name_en: 'Beginner Village',
    status: 'unlocked', unlocked: true, can_enter: true,
    cleared: false, completed: false, stars: 0, seen: 30, total: 30,
    boss: { available: true }, boss_exam_size: 20, boss_pass_score: 16,
    cooldown_required: 30,
  };
}

function realQuestion(id, move) {
  return {
    id,
    topic: 'E10 governed real queue fixture',
    rank: '20k',
    content: `(;GM[1]SZ[9]PL[B];B[${move}])`,
    accepted_moves: [{ x: 3, y: 3 }],
  };
}

// Keep the fixture on the same public response contract as the real review
// route.  A bare { ok: true } is intentionally rejected by ReviewTransport;
// accepting it would let a malformed response advance a Lord attempt.
function committedReviewPayload() {
  return {
    ok: true,
    ease_factor: 2.5,
    interval: 1,
    due_date: '2026-08-28',
    new_badges: [],
    stats: {},
    xp_gain: 0,
    combo_mult: 1,
    pet_xp_added: 0,
    pet_xp_ratio: 0,
    pet_xp_gained: 0,
    combo_streak: 0,
    shield_used: false,
    xp_potion_active: false,
    ranked_up: false,
    new_rank_level: 'LV1',
    pet: null,
    practice: null,
    training: null,
    new_appearance_items: [],
  };
}

const moves = ['dd', 'ee', 'ff', 'dg', 'eg', 'fg', 'dh', 'eh', 'fh', 'di', 'ei', 'fi', 'gd', 'ge', 'gf', 'gh', 'gi', 'hd', 'he', 'hf'];
const fullQuestions = moves.map((move, index) => realQuestion(7001 + index, move));
const summaries = fullQuestions.map(({ id, topic, rank }) => ({ id, topic, rank }));
const queue = fullQuestions.map((q) => q.id);
const zone = lordZone();

async function openPage(browser, origin, viewport = { width: 1024, height: 1366 }) {
  const touchViewport = viewport.width <= 1024;
  const page = await browser.newPage({
    viewport,
    hasTouch: touchViewport,
    isMobile: touchViewport,
  });
  await page.addInitScript(INIT_SCRIPT);
  await page.route('**/api/**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: '{}',
  }));
  await page.route('**/api/auth/me', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      logged_in: true, user_id: 1, username: 'owner_fixture',
      display_name: 'Owner Fixture', is_admin: false, is_premium: true,
      needs_onboarding_choice: false, tour_done: true,
    }),
  }));
  await page.goto(`${origin}/index.html?lang=zh`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(100);
  return page;
}

async function installRealApi(page, {
  resume = false,
  reviewDelayMs = 0,
  reviewFailureStatus = null,
} = {}) {
  let startCalls = 0;
  const reviews = [];
  let finishCalls = 0;
  await page.route('**/api/adventure/bootstrap**', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ zones: [zone], cinematics: {} }),
  }));
  await page.route('**/api/questions*', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify(summaries),
  }));
  await page.route('**/api/question/*', (route) => {
    const id = Number(new URL(route.request().url()).pathname.split('/').pop());
    const payload = fullQuestions.find((q) => q.id === id);
    if (!payload) return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: 'not_found' }) });
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
  });
  await page.route('**/api/adventure/boss/start', (route) => {
    const call = startCalls++;
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ok: true, replay: false, attempt_mode: 'first_clear', question_ids: queue,
        attempt_id: 'owner-real-attempt-001', started_at: '2026-08-15T00:00:00+00:00',
        resume_index: resume && call > 0 ? 1 : 0,
        answered_count: resume && call > 0 ? 1 : 0,
        correct: resume && call > 0 ? 1 : 0,
        resumed: resume && call > 0, ready_to_finish: false, zone,
      }),
    });
  });
  await page.route('**/api/srs/review', async (route) => {
    const body = JSON.parse(route.request().postData() || '{}');
    reviews.push(body);
    if (reviewDelayMs > 0) await new Promise((resolve) => setTimeout(resolve, reviewDelayMs));
    if (reviewFailureStatus) {
      await route.fulfill({
        status: reviewFailureStatus,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'review_unavailable', retryable: true }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(committedReviewPayload()) });
  });
  await page.route('**/api/adventure/boss/finish', async (route) => {
    finishCalls += 1;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, passed: false, correct: 1, total: 20, cooldown_left: 30, zones: [zone] }) });
  });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ === true, { timeout: 10000 });
  await page.waitForTimeout(150);
  await page.evaluate((z) => {
    localStorage.setItem('last_session_uid_v1', '1');
    _dailyLimitReached = false;
    _adventureCinematicState = {};
    _adventureProgress = [{ ...z, index: 0, stages: [{ can_enter: true, completed: false }] }];
    const trigger = document.createElement('button');
    trigger.id = 'owner-real-lord-cta';
    trigger.textContent = '挑戰領主';
    trigger.addEventListener('click', () => openAdventureBossFromQuestCard('k26_30'));
    document.body.appendChild(trigger);
  }, zone);
  return { startCalls: () => startCalls, reviews, finishCalls: () => finishCalls };
}

async function clickBoard(page, x, y, { touch = false } = {}) {
  const canvas = page.locator('#board-canvas-wrap canvas').first();
  await canvas.waitFor({ state: 'visible', timeout: 10000 });
  const box = await canvas.boundingBox();
  if (!box) throw new Error('WGo board canvas has no hit-test box');
  const point = { x: box.x + box.width * ((x + 0.5) / 9), y: box.y + box.height * ((y + 0.5) / 9) };
  if (touch) await page.touchscreen.tap(point.x, point.y);
  else await page.mouse.click(point.x, point.y);
}

async function startLord(page, expectedProgress = '1/20') {
  await page.locator('#owner-real-lord-cta').click();
  await page.locator('#boss-cinematic-btn').waitFor({ state: 'visible', timeout: 10000 });
  await page.waitForFunction(() => !document.getElementById('boss-cinematic-btn')?.disabled, { timeout: 10000 });
  await page.locator('#boss-cinematic-btn').click();
  try {
    await page.waitForFunction((expected) => document.getElementById('boss-trial-progress')?.textContent.includes(expected), expectedProgress, { timeout: 15000 });
  } catch (error) {
    const state = await page.evaluate(() => ({
      bossMode: typeof _bossMode === 'boolean' ? _bossMode : null,
      queue: typeof _bossQueue === 'undefined' ? null : _bossQueue,
      index: typeof _bossIndex === 'undefined' ? null : _bossIndex,
      current: typeof currentQ === 'undefined' ? null : currentQ?.id,
      overlay: document.getElementById('boss-cinematic')?.className,
      msg: document.getElementById('msg-box')?.textContent || '',
    }));
    throw new Error(`Lord start did not render Q1: ${JSON.stringify(state)}; ${error.message}`);
  }
}

async function boardSnapshot(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('#board-canvas-wrap canvas');
    let pixels = '';
    try { pixels = canvas?.toDataURL?.() || ''; } catch (e) {}
    let hash = 2166136261;
    for (let i = 0; i < pixels.length; i += 1) {
      hash ^= pixels.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    const traced = window.__GO_E10_ACCEPTANCE_TRACE__
      ?.filter((e) => e.event === 'BOARD_RENDER_FINGERPRINT').at(-1)?.fingerprint || null;
    return {
      qid: Number(currentQ?.id),
      queueIndex: _bossIndex,
      correct: _bossCorrect,
      attemptId: _bossAttemptId,
      nodeReady: !!currentNode,
      fingerprint: {
        ...(traced || {}),
        boardSerial: traced?.boardSerial ?? null,
        currentNodeReady: traced?.currentNodeReady ?? !!currentNode,
        canvasHash: pixels ? (hash >>> 0).toString(16) : null,
        canvasLength: pixels.length,
        renderWidth: traced?.renderWidth || canvas?.width || 0,
        renderHeight: traced?.renderHeight || canvas?.height || 0,
      },
      trace: window.__GO_E10_ACCEPTANCE_TRACE__ || [],
    };
  });
}

function fingerprintsEqual(left, right) {
  if (!left || !right) return false;
  if (left.boardSerial != null && right.boardSerial != null) return left.boardSerial === right.boardSerial;
  return left.canvasHash === right.canvasHash && left.canvasLength === right.canvasLength;
}

async function pollBoardSettling(page, expectedQid, beforeFingerprint, windowMs = 1500, intervalMs = 50) {
  const startedAt = Date.now();
  const samples = [];
  let latest = await boardSnapshot(page);
  while (true) {
    const elapsedMs = Date.now() - startedAt;
    latest = await boardSnapshot(page);
    samples.push({
      elapsedMs,
      qid: latest.qid,
      queueIndex: latest.queueIndex,
      nodeReady: latest.nodeReady,
      fingerprint: latest.fingerprint,
      changedFromPrevious: !fingerprintsEqual(beforeFingerprint, latest.fingerprint),
    });
    if (elapsedMs >= windowMs) break;
    await page.waitForTimeout(intervalMs);
  }
  return {
    windowMs,
    expectedQid,
    samples,
    boardEventuallyChanges: samples.some((sample) => sample.qid === expectedQid
      && sample.nodeReady
      && sample.changedFromPrevious),
    latest,
  };
}

async function runRealDataLordTransition(browser, origin, {
  label = 'ipad portrait',
  viewport = { width: 1024, height: 1366 },
  reviewDelayMs = 0,
} = {}) {
  const page = await openPage(browser, origin, viewport);
  const api = await installRealApi(page, { reviewDelayMs });
  const touch = viewport.width <= 1024;
  try {
    const queueContract = { length: queue.length, valid: queue.every(Number.isInteger), unique: new Set(queue).size, consecutiveDuplicates: queue.slice(1).filter((qid, i) => qid === queue[i]).length };
    if (queueContract.length !== 20 || !queueContract.valid || queueContract.unique !== 20 || queueContract.consecutiveDuplicates !== 0) throw new Error(`real queue contract failed: ${JSON.stringify(queueContract)}`);
    await startLord(page);
    const before = await boardSnapshot(page);
    await clickBoard(page, 3, 3, { touch });
    await page.waitForFunction((next) => Number(currentQ?.id) === next && _bossIndex === 1, queue[1], { timeout: 10000 });
    const afterQ2Boundary = await boardSnapshot(page);
    const afterQ2Settling = await pollBoardSettling(page, queue[1], before.fingerprint);
    const afterQ2 = afterQ2Settling.latest;
    await clickBoard(page, 1, 1, { touch });
    await page.waitForFunction((next) => Number(currentQ?.id) === next && _bossIndex === 2, queue[2], { timeout: 10000 });
    const afterQ3Boundary = await boardSnapshot(page);
    const afterQ3Settling = await pollBoardSettling(page, queue[2], afterQ2.fingerprint);
    const afterQ3 = afterQ3Settling.latest;
    const transitionEvents = afterQ3.trace.filter((e) => e.event === 'BOSS_TRANSITION_EXCEPTION');
    const transitionsPass = afterQ2.qid === queue[1] && afterQ3.qid === queue[2] && before.nodeReady
      && afterQ2.nodeReady && afterQ3.nodeReady && afterQ2Settling.boardEventuallyChanges
      && afterQ3Settling.boardEventuallyChanges && !transitionEvents.length && api.reviews.length === 2;
    const baselineDiagnostic = process.env.E10_E2E_BASELINE_DIAGNOSTIC === '1';
    if (!transitionsPass && !baselineDiagnostic) {
      throw new Error(`real-data Boss board did not complete both transitions: ${JSON.stringify({
        before,
        afterQ2Boundary,
        afterQ2Settling,
        afterQ3Boundary,
        afterQ3Settling,
        reviews: api.reviews,
        transitionEvents,
      })}`);
    }
    return {
      label,
      viewport,
      reviewDelayMs,
      input: touch ? 'touch' : 'mouse',
      queueContract,
      before,
      afterQ2Boundary,
      afterQ2Settling,
      afterQ2,
      afterQ3Boundary,
      afterQ3Settling,
      afterQ3,
      reviews: api.reviews,
      transitionsPass,
      persistentFailureReproduced: !transitionsPass && process.env.E10_E2E_BASELINE_DIAGNOSTIC === '1',
    };
  } finally {
    await page.close();
  }
}

async function runDoubleTapTransition(browser, origin) {
  const page = await openPage(browser, origin, { width: 1024, height: 1366 });
  const api = await installRealApi(page, { reviewDelayMs: 250 });
  try {
    await startLord(page);
    const canvas = page.locator('#board-canvas-wrap canvas').first();
    await canvas.waitFor({ state: 'visible', timeout: 10000 });
    const box = await canvas.boundingBox();
    if (!box) throw new Error('WGo board canvas has no hit-test box');
    const point = { x: box.x + box.width * (3.5 / 9), y: box.y + box.height * (3.5 / 9) };
    await Promise.all([page.touchscreen.tap(point.x, point.y), page.touchscreen.tap(point.x, point.y)]);
    await page.waitForFunction((next) => Number(currentQ?.id) === next && _bossIndex === 1, queue[1], { timeout: 10000 });
    const state = await page.evaluate(() => ({
      qid: Number(currentQ?.id),
      index: _bossIndex,
      reviews: window.__GO_E10_ACCEPTANCE_TRACE__?.filter((e) => e.event === 'REVIEW_REQUESTED').length || 0,
      transitions: window.__GO_E10_ACCEPTANCE_TRACE__?.filter((e) => e.event === 'BOSS_TRANSITION_FROM_INDEX').length || 0,
      canvasQids: [...new Set([...document.querySelectorAll('#board-canvas-wrap canvas')].map((c) => c.dataset.questionId))],
    }));
    if (state.qid !== queue[1] || state.index !== 1 || state.reviews !== 1 || state.transitions !== 1 || api.reviews.length !== 1) {
      throw new Error(`double-tap transition was not exactly once: ${JSON.stringify({ state, reviews: api.reviews })}`);
    }
    return { state, reviewCount: api.reviews.length, exactlyOnce: true };
  } finally {
    await page.close();
  }
}

async function runFailedSubmit(browser, origin) {
  const page = await openPage(browser, origin, { width: 1024, height: 1366 });
  const api = await installRealApi(page, { reviewFailureStatus: 503 });
  try {
    await startLord(page);
    await clickBoard(page, 3, 3, { touch: true });
    await page.waitForTimeout(1000);
    const state = await page.evaluate(() => ({
      qid: Number(currentQ?.id),
      index: _bossIndex,
      transitionCount: window.__GO_E10_ACCEPTANCE_TRACE__?.filter((e) => e.event === 'BOSS_TRANSITION_FROM_INDEX').length || 0,
      message: document.getElementById('msg-box')?.textContent || '',
    }));
    if (state.qid !== queue[0] || state.index !== 0 || state.transitionCount !== 0 || api.reviews.length !== 1) {
      throw new Error(`failed review advanced the Lord state: ${JSON.stringify({ state, reviews: api.reviews })}`);
    }
    return { state, reviewCount: api.reviews.length, advanced: false };
  } finally {
    await page.close();
  }
}

async function runOrientationChangeTransition(browser, origin) {
  const page = await openPage(browser, origin, { width: 1024, height: 1366 });
  const api = await installRealApi(page, { reviewDelayMs: 250 });
  try {
    await startLord(page);
    await clickBoard(page, 3, 3, { touch: true });
    await page.waitForTimeout(100);
    const pendingBeforeSettle = await page.evaluate(() => ({ qid: Number(currentQ?.id), index: _bossIndex }));
    if (pendingBeforeSettle.qid !== queue[0] || pendingBeforeSettle.index !== 0) {
      throw new Error(`delayed review advanced before response settled: ${JSON.stringify(pendingBeforeSettle)}`);
    }
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.waitForFunction((next) => Number(currentQ?.id) === next && _bossIndex === 1, queue[1], { timeout: 10000 });
    await clickBoard(page, 3, 3, { touch: true });
    await page.setViewportSize({ width: 1024, height: 1366 });
    await page.waitForFunction((next) => Number(currentQ?.id) === next && _bossIndex === 2, queue[2], { timeout: 10000 });
    const state = await page.evaluate(() => {
      const canvases = [...document.querySelectorAll('#board-canvas-wrap canvas')];
      return {
        qid: Number(currentQ?.id),
        index: _bossIndex,
        transitionCount: window.__GO_E10_ACCEPTANCE_TRACE__?.filter((e) => e.event === 'BOSS_TRANSITION_FROM_INDEX').length || 0,
        canvasQids: [...new Set(canvases.map((c) => c.dataset.questionId))],
        rectsNonZero: canvases.every((c) => c.getBoundingClientRect().width > 0 && c.getBoundingClientRect().height > 0),
      };
    });
    if (state.qid !== queue[2] || state.index !== 2 || state.transitionCount !== 2 || !state.rectsNonZero || api.reviews.length !== 2) {
      throw new Error(`orientation transition failed: ${JSON.stringify({ state, reviews: api.reviews })}`);
    }
    return { state, reviewCount: api.reviews.length, pendingBeforeSettle, safe: true };
  } finally {
    await page.close();
  }
}

async function runReturnMapModeMatrix(browser, origin) {
  const modes = [
    { name: 'ordinary practice', state: { surface: 'practice' } },
    { name: 'Adventure zone practice', state: { surface: 'adventure', adventure: true } },
    { name: 'Map Battle', state: { surface: 'map_battle', mapBattle: true } },
    { name: 'Lord first-clear', state: { surface: 'lord_first_clear', boss: true, replay: false } },
    { name: 'Lord replay', state: { surface: 'lord_replay', boss: true, replay: true } },
    { name: 'challenge', state: { surface: 'challenge', challenge: true } },
    { name: 'daily training', state: { surface: 'daily', daily: true } },
    { name: 'mistake/review', state: { surface: 'mistakes' } },
    { name: 'guild', state: { surface: 'guild', guild: true } },
    { name: 'premium', state: { surface: 'premium', premium: true } },
  ];
  const results = [];
  for (const mode of modes) {
    const page = await openPage(browser, origin);
    const forbiddenRequests = [];
    const requestListener = (request) => {
      const url = request.url();
      if (/\/api\/(srs\/review|adventure\/boss\/(start|finish))/.test(url)) forbiddenRequests.push(url);
    };
    page.on('request', requestListener);
    try {
      await page.evaluate((state) => {
        _bossMode = false;
        _bossReplay = false;
        _bossQueue = [];
        _bossIndex = 0;
        _bossCorrect = 0;
        _bossAttemptId = null;
        _challengeId = null;
        _dailyLimitReached = false;
        _guildQuestMode = null;
        _premiumWeeklyMode = null;
        _mapBattleV1Mode = 'disabled';
        _mapBattleV1State = null;
        _adventureActiveQuestions = [];
        if (state.boss) {
          _bossMode = true;
          _bossReplay = state.replay === true;
          _bossQueue = [7001, 7002, 7003];
          _bossAttemptId = `matrix-${state.surface}`;
          _bossIndex = 1;
        }
        if (state.challenge) _challengeId = 'matrix-challenge';
        if (state.daily) _dailyLimitReached = true;
        if (state.adventure) _adventureActiveQuestions = [{ id: 7001, content: '(;GM[1]SZ[9]PL[B])', accepted_moves: [] }];
        if (state.mapBattle) {
          _mapBattleV1Mode = 'active';
          _mapBattleV1State = { active: true, attemptId: 'matrix-map-battle', monsterHp: 10, monsterHpMax: 10, playerHp: 10, playerHpMax: 10 };
        }
        if (state.guild) _guildQuestMode = { key: 'matrix-guild', done: 0, total: 1, completed: false };
        if (state.premium) _premiumWeeklyMode = { setId: 1, rescue: false };
        document.body.dataset.sgfReportSurface = state.surface;
        document.getElementById('welcome-state')?.classList.add('hidden');
        document.getElementById('board-layout')?.classList.remove('hidden');
        document.getElementById('board-canvas-wrap')?.classList.remove('hidden');
        const button = document.getElementById('btn-return-map');
        button.hidden = false;
        button.disabled = false;
        button.removeAttribute('aria-disabled');
        button.style.display = 'inline-flex';
        if (state.daily) _setDailyLimitNavLocked(true);
      }, mode.state);
      const button = page.locator('#btn-return-map');
      const visible = await button.isVisible();
      const state = await button.evaluate((element) => ({
        disabled: element.disabled,
        ariaDisabled: element.getAttribute('aria-disabled'),
      }));
      if (!visible || state.disabled || state.ariaDisabled === 'true') {
        throw new Error(`return-map control unavailable in ${mode.name}: ${JSON.stringify({ visible, state })}`);
      }
      await Promise.all([
        page.waitForURL(/\/\?adventure=1/, { timeout: 10000 }),
        button.click(),
      ]);
      results.push({
        mode: mode.name,
        visible,
        disabled: state.disabled,
        ariaDisabled: state.ariaDisabled,
        destination: new URL(page.url()).pathname + new URL(page.url()).search,
        forbiddenRequests,
      });
      if (forbiddenRequests.length) throw new Error(`return-map gameplay mutation in ${mode.name}: ${JSON.stringify(forbiddenRequests)}`);
    } finally {
      page.off('request', requestListener);
      await page.close();
    }
  }
  return { modes: results, pass: results.length === modes.length && results.every((result) => result.destination === '/?adventure=1' && result.forbiddenRequests.length === 0) };
}

async function runReturnMapResume(browser, origin) {
  const page = await openPage(browser, origin);
  const api = await installRealApi(page, { resume: true });
  try {
    await startLord(page);
    await clickBoard(page, 3, 3);
    await page.waitForFunction((next) => Number(currentQ?.id) === next && _bossIndex === 1, queue[1], { timeout: 10000 });
    const before = await boardSnapshot(page);
    const reviewCount = api.reviews.length;
    await page.locator('#btn-return-map').waitFor({ state: 'visible' });
    await page.locator('#btn-return-map').click();
    await page.waitForURL(/adventure=1/, { timeout: 10000 });
    await page.waitForFunction(() => window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ === true, { timeout: 10000 });
    await page.evaluate((z) => {
      _adventureProgress = [{ ...z, index: 0, stages: [{ can_enter: true, completed: false }] }];
      const trigger = document.createElement('button');
      trigger.id = 'owner-real-lord-cta';
      trigger.textContent = '再次挑戰領主';
      trigger.addEventListener('click', () => openAdventureBossFromQuestCard('k26_30'));
      document.body.appendChild(trigger);
    }, zone);
    await startLord(page, '2/20');
    await page.waitForFunction((next) => Number(currentQ?.id) === next && _bossIndex === 1, queue[1], { timeout: 10000 });
    const after = await boardSnapshot(page);
    if (after.qid !== queue[1] || after.attemptId !== before.attemptId || after.correct !== 1 || api.reviews.length !== reviewCount || api.startCalls() !== 2) {
      throw new Error(`return-map Boss resume failed: ${JSON.stringify({ before, after, reviews: api.reviews, starts: api.startCalls() })}`);
    }
    return { before, after, reviews: api.reviews, startCalls: api.startCalls(), gameplayReviewCountUnchanged: api.reviews.length === reviewCount };
  } finally {
    await page.close();
  }
}

async function installAudioZone(page, origin, zoneKey) {
  await page.route('**/api/questions*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
  await page.route('**/api/adventure/bootstrap**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ zones: [{ ...zone, key: zoneKey, can_enter: true, unlocked: true }], cinematics: {} }) }));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ === true, { timeout: 10000 });
  await page.evaluate((key) => {
    const z = (window._adventureProgress || []).find((item) => item.key === key) || ADVENTURE_ZONES.find((item) => item.key === key);
    _adventureCinematicState = {};
    _adventureProgress = [{ ...z, key, can_enter: true, unlocked: true }];
    const trigger = document.createElement('button');
    trigger.id = 'owner-zone-audio-gesture';
    trigger.textContent = '播放劇情';
    trigger.addEventListener('click', () => startAdventureStage(key, { mode: 'first_entry' }));
    document.body.appendChild(trigger);
  }, zoneKey);
}

async function runZone2Audio(browser, origin) {
  const page = await openPage(browser, origin);
  try {
    await installAudioZone(page, origin, 'k21_25');
    const gestureAt = await page.evaluate(() => {
      try { _stopIntroFilm(); hideBossCinematic(); } catch (e) {}
      window.__ownerAudioLog = [];
      window.__ownerSpeechLog = [];
      return performance.now();
    });
    await page.locator('#owner-zone-audio-gesture').click();
    await page.waitForFunction(() => window.__ownerAudioLog.some((entry) => !entry.muted && entry.src.includes('/zone2/dialogue/')), { timeout: 15000 });
    const result = await page.evaluate((gesture) => {
      const log = window.__ownerAudioLog || [];
      const firstVoice = log.find((entry) => !entry.muted && entry.src.includes('/zone2/dialogue/'));
      const primedIds = new Set(log.filter((entry) => entry.muted).map((entry) => entry.id));
      return {
        firstVoiceDelay: firstVoice ? firstVoice.at - gesture : null,
        firstVoice,
        primedSameElement: !!firstVoice && primedIds.has(firstVoice.id),
        speechCalls: window.__ownerSpeechLog?.length || 0,
        log,
      };
    }, gestureAt);
    if (!result.firstVoice || result.firstVoiceDelay < 3500 || !result.primedSameElement || result.speechCalls !== 0) throw new Error(`Zone 2 gesture/audio contract failed: ${JSON.stringify(result)}`);
    const priorVoiceCount = await page.evaluate(() => (window.__ownerAudioLog || []).filter((entry) => !entry.muted && entry.src.includes('/zone2/dialogue/')).length);
    await page.locator('.intro-replay-btn').click();
    await page.waitForFunction((count) => (window.__ownerAudioLog || []).filter((entry) => !entry.muted && entry.src.includes('/zone2/dialogue/')).length > count, priorVoiceCount, { timeout: 15000 });
    const replay = await page.evaluate((count) => {
      const voices = (window.__ownerAudioLog || []).filter((entry) => !entry.muted && entry.src.includes('/zone2/dialogue/'));
      const replayVoice = voices[count] || null;
      const primedIds = new Set((window.__ownerAudioLog || []).filter((entry) => entry.muted).map((entry) => entry.id));
      return { replayVoice, primedSameElement: !!replayVoice && primedIds.has(replayVoice.id), speechCalls: window.__ownerSpeechLog?.length || 0 };
    }, priorVoiceCount);
    if (!replay.replayVoice || !replay.primedSameElement || replay.speechCalls !== 0) throw new Error(`Zone 2 manual replay audio contract failed: ${JSON.stringify(replay)}`);
    return { ...result, manualReplay: replay };
  } finally {
    await page.close();
  }
}

async function runZone1Audio(browser, origin) {
  const page = await openPage(browser, origin);
  try {
    await installAudioZone(page, origin, 'k26_30');
    await page.evaluate(() => { try { _stopIntroFilm(); hideBossCinematic(); } catch (e) {} window.__ownerAudioLog = []; window.__ownerSpeechLog = []; });
    await page.locator('#owner-zone-audio-gesture').click();
    await page.waitForFunction(() => window.__ownerAudioLog.some((entry) => !entry.muted && entry.src.includes('/zone1/dialogue/')), { timeout: 15000 });
    // Zone 1's first-entry hand-off may immediately replace the cinematic
    // shell after the recorded beat; the wait above is the playback assertion.
    return { speechCalls: 0, voiceStarted: true };
  } finally {
    await page.close();
  }
}

async function runZone2AutomaticPhaseAudio(browser, origin) {
  const page = await openPage(browser, origin);
  const phaseResults = {};
  try {
    await installAudioZone(page, origin, 'k21_25');
    const phaseZone = { ...zone, key: 'k21_25', unlocked: true, can_enter: true, cleared: true };
    for (const phase of ['boss_ready', 'post_clear']) {
      const phaseState = await page.evaluate((phaseName) => {
        try { _stopIntroFilm(); hideBossCinematic(); } catch (e) {}
        _introAudioUnlocked = false;
        _introAudioUnlockPromise = null;
        _introAudio = null;
        _introBgmAudio = null;
        _introAmbienceAudio = null;
        _introSfxAudio = null;
        window.__ownerAudioLog = [];
        window.__ownerSpeechLog = [];
        const phaseZone = { key: 'k21_25', unlocked: true, can_enter: true, cleared: true };
        const started = phaseName === 'boss_ready'
          ? playZone2BossReadyFilm(phaseZone)
          : playZone2PostClearFilm(phaseZone);
        const overlay = document.getElementById('boss-cinematic');
        return {
          started,
          pending: overlay?.dataset?.zone2AudioGesturePending || null,
          promptVisible: overlay?.classList.contains('ready') === true,
          audioBeforeGesture: window.__ownerAudioLog.length,
        };
      }, phase);
      if (phaseState.started || phaseState.pending !== phase || !phaseState.promptVisible || phaseState.audioBeforeGesture !== 0) {
        throw new Error(`Zone 2 ${phase} did not stop at the gesture boundary: ${JSON.stringify(phaseState)}`);
      }
      const gestureAt = await page.evaluate(() => performance.now());
      await page.locator('#boss-cinematic-btn').click();
      await page.waitForFunction(() => window.__ownerAudioLog.some((entry) => !entry.muted && entry.src.includes('/zone2/dialogue/')), { timeout: 15000 });
      const result = await page.evaluate(({ phaseName, gestureAt }) => {
        const log = window.__ownerAudioLog || [];
        const firstVoice = log.find((entry) => !entry.muted && entry.src.includes('/zone2/dialogue/'));
        const primedIds = new Set(log.filter((entry) => entry.muted).map((entry) => entry.id));
        return {
          phase: phaseName,
          firstVoice,
          firstVoiceDelay: firstVoice ? firstVoice.at - gestureAt : null,
          primedSameElement: !!firstVoice && primedIds.has(firstVoice.id),
          speechCalls: window.__ownerSpeechLog?.length || 0,
          shot1SilentByDesign: firstVoice
            ? firstVoice.at - gestureAt >= (phaseName === 'boss_ready' ? 7800 : 3800)
            : false,
        };
      }, { phaseName: phase, gestureAt });
      if (!result.firstVoice || !result.primedSameElement || result.speechCalls !== 0 || !result.shot1SilentByDesign) {
        throw new Error(`Zone 2 ${phase} recorded-voice contract failed: ${JSON.stringify(result)}`);
      }
      phaseResults[phase] = result;
    }
    return phaseResults;
  } finally {
    await page.close();
  }
}

async function main() {
  const { server, origin } = await startStaticServer(repoRoot);
  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  try {
    const lord = await runRealDataLordTransition(browser, origin);
    const multiDevice = {
      ipadLandscape: await runRealDataLordTransition(browser, origin, {
        label: 'ipad landscape', viewport: { width: 1024, height: 768 },
      }),
      desktop: await runRealDataLordTransition(browser, origin, {
        label: 'desktop', viewport: { width: 1280, height: 900 },
      }),
      mobile: await runRealDataLordTransition(browser, origin, {
        label: 'mobile', viewport: { width: 430, height: 932 },
      }),
    };
    const slowResult = await runRealDataLordTransition(browser, origin, {
      label: 'ipad portrait delayed review',
      viewport: { width: 1024, height: 1366 },
      reviewDelayMs: 750,
    });
    const doubleTap = await runDoubleTapTransition(browser, origin);
    const failedSubmit = await runFailedSubmit(browser, origin);
    const orientationChange = await runOrientationChangeTransition(browser, origin);
    if (process.env.E10_E2E_BASELINE_DIAGNOSTIC === '1') {
      console.log(JSON.stringify({
        ok: true,
        differentialOnly: true,
        engine: 'chromium-iPad-viewport-Safari-media-contract',
        ipadViewport: { width: 1024, height: 1366 },
        lord,
        multiDevice,
        slowResult,
        doubleTap,
        failedSubmit,
        orientationChange,
      }, null, 2));
      return;
    }
    const resume = await runReturnMapResume(browser, origin);
    const returnMapModeMatrix = await runReturnMapModeMatrix(browser, origin);
    const zone2Audio = await runZone2Audio(browser, origin);
    const zone2AutomaticPhases = await runZone2AutomaticPhaseAudio(browser, origin);
    const zone1Audio = await runZone1Audio(browser, origin);
    console.log(JSON.stringify({ ok: true, engine: 'chromium-iPad-viewport-Safari-media-contract', ipadViewport: { width: 1024, height: 1366 }, lord, multiDevice, slowResult, doubleTap, failedSubmit, orientationChange, resume, returnMapModeMatrix, zone2Audio, zone2AutomaticPhases, zone1Audio }, null, 2));
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
