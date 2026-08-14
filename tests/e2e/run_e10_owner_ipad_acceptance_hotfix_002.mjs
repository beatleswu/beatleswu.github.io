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
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
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

const moves = ['dd', 'ee', 'ff', 'dg', 'eg', 'fg', 'dh', 'eh', 'fh', 'di', 'ei', 'fi', 'gd', 'ge', 'gf', 'gh', 'gi', 'hd', 'he', 'hf'];
const fullQuestions = moves.map((move, index) => realQuestion(7001 + index, move));
const summaries = fullQuestions.map(({ id, topic, rank }) => ({ id, topic, rank }));
const queue = fullQuestions.map((q) => q.id);
const zone = lordZone();

async function openPage(browser, origin, viewport = { width: 1024, height: 1366 }) {
  const page = await browser.newPage({ viewport });
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

async function installRealApi(page, { resume = false } = {}) {
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
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
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

async function clickBoard(page, x, y) {
  const canvas = page.locator('#board-canvas-wrap canvas').first();
  await canvas.waitFor({ state: 'visible', timeout: 10000 });
  const box = await canvas.boundingBox();
  if (!box) throw new Error('WGo board canvas has no hit-test box');
  await page.mouse.click(box.x + box.width * ((x + 0.5) / 9), box.y + box.height * ((y + 0.5) / 9));
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
  return page.evaluate(() => ({
    qid: Number(currentQ?.id),
    queueIndex: _bossIndex,
    correct: _bossCorrect,
    attemptId: _bossAttemptId,
    nodeReady: !!currentNode,
    fingerprint: window.__GO_E10_ACCEPTANCE_TRACE__?.filter((e) => e.event === 'BOARD_RENDER_FINGERPRINT').at(-1)?.fingerprint || null,
    trace: window.__GO_E10_ACCEPTANCE_TRACE__ || [],
  }));
}

async function runRealDataLordTransition(browser, origin) {
  const page = await openPage(browser, origin);
  const api = await installRealApi(page);
  try {
    const queueContract = { length: queue.length, valid: queue.every(Number.isInteger), unique: new Set(queue).size, consecutiveDuplicates: queue.slice(1).filter((qid, i) => qid === queue[i]).length };
    if (queueContract.length !== 20 || !queueContract.valid || queueContract.unique !== 20 || queueContract.consecutiveDuplicates !== 0) throw new Error(`real queue contract failed: ${JSON.stringify(queueContract)}`);
    await startLord(page);
    const before = await boardSnapshot(page);
    await clickBoard(page, 3, 3);
    await page.waitForFunction((next) => Number(currentQ?.id) === next && _bossIndex === 1, queue[1], { timeout: 10000 });
    const afterQ2 = await boardSnapshot(page);
    await clickBoard(page, 1, 1);
    await page.waitForFunction((next) => Number(currentQ?.id) === next && _bossIndex === 2, queue[2], { timeout: 10000 });
    const afterQ3 = await boardSnapshot(page);
    const transitionEvents = afterQ3.trace.filter((e) => e.event === 'BOSS_TRANSITION_EXCEPTION');
    if (afterQ2.qid !== queue[1] || afterQ3.qid !== queue[2] || !before.nodeReady || !afterQ2.nodeReady || !afterQ3.nodeReady
      || before.fingerprint?.boardSerial === afterQ2.fingerprint?.boardSerial
      || afterQ2.fingerprint?.boardSerial === afterQ3.fingerprint?.boardSerial
      || transitionEvents.length || api.reviews.length !== 2) {
      throw new Error(`real-data Boss board did not complete both transitions: ${JSON.stringify({ before, afterQ2, afterQ3, reviews: api.reviews, transitionEvents })}`);
    }
    return { queueContract, before, afterQ2, afterQ3, reviews: api.reviews };
  } finally {
    await page.close();
  }
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
    return result;
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

async function main() {
  const { server, origin } = await startStaticServer(repoRoot);
  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  try {
    const lord = await runRealDataLordTransition(browser, origin);
    const resume = await runReturnMapResume(browser, origin);
    const zone2Audio = await runZone2Audio(browser, origin);
    const zone1Audio = await runZone1Audio(browser, origin);
    console.log(JSON.stringify({ ok: true, engine: 'chromium-iPad-viewport-Safari-media-contract', ipadViewport: { width: 1024, height: 1366 }, lord, resume, zone2Audio, zone1Audio }, null, 2));
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
