import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');

function loadPlaywright() {
  const require = createRequire(import.meta.url);
  const candidates = [
    process.env.E10_PLAYWRIGHT_CORE,
    process.env.PLAYWRIGHT_CORE_PATH,
    path.join(repoRoot, 'node_modules', 'playwright-core'),
    'C:/Users/beatl/AppData/Local/OpenAI/Codex/runtimes/cua_node/8e7585fc8f35ed57/bin/node_modules/playwright-core',
    'playwright-core',
  ].filter(Boolean);
  let lastError = null;
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(`playwright-core unavailable: ${lastError?.message || 'unknown error'}`);
}

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const executable = candidates.find((candidate) => fs.existsSync(candidate));
  if (!executable) throw new Error('Chromium/Chrome executable unavailable');
  return executable;
}

function contentType(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.webp': 'image/webp',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

function createStaticServer(root) {
  return http.createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    const relative = pathname === '/' ? 'tests/e2e/fixtures/w2_01_zone4_vertical_slice.html' : pathname.slice(1);
    const filePath = path.resolve(root, relative);
    if (filePath !== root && !filePath.startsWith(`${root}${path.sep}`)) {
      response.writeHead(403);
      response.end('forbidden');
      return;
    }
    fs.readFile(filePath, (error, data) => {
      if (error) {
        response.writeHead(error.code === 'ENOENT' ? 404 : 500);
        response.end(error.code || 'error');
        return;
      }
      response.writeHead(200, { 'Content-Type': contentType(filePath), 'Cache-Control': 'no-store' });
      response.end(data);
    });
  });
}

const { chromium } = loadPlaywright();
const executablePath = findChrome();
const server = createStaticServer(repoRoot);
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'go-odyssey-w2-01-zone4-'));
const viewports = [
  { name: 'desktop', width: 1440, height: 900, locale: 'zh-TW', reducedMotion: false },
  { name: 'ipad-landscape', width: 1180, height: 820, locale: 'zh-TW', reducedMotion: false },
  { name: 'ipad-portrait', width: 820, height: 1180, locale: 'zh-TW', reducedMotion: true },
  { name: 'mobile-portrait', width: 390, height: 844, locale: 'zh-TW', reducedMotion: false },
  { name: 'desktop-en-us', width: 1440, height: 900, locale: 'en-US', reducedMotion: false },
  { name: 'mobile-en-us', width: 390, height: 844, locale: 'en-US', reducedMotion: true },
];

let port;
let browser;
const results = [];
try {
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  port = server.address().port;
  browser = await chromium.launch({ headless: true, executablePath });

  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      locale: viewport.locale,
      reducedMotion: viewport.reducedMotion ? 'reduce' : 'no-preference',
    });
    const page = await context.newPage();
    const errors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(`console: ${message.text()}`);
    });
    page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
    page.on('requestfailed', (request) => errors.push(`requestfailed: ${request.url()}`));

    await page.goto(`http://127.0.0.1:${port}/?locale=${encodeURIComponent(viewport.locale)}`, { waitUntil: 'networkidle' });
    await page.locator('html[data-zone4-fixture-ready="true"]').waitFor();
    const root = page.locator('[data-zone4-vertical-slice]');
    await root.waitFor();

    assert.equal(await root.getAttribute('data-zone4-locale'), viewport.locale);
    assert.equal(await root.getAttribute('data-zone4-shot'), 'Z4_S01');
    assert.equal(await root.getAttribute('data-zone4-presentation-only'), 'true');
    assert.equal(await root.getAttribute('data-zone4-gameplay-mutation'), 'false');
    assert.equal(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches), viewport.reducedMotion);

    const bounds = await root.boundingBox();
    assert.ok(bounds && bounds.width <= viewport.width + 1, `${viewport.name} overflows horizontally`);
    assert.ok(bounds && bounds.height <= viewport.height + 1, `${viewport.name} overflows vertically`);
    assert.equal(await root.locator('[data-zone4-action="previous"]').isDisabled(), true);
    assert.equal(await root.locator('[data-zone4-action="replay"]').isVisible(), true);
    assert.equal(await root.locator('[data-zone4-image]').evaluate((image) => image.complete && image.naturalWidth > 0), true);

    await root.locator('[data-zone4-action="next"]').click();
    assert.equal(await root.getAttribute('data-zone4-shot'), 'Z4_S02');
    if (viewport.locale === 'zh-TW') {
      assert.equal(await root.locator('[data-zone4-line]').textContent(), '奇怪……我們剛才，是從哪邊進來的？');
      assert.equal(await root.getAttribute('data-zone4-dialogue-state'), 'localized');
    } else {
      assert.equal(await root.getAttribute('data-zone4-dialogue-state'), 'translation-pending');
      assert.equal(await root.locator('[data-zone4-line]').textContent(), 'Approved dialogue translation is not available');
      assert.doesNotMatch(await root.textContent(), /奇怪|哪一個|小水/);
    }

    await root.locator('[data-zone4-action="next"]').focus();
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('data-zone4-action')), 'next');
    await page.keyboard.press('Enter');
    assert.equal(await root.getAttribute('data-zone4-shot'), 'Z4_S03');

    for (let index = 3; index < 7; index += 1) {
      await root.locator('[data-zone4-action="next"]').click();
      assert.equal(await root.getAttribute('data-zone4-shot'), `Z4_S${String(index + 1).padStart(2, '0')}`);
    }
    assert.equal(await root.getAttribute('data-zone4-shot'), 'Z4_S07');
    assert.ok(await root.locator('[data-zone4-handoff]').isVisible());
    assert.equal(await root.locator('[data-zone4-image]').isHidden(), true);

    await root.locator('[data-zone4-action="replay"]').click();
    assert.equal(await root.getAttribute('data-zone4-shot'), 'Z4_S01');
    assert.equal(await root.getAttribute('data-zone4-replay-count'), '1');
    const snapshot = await page.evaluate(() => window.__w2Zone4Slice.snapshot());
    assert.deepEqual(snapshot, {
      contractVersion: 'W2_01_ZONE4_MISTY_FOREST_VERTICAL_SLICE_V1',
      zoneKey: 'k11_15',
      locale: viewport.locale,
      shotId: 'Z4_S01',
      phase: 'PRE_PLAY',
      replayCount: 1,
      presentationOnly: true,
      gameplayMutation: false,
    });

    await page.screenshot({ path: path.join(tempDir, `${viewport.name}.png`), fullPage: true });
    assert.deepEqual(errors, [], `${viewport.name} browser diagnostics: ${errors.join('; ')}`);
    results.push({ name: viewport.name, status: 'PASS' });
    await context.close();
  }
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.close(resolve));
  fs.rmSync(tempDir, { recursive: true, force: true });
}

console.log(JSON.stringify({
  contract: 'W2-01_ZONE4_MISTY_FOREST_VERTICAL_SLICE',
  viewportResults: results,
  browser: 'Chromium',
  screenshots: 'created-and-removed-from-temp-directory',
}, null, 2));
