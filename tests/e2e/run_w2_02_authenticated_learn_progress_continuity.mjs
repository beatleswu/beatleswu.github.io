import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const QUEST_KEY = 'life_death::LV1';
const QUESTION_ID = 101;

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
    '.mp3': 'audio/mpeg',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[ext] || 'application/octet-stream';
}

async function startStaticServer(rootDir) {
  const routeMap = {
    '/': 'index.html',
    '/curriculum': 'curriculum.html',
  };
  const server = http.createServer(async (req, res) => {
    try {
      const requestUrl = new URL(req.url, 'http://127.0.0.1');
      let relative = routeMap[requestUrl.pathname] || requestUrl.pathname;
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
  return { status, contentType: 'application/json', body: JSON.stringify(payload) };
}

function fixtureQuestion() {
  return {
    id: QUESTION_ID,
    token: 'w2-02-authenticated-continuity-token',
    discipline: 'life_death',
    stage: 'LV1',
    topic: 'Life & Death',
    rating: 800,
    content: '(;GM[1]FF[4]SZ[9]PL[B];B[ee])',
    accepted_moves: [{ x: 4, y: 4 }],
    native_answer: 'B[ee]',
    content_sha256: 'w2-02-authenticated-continuity-question',
  };
}

function questMeta(state) {
  return {
    quest_key: QUEST_KEY,
    stage_key: QUEST_KEY,
    discipline: 'life_death',
    stage: 'LV1',
    total: 1,
    practiced: state.reviewed ? 1 : 0,
    coins: 20,
    xp: 30,
    href: `/?discipline=life_death&stage=LV1&quest=${encodeURIComponent(QUEST_KEY)}&resume=1`,
  };
}

function curriculumSummary(state) {
  return {
    cardsCount: state.reviewed ? 1 : 0,
    units: [{
      discipline: 'life_death',
      stage: 'LV1',
      total: 1,
      practiced: state.reviewed ? 1 : 0,
      unlocked: 1,
      mapCount: 1,
      familyLabel: 'Life & Death',
      chapterBossTotal: 0,
      chapterBossDefeated: 0,
      bookBossTotal: 0,
      bookBossDefeated: 0,
      aggregate: false,
    }],
  };
}

function questBoard(state) {
  const meta = questMeta(state);
  if (state.completed) {
    return { accepted: [], claimable: [meta], quest_meta: [meta], open_quests: [], coins: 0, xp: 0 };
  }
  if (state.accepted) {
    return { accepted: [QUEST_KEY], claimable: [], quest_meta: [meta], open_quests: [], coins: 0, xp: 0 };
  }
  return { accepted: [], claimable: [], quest_meta: [], open_quests: [meta], coins: 0, xp: 0 };
}

function makeState() {
  return {
    accepted: false,
    reviewed: false,
    completed: false,
    acceptRequests: 0,
    reviewRequests: 0,
    progressRequests: 0,
  };
}

async function installApiMocks(page, state) {
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const requestUrl = new URL(request.url());
    const pathname = requestUrl.pathname;
    const method = request.method();

    if (pathname === '/api/auth/me') {
      await route.fulfill(jsonResponse({
        logged_in: true,
        user_id: 202,
        username: 'continuity-player',
        display_name: 'Continuity Player',
        is_premium: false,
      }));
      return;
    }
    if (pathname === '/api/auth/config') {
      await route.fulfill(jsonResponse({ google_client_id: '', turnstile_site_key: '' }));
      return;
    }
    if (pathname === '/api/subscription/status') {
      await route.fulfill(jsonResponse({ is_premium: false, active: false, remaining: 20, daily_limit: 20 }));
      return;
    }
    if (pathname === '/api/curriculum/summary') {
      await route.fulfill(jsonResponse(curriculumSummary(state)));
      return;
    }
    if (pathname === '/api/quest-board' && method === 'GET') {
      await route.fulfill(jsonResponse(questBoard(state)));
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
    if (pathname === '/api/user/coins') {
      await route.fulfill(jsonResponse({ coins: 0 }));
      return;
    }
    if (pathname === '/api/quest-board/accept' && method === 'POST') {
      state.accepted = true;
      state.acceptRequests += 1;
      await route.fulfill(jsonResponse({ ok: true }));
      return;
    }
    if (pathname === '/api/questions') {
      await route.fulfill(jsonResponse([fixtureQuestion()]));
      return;
    }
    if (pathname === `/api/question/${QUESTION_ID}`) {
      await route.fulfill(jsonResponse(fixtureQuestion()));
      return;
    }
    if (pathname === '/api/srs/due') {
      await route.fulfill(jsonResponse({ due: [], count: 0 }));
      return;
    }
    if (pathname === '/api/srs/all') {
      await route.fulfill(jsonResponse(state.reviewed ? [{ question_id: QUESTION_ID, repetitions: 1 }] : []));
      return;
    }
    if (pathname === '/api/badges/definitions' || pathname === '/api/badges/earned') {
      await route.fulfill(jsonResponse([]));
      return;
    }
    if (pathname === '/api/mistakes/stats') {
      await route.fulfill(jsonResponse({ total: 0 }));
      return;
    }
    if (pathname === '/api/shop/status') {
      await route.fulfill(jsonResponse({ inventory: {}, shield_active: false }));
      return;
    }
    if (pathname === '/api/unit-progress' && method === 'POST') {
      await route.fulfill(jsonResponse({ unit_complete: false }));
      return;
    }
    if (pathname === '/api/srs/review' && method === 'POST') {
      state.reviewed = true;
      state.completed = true;
      state.reviewRequests += 1;
      await route.fulfill(jsonResponse({
        ok: true,
        ease_factor: 2.5,
        interval: 1,
        due_date: '2099-01-01',
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
        new_rank_level: null,
        pet: null,
        practice: {},
        training: null,
        new_appearance_items: [],
        guild_progress: {
          ok: true,
          quest_key: QUEST_KEY,
          practiced: 1,
          total: 1,
          completed: true,
          next_question_id: null,
        },
      }));
      return;
    }
    if (pathname === '/api/quest-board/progress') {
      state.progressRequests += 1;
      await route.fulfill(jsonResponse({
        ok: true,
        quest_key: QUEST_KEY,
        practiced: state.reviewed ? 1 : 0,
        total: 1,
        completed: state.completed,
        next_question_id: state.completed ? null : QUESTION_ID,
      }));
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

async function waitForVisible(page, selector) {
  await page.waitForFunction((value) => {
    const element = document.querySelector(value);
    return !!element && !element.hidden && !element.classList.contains('hidden');
  }, selector);
}

async function assertNoHorizontalOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  assert.ok(dimensions.documentWidth <= dimensions.viewport + 1, `${label}: ${JSON.stringify(dimensions)}`);
  assert.ok(dimensions.bodyWidth <= dimensions.viewport + 1, `${label}: ${JSON.stringify(dimensions)}`);
}

async function activate(locator, page, hasTouch) {
  if (hasTouch) await locator.tap();
  else await locator.click();
}

async function assertCurriculumState(page, label, state, expectedState, expectedAction) {
  await waitForVisible(page, '[data-w2-surface="learn-onboarding-curriculum-continuity"]');
  const banner = page.locator('[data-w2-surface="learn-onboarding-curriculum-continuity"]');
  const action = banner.locator('[data-w2-cta="curriculum-first-action"]');
  assert.equal(await banner.getAttribute('data-w2-learn-state'), expectedState, `${label}: learn state`);
  assert.equal(await action.getAttribute('data-w2-next-action'), expectedAction, `${label}: next action`);
  assert.equal(await action.getAttribute('href'), '#quest-board', `${label}: action target`);
  const box = await action.boundingBox();
  assert.ok(box && box.width >= 44 && box.height >= 44, `${label}: CTA touch target`);
  await assertNoHorizontalOverflow(page, label);
  if (expectedState === 'claim') {
    assert.equal(await banner.getAttribute('data-w2-return-state'), 'server-synced');
    assert.match(await banner.innerText(), /progress was refreshed|進度以帳號資料重新同步/);
  }
  if (expectedState === 'open') assert.equal(state.accepted, false, `${label}: open state before acceptance`);
  if (expectedState === 'claim') assert.equal(state.accepted, true, `${label}: accepted state after Learn`);
}

async function runViewport(browser, origin, [label, viewport]) {
  const context = await browser.newContext({
    viewport,
    hasTouch: viewport.hasTouch,
    isMobile: viewport.isMobile,
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  const state = makeState();
  await installApiMocks(page, state);

  await page.goto(`${origin}/curriculum`, { waitUntil: 'domcontentloaded' });
  await assertCurriculumState(page, `${label}: initial`, state, 'open', 'open-quest-board');
  const banner = page.locator('[data-w2-surface="learn-onboarding-curriculum-continuity"]');
  const initialAction = banner.locator('[data-w2-cta="curriculum-first-action"]');
  await page.evaluate(() => I18n.setLang('zh'));
  assert.equal(await page.locator('html').getAttribute('lang'), 'zh-TW');
  assert.match(await banner.innerText(), /下一步修煉/);
  await page.evaluate(() => I18n.setLang('en'));
  assert.equal(await page.locator('html').getAttribute('lang'), 'en');
  assert.match(await banner.innerText(), /Your next learning step/);

  // Keyboard path reaches the existing quest board; the board's accept action
  // is then activated through the real pointer/touch event for this viewport.
  await initialAction.focus();
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.w2Cta), 'curriculum-first-action');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => location.hash === '#quest-board');
  const acceptQuest = page.locator('.qc-btn.accept').first();
  await acceptQuest.scrollIntoViewIfNeeded();
  await activate(acceptQuest, page, viewport.hasTouch);
  await page.waitForFunction(() => location.pathname === '/'
    && new URLSearchParams(location.search).get('discipline') === 'life_death'
    && new URLSearchParams(location.search).get('stage') === 'LV1'
    && new URLSearchParams(location.search).get('quest') === 'life_death::LV1'
    && new URLSearchParams(location.search).get('resume') === '1');
  assert.equal(state.acceptRequests, 1, `${label}: quest accepted once`);

  // This is the existing Learn surface, not a fixture page: the production
  // index.html renders the real WGo board and submits the canonical review.
  await waitForVisible(page, '#board-canvas-wrap');
  await page.waitForFunction(() => {
    const board = document.querySelector('#board-canvas-wrap canvas');
    return !!board && board.getBoundingClientRect().width > 0;
  });
  await waitForVisible(page, '#guild-quest-hud');
  assert.equal(await page.locator('#guild-quest-hud').getAttribute('hidden'), null);
  const board = page.locator('#board-canvas-wrap canvas').first();
  const boardBox = await board.boundingBox();
  assert.ok(boardBox, `${label}: real Learn board is laid out`);
  const reviewResponse = page.waitForResponse((response) =>
    response.url().includes('/api/srs/review') && response.request().method() === 'POST');
  await page.mouse.click(boardBox.x + boardBox.width / 2, boardBox.y + boardBox.height / 2);
  await reviewResponse;
  try {
    await page.waitForFunction(() => {
      const modal = document.getElementById('guild-quest-complete');
      return !!modal && !modal.hidden;
    });
  } catch (error) {
    const diagnostic = await page.evaluate(() => ({
      modalHidden: document.getElementById('guild-quest-complete')?.hidden,
      message: document.getElementById('msg-box')?.textContent,
      hud: document.getElementById('guild-quest-hud-count')?.textContent,
      title: document.getElementById('q-title')?.textContent,
      guildQuestMode: window._guildQuestMode || null,
    }));
    console.error(`${label}: Learn completion diagnostic ${JSON.stringify(diagnostic)}`);
    throw error;
  }
  assert.equal(state.reviewRequests, 1, `${label}: canonical review once`);
  assert.equal(state.completed, true, `${label}: server completion projection`);

  // The existing Learn completion return action sends the player back to the
  // curriculum hash; the curriculum then renders the refreshed server state.
  const returnButton = page.locator('#guild-quest-return');
  await returnButton.focus();
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'guild-quest-return');
  await page.keyboard.press('Enter');
  await page.waitForURL('**/curriculum#quest-board');
  await assertCurriculumState(page, `${label}: returned`, state, 'claim', 'claim-reward');
  const returnedBanner = page.locator('[data-w2-surface="learn-onboarding-curriculum-continuity"]');
  assert.match(await returnedBanner.innerText(), /Review and claim reward|查看並領取獎賞/);
  assert.equal(state.progressRequests >= 1, true, `${label}: server completion endpoint was consulted`);

  // A hard reload must preserve the same server-derived claimable state.
  await page.reload({ waitUntil: 'domcontentloaded' });
  await assertCurriculumState(page, `${label}: reload`, state, 'claim', 'claim-reward');

  // Back/forward does not leave contradictory progress in the curriculum.
  await page.goBack();
  await page.waitForFunction(() => location.pathname === '/');
  await page.goForward();
  await page.waitForURL('**/curriculum#quest-board');
  await assertCurriculumState(page, `${label}: forward`, state, 'claim', 'claim-reward');
  await context.close();
  return label;
}

async function main() {
  const { server, origin } = await startStaticServer(REPO_ROOT);
  const browser = await chromium.launch({ executablePath: findChrome(), headless: true });
  try {
    const passed = [];
    for (const viewport of VIEWPORTS) passed.push(await runViewport(browser, origin, viewport));
    console.log('AUTHENTICATED_CURRICULUM_ENTRY=PASS');
    console.log('REAL_LEARN_DESTINATION=PASS');
    console.log('REAL_LEARN_INTERACTION=PASS');
    console.log('SERVER_COMPLETION_SIGNAL=PASS');
    console.log('RETURN_CONTINUATION=PASS');
    console.log('PROGRESS_RELOAD_PRESERVED=PASS');
    console.log('BACK_FORWARD_CONTINUITY=PASS');
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
