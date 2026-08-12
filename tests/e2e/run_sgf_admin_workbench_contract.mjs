import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '..', '..');
const pages = [
  ['index.html', 'main_practice'],
  ['mistakes.html', 'main_practice'],
  ['rating_test.html', 'rating_test_server'],
  ['daily_challenge.html', 'daily_challenge_client'],
  ['community.html', 'friend_challenge_client_then_server_trust'],
  ['play.html', 'friend_challenge_client_then_server_trust'],
];
const viewports = [
  { name: 'desktop', width: 1440, height: 900, hasTouch: false },
  { name: 'ipad_portrait', width: 768, height: 1024, hasTouch: true },
  { name: 'ipad_landscape', width: 1024, height: 768, hasTouch: true },
];

function chromePath() {
  const candidates = [process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].filter(Boolean);
  const found = candidates.find((candidate) => fssync.existsSync(candidate));
  if (!found) throw new Error('No Chrome/Edge executable found; set CHROME_BIN.');
  return found;
}

function contentType(file) {
  return ({ '.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8' })[path.extname(file).toLowerCase()] || 'application/octet-stream';
}

async function serverFor(root) {
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1');
    if (url.pathname.startsWith('/api/')) {
      const payload = url.pathname === '/api/auth/me'
        ? { logged_in: true, user_id: 42, username: 'contract', is_admin: true, is_premium: true }
        : url.pathname.includes('/sgf-answer-review/bootstrap')
        ? { ok: true, security: { csrf_header: 'X-SGF-Answer-Review-CSRF', csrf_token: 'contract' }, owner: {}, queue_source: { detector_signatures: { detector_ranking_changed: false } }, groups: [], states: {}, progress: null }
        : { ok: true, items: [], batches: [] };
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify(payload));
      return;
    }
    let relative = decodeURIComponent(url.pathname);
    if (relative === '/') relative = '/index.html';
    const absolute = path.resolve(root, `.${relative}`);
    if (!absolute.startsWith(root)) { response.writeHead(404); response.end(); return; }
    const stat = await fs.stat(absolute).catch(() => null);
    if (!stat?.isFile()) { response.writeHead(404); response.end(); return; }
    response.writeHead(200, { 'Content-Type': contentType(absolute) });
    fssync.createReadStream(absolute).pipe(response);
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

const { server, origin } = await serverFor(repoRoot);
const browser = await chromium.launch({ headless: true, executablePath: chromePath() });
const failures = [];
try {
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport, hasTouch: viewport.hasTouch, isMobile: viewport.hasTouch });
    const page = await context.newPage();
    page.on('pageerror', () => {}); // Some standalone pages expect app APIs; contract checks remain deterministic.
    for (const [file, surface] of pages) {
      await page.goto(`${origin}/${file}`, { waitUntil: 'domcontentloaded' });
      const result = await page.evaluate((expected) => {
        const body = document.body;
        const trigger = document.querySelector('.sgf-report-trigger');
        const rect = trigger?.getBoundingClientRect();
        return {
          surface: body?.dataset.sgfReportSurface,
          widget: Boolean(trigger),
          touchTarget: Boolean(rect && rect.width >= 44 && rect.height >= 44),
          horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
          expected,
        };
      }, surface);
      if (result.surface !== surface) failures.push(`${viewport.name}/${file}: surface marker`);
      if (!result.widget) failures.push(`${viewport.name}/${file}: widget missing`);
      if (!result.touchTarget) failures.push(`${viewport.name}/${file}: touch target`);
      if (result.horizontalOverflow) failures.push(`${viewport.name}/${file}: horizontal overflow`);
    }
    await page.goto(`${origin}/sgf_answer_review.html`, { waitUntil: 'domcontentloaded' });
    const review = await page.evaluate(() => ({ panel: Boolean(document.querySelector('#unified-workbench-panel')), filters: Boolean(document.querySelector('#workbench-source-filter')), contract: document.body?.dataset?.responsiveContract || '' }));
    if (!review.panel || !review.filters) failures.push(`${viewport.name}/review: unified panel missing`);
    if (!review.contract.includes('ipad-768x1024')) failures.push(`${viewport.name}/review: responsive contract missing`);
    await context.close();
  }
} finally {
  await browser.close();
  server.close();
}
if (failures.length) throw new Error(failures.join('; '));
console.log('SGF admin workbench browser contract PASS: desktop, iPad portrait, iPad landscape');
