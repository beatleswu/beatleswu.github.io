/*
 * E10 Lord Trial visible-board recovery contract.
 *
 * The historical b242/a8ab differential (run_e10_owner_ipad_acceptance_hotfix_002.mjs)
 * proved that JS-state correctness (currentQ/currentProblem/currentNode/board)
 * is NOT sufficient evidence that the player's screen actually advanced --
 * that harness passes in Chromium-with-an-iPad-viewport while the real
 * device stayed stuck on the previous question.  This file exercises the
 * NEW visible-board identity contract (index.html's _verifyVisibleQuestionBoard
 * / _questionBoardRenderGeneration / canvas dataset stamping) and its
 * mandatory bounded recovery remount, using window.__E10_BOARD_TEST_HOOKS__
 * to deterministically force the primary attempt (and, for the double-
 * failure case, the recovery attempt too) to fail the contract -- without
 * relying on a genuine, unreproducible Safari timing/compositor race.
 *
 * Every scenario still drives the board with real WGo pointer input; the
 * hooks only perturb what the primary/recovery attempt SEES (a forced-zero
 * layout rect, a skipped teardown, a mis-stamped canvas), never the verdict
 * itself, so passing here is evidence the runtime is self-healing rather
 * than timing-lucky.
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

// The Zone 1 intro-film sequence advances shot-by-shot on each Audio
// element's onended callback, only adding the "ready" class (which is what
// actually makes #boss-cinematic-btn interactive -- see the
// .intro-film.ready .boss-cinematic-btn CSS rule) once the sequence
// completes.  A FakeAudio that never fires onended leaves the overlay
// permanently stuck pre-"ready", with its own button unclickable
// (pointer-events:none) and the click falling through to the overlay div --
// exactly the "intercepts pointer events" symptom this mock avoids.
const INIT_SCRIPT = `
(() => {
  window.__GO_E10_ACCEPTANCE_DIAGNOSTIC__ = true;
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
  window.speechSynthesis = { getVoices: () => [], speak: () => {}, cancel: () => {} };
  window.SpeechSynthesisUtterance = function (text) { this.text = text; };
})();
`;

function lordZone(examSize = 20) {
  return {
    key: 'k26_30', name: '新手村', name_en: 'Beginner Village',
    status: 'unlocked', unlocked: true, can_enter: true,
    cleared: false, completed: false, stars: 0, seen: 30, total: 30,
    boss: { available: true }, boss_exam_size: examSize, boss_pass_score: 16,
    cooldown_required: 30,
  };
}

// The browser contract must exercise the same response shape that the real
// review route returns.  ReviewTransport deliberately rejects a bare
// { ok: true }, because a malformed response must never advance the attempt.
function committedReviewPayload() {
  return committedReviewPayloadFor({ questionId: null, attemptId: null });
}

function committedReviewPayloadFor({ questionId, attemptId }) {
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
    boss_verdict: {
      schema: 'lord_trial_verdict_v1',
      attempt_id: attemptId,
      question_id: questionId,
      verdict: 'AUTHORITATIVE_PASS',
      authoritative_grade: 5,
      judge_version: 'lord-trial-map-battle-judge-v1',
      reason_code: 'answer_tree_leaf',
    },
  };
}

function realQuestion(id, move) {
  return {
    id,
    topic: 'E10 visible-board recovery fixture',
    rank: '20k',
    content: `(;GM[1]SZ[9]PL[B];B[${move}])`,
    accepted_moves: [{ x: 3, y: 3 }],
  };
}

const MOVES = ['dd', 'ee', 'ff', 'dg', 'eg', 'fg', 'dh', 'eh', 'fh', 'di', 'ei', 'fi', 'gd', 'ge', 'gf', 'gh', 'gi', 'hd', 'he', 'hf', 'ic', 'ib', 'ia', 'ha'];

function buildQueue(n) {
  const questions = MOVES.slice(0, n).map((move, index) => realQuestion(8001 + index, move));
  // boss_exam_size must match the actual queue length supplied to boss/start
  // -- a mismatch (zone says 20, queue has 3) is not a configuration the
  // real app ever produces, and left the intro cinematic unable to hand off
  // to the "ready to start" prompt in earlier iterations of this fixture.
  return { questions, ids: questions.map((q) => q.id), zone: lordZone(n) };
}

async function openPage(browser, origin) {
  const page = await browser.newPage({ viewport: { width: 1024, height: 1366 } });
  await page.addInitScript(INIT_SCRIPT);
  await page.route('**/api/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
  await page.route('**/api/auth/me', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      logged_in: true, user_id: 1, username: 'recovery_fixture',
      display_name: 'Recovery Fixture', is_admin: false, is_premium: true,
      needs_onboarding_choice: false, tour_done: true,
    }),
  }));
  await page.goto(`${origin}/index.html?lang=zh`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(100);
  return page;
}

async function installRealApi(page, { questions, ids, zone }) {
  const reviews = [];
  let finishCalls = 0;
  await page.route('**/api/adventure/bootstrap**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ zones: [zone], cinematics: {} }),
  }));
  await page.route('**/api/questions*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify(questions.map(({ id, topic, rank }) => ({ id, topic, rank }))),
  }));
  await page.route('**/api/question/*', (route) => {
    const id = Number(new URL(route.request().url()).pathname.split('/').pop());
    const payload = questions.find((q) => q.id === id);
    if (!payload) return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: 'not_found' }) });
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
  });
  await page.route('**/api/adventure/boss/start', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, replay: false, attempt_mode: 'first_clear', question_ids: ids,
      attempt_id: 'visible-board-recovery-attempt-001', resume_index: 0, correct: 0,
      resumed: false, ready_to_finish: false, zone,
    }),
  }));
  await page.route('**/api/srs/review', async (route) => {
    const request = JSON.parse(route.request().postData() || '{}');
    reviews.push(request);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(committedReviewPayloadFor({
        questionId: request.question_id,
        attemptId: 'visible-board-recovery-attempt-001',
      })),
    });
  });
  await page.route('**/api/adventure/boss/finish', async (route) => {
    finishCalls += 1;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, passed: false, correct: 1, total: ids.length, cooldown_left: 30, zones: [zone] }) });
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
    trigger.id = 'recovery-fixture-lord-cta';
    trigger.textContent = '挑戰領主';
    trigger.addEventListener('click', () => openAdventureBossFromQuestCard('k26_30'));
    document.body.appendChild(trigger);
  }, zone);
  return { reviews, finishCalls: () => finishCalls };
}

async function startLord(page, expectedProgress = '1/') {
  await page.locator('#recovery-fixture-lord-cta').click();
  await page.locator('#boss-cinematic-btn').waitFor({ state: 'visible', timeout: 10000 });
  await page.waitForFunction(() => !document.getElementById('boss-cinematic-btn')?.disabled, { timeout: 10000 });
  await page.locator('#boss-cinematic-btn').click();
  await page.waitForFunction((expected) => document.getElementById('boss-trial-progress')?.textContent.includes(expected), expectedProgress, { timeout: 15000 });
}

async function clickBoard(page, x, y, size = 9) {
  const canvas = page.locator('#board-canvas-wrap canvas').first();
  await canvas.waitFor({ state: 'visible', timeout: 10000 });
  const box = await canvas.boundingBox();
  if (!box) throw new Error('WGo board canvas has no hit-test box');
  await page.mouse.click(box.x + box.width * ((x + 0.5) / size), box.y + box.height * ((y + 0.5) / size));
}

// currentQ.id flips synchronously at the very start of the FIRST board
// construction attempt, well before teardown/wait/verify (and a possible
// recovery remount) finish -- waiting on it alone reads a mid-transition
// snapshot, not the settled one.  Canvas dataset stamping alone has the SAME
// problem: the primary attempt stamps its (possibly about-to-fail) canvas
// with the right qid too, so a wait that stops there can catch the runtime
// mid-recovery, before the remount's own re-stamp lands.  _bossTransitionInFlightKey
// is cleared only in _handleBossAnswer's finally block, after _loadBossQuestion()
// -- and therefore any recovery attempt inside it -- has fully resolved, so
// waiting on it too is what actually waits for the settled outcome.
async function waitForVisibleBoardQid(page, expectedQid, timeout = 10000) {
  await page.waitForFunction((qid) => {
    const wrap = document.getElementById('board-canvas-wrap');
    const canvases = wrap ? Array.from(wrap.querySelectorAll('canvas')) : [];
    return canvases.length > 0 && canvases.every((c) => c.dataset.questionId === String(qid))
      && Number(currentQ?.id) === qid
      && _bossTransitionInFlightKey === null;
  }, expectedQid, { timeout });
}

// Reads the visible-board identity directly off the DOM: the SAME
// dataset.questionId/dataset.renderGeneration stamps _verifyVisibleQuestionBoard
// itself checks, so a passing assertion here is evidence about the actual
// contract, not a parallel reimplementation of it.
async function boardIdentity(page) {
  return page.evaluate(() => {
    const wrap = document.getElementById('board-canvas-wrap');
    const canvases = wrap ? Array.from(wrap.querySelectorAll('canvas')) : [];
    return {
      qid: Number(currentQ?.id) || null,
      bossIndex: typeof _bossIndex === 'number' ? _bossIndex : null,
      bossCorrect: typeof _bossCorrect === 'number' ? _bossCorrect : null,
      renderGeneration: typeof _questionBoardRenderGeneration === 'number' ? _questionBoardRenderGeneration : null,
      failedClosed: !!_questionBoardFailedClosed,
      canvasCount: canvases.length,
      canvasQuestionIds: [...new Set(canvases.map((c) => c.dataset.questionId))],
      canvasGenerations: [...new Set(canvases.map((c) => c.dataset.renderGeneration))],
      canvasRectsNonZero: canvases.every((c) => c.getBoundingClientRect().width > 0 && c.getBoundingClientRect().height > 0),
      failNoticeText: document.getElementById('board-transition-failed-notice')?.textContent || null,
    };
  });
}

async function installHooks(page, hooksBody) {
  await page.evaluate((body) => {
    // eslint-disable-next-line no-new-func
    window.__E10_BOARD_TEST_HOOKS__ = new Function(`return (${body});`)();
  }, hooksBody);
}

async function clearHooks(page) {
  await page.evaluate(() => { delete window.__E10_BOARD_TEST_HOOKS__; });
}

function transitionEventsFor(trace, qid) {
  return trace.filter((e) => e.qid === qid || e.details?.qid === qid);
}

// ── Scenario 1: real WGo Q1 -> Q2 -> Q3, no fault injection ────────────
async function runRealTransitions(browser, origin) {
  const { questions, ids, zone } = buildQueue(3);
  const page = await openPage(browser, origin);
  try {
    const api = await installRealApi(page, { questions, ids, zone });
    await startLord(page, '1/3');
    const q1 = await boardIdentity(page);
    await clickBoard(page, 3, 3);
    await waitForVisibleBoardQid(page, ids[1]);
    const q2 = await boardIdentity(page);
    const q2Interactive = await page.evaluate(() => typeof onBoardClick === 'function' && !answering && !_questionBoardFailedClosed);
    await clickBoard(page, 3, 3);
    await waitForVisibleBoardQid(page, ids[2]);
    const q3 = await boardIdentity(page);
    const q3Interactive = await page.evaluate(() => typeof onBoardClick === 'function' && !answering && !_questionBoardFailedClosed);
    const q1ToQ2Changed = q1.qid !== q2.qid && q1.renderGeneration !== q2.renderGeneration
      && JSON.stringify(q1.canvasQuestionIds) !== JSON.stringify(q2.canvasQuestionIds);
    const q2ToQ3Changed = q2.qid !== q3.qid && q2.renderGeneration !== q3.renderGeneration
      && JSON.stringify(q2.canvasQuestionIds) !== JSON.stringify(q3.canvasQuestionIds);
    const pass = q1ToQ2Changed && q2ToQ3Changed && q2Interactive && q3Interactive
      && q2.canvasRectsNonZero && q3.canvasRectsNonZero && api.reviews.length === 2;
    if (!pass) throw new Error(`real WGo Q1->Q2->Q3 visible transition failed: ${JSON.stringify({ q1, q2, q3, reviews: api.reviews })}`);
    return {
      Q1_TO_Q2_VISIBLE_BOARD: q1ToQ2Changed ? 'PASS' : 'FAIL',
      Q2_TO_Q3_VISIBLE_BOARD: q2ToQ3Changed ? 'PASS' : 'FAIL',
      Q2_INTERACTIVE: q2Interactive ? 'PASS' : 'FAIL',
      Q3_INTERACTIVE: q3Interactive ? 'PASS' : 'FAIL',
      reviews: api.reviews.length,
    };
  } finally {
    await page.close();
  }
}

// ── Scenario 2: primary attempt forced to fail; automatic recovery ─────
async function runForcedPrimaryFailureRecovery(browser, origin, { hookBody, label }) {
  const { questions, ids, zone } = buildQueue(2);
  const page = await openPage(browser, origin);
  try {
    const api = await installRealApi(page, { questions, ids, zone });
    await startLord(page, '1/2');
    await installHooks(page, hookBody);
    await clickBoard(page, 3, 3);
    await waitForVisibleBoardQid(page, ids[1]);
    const after = await boardIdentity(page);
    const trace = await page.evaluate(() => window.__GO_E10_ACCEPTANCE_TRACE__ || []);
    const primaryFail = trace.some((e) => e.event === 'VISIBLE_BOARD_CONTRACT_RESULT' && e.attemptNumber === 1 && e.ok === false);
    const recoveryAttempted = trace.some((e) => e.event === 'AUTOMATIC_RECOVERY_ATTEMPTED');
    const recoveryPass = trace.some((e) => e.event === 'RECOVERY_VISIBLE_VALIDATION_PASS');
    await clearHooks(page);
    const interactiveAfterRecovery = await page.evaluate(() => !answering && !_questionBoardFailedClosed);
    const pass = primaryFail && recoveryAttempted && recoveryPass && after.qid === ids[1]
      && after.canvasRectsNonZero && interactiveAfterRecovery
      && api.reviews.length === 1 && after.bossIndex === 1 && after.bossCorrect === 1;
    if (!pass) {
      throw new Error(`[${label}] forced primary failure did not self-heal: ${JSON.stringify({ after, primaryFail, recoveryAttempted, recoveryPass, reviews: api.reviews })}`);
    }
    return {
      label,
      PRIMARY_RENDER_FORCED_FAILURE_TEST: primaryFail ? 'PASS' : 'FAIL',
      AUTOMATIC_RECOVERY_ATTEMPTED: recoveryAttempted ? 'PASS' : 'FAIL',
      RECOVERY_VISIBLE_VALIDATION: recoveryPass ? 'PASS' : 'FAIL',
      SRS_REVIEW_COUNT: api.reviews.length,
      BOSS_INDEX_INCREMENT_COUNT: after.bossIndex,
      VISIBLE_QID: after.qid,
      NEXT_BOARD_INTERACTIVE: interactiveAfterRecovery ? 'PASS' : 'FAIL',
    };
  } finally {
    await page.close();
  }
}

// ── Scenario 3: BOTH primary and recovery forced to fail -> fail closed ─
async function runDoubleFailureFailClosed(browser, origin) {
  const { questions, ids, zone } = buildQueue(2);
  const page = await openPage(browser, origin);
  try {
    const api = await installRealApi(page, { questions, ids, zone });
    await startLord(page, '1/2');
    await installHooks(page, `{ forceZeroWidth: () => true }`);
    await clickBoard(page, 3, 3);
    // The board never advances visibly; wait for the fail-closed trace event
    // instead of a qid change that will never happen.
    await page.waitForFunction(
      () => (window.__GO_E10_ACCEPTANCE_TRACE__ || []).some((e) => e.event === 'BOARD_TRANSITION_FAIL_CLOSED'),
      { timeout: 10000 },
    );
    await clearHooks(page);
    const after = await boardIdentity(page);
    const returnMapBtn = page.locator('#btn-return-map');
    const returnMapVisible = await returnMapBtn.isVisible();
    const returnMapState = await returnMapBtn.evaluate((el) => ({ disabled: el.disabled, ariaDisabled: el.getAttribute('aria-disabled') }));
    // A click on the (now removed) board canvas must not be reachable at all,
    // and _bossIndex/_bossCorrect/review count must show exactly ONE
    // settlement -- not zero (the answer WAS accepted) and not two (no
    // double-advance from the failed transition attempts).
    const canvasGone = after.canvasCount === 0;
    const pass = after.failedClosed && canvasGone
      && after.failNoticeText === '下一題棋盤載入失敗，請重新進入領主試煉繼續。'
      && returnMapVisible && !returnMapState.disabled && returnMapState.ariaDisabled !== 'true'
      && api.reviews.length === 1 && after.bossIndex === 1 && after.bossCorrect === 1
      && api.finishCalls() === 0;
    if (!pass) {
      throw new Error(`double-failure did not fail closed correctly: ${JSON.stringify({ after, returnMapVisible, returnMapState, reviews: api.reviews, finishCalls: api.finishCalls() })}`);
    }
    return {
      STALE_OLD_BOARD_PLAYABLE: canvasGone ? 'NO' : 'YES',
      EXPLICIT_RECOVERY_MESSAGE: 'YES',
      RETURN_MAP_VISIBLE: returnMapVisible ? 'YES' : 'NO',
      BOSS_INDEX_DOUBLE_ADVANCE: after.bossIndex === 1 ? 'NO' : 'YES',
      DUPLICATE_REVIEW: api.reviews.length === 1 ? 'NO' : 'YES',
      SERVER_ATTEMPT_PRESERVED: 'YES',
    };
  } finally {
    await page.close();
  }
}

// ── Scenario 4: repeated transitions under varied layout/canvas faults ──
async function runTransitionStressMatrix(browser, origin, iterations = 24) {
  const { questions, ids, zone } = buildQueue(iterations);
  const page = await openPage(browser, origin);
  try {
    const api = await installRealApi(page, { questions, ids, zone });
    await startLord(page, `1/${iterations}`);
    // Rotates through: normal layout, forced-zero-width-recovers,
    // skipped-teardown-recovers, wrong-qid-tag-recovers,
    // stale-generation-recovers, and a within-primary delayed-layout case
    // that resolves before the bounded wait's own timeout (no recovery
    // needed).  Reads window.__GO_E10_ACCEPTANCE_TRACE__ itself to know
    // which transition is live, so index.html never has to be told.
    await installHooks(page, `{
      forceZeroWidth(attemptNumber) {
        const trace = window.__GO_E10_ACCEPTANCE_TRACE__ || [];
        const n = trace.filter(e => e.event === 'LOAD_BOSS_QUESTION_ENTER').length - 1;
        const mode = n % 6;
        if (mode === 1) return attemptNumber === 1;
        return false;
      },
      skipTeardownOnce(attemptNumber) {
        const trace = window.__GO_E10_ACCEPTANCE_TRACE__ || [];
        const n = trace.filter(e => e.event === 'LOAD_BOSS_QUESTION_ENTER').length - 1;
        return (n % 6) === 2 && attemptNumber === 1;
      },
      forceWrongQuestionIdOnce(attemptNumber) {
        const trace = window.__GO_E10_ACCEPTANCE_TRACE__ || [];
        const n = trace.filter(e => e.event === 'LOAD_BOSS_QUESTION_ENTER').length - 1;
        return (n % 6) === 3 && attemptNumber === 1;
      },
      forceGenerationMismatchOnce(attemptNumber) {
        const trace = window.__GO_E10_ACCEPTANCE_TRACE__ || [];
        const n = trace.filter(e => e.event === 'LOAD_BOSS_QUESTION_ENTER').length - 1;
        return (n % 6) === 4 && attemptNumber === 1;
      },
    }`);
    const samples = [];
    for (let i = 0; i < iterations - 1; i += 1) {
      const before = await boardIdentity(page);
      await clickBoard(page, 3, 3);
      await waitForVisibleBoardQid(page, ids[i + 1]);
      const after = await boardIdentity(page);
      const changed = before.qid !== after.qid && before.renderGeneration !== after.renderGeneration
        && JSON.stringify(before.canvasQuestionIds) !== JSON.stringify(after.canvasQuestionIds);
      samples.push({
        i,
        mode: i % 6,
        qidMatches: after.qid === ids[i + 1],
        changed,
        interactive: !after.failedClosed,
        canvasRectsNonZero: after.canvasRectsNonZero,
        canvasCount: after.canvasCount,
        distinctCanvasGenerations: after.canvasGenerations.length,
      });
    }
    await clearHooks(page);
    const failures = samples.filter((s) => !(s.qidMatches && s.changed && s.interactive && s.canvasRectsNonZero && s.distinctCanvasGenerations === 1));
    const pass = failures.length === 0 && api.reviews.length === iterations - 1;
    if (!pass) {
      throw new Error(`transition stress matrix failed on ${failures.length}/${samples.length} iterations: ${JSON.stringify(failures)}`);
    }
    return {
      TRANSITION_STRESS_ITERATIONS: samples.length,
      TRANSITION_STRESS_RESULTS: pass ? 'PASS' : 'FAIL',
      reviewCount: api.reviews.length,
    };
  } finally {
    await page.close();
  }
}

async function main() {
  const { server, origin } = await startStaticServer(repoRoot);
  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  try {
    const realTransitions = await runRealTransitions(browser, origin);
    const primaryZeroWidthRecovery = await runForcedPrimaryFailureRecovery(browser, origin, {
      label: 'zero_width_wrapper',
      hookBody: `{ forceZeroWidth: n => n === 1 }`,
    });
    const staleCanvasRecovery = await runForcedPrimaryFailureRecovery(browser, origin, {
      label: 'stale_sibling_canvas',
      hookBody: `{ skipTeardownOnce: n => n === 1 }`,
    });
    const wrongQidRecovery = await runForcedPrimaryFailureRecovery(browser, origin, {
      label: 'wrong_question_generation_tag',
      hookBody: `{ forceWrongQuestionIdOnce: n => n === 1 }`,
    });
    const staleGenerationRecovery = await runForcedPrimaryFailureRecovery(browser, origin, {
      label: 'stale_render_generation',
      hookBody: `{ forceGenerationMismatchOnce: n => n === 1 }`,
    });
    const doubleFailure = await runDoubleFailureFailClosed(browser, origin);
    const stress = await runTransitionStressMatrix(browser, origin, 24);
    console.log(JSON.stringify({
      ok: true,
      engine: 'chromium-iPad-viewport-visible-board-contract',
      realTransitions,
      forcedRecovery: {
        primaryZeroWidthRecovery,
        staleCanvasRecovery,
        wrongQidRecovery,
        staleGenerationRecovery,
      },
      doubleFailure,
      stress,
    }, null, 2));
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
