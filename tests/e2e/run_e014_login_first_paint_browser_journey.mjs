import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const ALL_E9_FLAGS = {
  e9Shell: true,
  e9TopHud: true,
  e9LeftNav: true,
  e9RightCards: true,
  e9BottomDock: true,
  e9WorldStage: true,
};
const NO_E9_FLAGS = Object.fromEntries(Object.keys(ALL_E9_FLAGS).map((key) => [key, false]));

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

const ZONES = [
  ['k26_30', 'Beginner Village'],
  ['k21_25', 'Slime Plains'],
  ['k16_20', 'Mirror Lake'],
  ['k11_15', 'Tactical Tower'],
  ['k6_10', 'Red Canyon'],
  ['k1_5', 'Five Stones Plain'],
  ['d1_2', 'Cloud Gate'],
  ['d3_4', 'Ancient Ruins'],
  ['d5_6', 'War-God Ruins'],
  ['d7_plus', 'Order Temple'],
].map(([key, name], index) => ({
  key,
  name,
  nameEn: name,
  label: name,
  icon: 'village',
  status: index === 0 ? 'unlocked' : 'locked',
  locked: index !== 0,
  can_enter: index === 0,
  cleared: false,
  stars: 0,
  boss: { available: false },
  seen: 0,
  total: 20,
}));

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
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://127.0.0.1');
      let relative = decodeURIComponent(url.pathname);
      if (relative === '/') relative = '/index.html';
      let absolute = path.resolve(rootDir, `.${relative}`);
      if (!path.extname(absolute)) {
        const htmlRoute = `${absolute}.html`;
        if (fssync.existsSync(htmlRoute)) absolute = htmlRoute;
      }
      if (!absolute.startsWith(rootDir)) {
        res.writeHead(404);
        res.end('not found');
        return;
      }
      const stat = await fs.stat(absolute).catch(() => null);
      if (!stat?.isFile()) {
        res.writeHead(404);
        res.end('not found');
        return;
      }
      res.writeHead(200, {
        'Content-Type': contentTypeFor(absolute),
        'Cache-Control': 'no-store',
      });
      fssync.createReadStream(absolute).pipe(res);
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

function authMe(mode) {
  if (mode === 'unauthenticated') return { logged_in: false, e9_rollout: { effective_flags: NO_E9_FLAGS } };
  const e10 = mode === 'e10';
  return {
    logged_in: true,
    user_id: 14014,
    username: 'e014_browser_tester',
    nickname: 'E014 Browser Tester',
    display_name: 'E014 Browser Tester',
    is_admin: e10,
    is_premium: false,
    plan: 'free',
    needs_onboarding_choice: false,
    tour_done: true,
    elo_rating: 1300,
    newbie_quest_eligible: false,
    e9_rollout: {
      eligible: e10,
      reason: e10 ? 'admin_enabled' : 'global_disabled',
      effective_flags: e10 ? ALL_E9_FLAGS : NO_E9_FLAGS,
    },
  };
}

function apiPayload(pathname, method, mode) {
  if (pathname === '/api/auth/config') return { turnstile_site_key: '', google_client_id: '' };
  if (pathname === '/api/auth/login' && method === 'POST') return { ok: true, username: 'e014_browser_tester' };
  if (pathname === '/api/auth/logout' && method === 'POST') return { ok: true };
  if (pathname === '/api/auth/me') return authMe(mode);
  if (pathname === '/api/questions') return [];
  if (pathname === '/api/srs/due') return { due: [], count: 0 };
  if (pathname === '/api/mistakes/stats') return { total: 0, corrected: 0, worst5: [] };
  if (pathname === '/api/user/coins') return { coins: 0 };
  if (pathname === '/api/subscription/status') return { daily_limit: 20, remaining: 20 };
  if (pathname === '/api/adventure/bootstrap' || pathname === '/api/adventure/progress') {
    return { zones: ZONES, current_player_zone_key: 'k26_30', selected_zone_key: 'k26_30' };
  }
  if (pathname === '/api/skills/profile') return { display_name: 'E014 Browser Tester', rank_level: 'LV1' };
  if (pathname === '/api/daily-challenge/today') return { submitted: false };
  if (pathname === '/api/player/profile') return { display_name: 'E014 Browser Tester' };
  if (method === 'POST') return { ok: true };
  return { ok: true };
}

async function installApiMocks(page, mode, authDelayMs = 650) {
  await page.route('**/*', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (!pathname.startsWith('/api/')) {
      await route.continue();
      return;
    }
    if (pathname === '/api/auth/me') {
      await new Promise((resolve) => setTimeout(resolve, authDelayMs));
    }
    await route.fulfill(jsonResponse(apiPayload(pathname, request.method(), mode)));
  });
}

async function installWorldTrace(page) {
  await page.addInitScript(() => {
    window.__E014_WORLD_TRACE__ = [];
    const visible = (selector) => {
      const element = document.querySelector(selector);
      if (!element || element.hidden) return false;
      const style = getComputedStyle(element);
      if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const sample = (label) => {
      if (!document.documentElement) return;
      const frame = {
        label,
        time: performance.now(),
        presentationState: document.documentElement.getAttribute('data-world-presentation-state') || null,
        legacyVisible: visible('#skill-map'),
        welcomeVisible: visible('#welcome-state'),
        e10ShellVisible: visible('#e9-adventure-shell'),
        e10StageVisible: visible('#adventure-stage'),
        e10MapVisible: visible('#e9-map-stage'),
        activeShell: document.body?.getAttribute('data-adventure-shell-active') || null,
      };
      window.__E014_WORLD_TRACE__.push(frame);
    };
    window.__E014_SAMPLE_WORLD__ = sample;
    sample('init');
    const observe = () => {
      sample('dom-ready');
      const observer = new MutationObserver(() => sample('mutation'));
      observer.observe(document.documentElement, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ['hidden', 'class', 'style', 'data-adventure-shell-active', 'data-world-presentation-state', 'aria-hidden'],
      });
      const started = performance.now();
      const raf = () => {
        sample('raf');
        if (performance.now() - started < 5000) requestAnimationFrame(raf);
      };
      requestAnimationFrame(raf);
      window.addEventListener('load', () => sample('load'), { once: true });
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', observe, { once: true });
    else observe();
  });
}

function traceSummary(trace) {
  const e9Frames = trace.filter((frame) => frame.legacyVisible);
  const e10Frames = trace.filter((frame) => frame.e10MapVisible || frame.e10StageVisible);
  return {
    firstVisibleWorld: e9Frames.length && (!e10Frames.length || e9Frames[0].time <= e10Frames[0].time) ? 'E9' : (e10Frames.length ? 'E10' : 'NEUTRAL'),
    e9VisibleFrameCount: e9Frames.length,
    firstE9Frame: e9Frames[0] || null,
    firstE10Frame: e10Frames[0] || null,
    lastFrame: trace.at(-1) || null,
    sampleCount: trace.length,
  };
}

async function waitForE10Ready(page) {
  await page.waitForFunction(() => {
    const shell = document.querySelector('#e9-adventure-shell');
    const stage = document.querySelector('#adventure-stage');
    const map = document.querySelector('#e9-map-stage');
    return document.body?.dataset.adventureShellActive === 'e9'
      && shell && !shell.hidden
      && stage && !stage.hidden
      && map && !map.hidden;
  }, null, { timeout: 15000 });
}

async function loginAndWait(page, origin) {
  await page.goto(`${origin}/login`, { waitUntil: 'domcontentloaded' });
  await page.fill('#username', 'e014_browser_tester');
  await page.fill('#password', 'test-password');
  await page.click('#login-btn');
  try {
    await page.waitForURL((url) => new URL(url).pathname === '/', { waitUntil: 'commit', timeout: 10000 });
  } catch (error) {
    const state = await page.evaluate(() => ({
      url: location.href,
      buttonDisabled: document.querySelector('#login-btn')?.disabled,
      buttonText: document.querySelector('#login-btn-text')?.textContent,
      error: document.querySelector('#login-error')?.textContent,
    }));
    throw new Error(`${error.message}; login state=${JSON.stringify(state)}`);
  }
}

async function collectTrace(page) {
  await page.waitForTimeout(500);
  return page.evaluate(() => window.__E014_WORLD_TRACE__ || []);
}

async function runE10Journey(browser, origin, viewport, label, options = {}) {
  const context = await browser.newContext({ viewport, serviceWorkers: 'block' });
  const page = await context.newPage();
  await installWorldTrace(page);
  await installApiMocks(page, 'e10', options.authDelayMs ?? 650);
  await loginAndWait(page, origin);
  await waitForE10Ready(page);
  const trace = await collectTrace(page);
  const summary = traceSummary(trace);
  assert.equal(summary.e9VisibleFrameCount, 0, `${label}: legacy E9 map was visible before E10`);
  assert.equal(summary.firstVisibleWorld, 'E10', `${label}: first visible world was ${summary.firstVisibleWorld}`);
  return { label, viewport, summary };
}

async function runReloadJourney(browser, origin) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, serviceWorkers: 'block' });
  const page = await context.newPage();
  await installWorldTrace(page);
  await installApiMocks(page, 'e10', 650);
  await loginAndWait(page, origin);
  await waitForE10Ready(page);
  await page.evaluate(() => { window.__E014_WORLD_TRACE__ = []; });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await waitForE10Ready(page);
  const summary = traceSummary(await collectTrace(page));
  assert.equal(summary.e9VisibleFrameCount, 0, 'authenticated reload: legacy E9 map was visible before E10');
  return { label: 'authenticated_reload', viewport: { width: 1366, height: 768 }, summary };
}

async function runReloginJourney(browser, origin) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, serviceWorkers: 'block' });
  const page = await context.newPage();
  await installWorldTrace(page);
  await installApiMocks(page, 'e10', 650);
  await loginAndWait(page, origin);
  await waitForE10Ready(page);
  await page.evaluate(() => { window.__E014_WORLD_TRACE__ = []; });
  await Promise.all([
    page.waitForURL((url) => new URL(url).pathname === '/login', { waitUntil: 'commit', timeout: 10000 }),
    page.evaluate(() => window.doLogout()),
  ]);
  await loginAndWait(page, origin);
  await waitForE10Ready(page);
  const summary = traceSummary(await collectTrace(page));
  assert.equal(summary.e9VisibleFrameCount, 0, 'logout/relogin: legacy E9 map was visible before E10');
  return { label: 'logout_relogin', viewport: { width: 1366, height: 768 }, summary };
}

async function runDeepLinkJourney(browser, origin) {
  const context = await browser.newContext({ viewport: { width: 1024, height: 768 }, serviceWorkers: 'block' });
  const page = await context.newPage();
  await installWorldTrace(page);
  await installApiMocks(page, 'e10', 650);
  await page.goto(`${origin}/?adventure=1&zone=k26_30&resume=1`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('#board-canvas-wrap')?.classList.contains('hidden') === false, null, { timeout: 15000 });
  const summary = traceSummary(await collectTrace(page));
  assert.equal(summary.e9VisibleFrameCount, 0, 'deep-link resume: legacy E9 map was visible before practice resumed');
  return { label: 'deep_link_resume', viewport: { width: 1024, height: 768 }, summary };
}

async function runFallbackJourney(browser, origin) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, serviceWorkers: 'block' });
  const page = await context.newPage();
  await installWorldTrace(page);
  await installApiMocks(page, 'legacy', 650);
  await loginAndWait(page, origin);
  await page.waitForFunction(() => {
    const legacy = document.querySelector('#skill-map');
    const shell = document.querySelector('#e9-adventure-shell');
    const visible = legacy && !legacy.hidden && getComputedStyle(legacy).display !== 'none' && getComputedStyle(legacy).visibility !== 'hidden';
    return visible && shell?.hidden === true && document.body?.dataset.adventureShellActive === 'legacy';
  }, null, { timeout: 15000 });
  const summary = traceSummary(await collectTrace(page));
  assert.equal(summary.firstVisibleWorld, 'E9', 'legacy fallback should still reveal the legacy Adventure map');
  return { label: 'legacy_fallback', viewport: { width: 1366, height: 768 }, summary };
}

async function runUnauthenticatedJourney(browser, origin) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: 'block' });
  const page = await context.newPage();
  await installWorldTrace(page);
  await installApiMocks(page, 'unauthenticated', 300);
  await page.goto(`${origin}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForURL((url) => new URL(url).pathname === '/login', { waitUntil: 'commit', timeout: 10000 });
  return { label: 'unauthenticated_redirect', viewport: { width: 390, height: 844 }, summary: traceSummary(await page.evaluate(() => window.__E014_WORLD_TRACE__ || [])) };
}

async function main() {
  const { server, origin } = await startStaticServer(REPO_ROOT);
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  const results = [];
  try {
    results.push(await runE10Journey(browser, origin, { width: 1366, height: 768 }, 'desktop_login'));
    results.push(await runE10Journey(browser, origin, { width: 1024, height: 768 }, 'ipad_landscape_login'));
    results.push(await runE10Journey(browser, origin, { width: 768, height: 1024 }, 'ipad_portrait_login'));
    results.push(await runE10Journey(browser, origin, { width: 390, height: 844 }, 'mobile_login'));
    results.push(await runReloadJourney(browser, origin));
    results.push(await runReloginJourney(browser, origin));
    results.push(await runDeepLinkJourney(browser, origin));
    results.push(await runFallbackJourney(browser, origin));
    results.push(await runUnauthenticatedJourney(browser, origin));
    process.stdout.write(JSON.stringify({ ok: true, results }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
