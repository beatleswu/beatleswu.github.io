import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');

const VIEWPORTS = [
  ['DESKTOP', { width: 1366, height: 768, hasTouch: false, isMobile: false }],
  ['IPAD_LANDSCAPE', { width: 1024, height: 768, hasTouch: true, isMobile: true }],
  ['IPAD_PORTRAIT', { width: 768, height: 1024, hasTouch: true, isMobile: true }],
  ['MOBILE_PORTRAIT', { width: 390, height: 844, hasTouch: true, isMobile: true }],
];

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const executable = candidates.find((candidate) => fssync.existsSync(candidate));
  if (!executable) throw new Error('No Chrome/Edge executable found; set CHROME_BIN.');
  return executable;
}

function contentTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[ext] || 'application/octet-stream';
}

async function startStaticServer(rootDir) {
  const routeMap = {
    '/landing': 'landing.html',
    '/try': 'rating_test.html',
    '/login': 'login.html',
    '/curriculum': 'curriculum.html',
  };
  const server = http.createServer(async (req, res) => {
    try {
      const requestUrl = new URL(req.url, 'http://127.0.0.1');
      let relative = routeMap[requestUrl.pathname] || requestUrl.pathname;
      if (relative === '/') relative = '/landing';
      if (!path.extname(relative)) relative += '.html';
      const relativePath = relative.startsWith('/') ? relative : `/${relative}`;
      const absolute = path.resolve(rootDir, `.${relativePath}`);
      if (!absolute.startsWith(rootDir) || !fssync.existsSync(absolute)) {
        res.writeHead(404);
        res.end('not found');
        return;
      }
      const body = await fs.readFile(absolute);
      res.writeHead(200, { 'Content-Type': contentTypeFor(absolute), 'Cache-Control': 'no-store' });
      res.end(body);
    } catch (error) {
      res.writeHead(500);
      res.end(String(error));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  return { server, origin: `http://127.0.0.1:${address.port}` };
}

function jsonResponse(payload, status = 200) {
  return { status, contentType: 'application/json', body: JSON.stringify(payload) };
}

function fixtureQuestion(id = 1) {
  return {
    id,
    token: `w2-02-continuity-token-${id}`,
    discipline: 'life_death',
    rating: 800,
    content: '(;GM[1]FF[4]SZ[9]PL[B];B[ee])',
    accepted_moves: [{ x: 4, y: 4 }],
    native_answer: 'B[ee]',
    content_sha256: `w2-02-continuity-${id}`,
  };
}

function curriculumSummary() {
  return {
    cardsCount: 0,
    units: [{
      discipline: 'life_death', stage: 'LV1', total: 10, practiced: 0, unlocked: 10,
      mapCount: 10, familyLabel: 'Life & Death', chapterBossTotal: 0,
      chapterBossDefeated: 0, bookBossTotal: 0, bookBossDefeated: 0, aggregate: false,
    }],
  };
}

function makeState() {
  return { authenticated: false, claimCount: 0, sessionId: 'w2-02-continuity-session' };
}

async function installApiMocks(page, state, label) {
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const requestUrl = new URL(request.url());
    const pathname = requestUrl.pathname;
    const method = request.method();

    if (pathname === '/api/auth/me') {
      await route.fulfill(jsonResponse(state.authenticated
        ? { logged_in: true, username: 'w2player', display_name: 'First Player', is_premium: false }
        : { logged_in: false }));
      return;
    }
    if (pathname === '/api/auth/config') {
      await route.fulfill(jsonResponse({ google_client_id: '', turnstile_site_key: '' }));
      return;
    }
    if (pathname === '/api/rating_test/pool_info') {
      await route.fulfill(jsonResponse({ pool_size: 12 }));
      return;
    }
    if (pathname === '/api/rating_test/start' && method === 'POST') {
      await route.fulfill(jsonResponse({
        session_id: state.sessionId, cur_rating: 800, rank_label: '25k', total_rounds: 7,
        min_rounds: 7, pool_size: 12, question: fixtureQuestion(),
      }));
      return;
    }
    if (pathname === '/api/rating_test/answer' && method === 'POST') {
      await route.fulfill(jsonResponse({ finished: true, correct: true, cur_rating: 820, rank_label: '24k' }));
      return;
    }
    if (pathname === '/api/auth/register' && method === 'POST') {
      state.authenticated = true;
      await route.fulfill(jsonResponse({ ok: true, verify_email_sent: false, redirect: '/' }));
      return;
    }
    if (pathname === '/api/rating_test/claim_anon' && method === 'POST') {
      const body = request.postDataJSON();
      assert.equal(body.session_id, state.sessionId);
      assert.equal(state.authenticated, true);
      state.claimCount += 1;
      await route.fulfill(jsonResponse({ ok: true }));
      return;
    }
    if (pathname === '/api/subscription/status') {
      await route.fulfill(jsonResponse({ is_premium: false, active: false, remaining: 10 }));
      return;
    }
    if (pathname === '/api/curriculum/summary') {
      await route.fulfill(jsonResponse(curriculumSummary()));
      return;
    }
    if (pathname === '/api/quest-board') {
      await route.fulfill(jsonResponse({
        accepted: [], claimable: [], quest_meta: [], coins: 0, xp: 0,
        open_quests: [{
          quest_key: 'life_death::LV1', stage_key: 'life_death::LV1',
          discipline: 'life_death', stage: 'LV1', total: 10, practiced: 0, coins: 20, xp: 30,
        }],
      }));
      return;
    }
    if (pathname === '/api/quests/today') {
      await route.fulfill(jsonResponse({ quests: [] }));
      return;
    }
    if (pathname === '/api/player/appearance') {
      await route.fulfill(jsonResponse({ equipped: {}, wardrobe: [] }));
      return;
    }
    if (pathname === '/api/quest-board/accept' && method === 'POST') {
      await route.fulfill(jsonResponse({ ok: true }));
      return;
    }
    await route.fulfill(jsonResponse(method === 'POST' ? { ok: true } : {}));
  });
  for (const prefix of [
    'https://accounts.google.com/**',
    'https://cdn.jsdelivr.net/**',
    'https://cdn.socket.io/**',
    'https://fonts.googleapis.com/**',
    'https://fonts.gstatic.com/**',
  ]) await page.route(prefix, (route) => route.abort());
}

async function assertNoHorizontalOverflow(page) {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  assert.ok(dimensions.documentWidth <= dimensions.viewport + 1, JSON.stringify(dimensions));
  assert.ok(dimensions.bodyWidth <= dimensions.viewport + 1, JSON.stringify(dimensions));
}

async function waitForVisible(page, selector) {
  await page.waitForFunction((value) => {
    const element = document.querySelector(value);
    return !!element && !element.hidden && !element.classList.contains('hidden');
  }, selector);
}

async function activate(locator, page, touch) {
  if (touch) await locator.tap();
  else await locator.click();
}

async function runViewport(browser, origin, [label, viewport]) {
  const context = await browser.newContext({
    viewport, hasTouch: viewport.hasTouch, isMobile: viewport.isMobile,
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  const state = makeState();
  await installApiMocks(page, state, label);

  // Public first-play result CTA opens the existing signup authority.
  await page.goto(`${origin}/try`, { waitUntil: 'domcontentloaded' });
  await waitForVisible(page, '[data-w2-surface="learn-onboarding-orientation"]');
  const start = page.locator('#btn-start');
  await start.focus();
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => {
    const screen = document.getElementById('screen-test');
    return !!screen && !screen.classList.contains('hidden') && !!document.querySelector('#test-board-wrap canvas');
  });
  const board = page.locator('#test-board-wrap canvas').first();
  const boardBox = await board.boundingBox();
  assert.ok(boardBox, `${label}: first Go board is laid out`);
  const answerResponse = page.waitForResponse((response) => response.url().includes('/api/rating_test/answer'));
  await page.mouse.click(boardBox.x + boardBox.width / 2, boardBox.y + boardBox.height / 2);
  await answerResponse;
  await waitForVisible(page, '#screen-placement-result');
  const resultCta = page.locator('#screen-placement-result .btn-goto-home');
  await resultCta.focus();
  await page.keyboard.press('Enter');
  await waitForVisible(page, '#google-signup-modal');
  const fallback = page.locator('#email-signup-fallback');
  const fallbackUrl = new URL(await fallback.getAttribute('href'), origin);
  assert.equal(fallbackUrl.pathname, '/login');
  assert.equal(fallbackUrl.searchParams.get('from'), 'try');
  assert.equal(fallbackUrl.searchParams.get('sid'), state.sessionId);
  assert.equal(fallbackUrl.searchParams.get('next'), '/curriculum');

  await activate(fallback, page, viewport.hasTouch);
  await page.waitForURL('**/login?tab=register&from=try&sid=*&next=*');
  assert.equal(new URL(page.url()).pathname, '/login');
  assert.equal(new URL(page.url()).searchParams.get('next'), '/curriculum');
  await page.locator('#reg-username').focus();
  await page.locator('#reg-username').fill('w2player');
  await page.locator('#reg-nickname').fill('First Player');
  await page.locator('#reg-email').fill('first-player@example.com');
  await page.locator('#reg-password').fill('safe-pass-123');
  await page.locator('#reg-confirm').fill('safe-pass-123');
  assert.equal(await page.locator('#reg-btn').isVisible(), true);
  // Enter on the final input exercises the page's keyboard contract once; the
  // register button itself remains a native pointer/touch target.
  await page.locator('#reg-confirm').focus();
  await page.keyboard.press('Enter');
  await page.waitForURL('**/curriculum');
  assert.equal(state.claimCount, 1);

  // Authenticated Learn entry has a single obvious first action backed by the existing quest board.
  await waitForVisible(page, '[data-w2-surface="learn-onboarding-curriculum-continuity"]');
  const continuation = page.locator('[data-w2-surface="learn-onboarding-curriculum-continuity"]');
  const firstAction = continuation.locator('[data-w2-cta="curriculum-first-action"]');
  assert.equal(await firstAction.getAttribute('href'), '#quest-board');
  assert.equal(await page.locator('.qc-btn.accept').count(), 1);
  assert.equal(await page.locator('[data-w2-cta="first-play-start"]').count(), 0);
  await assertNoHorizontalOverflow(page);

  await page.evaluate(() => I18n.setLang('zh'));
  assert.equal(await page.locator('html').getAttribute('lang'), 'zh-TW');
  assert.match(await continuation.innerText(), /下一步修煉/);
  await page.evaluate(() => I18n.setLang('en'));
  assert.equal(await page.locator('html').getAttribute('lang'), 'en');
  assert.match(await continuation.innerText(), /Your next learning step/);

  await firstAction.focus();
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.w2Cta), 'curriculum-first-action');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => location.hash === '#quest-board');
  const acceptQuest = page.locator('.qc-btn.accept').first();
  await activate(acceptQuest, page, viewport.hasTouch);
  await page.waitForFunction(() => location.pathname === '/'
    && new URLSearchParams(location.search).get('discipline') === 'life_death'
    && new URLSearchParams(location.search).get('stage') === 'LV1');
  assert.equal(new URL(page.url()).pathname, '/');

  // Back/forward preserves the deterministic route decision in the browser history.
  await page.goBack();
  await page.waitForFunction(() => location.pathname === '/curriculum' && location.hash === '#quest-board');
  await page.goForward();
  await page.waitForFunction(() => location.pathname === '/'
    && new URLSearchParams(location.search).get('discipline') === 'life_death'
    && new URLSearchParams(location.search).get('stage') === 'LV1');

  await context.close();
  return label;
}

async function main() {
  const { server, origin } = await startStaticServer(REPO_ROOT);
  const browser = await chromium.launch({ executablePath: findChrome(), headless: true });
  try {
    const passed = [];
    for (const viewport of VIEWPORTS) passed.push(await runViewport(browser, origin, viewport));
    console.log('NO_DEAD_PRIMARY_CTA=PASS');
    console.log('SIGNUP_CLAIM_CONTINUITY=PASS');
    console.log('AUTH_RETURN_TARGET=PASS');
    console.log('AUTHENTICATED_LEARN_ENTRY=PASS');
    console.log('CURRICULUM_FIRST_ACTION=PASS');
    console.log('ZH_TW_PATH=PASS');
    console.log('EN_US_PATH=PASS');
    console.log('KEYBOARD_PATH=PASS');
    console.log('POINTER_PATH=PASS');
    console.log('FOCUS_PATH=PASS');
    for (const label of passed) console.log(`${label}=PASS`);
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
