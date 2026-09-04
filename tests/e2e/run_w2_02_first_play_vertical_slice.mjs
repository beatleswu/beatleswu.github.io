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
  ['DESKTOP', { width: 1366, height: 768 }],
  ['IPAD_LANDSCAPE', { width: 1024, height: 768 }],
  ['IPAD_PORTRAIT', { width: 768, height: 1024 }],
  ['MOBILE_PORTRAIT', { width: 390, height: 844 }],
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
    '.mp3': 'audio/mpeg',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[ext] || 'application/octet-stream';
}

async function startStaticServer(rootDir) {
  const routeMap = { '/landing': 'landing.html', '/try': 'rating_test.html' };
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
      res.writeHead(200, {
        'Content-Type': contentTypeFor(absolute),
        'Cache-Control': 'no-store',
      });
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
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  };
}

function fixtureQuestion(id = 1) {
  return {
    id,
    token: `w2-02-fixture-token-${id}`,
    discipline: 'life_death',
    rating: 800,
    content: '(;GM[1]FF[4]SZ[9]PL[B];B[ee])',
    accepted_moves: [{ x: 4, y: 4 }],
    native_answer: 'B[ee]',
    content_sha256: `w2-02-fixture-${id}`,
  };
}

function apiPayload(pathname, method) {
  if (pathname === '/api/auth/me') return { logged_in: false };
  if (pathname === '/api/auth/config') return { google_client_id: '', turnstile_site_key: '' };
  if (pathname === '/api/rating_test/pool_info') return { pool_size: 12 };
  if (pathname === '/api/rating_test/start' && method === 'POST') {
    return {
      session_id: 'w2-02-fixture-session',
      cur_rating: 800,
      rank_label: '25k',
      total_rounds: 7,
      min_rounds: 7,
      pool_size: 12,
      question: fixtureQuestion(),
    };
  }
  if (pathname === '/api/rating_test/answer' && method === 'POST') {
    return {
      finished: true,
      correct: true,
      cur_rating: 820,
      rank_label: '24k',
    };
  }
  if (pathname.startsWith('/api/rating_test/result/')) return {};
  return method === 'POST' ? { ok: true } : {};
}

async function installApiMocks(page) {
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    await route.fulfill(jsonResponse(apiPayload(pathname, request.method())));
  });
  await page.route('https://cdn.jsdelivr.net/**', (route) => route.abort());
  await page.route('https://cdn.socket.io/**', (route) => route.abort());
  await page.route('https://fonts.googleapis.com/**', (route) => route.abort());
  await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
}

async function waitForVisible(page, selector) {
  await page.waitForFunction((value) => {
    const element = document.querySelector(value);
    return !!element && !element.hidden && !element.classList.contains('hidden');
  }, selector);
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

async function assertTouchTarget(page, locator) {
  const box = await locator.boundingBox();
  assert.ok(box, 'first-play CTA must be laid out');
  assert.ok(box.width >= 44 && box.height >= 44, `CTA touch target too small: ${JSON.stringify(box)}`);
}

async function runViewport(browser, origin, [label, viewport]) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  await installApiMocks(page);
  await page.goto(`${origin}/landing`, { waitUntil: 'domcontentloaded' });

  const section = page.locator('[data-w2-surface="learn-onboarding-first-play"]');
  const ctas = page.locator('[data-w2-cta="first-play-start"]');
  assert.equal(await ctas.count(), 2);
  assert.equal(await ctas.nth(0).getAttribute('href'), '/try');
  assert.equal(await ctas.nth(1).getAttribute('href'), '/try');
  await section.scrollIntoViewIfNeeded();
  await assertTouchTarget(page, ctas.nth(1));
  await assertNoHorizontalOverflow(page);

  await page.evaluate(() => I18n.setLang('zh'));
  assert.equal(await page.locator('#first-play-title').innerText(), '確認你的起點\n開啟修煉之旅');
  assert.equal(await page.locator('html').getAttribute('lang'), 'zh-TW');
  await page.evaluate(() => I18n.setLang('en'));
  assert.match(await page.locator('#first-play-title').innerText(), /Confirm your starting point/);
  assert.equal(await page.locator('html').getAttribute('lang'), 'en');

  // Pointer path: public landing CTA reaches the existing /try authority.
  await ctas.nth(1).click();
  await page.waitForURL('**/try');
  assert.equal(new URL(page.url()).pathname, '/try');
  await waitForVisible(page, '[data-w2-surface="learn-onboarding-orientation"]');
  const orientation = page.locator('[data-w2-surface="learn-onboarding-orientation"]');
  assert.equal(await orientation.locator('[data-w2-step]').count(), 3);
  assert.match(await orientation.innerText(), /Your first Go step/);

  await page.evaluate(() => I18n.setLang('zh'));
  assert.match(await orientation.innerText(), /你的第一步圍棋練習/);
  assert.match(await orientation.innerText(), /看懂棋盤/);
  await page.evaluate(() => I18n.setLang('en'));
  assert.match(await orientation.innerText(), /Play one move/);
  assert.match(await orientation.innerText(), /Find your next path/);
  assert.equal(await page.locator('html').getAttribute('lang'), 'en');

  // Keyboard path: the native start button opens the server-backed Go board.
  const startButton = page.locator('#btn-start');
  await startButton.focus();
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => {
    const screen = document.getElementById('screen-test');
    return !!screen && !screen.classList.contains('hidden')
      && !!document.querySelector('#test-board-wrap canvas');
  });
  assert.ok(await page.locator('#test-board-wrap canvas').count() >= 1);
  await assertNoHorizontalOverflow(page);

  const board = page.locator('#test-board-wrap canvas').first();
  const boardBox = await board.boundingBox();
  assert.ok(boardBox, 'first Go board must be laid out');
  const answerResponse = page.waitForResponse((response) => response.url().includes('/api/rating_test/answer'));
  // WGo paints its interactive board as a canvas; use a real pointer event at
  // the board centre so the library's canvas listener receives the click.
  await page.mouse.click(boardBox.x + boardBox.width / 2, boardBox.y + boardBox.height / 2);
  await answerResponse;
  await page.waitForFunction(() => {
    const screen = document.getElementById('screen-placement-result');
    return !!screen && !screen.classList.contains('hidden')
      && !!screen.querySelector('.btn-goto-home');
  });
  const nextAction = page.locator('#screen-placement-result .btn-goto-home');
  assert.equal(await nextAction.getAttribute('data-w2-next-action'), 'save-and-continue-learning');
  assert.match(await nextAction.innerText(), /Sign up to save your rank and start learning/);
  await assertNoHorizontalOverflow(page);

  await context.close();
  return label;
}

async function main() {
  const { server, origin } = await startStaticServer(REPO_ROOT);
  const browser = await chromium.launch({ executablePath: findChrome(), headless: true });
  try {
    const passed = [];
    for (const viewport of VIEWPORTS) passed.push(await runViewport(browser, origin, viewport));
    console.log(`NO_DEAD_PRIMARY_CTA=PASS`);
    console.log(`ZH_TW_PATH=PASS`);
    console.log(`EN_US_PATH=PASS`);
    console.log(`KEYBOARD_PATH=PASS`);
    console.log(`POINTER_PATH=PASS`);
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
