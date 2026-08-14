/*
 * E10 Owner true-device acceptance regression.
 *
 * This contract deliberately drives the production board surface.  It never
 * calls submitSRS() or _handleBossAnswer() to simulate an answer; the only
 * answer input is a real pointer click on the WGo canvas.  The fixture only
 * supplies deterministic question/API responses and leaves the answer/event
 * path owned by index.html.
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

const FAKE_INIT_SCRIPT = `
(() => {
  class FakeAudio { constructor() {} play() { return Promise.resolve(); } pause() {} }
  window.Audio = FakeAudio;
  window.speechSynthesis = { getVoices: () => [], speak: () => {}, cancel: () => {} };
  window.SpeechSynthesisUtterance = function () {};
})();
`;

async function newPage(browser, origin, { viewport = { width: 1440, height: 900 }, shell = false } = {}) {
  const page = await browser.newPage({ viewport });
  await page.addInitScript(FAKE_INIT_SCRIPT);
  await page.route('**/api/**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: '{}',
  }));
  await page.route('**/api/auth/me', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      logged_in: true,
      user_id: 1,
      username: 'owner_acceptance_fixture',
      display_name: 'Owner Acceptance Fixture',
      is_admin: false,
      is_premium: true,
      needs_onboarding_choice: false,
      tour_done: true,
    }),
  }));
  const query = shell
    ? '?lang=zh&E9_DEBUG=1&e9Shell=1&e9TopHud=1&e9LeftNav=1&e9RightCards=1&e9BottomDock=1&e9WorldStage=1&go-odyssey-static-contract=e10-vs1f-integrated-world-map&staticContract=e10-vs1f-integrated-world-map'
    : '?lang=zh';
  await page.goto(`${origin}/index.html${query}`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(120);
  return page;
}

function lordZone({ cleared = false } = {}) {
  return {
    key: 'k26_30', name: '新手村', name_en: 'Beginner Village',
    status: cleared ? 'completed' : 'unlocked', unlocked: true,
    can_enter: true, cleared, completed: cleared, stars: cleared ? 2 : 0,
    seen: 30, total: 30, boss: { available: !cleared },
    boss_exam_size: 20, boss_pass_score: 16, cooldown_required: 30,
  };
}

function question(id, move, acceptedMove = null) {
  return {
    id,
    topic: 'Owner board fixture',
    content: `(;GM[1]SZ[9]PL[B];B[${move}])`,
    accepted_moves: acceptedMove ? [acceptedMove] : [],
  };
}

async function runRealBoardProgress(browser, origin) {
  const fixtureQuestions = [
    question(101, 'dd', { x: 3, y: 3 }),
    question(102, 'ee', { x: 3, y: 3 }),
    question(103, 'ff', { x: 3, y: 3 }),
  ];
  const fixtureZone = lordZone();
  const page = await newPage(browser, origin, {
    viewport: { width: 1024, height: 1366 },
  });
  // Reload once with the deterministic bootstrap installed. The legacy page
  // starts its own request during load; an empty late response must not race
  // the real board-answer fixture after we install it.
  await page.route('**/api/adventure/bootstrap**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ zones: [fixtureZone], cinematics: {} }),
  }));
  await page.route('**/api/questions**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(fixtureQuestions),
  }));
  await page.addInitScript(() => {
    localStorage.setItem('last_session_uid_v1', '1');
    localStorage.setItem('adventure_bossready_seen_v1', JSON.stringify({ 1: { k26_30: Date.now() } }));
  });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ === true, { timeout: 10000 });
  await page.waitForTimeout(150);
  const startRequests = [];
  await page.route('**/api/adventure/boss/start', async (route) => {
    startRequests.push(route.request().postData() || '');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        replay: false,
        attempt_mode: 'first_clear',
        question_ids: [101, 102, 103],
        attempt_id: 'ipad-board-attempt-001',
        zone: lordZone(),
      }),
    });
  });
  await page.route('**/api/adventure/boss/finish', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      ok: true, passed: false, correct: 1, total: 3, cooldown_left: 30,
      zones: [lordZone(), { key: 'k21_25', unlocked: false }],
    }),
  }));
  try {
    await page.evaluate(({ fixtureQuestions, fixtureZone }) => {
      allQuestions = fixtureQuestions;
      _adventureProgress = [{
        ...fixtureZone,
        index: 0,
        stages: [{ can_enter: true, completed: false }],
      }];
      SRS.review = async (questionId, grade, unit, unitDone, metadata) => {
        window.__ownerReviewLog = window.__ownerReviewLog || [];
        window.__ownerReviewLog.push({
          questionId: Number(questionId), grade: Number(grade), metadata,
        });
        return { ok: true };
      };
      SRS.reportUnitProgress = async () => ({ unit_complete: false });
      SRS.markSeen = () => {};
      // This is the same canonical Lord entry used by the production CTA;
      // the test does not call either answer-settlement function directly.
      const trigger = document.createElement('button');
      trigger.id = 'owner-fixture-lord-cta';
      trigger.textContent = '挑戰領主';
      trigger.addEventListener('click', () => openAdventureBossFromQuestCard('k26_30'));
      document.body.appendChild(trigger);
    }, { fixtureQuestions, fixtureZone });
    await page.locator('#owner-fixture-lord-cta').click();
    await page.locator('#boss-cinematic-btn').click();
    await page.waitForTimeout(6500);
    await page.waitForFunction(() => document.getElementById('boss-trial-progress')?.textContent.includes('1/3'));
    await page.locator('#board-canvas-wrap canvas').first().waitFor({ state: 'visible' });

    async function clickBoardAt(x, y) {
      const box = await page.locator('#board-canvas-wrap canvas').first().boundingBox();
      if (!box) throw new Error('WGo board canvas has no hit-test box');
      const size = 9;
      await page.mouse.click(box.x + box.width * ((x + 0.5) / size), box.y + box.height * ((y + 0.5) / size));
    }

    // Q1: actual WGo board move matches the fixture solution [dd].
    await clickBoardAt(3, 3);
    await page.waitForFunction(() => document.getElementById('boss-trial-progress')?.textContent.includes('2/3'));
    const afterCorrect = await page.evaluate(() => ({
      progress: document.getElementById('boss-trial-progress')?.textContent || '',
      currentQuestion: Number(currentQ?.id),
      bossIndex: _bossIndex,
      bossCorrect: _bossCorrect,
    }));
    if (!afterCorrect.progress.includes('已答對 1') || afterCorrect.currentQuestion !== 102
      || afterCorrect.bossIndex !== 1 || afterCorrect.bossCorrect !== 1) {
      throw new Error(`real correct board answer did not advance Boss queue: ${JSON.stringify(afterCorrect)}`);
    }

    // Q2: an actual off-tree move is a wrong answer and must advance once
    // without incrementing the correct tally.
    await clickBoardAt(1, 1);
    await page.waitForFunction(() => document.getElementById('boss-trial-progress')?.textContent.includes('3/3'));
    const trace = await page.evaluate(() => ({
      progress: document.getElementById('boss-trial-progress')?.textContent || '',
      currentQuestion: Number(currentQ?.id),
      bossIndex: _bossIndex,
      bossCorrect: _bossCorrect,
      reviewLog: window.__ownerReviewLog || [],
      nextDisabled: !!document.querySelector('.btn-row button[onclick="nextQuestion()"]')?.disabled,
      queue: _bossQueue.slice(),
    }));
    if (!trace.progress.includes('已答對 1') || trace.currentQuestion !== 103
      || trace.bossIndex !== 2 || trace.bossCorrect !== 1) {
      throw new Error(`real wrong board answer did not advance exactly once: ${JSON.stringify(trace)}`);
    }
    if (trace.reviewLog.length !== 2
      || trace.reviewLog[0].questionId !== 101 || trace.reviewLog[0].grade < 3
      || trace.reviewLog[1].questionId !== 102 || trace.reviewLog[1].grade !== 0
      || trace.reviewLog[0].metadata?.source_context !== 'boss_trial:ipad-board-attempt-001'
      || trace.reviewLog[1].metadata?.source_context !== 'boss_trial:ipad-board-attempt-001') {
      throw new Error(`unexpected real board review path: ${JSON.stringify(trace.reviewLog)}`);
    }
    if (!trace.nextDisabled || JSON.stringify(trace.queue) !== JSON.stringify([101, 102, 103])) {
      throw new Error(`Boss queue/Next authority contract failed: ${JSON.stringify(trace)}`);
    }
    if (startRequests.length !== 1) throw new Error(`expected one Lord start request, got ${startRequests.length}`);
    return { afterCorrect, trace };
  } finally {
    await page.close();
  }
}

async function runRealBoardResume(browser, origin) {
  const fixtureQuestions = [
    question(101, 'dd', { x: 3, y: 3 }),
    question(102, 'ee', { x: 3, y: 3 }),
    question(103, 'ff', { x: 3, y: 3 }),
  ];
  const fixtureZone = lordZone();
  const page = await newPage(browser, origin, {
    viewport: { width: 1024, height: 1366 },
  });
  await page.route('**/api/adventure/bootstrap**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ zones: [fixtureZone], cinematics: {} }),
  }));
  await page.route('**/api/questions**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(fixtureQuestions),
  }));
  await page.addInitScript(() => {
    localStorage.setItem('last_session_uid_v1', '1');
    localStorage.setItem('adventure_bossready_seen_v1', JSON.stringify({ 1: { k26_30: Date.now() } }));
  });
  const startRequests = [];
  await page.route('**/api/adventure/boss/start', async (route) => {
    const callIndex = startRequests.length;
    startRequests.push(route.request().postData() || '');
    const resumed = callIndex === 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        replay: false,
        attempt_mode: 'first_clear',
        question_ids: [101, 102, 103],
        resume_index: resumed ? 1 : 0,
        answered_count: resumed ? 1 : 0,
        correct: resumed ? 1 : 0,
        resumed,
        ready_to_finish: false,
        attempt_id: 'ipad-resume-attempt-001',
        zone: fixtureZone,
      }),
    });
  });
  await page.route('**/api/adventure/boss/finish', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      ok: true, passed: false, correct: 1, total: 3, cooldown_left: 30,
      zones: [fixtureZone, { key: 'k21_25', unlocked: false }],
    }),
  }));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ === true, { timeout: 10000 });
  await page.waitForTimeout(150);

  async function installRealEntryAndSrs() {
    await page.evaluate(({ fixtureQuestions: questions, fixtureZone: zone }) => {
      allQuestions = questions;
      _adventureProgress = [{
        ...zone,
        index: 0,
        stages: [{ can_enter: true, completed: false }],
      }];
      SRS.review = async (questionId, grade, unit, unitDone, metadata) => {
        window.__ownerResumeReviewLog = window.__ownerResumeReviewLog || [];
        window.__ownerResumeReviewLog.push({
          questionId: Number(questionId), grade: Number(grade), metadata,
        });
        return { ok: true };
      };
      SRS.reportUnitProgress = async () => ({ unit_complete: false });
      SRS.markSeen = () => {};
      const trigger = document.createElement('button');
      trigger.id = 'owner-fixture-lord-resume-cta';
      trigger.textContent = '??蜓';
      trigger.addEventListener('click', () => openAdventureBossFromQuestCard('k26_30'));
      document.body.appendChild(trigger);
    }, { fixtureQuestions, fixtureZone });
  }

  async function clickBoardAt(x, y) {
    const box = await page.locator('#board-canvas-wrap canvas').first().boundingBox();
    if (!box) throw new Error('WGo board canvas has no hit-test box');
    await page.mouse.click(box.x + box.width * ((x + 0.5) / 9), box.y + box.height * ((y + 0.5) / 9));
  }

  try {
    await installRealEntryAndSrs();
    await page.locator('#owner-fixture-lord-resume-cta').click();
    await page.locator('#boss-cinematic-btn').click();
    await page.waitForTimeout(6500);
    await page.waitForFunction(() => document.getElementById('boss-trial-progress')?.textContent.includes('1/3'));
    await clickBoardAt(3, 3);
    await page.waitForFunction(() => document.getElementById('boss-trial-progress')?.textContent.includes('2/3'));
    const beforeReload = await page.evaluate(() => ({
      progress: document.getElementById('boss-trial-progress')?.textContent || '',
      currentQuestion: Number(currentQ?.id),
      bossIndex: _bossIndex,
      bossCorrect: _bossCorrect,
      attemptId: _bossAttemptId,
      reviewLog: window.__ownerResumeReviewLog || [],
    }));
    if (beforeReload.currentQuestion !== 102 || beforeReload.bossIndex !== 1 || beforeReload.bossCorrect !== 1
      || beforeReload.attemptId !== 'ipad-resume-attempt-001'
      || beforeReload.reviewLog[0]?.metadata?.source_context !== 'boss_trial:ipad-resume-attempt-001') {
      throw new Error(`pre-reload Boss state is wrong: ${JSON.stringify(beforeReload)}`);
    }

    // Preserve the browser session, but rebuild the page and re-enter through
    // the same Lord CTA. The second mocked start response is the server-owned
    // resume response, not a client cursor supplied by this test.
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ === true, { timeout: 10000 });
    await page.waitForTimeout(150);
    await installRealEntryAndSrs();
    await page.locator('#owner-fixture-lord-resume-cta').click();
    await page.locator('#boss-cinematic-btn').click();
    await page.waitForTimeout(6500);
    await page.waitForFunction(() => document.getElementById('boss-trial-progress')?.textContent.includes('2/3'));
    const afterReload = await page.evaluate(() => ({
      progress: document.getElementById('boss-trial-progress')?.textContent || '',
      currentQuestion: Number(currentQ?.id),
      bossIndex: _bossIndex,
      bossCorrect: _bossCorrect,
      queue: _bossQueue.slice(),
      attemptId: _bossAttemptId,
    }));
    if (afterReload.currentQuestion !== 102 || afterReload.bossIndex !== 1 || afterReload.bossCorrect !== 1
      || JSON.stringify(afterReload.queue) !== JSON.stringify([101, 102, 103])
      || afterReload.attemptId !== 'ipad-resume-attempt-001') {
      throw new Error(`page reload did not resume Q2 from server state: ${JSON.stringify(afterReload)}`);
    }
    await clickBoardAt(1, 1);
    await page.waitForFunction(() => document.getElementById('boss-trial-progress')?.textContent.includes('3/3'));
    if (startRequests.length !== 2) throw new Error(`expected exactly two start calls, got ${startRequests.length}`);
    return { beforeReload, afterReload, startRequests };
  } finally {
    await page.close();
  }
}

async function runLostFinishRecovery(browser, origin) {
  const fixtureZone = lordZone();
  const page = await newPage(browser, origin, {
    viewport: { width: 1024, height: 1366 },
  });
  let finishCalls = 0;
  await page.route('**/api/adventure/bootstrap**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ zones: [fixtureZone], cinematics: {} }),
  }));
  await page.route('**/api/questions**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify([question(301, 'dd')]),
  }));
  await page.route('**/api/adventure/boss/start', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      ok: true,
      replay: false,
      attempt_mode: 'first_clear',
      question_ids: [301, 302, 303],
      resumed: true,
      resume_index: 3,
      answered_count: 3,
      correct: 2,
      ready_to_finish: true,
      attempt_id: 'lost-finish-attempt-001',
      zone: fixtureZone,
    }),
  }));
  await page.route('**/api/adventure/boss/finish', async (route) => {
    finishCalls += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true, passed: false, correct: 2, total: 3, cooldown_left: 30,
        zones: [fixtureZone],
      }),
    });
  });
  await page.addInitScript(() => {
    localStorage.setItem('last_session_uid_v1', '1');
    localStorage.setItem('adventure_bossready_seen_v1', JSON.stringify({ 1: { k26_30: Date.now() } }));
  });
  await page.goto(`${origin}/index.html?lang=zh`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ === true, { timeout: 10000 });
  await page.evaluate((zone) => {
    _adventureProgress = [{ ...zone, index: 0, stages: [{ can_enter: true, completed: false }] }];
    const trigger = document.createElement('button');
    trigger.id = 'owner-fixture-lord-finish-recovery-cta';
    trigger.textContent = '??蜓';
    trigger.addEventListener('click', () => openAdventureBossFromQuestCard('k26_30'));
    document.body.appendChild(trigger);
  }, fixtureZone);
  try {
    await page.locator('#owner-fixture-lord-finish-recovery-cta').click();
    await page.locator('#boss-cinematic-btn').click();
    for (let i = 0; i < 100 && finishCalls !== 1; i += 1) await page.waitForTimeout(50);
    if (finishCalls !== 1) throw new Error(`lost-finish recovery called finish ${finishCalls} times`);
    return { finishCalls };
  } finally {
    await page.close();
  }
}

async function runReplayCta(browser, origin, stars) {
  const page = await newPage(browser, origin, {
    viewport: { width: 1024, height: 1366 },
    shell: true,
  });
  await page.route('**/api/questions**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: '[]',
  }));
  await page.route('**/api/adventure/bootstrap**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      zones: [{ ...lordZone({ cleared: true }), stars }],
      primary_action: { kind: 'replay_completed', zone_key: 'k26_30' },
      secondary_action: stars < 3 ? { kind: 'replenish_stars', zone_key: 'k26_30' } : null,
      cinematics: {},
    }),
  }));
  await page.addInitScript(() => {
    localStorage.setItem('last_session_uid_v1', '1');
    localStorage.setItem('adventure_bossready_seen_v1', JSON.stringify({ 1: { k26_30: Date.now() } }));
  });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);
  const bossStarts = [];
  await page.route('**/api/adventure/bootstrap**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      zones: [
        { ...lordZone({ cleared: true }), stars },
        { key: 'k21_25', name: '史萊姆平原', name_en: 'Slime Plains', status: 'locked', locked: true, can_enter: false, cleared: false, stars: 0, seen: 0, total: 20, boss: { available: false } },
      ],
      current_zone_key: 'k26_30',
      selected: { zone_key: 'k26_30' },
      recommended: { zone_key: 'k26_30' },
      primary_action: { kind: 'replay_completed', zone_key: 'k26_30' },
      secondary_action: stars < 3 ? { kind: 'replenish_stars', zone_key: 'k26_30' } : null,
      cinematics: {},
    }),
  }));
  await page.route('**/api/adventure/boss/start', async (route) => {
    bossStarts.push(route.request().postData() || '');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, replay: true, attempt_mode: 'replay', attempt_id: `replay-attempt-${stars}`, question_ids: [201], zone: lordZone({ cleared: true }) }),
    });
  });
  try {
    const fixtureQuestion = question(201, 'dd');
    await page.evaluate((fixtureQuestion) => {
      allQuestions = [fixtureQuestion];
      SRS.review = async () => ({ ok: true });
      SRS.reportUnitProgress = async () => ({ unit_complete: false });
      SRS.markSeen = () => {};
    }, fixtureQuestion);
    await page.locator('#e9-world-stage-details-cta').waitFor({ state: 'visible', timeout: 10000 });
    const before = await page.evaluate(() => ({
      primary: document.getElementById('e9-world-stage-details-cta')?.textContent || '',
      secondary: (() => {
        const node = document.getElementById('e9-world-stage-details-secondary-cta');
        return node ? { hidden: node.hidden, disabled: node.disabled, text: node.textContent || '' } : null;
      })(),
    }));
    if (!before.primary.includes('再次挑戰領主')) {
      throw new Error(`cleared ${stars}-star primary CTA is not replay: ${JSON.stringify(before)}`);
    }
    if (stars < 3) {
      if (!before.secondary || before.secondary.hidden || before.secondary.disabled
        || !before.secondary.text.includes('補星修行')) {
        throw new Error(`cleared ${stars}-star secondary training CTA missing: ${JSON.stringify(before)}`);
      }
    } else if (before.secondary && !before.secondary.hidden) {
      throw new Error('3-star cleared zone unexpectedly exposes a star-training CTA');
    }

    await page.locator('#e9-world-stage-details-cta').click();
    await page.locator('#boss-cinematic-btn').waitFor({ state: 'visible', timeout: 10000 });
    const cardLabel = await page.locator('#boss-cinematic-btn').textContent();
    if (!cardLabel.includes('再次挑戰領主')) throw new Error(`Lord Card replay label missing: ${cardLabel}`);
    await page.locator('#boss-cinematic-btn').click();
    await page.locator('#boss-trial-progress').waitFor({ state: 'visible', timeout: 10000 });
    if (bossStarts.length !== 1) throw new Error(`expected one replay boss/start request, got ${bossStarts.length}`);
    return { stars, primary: before.primary, secondary: before.secondary?.text || '', bossStarts };
  } finally {
    await page.close();
  }
}

async function main() {
  const { server, origin } = await startStaticServer(repoRoot);
  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  try {
    const board = await runRealBoardProgress(browser, origin);
    const resume = await runRealBoardResume(browser, origin);
    const lostFinish = await runLostFinishRecovery(browser, origin);
    const replay = [];
    for (const stars of [1, 2, 3]) replay.push(await runReplayCta(browser, origin, stars));
    console.log(JSON.stringify({
      ok: true,
      ipadViewport: { width: 1024, height: 1366 },
      realBoard: board,
      resume,
      lostFinish,
      replay,
    }, null, 2));
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
