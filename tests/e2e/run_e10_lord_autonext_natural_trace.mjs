/**
 * E10 Lord Trial auto-next — natural browser reproduction and causal trace.
 *
 * First execution of the real answering click against the real stack:
 *
 *   real mouse click on the real WGo board
 *     -> WGo's own event translation -> real onBoardClick()
 *     -> real submitSRS() -> real SRS.review()
 *     -> real POST /api/srs/review (real Flask, real signed Boss attempt,
 *        real disposable PostgreSQL)
 *     -> whatever the real client then does, observed rather than assumed.
 *
 * Nothing is stubbed, mocked or fulfilled. `page.route` is never called.
 * `submitSRS` is never invoked directly — the click is a real mouse event,
 * so the entire onBoardClick path runs as it does in Production.
 *
 * Observation is passive:
 *
 *   - `window.__GO_E10_ACCEPTANCE_DIAGNOSTIC__` is production's own
 *     test-facing switch (index.html:8678). It only makes
 *     `_e10AcceptanceTrace()` append to an array; it changes no behaviour
 *     and no branch. No production source is modified to run this.
 *   - console / pageerror / unhandledrejection / response are Playwright
 *     listeners, outside the page's control flow.
 *
 * Secrets: this script never reads secret_key.txt; the harness it drives
 * injects a synthetic SECRET_KEY and blocks any access to that file.
 * Request bodies are recorded as question_id/grade plus a boolean for
 * whether source_context carries a Boss attempt marker — never the marker
 * itself, never cookies, never headers.
 *
 * Usage:
 *   node tests/e2e/run_e10_lord_autonext_natural_trace.mjs
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
const SETTLE_MS = 8000;

function resolveChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (fssync.existsSync(candidate)) return candidate;
  }
  throw new Error('No Chrome/Edge executable found. Set CHROME_BIN.');
}

/** CLI: --fixture single_ply|multi_ply, --badge-priming */
function parseArgs(argv) {
  const options = { fixture: 'single_ply', badgePriming: false, rankPriming: false, swParity: false };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--fixture') { options.fixture = argv[i + 1]; i += 1; }
    else if (argv[i] === '--badge-priming') { options.badgePriming = true; }
    else if (argv[i] === '--rank-priming') { options.rankPriming = true; }
    else if (argv[i] === '--sw-parity') { options.swParity = true; }
  }
  return options;
}

const OPTIONS = parseArgs(process.argv.slice(2));

function startRuntime() {
  const harnessArgs = [HARNESS, 'serve', '--fixture', OPTIONS.fixture];
  if (OPTIONS.badgePriming) harnessArgs.push('--badge-priming');
  if (OPTIONS.rankPriming) harnessArgs.push('--rank-priming');
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON_BIN || 'python', harnessArgs, {
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
      if (payload && payload.unavailable) {
        clearTimeout(timer);
        rl.close();
        child.kill();
        reject(Object.assign(new Error(payload.reason || 'unavailable'), { unavailable: true }));
        return;
      }
      if (payload && payload.ready === true) {
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
  try { child.stdin.end(); } catch { /* already gone */ }
  return new Promise((resolve) => {
    const timer = setTimeout(() => { try { child.kill(); } catch {} resolve(); }, 30000);
    child.on('exit', () => { clearTimeout(timer); resolve(); });
  });
}

/** State read with bare identifiers: index.html's top-level `let` bindings
 *  are lexical globals and are NOT window properties. */
const READ_STATE = () => {
  const wrap = document.getElementById('board-canvas-wrap');
  const msg = document.getElementById('msg-box');
  const progress = document.getElementById('boss-trial-progress');
  return {
    bossMode: typeof _bossMode !== 'undefined' ? _bossMode : null,
    bossIndex: typeof _bossIndex !== 'undefined' ? _bossIndex : null,
    bossCorrect: typeof _bossCorrect !== 'undefined' ? _bossCorrect : null,
    bossQueueLength: typeof _bossQueue !== 'undefined' && _bossQueue ? _bossQueue.length : null,
    bossQueue: typeof _bossQueue !== 'undefined' && _bossQueue ? _bossQueue.slice() : null,
    bossAttemptIdPresent: typeof _bossAttemptId !== 'undefined' && Boolean(_bossAttemptId),
    bossFinishInFlight: typeof _bossFinishInFlight !== 'undefined' ? _bossFinishInFlight : null,
    bossTransitionInFlightKey: typeof _bossTransitionInFlightKey !== 'undefined'
      ? _bossTransitionInFlightKey : null,
    bossLastSettledKey: typeof _bossLastSettledKey !== 'undefined' ? _bossLastSettledKey : null,
    currentQuestionId: typeof currentQ !== 'undefined' && currentQ ? Number(currentQ.id) : null,
    currentNodePresent: typeof currentNode !== 'undefined' && Boolean(currentNode),
    answering: typeof answering !== 'undefined' ? answering : null,
    solved: typeof solved !== 'undefined' ? solved : null,
    boardFailedClosed: typeof _questionBoardFailedClosed !== 'undefined'
      ? _questionBoardFailedClosed : null,
    srsDoneCount: typeof srsDoneCount !== 'undefined' ? srsDoneCount : null,
    canvasCount: wrap ? wrap.querySelectorAll('canvas').length : 0,
    boardHidden: wrap ? wrap.classList.contains('hidden') : null,
    msgText: msg ? (msg.textContent || '').trim().slice(0, 200) : null,
    progressText: progress ? (progress.textContent || '').trim().slice(0, 120) : null,
    // Which pre-Boss-authority presentation branches this account can even
    // reach. These are value gates, not key gates: the response can carry
    // every field and still skip the branch when the value is null/absent.
    // Badge callback evidence. onNewBadge (index.html:8359) queues the def,
    // calls _showNextBadge() -- which writes #badge-popup-* and adds .show --
    // and launchConfetti(), which appends .confetti-piece nodes. Observing
    // those proves the callback body actually ran, rather than inferring it.
    badgeQueueLength: typeof _badgeQueue !== 'undefined' && Array.isArray(_badgeQueue)
      ? _badgeQueue.length : null,
    badgePopupShown: Boolean(document.getElementById('badge-popup')?.classList.contains('show')),
    badgePopupName: (document.getElementById('badge-popup-name')?.textContent || '').trim(),
    confettiPieces: document.querySelectorAll('.confetti-piece').length,
    quizPetPresent: typeof _quizPet !== 'undefined' && Boolean(_quizPet),
    adventureActiveQuestions: typeof _adventureActiveQuestions !== 'undefined'
      && Array.isArray(_adventureActiveQuestions) ? _adventureActiveQuestions.length : null,
    isAdventureZonePractice: typeof _isAdventureZonePractice === 'function'
      ? _isAdventureZonePractice() : null,
    premiumWeeklyMode: typeof _premiumWeeklyMode !== 'undefined' && Boolean(_premiumWeeklyMode),
    guildQuestMode: typeof _guildQuestMode !== 'undefined' && Boolean(_guildQuestMode),
    challengeId: typeof _challengeId !== 'undefined' ? Boolean(_challengeId) : null,
    mapBattleV1Mode: typeof _mapBattleV1Mode !== 'undefined' ? _mapBattleV1Mode : null,
    // Answer-tree depth of the question on the board. A 1-ply answer takes
    // onBoardClick's synchronous submitSRS(3); a deeper one goes through a
    // 400ms setTimeout first, which is a different async ordering.
    answerTreeDepth: (() => {
      if (typeof currentProblem === 'undefined' || !currentProblem || !currentProblem.tree) return null;
      let node = currentProblem.tree;
      let depth = 0;
      while (node && node.children && node.children.length) { node = node.children[0]; depth += 1; }
      return depth;
    })(),
  };
};

/** The correct point, plus the viewport pixel WGo would translate back to it. */
const ANSWER_TARGET = () => {
  const answerNode = ((currentNode && currentNode.children) || []).find((c) => c && c.move);
  if (!answerNode) return { error: 'no_answer_node_in_tree' };
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
    boardPoint: { x, y },
    displayPoint: { x: displayX, y: displayY },
    viewportPoint: {
      x: Math.round(rect.left + layerX * scaleX),
      y: Math.round(rect.top + layerY * scaleY),
    },
    // WGo's own inverse, so the pixel is verified rather than trusted.
    roundTrip: {
      x: Math.round((layerX * pixelRatio - board.left) / board.fieldWidth),
      y: Math.round((layerY * pixelRatio - board.top) / board.fieldHeight),
    },
  };
};

/** Service worker state. A freshly registered worker does not control the
 *  page it was registered from; control begins on the next navigation. */
async function swState(page) {
  return page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) return { supported: false };
    const registrations = await navigator.serviceWorker.getRegistrations();
    const controller = navigator.serviceWorker.controller;
    return {
      supported: true,
      registration_count: registrations.length,
      active_script: registrations[0]?.active?.scriptURL || null,
      active_state: registrations[0]?.active?.state || null,
      controller_present: Boolean(controller),
      controller_script: controller ? controller.scriptURL : null,
    };
  });
}

/** Bring the page under real service-worker control, as a returning visitor
 *  in Production would be: register on first load, then navigate again. */
async function establishServiceWorkerControl(page, baseUrl) {
  await page.waitForFunction(
    async () => {
      if (!('serviceWorker' in navigator)) return true;
      const registrations = await navigator.serviceWorker.getRegistrations();
      return registrations.some((registration) => registration.active);
    },
    undefined,
    { timeout: 60000 },
  );
  await page.goto(`${baseUrl}/`, { waitUntil: 'load' });
  await page.waitForFunction(
    () => Boolean(navigator.serviceWorker && navigator.serviceWorker.controller),
    undefined,
    { timeout: 60000 },
  );
}

async function enterLordTrial(page, runtime) {
  await page.waitForFunction(
    (zoneKey) => typeof _adventureProgress !== 'undefined'
      && Array.isArray(_adventureProgress)
      && _adventureProgress.some((zone) => zone && zone.key === zoneKey),
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

/** Server-authoritative attempt state, via the real resume path. */
async function serverAttemptState(page) {
  return page.evaluate(async (zoneKey) => {
    const res = await fetch('/api/adventure/boss/start', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zone_key: zoneKey }),
    });
    const data = await res.json();
    return {
      ok: data.ok,
      resumed: data.resumed,
      answered_count: data.answered_count,
      correct: data.correct,
      resume_index: data.resume_index,
      total: data.total,
      ready_to_finish: data.ready_to_finish,
      first_queue_qid: (data.question_ids || [])[0] ?? null,
    };
  }, ZONE_KEY);
}

async function main() {
  const report = {
    contract: 'e10_lord_autonext_natural_trace',
    intercepted_routes: [],
    console_messages: [],
    page_errors: [],
    unhandled_rejections: [],
    failed_resources: [],
    network: { srs_review: [] },
    phases: {},
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
  report.options = OPTIONS;
  report.evidence = {
    fixture: runtime.fixture,
    badge_priming: runtime.badge_priming,
    rank_priming: runtime.rank_priming,
    katago_cache_backend: runtime.katago_cache_backend,
    katago_cache_access_attempts: runtime.katago_cache_access_attempts,
    base_url: runtime.base_url,
    postgres_container: runtime.postgres_container,
    stubbed_companion_modules: runtime.stubbed_companion_modules,
    secret_key_is_synthetic: runtime.secret_key_is_synthetic,
    secret_file_access_attempts: runtime.secret_file_access_attempts,
  };

  const browser = await chromium.launch({ executablePath: resolveChrome(), headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    // Production's own diagnostics switch: recording only, no branch change.
    await context.addInitScript(() => {
      window.__GO_E10_ACCEPTANCE_DIAGNOSTIC__ = true;
      window.__TRACE_REJECTIONS__ = [];
      window.addEventListener('unhandledrejection', (event) => {
        const reason = event.reason;
        window.__TRACE_REJECTIONS__.push({
          at: Math.round(performance.now()),
          name: reason && reason.name || null,
          message: String(reason && reason.message || reason).slice(0, 500),
          stack: String(reason && reason.stack || '').split('\n').slice(0, 6).join('\n'),
        });
      });
    });
    const page = await context.newPage();

    page.on('console', (message) => {
      report.console_messages.push({
        at: Date.now(),
        type: message.type(),
        text: message.text().slice(0, 500),
      });
    });
    page.on('pageerror', (error) => {
      report.page_errors.push({
        at: Date.now(),
        name: error && error.name || null,
        message: String(error && error.message || error).slice(0, 500),
        stack: String(error && error.stack || '').split('\n').slice(0, 8).join('\n'),
      });
    });
    page.on('response', async (response) => {
      const status = response.status();
      let pathname = '(unparseable)';
      try { pathname = new URL(response.url()).pathname; } catch { /* placeholder */ }
      if (status >= 400) {
        report.failed_resources.push({
          path: pathname,
          resource_type: response.request().resourceType(),
          status,
        });
      }
      if (pathname !== '/api/srs/review') return;
      const request = response.request();
      let requestShape = null;
      try {
        const body = JSON.parse(request.postData() || '{}');
        requestShape = {
          question_id: body.question_id ?? null,
          grade: body.grade ?? null,
          // The marker itself is a session-scoped identifier; only its
          // shape is recorded.
          source_context_is_boss: String(body.source_context || '').startsWith('boss_trial:'),
        };
      } catch { /* leave null */ }
      let responseKeys = null;
      let responseOk = null;
      let truthyFields = null;
      let falsyFields = null;
      let newBadges = null;
      try {
        const payload = await response.json();
        responseKeys = Object.keys(payload).sort();
        responseOk = payload.ok ?? null;
        // Which fields are actually truthy decides which `if (data.x)`
        // branches run. The account is fully synthetic and disposable, so
        // this carries no real user data.
        const gates = ['monster', 'pet', 'practice', 'player', 'sp', 'loot',
          'appearance_loot', 'new_appearance_items', 'quest_updates', 'new_badges',
          'xp_gain', 'combo_streak', 'ranked_up', 'shield_used', 'pet_xp_gained'];
        const isTruthy = (value) => Boolean(value)
          && !(Array.isArray(value) && value.length === 0);
        truthyFields = gates.filter((key) => isTruthy(payload[key])).sort();
        falsyFields = gates.filter((key) => !isTruthy(payload[key])).sort();
        // Badge ids only; they are static catalogue identifiers, not user data.
        newBadges = Array.isArray(payload.new_badges) ? payload.new_badges : [];
      } catch { /* leave null */ }
      report.network.srs_review.push({
        at: Date.now(),
        status,
        request: requestShape,
        response_key_count: responseKeys ? responseKeys.length : null,
        response_keys: responseKeys,
        response_ok: responseOk,
        gated_fields_truthy: truthyFields,
        gated_fields_falsy: falsyFields,
        response_new_badges: newBadges,
        timing_ms: response.request().timing()
          ? Math.round(response.request().timing().responseEnd) : null,
      });
    });

    // ── authenticate, load the real page, enter the real Lord Trial ────
    await page.goto(`${runtime.base_url}/login`, { waitUntil: 'domcontentloaded' });
    const login = await page.evaluate(async (creds) => {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(creds),
      });
      return { status: res.status, ok: (await res.json()).ok === true };
    }, { username: runtime.username, password: runtime.password });
    report.phases.login = login;

    await page.goto(`${runtime.base_url}/`, { waitUntil: 'load' });
    report.phases.service_worker_before = await swState(page);
    if (OPTIONS.swParity) {
      await establishServiceWorkerControl(page, runtime.base_url);
      report.phases.service_worker_controlling = await swState(page);
      report.phases.sw_version = await page.evaluate(async () => {
        const text = await (await fetch('/sw.js', { cache: 'no-store' })).text();
        const match = text.match(/const VERSION\s*=\s*'([^']+)'/);
        const identity = text.match(/const ASSET_IDENTITY\s*=\s*'([^']+)'/);
        return { version: match ? match[1] : null, asset_identity: identity ? identity[1] : null };
      });
    }
    await enterLordTrial(page, runtime);

    report.phases.initial_client = await page.evaluate(READ_STATE);
    report.phases.initial_server = await serverAttemptState(page);
    const target = await page.evaluate(ANSWER_TARGET);
    report.phases.answer_target = target;
    if (target.error) throw new Error(`cannot locate the answer point: ${target.error}`);

    // Trace entries produced before the click, so the click's own entries
    // can be separated from board-setup noise.
    const traceBeforeClick = await page.evaluate(
      () => (window.__GO_E10_ACCEPTANCE_TRACE__ || []).length,
    );

    // ── the real answering click ───────────────────────────────────────
    const reviewSettled = page.waitForResponse(
      (response) => {
        try { return new URL(response.url()).pathname === '/api/srs/review'; }
        catch { return false; }
      },
      { timeout: 60000 },
    ).then(
      (response) => ({ arrived: true, status: response.status() }),
      (error) => ({ arrived: false, error: String(error && error.message || error) }),
    );

    // Stone-placement timeline, so the multi-ply path (player move ->
    // answering=true -> 400ms setTimeout -> opponent reply -> submitSRS)
    // is observed rather than assumed. Reads board state only; the 400ms
    // timer is production's own and is never shortened or bypassed.
    await page.evaluate(() => {
      window.__STONE_TIMELINE__ = [];
      const sample = () => {
        const stones = [];
        if (typeof logicBoard !== 'undefined' && Array.isArray(logicBoard)) {
          for (let x = 0; x < logicBoard.length; x += 1) {
            const column = logicBoard[x] || [];
            for (let y = 0; y < column.length; y += 1) {
              if (column[y]) stones.push(`${x},${y},${column[y]}`);
            }
          }
        }
        window.__STONE_TIMELINE__.push({
          at: Math.round(performance.now()),
          stones: stones.length,
          answering: typeof answering !== 'undefined' ? answering : null,
          solved: typeof solved !== 'undefined' ? solved : null,
          qid: typeof currentQ !== 'undefined' && currentQ ? Number(currentQ.id) : null,
        });
      };
      window.__STONE_SAMPLER__ = setInterval(sample, 20);
      sample();
    });

    const clickAt = Date.now();
    await page.mouse.click(target.viewportPoint.x, target.viewportPoint.y);
    report.phases.click = { at: clickAt, viewportPoint: target.viewportPoint };
    report.phases.review_settled = await reviewSettled;

    // Let every downstream async step run to completion or die trying.
    await page.waitForTimeout(SETTLE_MS);

    report.phases.stone_timeline = await page.evaluate(() => {
      clearInterval(window.__STONE_SAMPLER__);
      const timeline = window.__STONE_TIMELINE__ || [];
      // Collapse to transitions only; a 20ms poll over 8s is noise otherwise.
      const transitions = [];
      let previous = null;
      for (const sample of timeline) {
        const key = `${sample.stones}|${sample.answering}|${sample.solved}|${sample.qid}`;
        if (key !== previous) { transitions.push(sample); previous = key; }
      }
      return transitions;
    });
    report.phases.after_client = await page.evaluate(READ_STATE);
    report.phases.after_server = await serverAttemptState(page);
    report.phases.trace = await page.evaluate(
      (skip) => (window.__GO_E10_ACCEPTANCE_TRACE__ || []).slice(skip),
      traceBeforeClick,
    );
    report.unhandled_rejections = await page.evaluate(
      () => window.__TRACE_REJECTIONS__ || [],
    );

    // ── leave and re-enter, exactly as the Owner did ───────────────────
    await page.goto(`${runtime.base_url}/`, { waitUntil: 'load' });
    await enterLordTrial(page, runtime);
    report.phases.reenter_client = await page.evaluate(READ_STATE);
    report.phases.reenter_server = await serverAttemptState(page);

    await context.close();
  } finally {
    await browser.close();
    await stopRuntime(child);
  }

  // ── derived verdicts (no interpretation beyond arithmetic) ──────────
  const initial = report.phases.initial_client || {};
  const after = report.phases.after_client || {};
  const initialServer = report.phases.initial_server || {};
  const afterServer = report.phases.after_server || {};
  const reenterServer = report.phases.reenter_server || {};
  const reenterClient = report.phases.reenter_client || {};
  const review = report.network.srs_review[0] || null;

  report.verdict = {
    REAL_WGO_CLICK_EXECUTED: Boolean(report.phases.click),
    // onBoardClick submits grade 3 for a correct answer and 0 for a wrong
    // one (index.html:11129+); 3 is the correct-answer grade, not a partial.
    CLICK_WAS_GRADED_CORRECT: Number(review?.request?.grade ?? -1) >= 3,
    SIGNED_BOSS_ATTEMPT_USED: review?.request?.source_context_is_boss === true,
    SRS_REVIEW_HTTP_STATUS: review?.status ?? null,
    SRS_REVIEW_RESPONSE_KEY_COUNT: review?.response_key_count ?? null,
    PRODUCTION_SHAPED_RESPONSE_USED: (review?.response_key_count ?? 0) > 20,
    SERVER_REVIEW_COMMITTED:
      Number(afterServer.answered_count || 0) === Number(initialServer.answered_count || 0) + 1,
    CLIENT_BOSS_INDEX_ADVANCED: after.bossIndex !== initial.bossIndex,
    VISIBLE_QUESTION_CHANGED: after.currentQuestionId !== initial.currentQuestionId,
    OWNER_CLASS_REPRODUCED:
      Number(afterServer.answered_count || 0) === Number(initialServer.answered_count || 0) + 1
      && after.currentQuestionId === initial.currentQuestionId
      && Number(reenterServer.answered_count || 0) >= 1
      && reenterClient.currentQuestionId !== initial.currentQuestionId,
    NO_ROUTE_INTERCEPTION: report.intercepted_routes.length === 0,
  };
  report.verdict.BROWSER_403_OBSERVED = report.failed_resources.some((r) => r.status === 403);
  report.verdict.ANSWER_TREE_DEPTH = initial.answerTreeDepth ?? null;
  report.verdict.NEW_BADGES_RETURNED = Array.isArray(review?.response_new_badges)
    ? review.response_new_badges.length : null;
  report.verdict.RANK_UP_RETURNED = report.network.srs_review.some(
    (entry) => (entry.gated_fields_truthy || []).includes('ranked_up'),
  );
  report.verdict.KATAGO_CACHE_BACKEND = report.evidence.katago_cache_backend ?? null;
  report.verdict.REPO_ROOT_KATAGO_CACHE_ACCESSED =
    (report.evidence.katago_cache_access_attempts || []).length > 0;

  console.log(JSON.stringify(report, null, 2));
  return 0;
}

main().then(
  (code) => { process.exitCode = code; },
  (error) => {
    console.error(error && error.stack || String(error));
    process.exitCode = 1;
  },
);
