/**
 * E10 V1A Lord review architecture contract runner.
 *
 * This is a real-path release gate: disposable PostgreSQL, the real Flask
 * app, the real signed Boss attempt, the real index.html/srs.js, real WGo,
 * and real browser clicks.  It never intercepts /api/srs/review.
 *
 * The runner reports contract evidence instead of deciding whether a frozen
 * b3cb baseline is expected-red.  The pytest wrapper classifies that result.
 */

import { spawn } from 'node:child_process';
import fssync from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import readline from 'node:readline';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const HARNESS = path.join(REPO_ROOT, 'tests', 'lord_trial_natural_runtime.py');
const ZONE_KEY = 'k26_30';
const SETTLE_MS = 1500;

const FAULTS = new Set([
  'BADGE_PRESENTATION_THROW',
  'PET_PRESENTATION_THROW',
  'MONSTER_PRESENTATION_THROW',
  'QUEST_PRESENTATION_THROW',
  'XP_PRESENTATION_THROW',
  'LOOT_PRESENTATION_THROW',
  'AUDIO_PRESENTATION_REJECT',
]);

function parseArgs(argv) {
  const options = { fixture: 'multi_ply', fault: null, badgePriming: false, rankPriming: false };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--fixture') { options.fixture = argv[++i]; }
    else if (argv[i] === '--presentation-failure') { options.fault = argv[++i]; }
    else if (argv[i] === '--badge-priming') { options.badgePriming = true; }
    else if (argv[i] === '--rank-priming') { options.rankPriming = true; }
  }
  if (options.fault && !FAULTS.has(options.fault)) {
    throw new Error(`unknown presentation fault: ${options.fault}`);
  }
  return options;
}

const OPTIONS = parseArgs(process.argv.slice(2));

function resolveChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  for (const candidate of candidates) if (fssync.existsSync(candidate)) return candidate;
  throw Object.assign(new Error('No Chrome/Edge executable found. Set CHROME_BIN.'), { unavailable: true });
}

function startRuntime() {
  const args = [HARNESS, 'serve', '--fixture', OPTIONS.fixture];
  if (OPTIONS.badgePriming) args.push('--badge-priming');
  if (OPTIONS.rankPriming) args.push('--rank-priming');
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON_BIN || 'python', args, {
      cwd: REPO_ROOT,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    const stderrTail = [];
    child.stderr.setEncoding('utf-8');
    child.stderr.on('data', (chunk) => {
      stderrTail.push(chunk);
      if (stderrTail.length > 80) stderrTail.shift();
    });
    const rl = readline.createInterface({ input: child.stdout });
    const timer = setTimeout(() => {
      rl.close();
      child.kill();
      reject(new Error(`runtime handshake timed out\n${stderrTail.join('')}`));
    }, 300000);
    rl.on('line', (line) => {
      let payload;
      try { payload = JSON.parse(line); } catch { return; }
      if (payload?.unavailable) {
        clearTimeout(timer);
        rl.close();
        child.kill();
        reject(Object.assign(new Error(payload.reason || 'runtime unavailable'), { unavailable: true }));
      } else if (payload?.ready === true) {
        clearTimeout(timer);
        rl.close();
        resolve({ child, runtime: payload });
      }
    });
    child.on('exit', (code) => {
      clearTimeout(timer);
      reject(new Error(`runtime exited early with code ${code}\n${stderrTail.join('')}`));
    });
  });
}

function stopRuntime(child) {
  try { child.stdin.end(); } catch {}
  return new Promise((resolve) => {
    const timer = setTimeout(() => { try { child.kill(); } catch {} resolve(); }, 30000);
    child.on('exit', () => { clearTimeout(timer); resolve(); });
  });
}

async function readState(page) {
  return page.evaluate(() => {
    const wrap = document.getElementById('board-canvas-wrap');
    const canvases = [...(wrap?.querySelectorAll('canvas') || [])];
    const trace = window.__GO_E10_ACCEPTANCE_TRACE__ || [];
    return {
      bossMode: typeof _bossMode !== 'undefined' ? _bossMode : null,
      bossIndex: typeof _bossIndex !== 'undefined' ? _bossIndex : null,
      bossQueue: typeof _bossQueue !== 'undefined' && _bossQueue ? _bossQueue.slice() : [],
      currentQuestionId: typeof currentQ !== 'undefined' && currentQ ? Number(currentQ.id) : null,
      boardHidden: wrap?.classList.contains('hidden') ?? null,
      canvasCount: canvases.length,
      visibleBoardQuestionIds: canvases.map((canvas) => canvas.dataset.questionId || null),
      boardFailedClosed: typeof _questionBoardFailedClosed !== 'undefined'
        ? _questionBoardFailedClosed : null,
      trace,
    };
  });
}

async function serverAttemptState(page) {
  return page.evaluate(async (zoneKey) => {
    const response = await fetch('/api/adventure/boss/start', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zone_key: zoneKey }),
    });
    const data = await response.json();
    return {
      status: response.status,
      ok: data.ok === true,
      answered_count: Number(data.answered_count || 0),
      correct: Number(data.correct || 0),
      resume_index: Number(data.resume_index || 0),
      question_ids: data.question_ids || [],
      ready_to_finish: data.ready_to_finish === true,
    };
  }, ZONE_KEY);
}

async function answerTarget(page) {
  return page.evaluate(() => {
    const answerNode = ((currentNode && currentNode.children) || []).find((child) => child && child.move);
    if (!answerNode) return { error: 'no_answer_node' };
    const { x, y } = answerNode.move;
    const displayX = typeof _bx === 'function' ? _bx(x) : x;
    const displayY = typeof _by === 'function' ? _by(y) : y;
    const element = board.element;
    const rect = element.getBoundingClientRect();
    const pixelRatio = board.pixelRatio || 1;
    const scaleX = element.offsetWidth ? rect.width / element.offsetWidth : 1;
    const scaleY = element.offsetHeight ? rect.height / element.offsetHeight : 1;
    const layerX = board.getX(displayX) / pixelRatio;
    const layerY = board.getY(displayY) / pixelRatio;
    return {
      viewportPoint: {
        x: Math.round(rect.left + layerX * scaleX),
        y: Math.round(rect.top + layerY * scaleY),
      },
      boardPoint: { x, y },
      roundTrip: {
        x: Math.round((layerX * pixelRatio - board.left) / board.fieldWidth),
        y: Math.round((layerY * pixelRatio - board.top) / board.fieldHeight),
      },
    };
  });
}

async function installPresentationFault(page, fault) {
  if (!fault) return;
  await page.evaluate((faultName) => {
    const fail = () => { throw new Error(faultName); };
    // These are test-only monkey patches at the presentation boundary.  No
    // route, response body, or server authority is replaced.
    if (faultName === 'BADGE_PRESENTATION_THROW') {
      if (typeof launchConfetti === 'function') launchConfetti = fail;
      if (typeof onNewBadge === 'function') onNewBadge = fail;
    } else if (faultName === 'PET_PRESENTATION_THROW') {
      if (typeof petReact === 'function') petReact = fail;
    } else if (faultName === 'MONSTER_PRESENTATION_THROW') {
      if (typeof updateMonsterUI === 'function') updateMonsterUI = fail;
    } else if (faultName === 'QUEST_PRESENTATION_THROW') {
      if (typeof updateQuestPanel === 'function') updateQuestPanel = fail;
    } else if (faultName === 'XP_PRESENTATION_THROW') {
      if (typeof spawnXpFloat === 'function') spawnXpFloat = fail;
      if (typeof showRankUpPopup === 'function') showRankUpPopup = fail;
    } else if (faultName === 'LOOT_PRESENTATION_THROW') {
      if (typeof showLootToast === 'function') showLootToast = fail;
    } else if (faultName === 'AUDIO_PRESENTATION_REJECT') {
      if (window.SFX) window.SFX.play = fail;
      if (typeof playSoundBadgeUnlock === 'function') playSoundBadgeUnlock = fail;
      if (typeof playSoundVictory === 'function') playSoundVictory = fail;
    }
    window.__E10_LORD_REVIEW_FAULT_INJECTION__ = {
      name: faultName,
      installed: true,
    };
  }, fault);
}

async function loginAndEnter(page, runtime) {
  await page.goto(`${runtime.base_url}/login`, { waitUntil: 'domcontentloaded' });
  const login = await page.evaluate(async (credentials) => {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials),
    });
    return { status: response.status, body: await response.json() };
  }, { username: runtime.username, password: runtime.password });
  if (login.status !== 200 || login.body?.ok !== true) throw new Error(`login failed: ${JSON.stringify(login)}`);
  await page.goto(`${runtime.base_url}/`, { waitUntil: 'load' });
  await page.waitForFunction(
    (zoneKey) => typeof _adventureProgress !== 'undefined'
      && Array.isArray(_adventureProgress)
      && _adventureProgress.some((zone) => zone?.key === zoneKey),
    ZONE_KEY,
    { timeout: 90000 },
  );
  await page.evaluate((zoneKey) => startBossBattle(zoneKey), ZONE_KEY);
  await page.waitForSelector('#boss-cinematic.show', { timeout: 30000 });
  await page.click('#boss-cinematic-btn');
  await page.waitForFunction(
    () => typeof _bossMode !== 'undefined' && _bossMode === true
      && Array.isArray(_bossQueue) && _bossQueue.length > 0,
    undefined,
    { timeout: 90000 },
  );
  await page.waitForFunction(
    () => typeof board !== 'undefined' && Boolean(board)
      && typeof currentNode !== 'undefined' && Boolean(currentNode)
      && !document.getElementById('board-canvas-wrap')?.classList.contains('hidden'),
    undefined,
    { timeout: 90000 },
  );
}

async function clickAndSettle(page, stateBefore) {
  const target = await answerTarget(page);
  if (target.error) throw new Error(target.error);
  const reviewResponse = page.waitForResponse(
    (response) => {
      try { return new URL(response.url()).pathname === '/api/srs/review'; }
      catch { return false; }
    },
    { timeout: 90000 },
  );
  await page.mouse.click(target.viewportPoint.x, target.viewportPoint.y);
  const response = await reviewResponse;
  const responseBody = await response.json();
  await page.waitForTimeout(SETTLE_MS);
  const after = await readState(page);
  return {
    target,
    response: {
      status: response.status(),
      ok: responseBody?.ok === true,
      keys: Object.keys(responseBody || {}).sort(),
      body: responseBody,
    },
    after,
  };
}

async function main() {
  const report = {
    contract: 'e10_lord_review_architecture_contract_v1a',
    options: OPTIONS,
    intercepted_routes: [],
    console_errors: [],
    page_errors: [],
    unhandled_rejections: [],
    phases: {},
    evidence: {},
  };
  let started;
  try {
    started = await startRuntime();
  } catch (error) {
    if (error.unavailable) {
      console.log(JSON.stringify({ ...report, skipped: true, reason: error.message }, null, 2));
      return 2;
    }
    throw error;
  }
  const { child, runtime } = started;
  report.evidence.runtime = {
    fixture: runtime.fixture,
    base_url: runtime.base_url,
    postgres_container: runtime.postgres_container,
    stubbed_companion_modules: runtime.stubbed_companion_modules,
    secret_key_is_synthetic: runtime.secret_key_is_synthetic,
    secret_file_access_attempts: runtime.secret_file_access_attempts,
    katago_cache_backend: runtime.katago_cache_backend,
    katago_cache_access_attempts: runtime.katago_cache_access_attempts,
  };
  const browser = await chromium.launch({ executablePath: resolveChrome(), headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await context.addInitScript(() => {
      window.__GO_E10_ACCEPTANCE_DIAGNOSTIC__ = true;
      window.__TRACE_REJECTIONS__ = [];
      window.addEventListener('unhandledrejection', (event) => {
        window.__TRACE_REJECTIONS__.push({
          message: String(event.reason?.message || event.reason).slice(0, 500),
        });
      });
    });
    const page = await context.newPage();
    page.on('console', (message) => {
      if (['error', 'warning'].includes(message.type())) {
        report.console_errors.push({ type: message.type(), text: message.text().slice(0, 500) });
      }
    });
    page.on('pageerror', (error) => {
      report.page_errors.push({ name: error.name, message: String(error.message).slice(0, 500) });
    });

    await loginAndEnter(page, runtime);
    const initial = await readState(page);
    const initialServer = await serverAttemptState(page);
    report.phases.initial = initial;
    report.phases.initial_server = initialServer;
    report.evidence.real_flask = true;
    report.evidence.real_route = true;
    report.evidence.real_signed_attempt = Boolean(initial.bossMode && initial.bossQueue.length);
    report.evidence.real_wgo = Boolean(initial.canvasCount > 0);

    if (OPTIONS.fault) {
      await installPresentationFault(page, OPTIONS.fault);
      const result = await clickAndSettle(page, initial);
      const serverAfter = await serverAttemptState(page);
      report.phases.fault_result = result;
      report.phases.after_server = serverAfter;
      report.evidence.fault_injection = await page.evaluate(
        () => window.__E10_LORD_REVIEW_FAULT_INJECTION__ || null,
      );
      report.unhandled_rejections = await page.evaluate(() => window.__TRACE_REJECTIONS__ || []);
    } else {
      const first = await clickAndSettle(page, initial);
      const secondBefore = first.after;
      const second = await clickAndSettle(page, secondBefore);
      const finalServer = await serverAttemptState(page);
      const finalState = await readState(page);
      report.phases.first = first;
      report.phases.second = second;
      report.phases.final = finalState;
      report.phases.final_server = finalServer;
      report.evidence.queue_qids = initial.bossQueue;
      report.unhandled_rejections = await page.evaluate(() => window.__TRACE_REJECTIONS__ || []);

      // A legitimate server rejection: the signed attempt is real, but this
      // request declares a forged attempt identity.  No response is faked.
      const rejected = await page.evaluate(async (qid) => {
        const response = await fetch('/api/srs/review', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question_id: qid,
            grade: 3,
            unit_name: null,
            unit_done: false,
            source_context: 'boss_trial:forged-attempt-id',
          }),
        });
        return { status: response.status, body: await response.json() };
      }, finalState.currentQuestionId);
      report.phases.rejected_review = rejected;
      report.phases.after_rejected_client = await readState(page);
      report.phases.after_rejected_server = await serverAttemptState(page);
    }

    await context.close();
  } finally {
    await browser.close();
    await stopRuntime(child);
  }

  const initial = report.phases.initial || {};
  const initialServer = report.phases.initial_server || {};
  const first = report.phases.first || {};
  const second = report.phases.second || {};
  const final = report.phases.final || {};
  const finalServer = report.phases.final_server || {};
  const firstResponse = first.response || {};
  const secondResponse = second.response || {};
  const faultResult = report.phases.fault_result || {};
  const faultServer = report.phases.after_server || {};
  const trace = final.trace || faultResult.after?.trace || [];
  const transitionFrom = trace.filter((event) => event.event === 'BOSS_TRANSITION_FROM_INDEX');
  const reviewCount = OPTIONS.fault ? (faultResult.response ? 1 : 0) : (firstResponse.status ? 1 : 0) + (secondResponse.status ? 1 : 0);
  const responseShape = OPTIONS.fault ? faultResult.response : firstResponse;

  report.verdict = {
    REAL_FLASK: report.evidence.real_flask === true,
    REAL_ROUTE: report.evidence.real_route === true,
    REAL_SIGNED_ATTEMPT: report.evidence.real_signed_attempt === true,
    REAL_WGO_CLICK: OPTIONS.fault ? Boolean(faultResult.target) : Boolean(first.target && second.target),
    PRODUCTION_SHAPED_RESPONSE: (responseShape.keys || []).length > 20,
    SRS_REVIEW_REQUEST_COUNT: reviewCount,
    SERVER_ANSWERED_COUNT: OPTIONS.fault
      ? Number(faultServer.answered_count || 0) - Number(initialServer.answered_count || 0)
      : Number(finalServer.answered_count || 0) - Number(initialServer.answered_count || 0),
    CLIENT_BOSS_INDEX: OPTIONS.fault ? faultResult.after?.bossIndex : final.bossIndex,
    CURRENT_QID: OPTIONS.fault ? faultResult.after?.currentQuestionId : final.currentQuestionId,
    VISIBLE_BOARD_QID: OPTIONS.fault
      ? faultResult.after?.visibleBoardQuestionIds?.find(Boolean) || null
      : final.visibleBoardQuestionIds?.find(Boolean) || null,
    DUPLICATE_REVIEW: OPTIONS.fault ? false : reviewCount !== 2,
    DUPLICATE_PROGRESS: OPTIONS.fault ? false : transitionFrom.length !== 2,
    PRESENTATION_FAILURE_OBSERVED: OPTIONS.fault
      ? [...report.console_errors, ...report.page_errors, ...report.unhandled_rejections]
        .some((entry) => JSON.stringify(entry).includes(OPTIONS.fault))
      : false,
    SERVER_REVIEW_COMMITTED: OPTIONS.fault
      ? Number(faultServer.answered_count || 0) === Number(initialServer.answered_count || 0) + 1
      : null,
    SERVER_REJECTION_COMMITTED: report.phases.after_rejected_server
      ? Number(report.phases.after_rejected_server.answered_count || 0)
        !== Number(report.phases.after_server?.answered_count || 0)
      : null,
    CLIENT_ADVANCED_AFTER_REJECTION: report.phases.after_rejected_client
      ? Number(report.phases.after_rejected_client.bossIndex || 0)
        !== Number(report.phases.final?.bossIndex || 0)
      : null,
    NO_ROUTE_INTERCEPTION: report.intercepted_routes.length === 0,
  };
  console.log(JSON.stringify(report, null, 2));
  return 0;
}

main().then(
  (code) => { process.exitCode = code; },
  (error) => { console.error(error?.stack || String(error)); process.exitCode = 1; },
);
