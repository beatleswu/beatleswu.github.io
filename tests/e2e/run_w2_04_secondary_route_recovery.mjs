import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const require = createRequire(import.meta.url);

let playwright;
try {
  playwright = require('playwright-core');
} catch {
  playwright = require(path.resolve(repoRoot, '..', '..', 'go-website', 'node_modules', 'playwright-core'));
}
const { chromium } = playwright;

const weeklyPagePath = path.join(repoRoot, 'premium_weekly.html');
const VIEWPORTS = [
  { name: 'desktop', width: 1366, height: 768, mobileRail: false },
  { name: 'ipad-landscape', width: 1024, height: 768, mobileRail: false },
  { name: 'ipad-portrait', width: 768, height: 1024, mobileRail: true },
  { name: 'mobile-portrait', width: 390, height: 844, mobileRail: true },
];
const NAV_ROUTES = [
  '/', '/curriculum', '/mistakes', '/stats', '/community', '/hero',
  '/inventory', '/badges', '/rating_test', '/play', '/shop', '/upgrade',
];

function findChrome() {
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
  throw new Error('No Chromium executable found; set CHROME_BIN.');
}

function contentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.webp': 'image/webp',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
  }[ext] || 'text/plain; charset=utf-8';
}

function htmlPage(id, title) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${title}</title></head><body><main id="${id}"><h1>${title}</h1></main></body></html>`;
}

async function startServer() {
  const weeklyPage = await fs.readFile(weeklyPagePath);
  const assets = new Map([
    ['/i18n.js', path.join(repoRoot, 'i18n.js')],
    ['/site-nav.js', path.join(repoRoot, 'site-nav.js')],
    ['/mobile-nav.js', path.join(repoRoot, 'mobile-nav.js')],
  ]);
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1');
    const pathname = url.pathname;
    if (pathname.startsWith('/api/')) {
      let payload = {};
      if (pathname === '/api/auth/me') {
        payload = { logged_in: true, is_admin: false, has_email: false, email_verified: true };
      } else if (pathname === '/api/premium/weekly/reports') {
        payload = { reports: [] };
      }
      response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      response.end(JSON.stringify(payload));
      return;
    }
    if (pathname === '/') {
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      response.end(htmlPage('home-sentinel', 'Lobby'));
      return;
    }
    if (pathname === '/upgrade') {
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      response.end(htmlPage('upgrade-sentinel', 'Pass'));
      return;
    }
    if (pathname === '/premium/weekly' || pathname === '/premium_weekly.html') {
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      response.end(weeklyPage);
      return;
    }
    const filePath = assets.get(pathname);
    if (filePath) {
      try {
        const body = await fs.readFile(filePath);
        response.writeHead(200, { 'Content-Type': contentType(filePath) });
        response.end(body);
      } catch {
        response.writeHead(404);
        response.end('not found');
      }
      return;
    }
    if (pathname.startsWith('/assets/')) {
      const assetsRoot = path.resolve(repoRoot, 'assets');
      const candidate = path.resolve(repoRoot, pathname.slice(1));
      if (candidate.startsWith(`${assetsRoot}${path.sep}`)) {
        try {
          const body = await fs.readFile(candidate);
          response.writeHead(200, { 'Content-Type': contentType(candidate) });
          response.end(body);
          return;
        } catch {
          // The visual asset is not part of this navigation contract.
        }
      }
    }
    response.writeHead(404);
    response.end('not found');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  return { server, origin: `http://127.0.0.1:${port}` };
}

async function waitForWeeklyShell(page) {
  await page.waitForSelector('header.cg-nav .cg-brand', { state: 'visible' });
  await page.waitForSelector('#mobile-nav .mnb', { state: 'attached' });
}

async function inspectNavigation(page) {
  return page.evaluate((navRoutes) => {
    const header = document.querySelector('header.cg-nav');
    const rail = document.querySelector('#mobile-nav');
    const headerLinks = [...document.querySelectorAll('header.cg-nav a[href]')];
    const railLinks = [...document.querySelectorAll('#mobile-nav a[href]')];
    const railStyle = rail ? getComputedStyle(rail) : null;
    const focusTarget = document.activeElement;
    const focusStyle = focusTarget ? getComputedStyle(focusTarget) : null;
    return {
      headerVisible: Boolean(header && getComputedStyle(header).display !== 'none'),
      brandHref: header?.querySelector('.cg-brand')?.getAttribute('href'),
      parentHref: header?.querySelector('a[href="/upgrade"]')?.getAttribute('href'),
      headerHrefs: headerLinks.map(link => link.getAttribute('href')),
      railHrefs: railLinks.map(link => link.getAttribute('href')),
      railDisplay: railStyle?.display,
      railAriaLabel: rail?.getAttribute('aria-label'),
      headerCurrentCount: document.querySelectorAll('header.cg-nav a[aria-current="page"]').length,
      railCurrentCount: document.querySelectorAll('#mobile-nav a[aria-current="page"]').length,
      focusTag: focusTarget?.tagName || null,
      focusOutline: focusStyle ? { style: focusStyle.outlineStyle, width: focusStyle.outlineWidth } : null,
      knownRailRoutes: railLinks.every(link => navRoutes.includes(link.getAttribute('href'))),
      bodyOverflow: document.documentElement.scrollWidth > window.innerWidth,
    };
  }, NAV_ROUTES);
}

async function checkLocale(page, lang, expected) {
  await page.evaluate((value) => {
    localStorage.setItem('cgo_lang', value);
  }, lang);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await waitForWeeklyShell(page);
  await page.waitForFunction((value) => document.documentElement.lang === value, expected.documentLang);
  const state = await page.evaluate(() => ({
    documentLang: document.documentElement.lang,
    navAria: document.querySelector('header.cg-nav .cg-nav-links')?.getAttribute('aria-label'),
    brandText: document.querySelector('header.cg-nav .cg-brand-text')?.textContent?.trim(),
    mobilePractice: document.querySelector('#mobile-nav a[href="/"]')?.textContent?.trim(),
  }));
  if (state.documentLang !== expected.documentLang) throw new Error(`locale ${lang}: document language mismatch`);
  if (state.navAria !== expected.navAria) throw new Error(`locale ${lang}: navigation aria label mismatch`);
  if (state.brandText !== expected.brandText) throw new Error(`locale ${lang}: brand label mismatch`);
  if (!state.mobilePractice || (lang === 'en' ? !state.mobilePractice.includes('Lobby') : !state.mobilePractice.includes('大廳'))) {
    throw new Error(`locale ${lang}: mobile home label mismatch`);
  }
}

async function runViewport(browser, origin, spec) {
  const context = await browser.newContext({
    viewport: { width: spec.width, height: spec.height },
    hasTouch: spec.name.includes('ipad') || spec.name.includes('mobile'),
    isMobile: spec.name.includes('ipad') || spec.name.includes('mobile'),
    serviceWorkers: 'block',
  });
  await context.addInitScript(() => {
    if (!localStorage.getItem('cgo_lang')) localStorage.setItem('cgo_lang', 'zh');
  });
  const page = await context.newPage();
  const failures = [];
  try {
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/auth/me') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ logged_in: true, is_admin: false, has_email: false, email_verified: true }) });
      } else if (url.pathname === '/api/premium/weekly/reports') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ reports: [] }) });
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
      }
    });
    await page.route('https://cdn.socket.io/**', route => route.abort());
    await page.goto(`${origin}/premium/weekly`, { waitUntil: 'domcontentloaded' });
    await waitForWeeklyShell(page);

    let state = await inspectNavigation(page);
    if (!state.headerVisible) failures.push('shared recovery header is not visible');
    if (state.brandHref !== '/') failures.push('weekly route has no Home recovery destination');
    if (state.parentHref !== '/upgrade') failures.push('weekly route has no valid parent Pass destination');
    if (JSON.stringify(state.railHrefs) !== JSON.stringify(NAV_ROUTES)) failures.push('weekly route mobile destinations differ from shared contract');
    if (!state.knownRailRoutes) failures.push('weekly route mobile rail contains an unknown destination');
    if (!state.railAriaLabel) failures.push('weekly route mobile rail lacks an accessible label');
    if (state.headerCurrentCount !== 0 || state.railCurrentCount !== 0) failures.push('secondary weekly route reports a misleading current primary destination');
    if (state.bodyOverflow) failures.push('weekly route has page-wide horizontal overflow');
    if (spec.mobileRail && state.railDisplay !== 'flex') failures.push('mobile recovery rail is not visible');
    if (!spec.mobileRail && state.railDisplay !== 'none') failures.push('mobile recovery rail should be hidden outside mobile breakpoint');

    await page.locator('header.cg-nav .cg-brand').click();
    await page.waitForURL(url => new URL(url).pathname === '/');
    if (!await page.locator('#home-sentinel').isVisible()) failures.push('Home recovery destination did not load');
    await page.goBack({ waitUntil: 'domcontentloaded' });
    await waitForWeeklyShell(page);

    if (!spec.mobileRail) {
      await page.locator('header.cg-nav a[href="/upgrade"]').click();
      await page.waitForURL(url => new URL(url).pathname === '/upgrade');
      if (!await page.locator('#upgrade-sentinel').isVisible()) failures.push('parent Pass destination did not load');
      await page.goBack({ waitUntil: 'domcontentloaded' });
      await waitForWeeklyShell(page);
    }

    const focusTarget = page.locator('header.cg-nav .cg-brand');
    await focusTarget.focus();
    await page.keyboard.press('Tab');
    state = await inspectNavigation(page);
    if (state.focusTag !== 'A' || state.focusOutline?.style === 'none' || state.focusOutline?.width === '0px') {
      failures.push('keyboard focus is not visibly represented on the recovery navigation');
    }

    if (spec.name === 'desktop') {
      const english = page.waitForNavigation({ waitUntil: 'domcontentloaded' });
      await page.locator('.i18n-switcher-btn[data-lang="en"]').click();
      await english;
      await waitForWeeklyShell(page);
      await checkLocale(page, 'zh', { documentLang: 'zh-TW', navAria: '主要導覽', brandText: '弈境奇兵 (Go Odyssey)' });
      await checkLocale(page, 'en', { documentLang: 'en', navAria: 'Main navigation', brandText: 'Go Odyssey' });
    }
  } finally {
    await context.close();
  }
  return { name: spec.name, viewport: { width: spec.width, height: spec.height }, failures };
}

async function main() {
  const { server, origin } = await startServer();
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  try {
    const results = [];
    for (const spec of VIEWPORTS) results.push(await runViewport(browser, origin, spec));
    const failures = results.flatMap(result => result.failures.map(failure => `${result.name}: ${failure}`));
    if (failures.length) throw new Error(failures.join('\n'));
    process.stdout.write(JSON.stringify({ ok: true, issue: { before: 1, after: 0 }, viewports: results }, null, 2));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
