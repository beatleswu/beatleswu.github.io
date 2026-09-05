import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_CORE_PATH || 'playwright-core');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const proofPath = '/docs/evidence/w2_03_hero_right_arm_true_skeletal_weapon_vertical_proof_006/proof.html';
const evidenceDir = path.join(
  repoRoot,
  'docs',
  'evidence',
  'w2_03_hero_right_arm_true_skeletal_weapon_vertical_proof_006',
);
const viewports = [
  ['desktop', 1440, 1000],
  ['ipad-portrait', 820, 1180],
  ['mobile-portrait', 430, 932],
];

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const executable = candidates.find(candidate => fssync.existsSync(candidate));
  if (!executable) throw new Error('No Chrome/Edge executable found. Set CHROME_BIN.');
  return executable;
}

function contentTypeFor(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

async function startFixtureServer() {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url || '/', 'http://127.0.0.1');
      const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '');
      const absolute = path.resolve(repoRoot, relative);
      if (absolute !== repoRoot && !absolute.startsWith(`${repoRoot}${path.sep}`)) {
        response.writeHead(403);
        response.end('forbidden');
        return;
      }
      const stat = await fs.stat(absolute).catch(() => null);
      if (!stat?.isFile()) {
        response.writeHead(404);
        response.end('not found');
        return;
      }
      const body = await fs.readFile(absolute);
      response.writeHead(200, {
        'Content-Type': contentTypeFor(absolute),
        'Cache-Control': 'no-store',
        'Content-Length': body.length,
      });
      response.end(body);
    } catch (error) {
      response.writeHead(500);
      response.end(String(error));
    }
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address();
  return {server, origin: `http://127.0.0.1:${address.port}`};
}

async function captureSequence(page, state, frameDir, count, delayMs) {
  await page.locator(`[data-state="${state}"]`).click();
  await page.waitForTimeout(80);
  await fs.mkdir(frameDir, {recursive: true});
  for (let index = 0; index < count; index += 1) {
    await page.waitForTimeout(delayMs);
    await page.locator('.stage').screenshot({
      path: path.join(frameDir, `${String(index).padStart(3, '0')}.png`),
      animations: 'disabled',
    });
  }
}

const {server, origin} = await startFixtureServer();
const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'go-odyssey-w2-03-right-arm-006-'));
const results = [];
try {
  const browser = await chromium.launch({headless: true, executablePath: findChrome()});
  try {
    for (const [label, width, height] of viewports) {
      const page = await browser.newPage({viewport: {width, height}, deviceScaleFactor: 1});
      const errors = [];
      page.on('pageerror', error => errors.push(String(error)));
      page.on('console', message => {
        if (message.type() === 'error') errors.push(message.text());
      });
      await page.goto(`${origin}${proofPath}?viewport=${label}`, {waitUntil: 'networkidle'});
      await page.waitForFunction(() => window.__rightArmProof?.ready === true);
      const openDir = path.join(tempRoot, label, 'open');
      const gripDir = path.join(tempRoot, label, 'grip');
      await captureSequence(page, 'OPEN', openDir, 12, 120);
      await captureSequence(page, 'GRIP', gripDir, 12, 120);
      const proof = await page.evaluate(() => window.__rightArmProof);
      results.push({label, width, height, proof, errors});
      await page.close();
    }

    const debugPage = await browser.newPage({viewport: {width: 1440, height: 1000}, deviceScaleFactor: 1});
    const debugErrors = [];
    debugPage.on('pageerror', error => debugErrors.push(String(error)));
    await debugPage.goto(`${origin}${proofPath}?debug=1`, {waitUntil: 'networkidle'});
    await debugPage.waitForFunction(() => window.__rightArmProof?.ready === true);
    await debugPage.locator('[data-state="GRIP"]').click();
    await debugPage.locator('[data-action="debug"]').click();
    const debugDir = path.join(tempRoot, 'desktop-debug-slow-motion', 'grip');
    await captureSequence(debugPage, 'GRIP', debugDir, 12, 240);
    results.push({
      label: 'desktop-debug-slow-motion',
      width: 1440,
      height: 1000,
      proof: await debugPage.evaluate(() => ({...window.__rightArmProof, debug: window.__rightArmDebug === true})),
      errors: debugErrors,
    });
    await debugPage.close();
  } finally {
    await browser.close();
  }
} finally {
  server.close();
}

await fs.writeFile(
  path.join(evidenceDir, 'browser-results.json'),
  `${JSON.stringify({ok: results.every(result => result.errors.length === 0 && result.proof?.missing?.length === 0), results}, null, 2)}\n`,
  'utf8',
);
console.log(JSON.stringify({ok: true, temp_root: tempRoot, evidence_dir: evidenceDir, results}, null, 2));
