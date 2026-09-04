import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const fixturePath = path.join(__dirname, 'fixtures', 'w2_04_website_ux_navigation.html');
const require = createRequire(import.meta.url);

let playwright;
try {
  playwright = require('playwright-core');
} catch {
  playwright = require(path.resolve(repoRoot, '..', '..', 'go-website', 'node_modules', 'playwright-core'));
}
const { chromium } = playwright;

const NAV_ROUTES = [
  '/', '/curriculum', '/mistakes', '/stats', '/community', '/hero',
  '/inventory', '/badges', '/rating_test', '/play', '/shop', '/upgrade',
];

const VIEWPORTS = [
  { name: 'desktop', width: 1366, height: 768, mobileRail: false },
  { name: 'ipad-landscape', width: 1024, height: 768, mobileRail: false },
  { name: 'ipad-portrait', width: 768, height: 1024, mobileRail: true },
  { name: 'mobile-portrait', width: 390, height: 844, mobileRail: true },
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
  }[ext] || 'text/plain; charset=utf-8';
}

async function startServer() {
  const fixture = await fs.readFile(fixturePath);
  const server = http.createServer(async (request, response) => {
    const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
    let filePath;
    if (pathname === '/' || NAV_ROUTES.includes(pathname) || pathname === '/w2-04-fixture.html') {
      filePath = fixturePath;
    } else if (pathname === '/mobile-nav.js' || pathname === '/i18n.js') {
      filePath = path.join(repoRoot, pathname.slice(1));
    }
    if (!filePath) {
      response.writeHead(404);
      response.end('not found');
      return;
    }
    const body = filePath === fixturePath ? fixture : await fs.readFile(filePath);
    response.writeHead(200, { 'Content-Type': contentType(filePath) });
    response.end(body);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  return { server, origin: `http://127.0.0.1:${port}` };
}

async function inspectRail(page) {
  return page.evaluate(() => {
    const nav = document.querySelector('#mobile-nav');
    const links = [...document.querySelectorAll('#mobile-nav .mnb')];
    const style = nav ? getComputedStyle(nav) : null;
    const rect = nav?.getBoundingClientRect();
    const bodyOverflow = document.documentElement.scrollWidth > window.innerWidth;
    const visibleLinks = links.filter(link => {
      const box = link.getBoundingClientRect();
      const centerX = box.left + box.width / 2;
      return centerX >= 0 && centerX <= window.innerWidth && box.bottom > 0 && box.top < window.innerHeight;
    });
    const centersClear = visibleLinks.every(link => {
      const box = link.getBoundingClientRect();
      if (!box.width || !box.height) return false;
      return document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2) === link
        || link.contains(document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2));
    });
    return {
      ariaLabel: nav?.getAttribute('aria-label'),
      hrefs: links.map(link => link.getAttribute('href')),
      activeCount: links.filter(link => link.getAttribute('aria-current') === 'page').length,
      display: style?.display,
      rect: rect ? { width: rect.width, height: rect.height } : null,
      scrollable: Boolean(nav && nav.scrollWidth > nav.clientWidth),
      bodyOverflow,
      centersClear,
    };
  });
}

async function runViewport(browser, origin, spec) {
  const context = await browser.newContext({
    viewport: { width: spec.width, height: spec.height },
    hasTouch: spec.name.includes('ipad') || spec.name.includes('mobile'),
    isMobile: spec.name.includes('ipad') || spec.name.includes('mobile'),
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  const failures = [];
  try {
    await page.goto(`${origin}/`, { waitUntil: 'networkidle' });
    await page.waitForSelector('#mobile-nav .mnb', { state: 'attached' });
    const initial = await inspectRail(page);
    if (initial.hrefs.length !== NAV_ROUTES.length) failures.push('wrong mobile destination count');
    if (JSON.stringify(initial.hrefs) !== JSON.stringify(NAV_ROUTES)) failures.push('mobile destinations differ from contract');
    if (initial.activeCount !== 1) failures.push('exactly one current-page destination is required');
    if (!initial.ariaLabel) failures.push('mobile rail lacks an accessible label');
    if (initial.bodyOverflow) failures.push('page has horizontal overflow');
    if (spec.mobileRail) {
      if (initial.display !== 'flex') failures.push('mobile rail is not visible');
      if (!initial.scrollable) failures.push('mobile rail does not expose overflow destinations');
      if (!initial.centersClear) failures.push('mobile rail item is intercepted at its center');
    } else if (initial.display !== 'none') {
      failures.push('mobile rail should stay hidden outside mobile breakpoint');
    }

    if (!spec.mobileRail) {
      const desktopCommunity = page.locator('header a[href="/community"]');
      if (!await desktopCommunity.isVisible()) failures.push('desktop navigation is not visible');
      await desktopCommunity.click();
      if (!page.url().endsWith('/community')) failures.push('desktop navigation did not transition');
      await page.goBack({ waitUntil: 'networkidle' });
    }

    await page.evaluate(() => I18n.setLang('en'));
    const englishLabel = await page.locator('#mobile-nav').getAttribute('aria-label');
    const englishShop = await page.locator('#mobile-nav a[href="/shop"] span').last().innerText();
    if (englishLabel !== 'Main navigation' || englishShop !== 'Shop') failures.push('English labels did not switch');
    await page.evaluate(() => I18n.setLang('zh'));
    const chineseShop = await page.locator('#mobile-nav a[href="/shop"] span').last().innerText();
    if (chineseShop !== '商店') failures.push('Chinese labels did not switch back');

    if (spec.mobileRail) {
      const focusProbe = await page.evaluate(() => {
        const link = document.querySelector('#mobile-nav a[href="/shop"]');
        link.focus({ focusVisible: true });
        const style = getComputedStyle(link);
        return { focused: document.activeElement === link, outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
      });
      if (!focusProbe.focused || focusProbe.outlineStyle === 'none' || focusProbe.outlineWidth === '0px') {
        failures.push('keyboard focus is not visibly represented');
      }
    }

    await page.locator('#primary-cta').click();
    if (!page.url().endsWith('/curriculum')) failures.push('primary CTA did not transition to Learn/Guild');
    await page.goBack({ waitUntil: 'networkidle' });
    if (!page.url().endsWith('/')) failures.push('browser back did not return to Lobby');

    if (spec.mobileRail) {
      const shop = page.locator('#mobile-nav a[href="/shop"]');
      await shop.scrollIntoViewIfNeeded();
      await shop.click();
      if (!page.url().endsWith('/shop')) failures.push('mobile Shop destination did not transition');
      const activeShop = await page.locator('#mobile-nav a[href="/shop"]').getAttribute('aria-current');
      if (activeShop !== 'page') failures.push('Shop route did not set current-page semantics');
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
    process.stdout.write(JSON.stringify({ ok: true, viewports: results }, null, 2));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
