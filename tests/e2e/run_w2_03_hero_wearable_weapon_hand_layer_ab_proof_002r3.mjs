import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_CORE_PATH || 'playwright-core');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const reviewPath = '/docs/planning/w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3.html';
const evidenceDir = path.resolve(
  process.env.W2_03_AB_EVIDENCE_DIR
    || path.join(repoRoot, 'tests', 'e2e', 'evidence', 'w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3'),
);

const viewports = [
  ['desktop', 1440, 1000],
  ['ipad-portrait', 820, 1180],
  ['mobile-portrait', 430, 932],
];

function contentTypeFor(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
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
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

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

async function inspectStage(page, selector) {
  return page.evaluate((stageSelector) => {
    const stage = document.querySelector(stageSelector);
    const images = [...(stage?.querySelectorAll('img') || [])];
    const weapon = images.find(image => image.src.endsWith('/wooden_sword.png'));
    const base = images.find(image => image.classList.contains('character-base'));
    return {
      supported: stage?.dataset.supported || '',
      presentationState: stage?.dataset.presentationState || '',
      order: images.map(image => image.className),
      sources: images.map(image => image.getAttribute('src')),
      baseIndex: base ? images.indexOf(base) : -1,
      weaponIndex: weapon ? images.indexOf(weapon) : -1,
      weaponMode: weapon?.dataset.presentationMode || '',
      weaponLayer: weapon?.dataset.presentationLayer || '',
      weaponVariant: weapon?.dataset.presentationVariant || '',
      weaponOcclusion: weapon?.dataset.presentationOcclusion || '',
      weaponTransform: weapon ? getComputedStyle(weapon).transform : '',
      weaponNaturalWidth: weapon?.naturalWidth || 0,
      weaponNaturalHeight: weapon?.naturalHeight || 0,
    };
  }, selector);
}

async function run() {
  await fs.mkdir(evidenceDir, { recursive: true });
  const { server, origin } = await startFixtureServer();
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  const results = [];
  try {
    for (const [viewportName, width, height] of viewports) {
      const context = await browser.newContext({
        viewport: { width, height },
        deviceScaleFactor: 2,
        locale: 'en-US',
        serviceWorkers: 'block',
      });
      const page = await context.newPage();
      const pageErrors = [];
      page.on('pageerror', error => pageErrors.push(error.message));
      await page.goto(`${origin}${reviewPath}?viewport=${viewportName}`, { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => document.documentElement.dataset.proofReady === 'yes', null, { timeout: 15000 });
      await page.waitForFunction(() => [...document.querySelectorAll('.proof-stage img')]
        .every(image => image.complete && image.naturalWidth > 0), null, { timeout: 15000 });

      const a = await inspectStage(page, '#stage-a');
      const b = await inspectStage(page, '#stage-b');
      assert.equal(a.weaponMode, 'CARRIED_AT_HIP', `${viewportName} A keeps R2 mode`);
      assert.equal(a.weaponLayer, 'BACK_WEAPON', `${viewportName} A keeps back layer`);
      assert.equal(a.weaponVariant, '', `${viewportName} A has no review variant`);
      assert.equal(a.weaponOcclusion, 'BACK_WEAPON', `${viewportName} A keeps back occlusion`);
      assert.ok(a.weaponIndex >= 0 && a.baseIndex >= 0 && a.weaponIndex < a.baseIndex,
        `${viewportName} A weapon remains behind base`);
      assert.match(a.weaponTransform, /matrix\(/, `${viewportName} A has bounded transform`);

      assert.equal(b.weaponMode, 'FRONT_WEAPON_HAND_ALIGNED', `${viewportName} B mode`);
      assert.equal(b.weaponLayer, 'FRONT_WEAPON', `${viewportName} B front layer`);
      assert.equal(b.weaponVariant, 'FRONT_WEAPON_HAND_ALIGNED', `${viewportName} B review variant`);
      assert.equal(b.weaponOcclusion, 'FRONT_WEAPON', `${viewportName} B occlusion`);
      assert.ok(b.weaponIndex >= 0 && b.baseIndex >= 0 && b.weaponIndex > b.baseIndex,
        `${viewportName} B weapon is in front of base`);
      assert.match(b.weaponTransform, /matrix\(/, `${viewportName} B has bounded transform`);
      assert.equal(a.weaponNaturalWidth, b.weaponNaturalWidth, `${viewportName} reuses sword art`);
      assert.equal(a.weaponNaturalHeight, b.weaponNaturalHeight, `${viewportName} reuses sword art`);
      assert.deepEqual(pageErrors, [], `${viewportName} page errors`);

      const fullPath = path.join(evidenceDir, `${viewportName}-ab.png`);
      const closePath = path.join(evidenceDir, `${viewportName}-right-hand-closeup.png`);
      await page.locator('.ab-grid').screenshot({ path: fullPath, animations: 'disabled' });
      await page.locator('.closeup-grid').screenshot({ path: closePath, animations: 'disabled' });
      results.push({ viewport: viewportName, width, height, variantA: a, variantB: b, fullPath, closePath });
      await context.close();
    }
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
  await fs.writeFile(path.join(evidenceDir, 'browser-results.json'), JSON.stringify(results, null, 2));
  console.log(`W2_03_AB_EVIDENCE_DIR=${evidenceDir}`);
  console.log('W2_03_WEAPON_HAND_LAYER_AB_PROOF=PASS');
  console.log(`W2_03_WEAPON_HAND_LAYER_AB_VIEWPORT_COUNT=${results.length}`);
  console.log('OWNER_SELECTION_REQUIRED=YES');
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
