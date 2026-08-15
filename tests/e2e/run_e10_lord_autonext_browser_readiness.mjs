/**
 * E10 Lord Trial auto-next — browser/WGo readiness probe (foundation only).
 *
 * This script proves that the disposable real-path runtime built by
 * `tests/lord_trial_natural_runtime.py` can be driven by a real browser all
 * the way to a rendered, clickable Lord Trial board, using the real
 * application at every step:
 *
 *   real login route  ->  real index.html  ->  real adventure state
 *   ->  real startBossBattle('k26_30')  ->  real Zone 1 Lord card
 *   ->  real /api/adventure/boss/start  ->  real _loadBossQuestion()
 *   ->  real WGo board
 *
 * Deliberately NOT done here: clicking the correct point. Answering is the
 * first step of the natural reproduction itself, and belongs to the trace
 * task, not to a readiness probe. This script stops at the last
 * non-mutating observation before that click and reports whether the click
 * is genuinely available.
 *
 * No route is stubbed, mocked, or fulfilled by this script. `page.route` is
 * never called. In particular /api/srs/review is never intercepted — the
 * blind spot that made the previous acceptance scripts unable to see this
 * defect (they answered it with a literal {"ok":true}).
 *
 * Usage:
 *   node tests/e2e/run_e10_lord_autonext_browser_readiness.mjs
 *
 * Requires: docker (for the disposable PostgreSQL), python on PATH, and a
 * local Chrome/Edge (CHROME_BIN honoured, same convention as the other
 * scripts in this directory).
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

/**
 * Start the disposable runtime and wait for its one-line handshake.
 * Everything it provisions (PostgreSQL container, database, user, session
 * secret, question corpus) is torn down when this process closes its stdin.
 */
function startRuntime() {
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON_BIN || 'python', [HARNESS, 'serve'], {
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
      try {
        payload = JSON.parse(line);
      } catch {
        return; // startup diagnostics and werkzeug logs share this stream
      }
      if (payload && payload.unavailable) {
        clearTimeout(timer);
        rl.close();
        child.kill();
        reject(Object.assign(new Error(payload.reason || 'runtime unavailable'), { unavailable: true }));
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

async function main() {
  const report = {
    contract: 'e10_lord_autonext_browser_readiness',
    intercepted_routes: [],
    checks: {},
    evidence: {},
    browser_errors: [],
    // Non-2xx responses, classified only (path/type/status). Not a
    // foundation blocker; recorded so an intermittent one can be named
    // instead of guessed at.
    failed_resources: [],
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
  report.evidence.base_url = runtime.base_url;
  report.evidence.postgres_container = runtime.postgres_container;
  report.evidence.questions_json_path = runtime.questions_json_path;
  report.evidence.stubbed_companion_modules = runtime.stubbed_companion_modules;

  const browser = await chromium.launch({ executablePath: resolveChrome(), headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    page.on('console', (message) => {
      if (message.type() === 'error') report.browser_errors.push({ kind: 'console', text: message.text() });
    });
    page.on('pageerror', (error) => {
      report.browser_errors.push({ kind: 'pageerror', text: String(error && error.message || error) });
    });
    // Classification only, for non-2xx responses. Deliberately records the
    // pathname, the resource type and the status and nothing else: no query
    // string, no headers, no cookies, no body. A console line like "Failed
    // to load resource: ... 403" names no path, which is why this exists.
    page.on('response', (response) => {
      const status = response.status();
      if (status < 400) return;
      let pathname = '(unparseable)';
      try {
        pathname = new URL(response.url()).pathname;
      } catch { /* keep the placeholder */ }
      report.failed_resources.push({
        path: pathname,
        resource_type: response.request().resourceType(),
        status,
      });
    });

    // ── real login, through the real login page's own form ────────────
    await page.goto(`${runtime.base_url}/login`, { waitUntil: 'domcontentloaded' });
    const loginResponse = await page.evaluate(async (creds) => {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(creds),
      });
      return { status: res.status, body: await res.json() };
    }, { username: runtime.username, password: runtime.password });
    report.evidence.login_status = loginResponse.status;
    report.checks.AUTHENTICATED_PAGE = loginResponse.status === 200 && loginResponse.body?.ok === true;

    // ── real index.html ───────────────────────────────────────────────
    await page.goto(`${runtime.base_url}/`, { waitUntil: 'load' });
    // index.html declares its runtime state with top-level `let`, which lives
    // in the script's global lexical scope and is deliberately NOT reachable
    // as a `window.*` property. Every state read below therefore uses bare
    // identifiers guarded by `typeof`, which is what actually observes the
    // real page state rather than silently reading `undefined`.
    const pageShape = await page.evaluate(() => ({
      hasSubmitSRS: typeof submitSRS === 'function',
      hasNextQuestion: typeof nextQuestion === 'function',
      hasHandleBossAnswer: typeof _handleBossAnswer === 'function',
      hasLoadBossQuestion: typeof _loadBossQuestion === 'function',
      hasStartBossBattle: typeof startBossBattle === 'function',
      hasOnBoardClick: typeof onBoardClick === 'function',
      // srs.js exposes its module through a top-level `const SRS`, which is
      // likewise a lexical global rather than a window property.
      hasSRSReview: typeof SRS !== 'undefined' && typeof SRS.review === 'function',
      srsReviewPostsToRealRoute: typeof SRS !== 'undefined'
        && typeof SRS.review === 'function'
        && SRS.review.toString().includes("fetch('/api/srs/review'"),
      hasWGo: typeof window.WGo !== 'undefined',
      title: document.title,
    }));
    report.evidence.page_shape = pageShape;
    report.checks.BROWSER_PAGE_LOAD = Boolean(pageShape.hasSubmitSRS && pageShape.hasNextQuestion);
    report.checks.REAL_WGO_PRESENT = Boolean(pageShape.hasWGo);
    report.checks.REAL_SRS_JS_LOADED_IN_PAGE = Boolean(
      pageShape.hasSRSReview && pageShape.srsReviewPostsToRealRoute,
    );

    // ── real adventure state, then the real Lord Trial entry ──────────
    await page.waitForFunction(
      (zoneKey) => typeof _adventureProgress !== 'undefined'
        && Array.isArray(_adventureProgress)
        && _adventureProgress.some((zone) => zone && zone.key === zoneKey),
      ZONE_KEY,
      { timeout: 90000 },
    );
    report.evidence.zone_state = await page.evaluate(
      (zoneKey) => (_adventureProgress || []).find((zone) => zone && zone.key === zoneKey) || null,
      ZONE_KEY,
    );

    await page.evaluate((zoneKey) => startBossBattle(zoneKey), ZONE_KEY);
    await page.waitForSelector('#boss-cinematic.show', { timeout: 30000 });
    report.evidence.lord_card_phase = await page.evaluate(
      () => document.getElementById('boss-cinematic')?.className || '',
    );

    // Real CTA on the real Zone 1 Lord card: the ritual, the real
    // /api/adventure/boss/start call and the real _loadBossQuestion() all
    // run from this one genuine click.
    await page.click('#boss-cinematic-btn');
    await page.waitForFunction(
      () => typeof _bossMode !== 'undefined' && _bossMode === true
        && Array.isArray(_bossQueue) && _bossQueue.length > 0,
      undefined,
      { timeout: 90000 },
    );
    const attempt = await page.evaluate(() => ({
      bossMode: _bossMode === true,
      attemptId: _bossAttemptId || null,
      queueLength: (_bossQueue || []).length,
      index: _bossIndex,
      currentQuestionId: typeof currentQ !== 'undefined' && currentQ ? Number(currentQ.id) : null,
    }));
    report.evidence.attempt = attempt;
    report.checks.LORD_TRIAL_ENTRY = attempt.bossMode === true && attempt.queueLength > 0;
    report.checks.SIGNED_ATTEMPT_ACTIVE = typeof attempt.attemptId === 'string' && attempt.attemptId.length > 0;

    // ── real board render ─────────────────────────────────────────────
    await page.waitForFunction(
      () => typeof board !== 'undefined' && Boolean(board)
        && typeof currentNode !== 'undefined' && Boolean(currentNode)
        && !document.getElementById('board-canvas-wrap')?.classList.contains('hidden'),
      undefined,
      { timeout: 90000 },
    );
    const boardState = await page.evaluate(() => {
      const wrap = document.getElementById('board-canvas-wrap');
      const rect = wrap ? wrap.getBoundingClientRect() : null;
      return {
        hasBoard: Boolean(board),
        boardSize: currentProblem ? currentProblem.size : null,
        canvasCount: wrap ? wrap.querySelectorAll('canvas').length : 0,
        wrapVisible: Boolean(rect && rect.width > 0 && rect.height > 0),
        wrapRect: rect ? { width: Math.round(rect.width), height: Math.round(rect.height) } : null,
        answerChildren: currentNode ? (currentNode.children || []).length : 0,
      };
    });
    report.evidence.board = boardState;
    report.checks.REAL_BOARD_RENDERED = Boolean(
      boardState.hasBoard && boardState.canvasCount > 0 && boardState.wrapVisible,
    );

    // ── clickability, WITHOUT answering ───────────────────────────────
    // Everything onBoardClick() checks before it can accept a move is read
    // here, plus a real hit test of the board surface at the point the
    // correct answer occupies. Nothing is clicked: the answer itself is the
    // first step of the natural reproduction and belongs to the trace task.
    const clickability = await page.evaluate(() => {
      const answerNode = ((currentNode && currentNode.children) || []).find((child) => child && child.move);
      if (!answerNode) return { reason: 'no_answer_node_in_tree' };
      const { x, y } = answerNode.move;
      const displayX = typeof _bx === 'function' ? _bx(x) : x;
      const displayY = typeof _by === 'function' ? _by(y) : y;
      // WGo translates a click with (layerX * pixelRatio - left) / fieldWidth,
      // rounded. This is that mapping run forwards, then run back through
      // WGo's own formula so the coordinate is verified, not assumed.
      let hit = null;
      try {
        const element = board.element;
        const rect = element.getBoundingClientRect();
        const pixelRatio = board.pixelRatio || 1;
        const scaleX = element.offsetWidth ? rect.width / element.offsetWidth : 1;
        const scaleY = element.offsetHeight ? rect.height / element.offsetHeight : 1;
        const layerX = board.getX(displayX) / pixelRatio;
        const layerY = board.getY(displayY) / pixelRatio;
        const viewportX = rect.left + layerX * scaleX;
        const viewportY = rect.top + layerY * scaleY;
        const backX = Math.round((layerX * pixelRatio - board.left) / board.fieldWidth);
        const backY = Math.round((layerY * pixelRatio - board.top) / board.fieldHeight);
        const hitElement = document.elementFromPoint(Math.round(viewportX), Math.round(viewportY));
        hit = {
          viewportPoint: { x: Math.round(viewportX), y: Math.round(viewportY) },
          pixelRatio,
          scale: { x: Number(scaleX.toFixed(4)), y: Number(scaleY.toFixed(4)) },
          roundTrip: { x: backX, y: backY },
          roundTripMatches: backX === displayX && backY === displayY,
          tag: hitElement ? hitElement.tagName : null,
          insideBoardWrap: Boolean(hitElement && hitElement.closest('#board-canvas-wrap')),
        };
      } catch (error) {
        hit = { error: String(error && error.message || error) };
      }
      return {
        answerPoint: { x, y },
        displayPoint: { x: displayX, y: displayY },
        onBoardClickIsFunction: typeof onBoardClick === 'function',
        answering: answering === true,
        solved: solved === true,
        boardFailedClosed: _questionBoardFailedClosed === true,
        pointIsEmpty: !(logicBoard && logicBoard[x] && logicBoard[x][y] !== null),
        hit,
      };
    });
    report.evidence.clickability = clickability;
    report.checks.REAL_BOARD_CLICK_CAPABLE = Boolean(
      clickability.onBoardClickIsFunction
      && clickability.answering === false
      && clickability.solved === false
      && clickability.boardFailedClosed === false
      && clickability.pointIsEmpty === true
      && clickability.hit
      && clickability.hit.insideBoardWrap === true
      && clickability.hit.roundTripMatches === true,
    );

    // The attempt must still be unanswered: a readiness probe that silently
    // consumed a question would corrupt the reproduction it is preparing.
    const answered = await page.evaluate(async (zoneKey) => {
      const res = await fetch('/api/adventure/boss/start', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zone_key: zoneKey }),
      });
      return res.json();
    }, ZONE_KEY);
    report.evidence.attempt_after_probe = {
      resumed: answered?.resumed,
      answered_count: answered?.answered_count,
      correct: answered?.correct,
    };
    report.checks.PROBE_DID_NOT_ANSWER = Number(answered?.answered_count || 0) === 0;

    await context.close();
  } finally {
    await browser.close();
    await stopRuntime(child);
  }

  report.checks.NO_ROUTE_INTERCEPTION = report.intercepted_routes.length === 0;
  report.ok = Object.values(report.checks).every((value) => value === true);
  console.log(JSON.stringify(report, null, 2));
  return report.ok ? 0 : 1;
}

main().then(
  (code) => { process.exitCode = code; },
  (error) => {
    console.error(error && error.stack || String(error));
    process.exitCode = 1;
  },
);
