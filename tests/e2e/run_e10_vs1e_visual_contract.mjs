import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const shellFlags = 'E9_DEBUG=1&e9Shell=1&e9TopHud=1&e9LeftNav=1&e9RightCards=1&e9BottomDock=1&e9WorldStage=1';

const zones = [
  ['k26_30', '圍棋新手村', 'Beginner Village', 'completed', false, true, 3, 30, 30],
  ['k21_25', '史萊姆平原', 'Slime Plains', 'unlocked', false, false, 1, 18, 25],
  ['k16_20', '哥布林洞穴', 'Goblin Cave', 'unlocked', false, false, 0, 12, 20],
  ['k11_15', '暮光森林', 'Twilight Forest', 'locked', true, false, 0, 0, 20],
  ['k6_10', '天空之塔', 'Sky Tower', 'locked', true, false, 0, 0, 20],
  ['k1_5', '王者城堡', 'Royal Castle', 'unlocked', false, false, 0, 8, 20],
  ['d1_2', '星海迴廊', 'Star Sea Passage', 'locked', true, false, 0, 0, 20],
  ['d3_4', '深淵熔爐', 'Abyssal Forge', 'locked', true, false, 0, 0, 20],
  ['d5_6', '永夜聖殿', 'Eternal Night Shrine', 'locked', true, false, 0, 0, 20],
  ['d7_plus', '上古終焉神殿', 'Ancient Doom Temple', 'locked', true, false, 0, 0, 20],
].map(([key, name, name_en, status, locked, cleared, stars, seen, total]) => ({
  key,
  label: name,
  name,
  name_en,
  icon: 'zone',
  status,
  locked,
  can_enter: !locked,
  cleared,
  completed: cleared,
  stars,
  seen,
  total,
  boss: { available: !locked && !cleared },
}));

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const executable = candidates.find((candidate) => fssync.existsSync(candidate));
  if (!executable) throw new Error('No Chrome/Edge executable found.');
  return executable;
}

function contentTypeFor(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

async function startStaticServer() {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://127.0.0.1');
      const relative = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname);
      const absolute = path.resolve(repoRoot, `.${relative}`);
      if (!absolute.startsWith(repoRoot)) throw new Error('path outside repository');
      const stat = await fs.stat(absolute).catch(() => null);
      if (!stat?.isFile()) {
        response.writeHead(404);
        response.end('not found');
        return;
      }
      response.writeHead(200, { 'Content-Type': contentTypeFor(absolute) });
      fssync.createReadStream(absolute).pipe(response);
    } catch (error) {
      response.writeHead(500);
      response.end(String(error));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

function apiResponse(pathname, method) {
  if (pathname === '/api/auth/me') {
    return {
      logged_in: true,
      user_id: 42,
      username: 'visual_fixture',
      nickname: '晨星騎士',
      display_name: '晨星騎士',
      is_admin: false,
      is_premium: false,
      needs_onboarding_choice: false,
      tour_done: true,
      elo_rating: 1450,
      newbie_quest_eligible: false,
    };
  }
  if (pathname === '/api/skills/profile') return { display_name: '晨星騎士', rank_level: 'LV12' };
  if (pathname === '/api/user/coins') return { coins: 123456 };
  if (pathname === '/api/adventure/bootstrap') return { zones };
  if (pathname === '/api/daily-challenge/today') return { submitted: false };
  if (pathname === '/api/srs/due') return { count: 17, due: [] };
  if (pathname === '/api/mistakes/stats') return { total: 28, corrected: 9, worst5: [] };
  if (pathname === '/api/questions') return [];
  if (pathname === '/api/subscription/status') return { daily_limit: 20, remaining: 10 };
  if (pathname === '/api/analytics/events' || method === 'POST') return null;
  return { ok: true };
}

async function installApiFixture(page, browserErrors) {
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors.push({ kind: 'console', text: message.text() });
  });
  page.on('pageerror', (error) => browserErrors.push({ kind: 'pageerror', text: String(error) }));
  page.on('requestfailed', (request) => {
    browserErrors.push({ kind: 'requestfailed', text: `${request.method()} ${request.url()}` });
  });
  page.on('response', (response) => {
    if (response.status() >= 500) {
      browserErrors.push({ kind: 'http5xx', text: `${response.status()} ${response.url()}` });
    }
  });
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const payload = apiResponse(new URL(request.url()).pathname, request.method());
    await route.fulfill(payload === null
      ? { status: 204, body: '' }
      : { status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
  });
}

async function waitForShell(page) {
  await page.locator('#e9-adventure-shell[data-e10-visual-skin="immersive-rpg"]').waitFor({ state: 'visible' });
  await page.locator('#e9-world-stage-zones [data-zone="k26_30"]').waitFor({ state: 'visible' });
  const count = await page.locator('#e9-world-stage-zones [data-zone]').count();
  if (count !== 10) throw new Error(`expected 10 World Stage nodes, got ${count}`);
}

async function runtimeSnapshot(page) {
  return page.evaluate(() => {
    const roundRect = (value) => value && Object.fromEntries(
      ['x', 'y', 'width', 'height', 'top', 'right', 'bottom', 'left']
        .map((key) => [key, Math.round(value[key] * 100) / 100])
    );
    const rect = (selector) => {
      const element = document.querySelector(selector);
      return element ? element.getBoundingClientRect().toJSON() : null;
    };
    const allTargets = Array.from(document.querySelectorAll(
      '#e9-adventure-shell a[href], #e9-adventure-shell button:not([disabled])'
    )).filter((element) => {
      const style = getComputedStyle(element);
      const target = element.getBoundingClientRect();
      return !element.hidden && style.display !== 'none' && style.visibility !== 'hidden'
        && target.width > 0 && target.height > 0;
    });
    const duplicateIds = Array.from(document.querySelectorAll('[id]'))
      .map((element) => element.id)
      .filter((id, index, ids) => ids.indexOf(id) !== index);
    return {
      activeShell: document.body.getAttribute('data-adventure-shell-active'),
      skin: document.body.getAttribute('data-e10-visual-skin'),
      shellSkin: document.querySelector('#e9-adventure-shell')?.getAttribute('data-e10-visual-skin'),
      lang: window.I18n?.getLang?.(),
      nodeCount: document.querySelectorAll('#e9-world-stage-zones [data-zone]').length,
      legacyVisible: Array.from(document.querySelectorAll(
        '#welcome-state > .guild-hall-hero, #welcome-state > .guild-entry-grid, #skill-map, #welcome-state > .home-left-col, #welcome-state > .home-report'
      )).some((element) => !element.hidden),
      map: roundRect(rect('#e9-map-stage')),
      stage: roundRect(rect('#adventure-stage')),
      nav: roundRect(rect('#left-nav')),
      drawer: roundRect(rect('#e9-right-drawer-panel')),
      details: roundRect(rect('#e9-world-stage-details:not([hidden]), #e9-newbie-mainline:not([hidden])')),
      drawerExpanded: document.querySelector('#e9-right-drawer-toggle')?.getAttribute('aria-expanded'),
      detailsVisible: !!document.querySelector('#e9-world-stage-details:not([hidden]), #e9-newbie-mainline:not([hidden])'),
      inlineDetailsVisible: !!document.querySelector('.e9-zone[aria-pressed="true"] > .e9-zone__inline-details'),
      bottomDockVisible: (() => {
        const dock = document.querySelector('#bottom-dock');
        if (!dock) return false;
        const style = getComputedStyle(dock);
        const box = dock.getBoundingClientRect();
        return style.display !== 'none' && box.width > 0 && box.height > 0;
      })(),
      navPosition: getComputedStyle(document.querySelector('#left-nav')).position,
      navSlotPosition: getComputedStyle(document.querySelector('#e9-left-nav-slot')).position,
      navColumns: getComputedStyle(document.querySelector('.e9-nav__list')).gridTemplateColumns,
      horizontalOverflow: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
      minimumTarget: allTargets.reduce((smallest, element) => {
        const target = element.getBoundingClientRect();
        return Math.min(smallest, target.width, target.height);
      }, Number.POSITIVE_INFINITY),
      duplicateIds: [...new Set(duplicateIds)],
      bossAnchorsVisibility: getComputedStyle(document.querySelector('#e9-world-stage-boss-anchors')).visibility,
      aria: {
        drawerControls: document.querySelector('#e9-right-drawer-toggle')?.getAttribute('aria-controls'),
        mapLabel: document.querySelector('#e9-map-stage')?.getAttribute('aria-label'),
      },
    };
  });
}

async function saveViewportScreenshot(page, outputDir, filename) {
  const output = path.join(outputDir, filename);
  await page.screenshot({ path: output, fullPage: false });
  return output;
}

async function resetViewportScroll(page) {
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.querySelector('main')?.scrollTo(0, 0);
    document.querySelector('.practice')?.scrollTo(0, 0);
  });
}

async function runCase(browser, origin, outputDir, spec) {
  const page = await browser.newPage({ viewport: spec.viewport });
  const browserErrors = [];
  await installApiFixture(page, browserErrors);
  const url = `${origin}/index.html?lang=${spec.lang}&${shellFlags}`;
  await page.goto(url, { waitUntil: 'networkidle' });
  await waitForShell(page);

  let detailMapBefore = null;
  if (spec.zone) {
    detailMapBefore = await runtimeSnapshot(page);
    const zone = page.locator(`[data-zone="${spec.zone}"]`);
    if (await zone.count() !== 1) throw new Error(`missing unique zone ${spec.zone}`);
    await zone.scrollIntoViewIfNeeded();
    if (await zone.isEnabled()) await zone.click();
  }

  let beforeOpen = null;
  let afterOpen = null;
  let escaped = null;
  if (spec.progressDrawerCheck) {
    beforeOpen = await runtimeSnapshot(page);
    const toggle = page.locator('#e9-right-drawer-toggle');
    if (await toggle.count() !== 1) throw new Error('drawer toggle is not unique');
    await toggle.click();
    await page.locator('#e9-right-drawer-panel').waitFor({ state: 'visible' });
    await resetViewportScroll(page);
    afterOpen = await runtimeSnapshot(page);
    if (spec.escapeCheck) {
      await page.keyboard.press('Escape');
      escaped = await page.locator('#e9-right-drawer-toggle').getAttribute('aria-expanded');
      await resetViewportScroll(page);
    }
  }

  const snapshot = await runtimeSnapshot(page);
  const screenshot = await saveViewportScreenshot(page, outputDir, spec.filename);
  await page.close();
  return { ...spec, screenshot, beforeOpen, afterOpen, escaped, detailMapBefore, snapshot, browserErrors };
}

function assertCase(result) {
  const failures = [];
  const { snapshot, specName, browserErrors } = result;
  if (snapshot.activeShell !== 'e9') failures.push(`${specName}: E9 shell not active`);
  if (snapshot.skin !== 'immersive-rpg' || snapshot.shellSkin !== 'immersive-rpg') {
    failures.push(`${specName}: RPG skin marker missing`);
  }
  if (snapshot.nodeCount !== 10) failures.push(`${specName}: node count ${snapshot.nodeCount}`);
  if (snapshot.legacyVisible) failures.push(`${specName}: Legacy shell remains visible`);
  if (snapshot.horizontalOverflow !== 0) failures.push(`${specName}: horizontal overflow ${snapshot.horizontalOverflow}`);
  if (snapshot.minimumTarget < 44) failures.push(`${specName}: interactive target below 44px (${snapshot.minimumTarget})`);
  if (snapshot.duplicateIds.length) failures.push(`${specName}: duplicate IDs ${snapshot.duplicateIds.join(', ')}`);
  if (snapshot.bossAnchorsVisibility !== 'hidden') failures.push(`${specName}: Boss anchors visible`);
  if (snapshot.aria.drawerControls !== 'e9-right-drawer-panel') failures.push(`${specName}: aria-controls drift`);
  if (!snapshot.aria.mapLabel) failures.push(`${specName}: map accessible label missing`);
  if (browserErrors.length) failures.push(`${specName}: browser errors ${JSON.stringify(browserErrors)}`);
  if (result.beforeOpen && result.afterOpen) {
    const before = result.beforeOpen.map;
    const after = result.afterOpen.map;
    for (const key of ['left', 'right', 'width', 'height']) {
      if (before[key] !== after[key]) failures.push(`${specName}: drawer changed map ${key}`);
    }
  }
  if (result.escapeCheck && result.escaped !== 'false') failures.push(`${specName}: Escape did not close drawer`);
  if (result.layout === 'rail') {
    if (!snapshot.nav || !snapshot.map || snapshot.nav.right > snapshot.map.left) {
      failures.push(`${specName}: vertical navigation rail is not left of map`);
    }
  }
  if (result.layout === 'bottom-dock') {
    if (snapshot.navPosition !== 'fixed' && snapshot.navSlotPosition !== 'fixed') {
      failures.push(`${specName}: navigation is not a fixed bottom dock`);
    }
    if (!snapshot.navColumns || snapshot.navColumns.split(' ').length !== 6) {
      failures.push(`${specName}: bottom dock is not one six-item row`);
    }
    if (snapshot.bottomDockVisible) failures.push(`${specName}: secondary dock competes with primary navigation`);
  }
  if (result.detailOpen) {
    if (!snapshot.detailsVisible || !snapshot.details) failures.push(`${specName}: detail overlay is not visible`);
    if (snapshot.details && snapshot.map && (
      snapshot.details.left < snapshot.map.left
      || snapshot.details.right > snapshot.map.right
      || snapshot.details.top < snapshot.map.top
      || snapshot.details.bottom > snapshot.map.bottom
    )) failures.push(`${specName}: detail overlay escapes map bounds`);
    if (result.detailMapBefore && (
      result.detailMapBefore.map.width !== snapshot.map.width
      || result.detailMapBefore.map.height !== snapshot.map.height
    )) failures.push(`${specName}: opening details changed map size`);
  }
  if (result.mobileInline) {
    if (!snapshot.inlineDetailsVisible || snapshot.detailsVisible) {
      failures.push(`${specName}: mobile details are not selected-card inline only`);
    }
  }
  return failures;
}

async function runLegacyCase(browser, origin, outputDir) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const browserErrors = [];
  await installApiFixture(page, browserErrors);
  await page.goto(
    `${origin}/index.html?lang=zh&e9Shell=1&e9WorldStage=1&host=godokoro.com`,
    { waitUntil: 'networkidle' }
  );
  await page.locator('#welcome-state').waitFor({ state: 'visible' });
  const snapshot = await page.evaluate(() => ({
    activeShell: document.body.getAttribute('data-adventure-shell-active'),
    skin: document.body.getAttribute('data-e10-visual-skin'),
    shellHidden: document.querySelector('#e9-adventure-shell')?.hidden,
    worldNodes: document.querySelectorAll('#e9-world-stage-zones [data-zone]').length,
    drawerVisible: !!document.querySelector('#e9-right-drawer-toggle'),
  }));
  const screenshot = await saveViewportScreenshot(page, outputDir, 'legacy-nonallowlisted-1440x900-zh.png');
  await page.close();
  const failures = [];
  if (snapshot.activeShell !== 'legacy') failures.push('Legacy: query/host activated E9 shell');
  if (snapshot.skin !== null) failures.push('Legacy: RPG skin marker leaked');
  if (!snapshot.shellHidden) failures.push('Legacy: E9 shell is not hidden');
  if (snapshot.worldNodes !== 0 || snapshot.drawerVisible) failures.push('Legacy: World Stage UI leaked');
  if (browserErrors.length) failures.push(`Legacy: browser errors ${JSON.stringify(browserErrors)}`);
  return { specName: 'legacy-nonallowlisted', screenshot, snapshot, browserErrors, failures };
}

async function runLifecycleCase(browser, origin) {
  const page = await browser.newPage({ viewport: { width: 1024, height: 768 } });
  const browserErrors = [];
  await installApiFixture(page, browserErrors);
  await page.goto(`${origin}/index.html?lang=en&${shellFlags}`, { waitUntil: 'networkidle' });
  await waitForShell(page);
  const beforeGeneration = await page.evaluate(() => window.E9.getLifecycleGeneration());
  const destroyed = await page.evaluate(() => {
    window.E9.destroyShell();
    return {
      activeShell: document.body.getAttribute('data-adventure-shell-active'),
      bodySkin: document.body.getAttribute('data-e10-visual-skin'),
      shellSkin: document.querySelector('#e9-adventure-shell')?.getAttribute('data-e10-visual-skin'),
      shellHidden: document.querySelector('#e9-adventure-shell')?.hidden,
      mountedSlots: document.querySelectorAll('[data-e9-loaded], [data-e9-inited]').length,
    };
  });
  await page.evaluate(() => {
    window.__GO_E9_ACTIVE_SHELL__ = 'e9';
    window.E9.initShell();
  });
  await waitForShell(page);
  const remounted = await runtimeSnapshot(page);
  const afterGeneration = await page.evaluate(() => window.E9.getLifecycleGeneration());
  await page.close();
  const failures = [];
  if (
    destroyed.activeShell !== 'legacy'
    || destroyed.bodySkin !== null
    || destroyed.shellSkin !== null
    || !destroyed.shellHidden
    || destroyed.mountedSlots !== 0
  ) failures.push('lifecycle: destroy did not clean shell and skin ownership');
  if (
    remounted.activeShell !== 'e9'
    || remounted.skin !== 'immersive-rpg'
    || remounted.nodeCount !== 10
    || remounted.duplicateIds.length
    || afterGeneration <= beforeGeneration
  ) failures.push('lifecycle: clean remount did not converge');
  if (browserErrors.length) failures.push(`lifecycle: browser errors ${JSON.stringify(browserErrors)}`);
  return { beforeGeneration, afterGeneration, destroyed, remounted, browserErrors, failures };
}

async function main() {
  const args = process.argv.slice(2);
  const outputIndex = args.indexOf('--out');
  if (outputIndex < 0 || !args[outputIndex + 1]) throw new Error('--out <unique-directory> is required');
  const outputDir = path.resolve(args[outputIndex + 1]);
  if (fssync.existsSync(outputDir)) throw new Error(`output directory already exists: ${outputDir}`);
  await fs.mkdir(outputDir, { recursive: true });

  const { server, origin } = await startStaticServer();
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  try {
    const specs = [
      { specName: 'desktop-1920-closed', viewport: { width: 1920, height: 1080 }, lang: 'zh', filename: 'desktop-1920x1080-closed-zh.png', layout: 'rail' },
      { specName: 'desktop-1920-details', viewport: { width: 1920, height: 1080 }, lang: 'en', filename: 'desktop-1920x1080-drawer-open-en.png', zone: 'k1_5', detailOpen: true, layout: 'rail', progressDrawerCheck: true, escapeCheck: true },
      { specName: 'desktop-1440', viewport: { width: 1440, height: 900 }, lang: 'zh', filename: 'desktop-1440x900-zh.png', layout: 'rail' },
      { specName: 'tablet-landscape-closed', viewport: { width: 1024, height: 768 }, lang: 'en', filename: 'tablet-1024x768-closed-en.png', layout: 'rail' },
      { specName: 'tablet-landscape-details', viewport: { width: 1024, height: 768 }, lang: 'zh', filename: 'tablet-1024x768-drawer-open-zh.png', zone: 'k1_5', detailOpen: true, layout: 'rail', progressDrawerCheck: true, escapeCheck: true },
      { specName: 'tablet-portrait-closed', viewport: { width: 768, height: 1024 }, lang: 'en', filename: 'tablet-768x1024-portrait-closed-en.png', layout: 'bottom-dock' },
      { specName: 'tablet-portrait-details', viewport: { width: 768, height: 1024 }, lang: 'zh', filename: 'tablet-768x1024-portrait-drawer-open-zh.png', zone: 'k1_5', detailOpen: true, layout: 'bottom-dock' },
      { specName: 'mobile-zone-1', viewport: { width: 390, height: 844 }, lang: 'zh', filename: 'mobile-390x844-zone-1-zh.png', zone: 'k26_30', mobileInline: true, layout: 'bottom-dock' },
      { specName: 'mobile-zone-6', viewport: { width: 390, height: 844 }, lang: 'en', filename: 'mobile-390x844-zone-6-inline-en.png', zone: 'k1_5', mobileInline: true, layout: 'bottom-dock' },
      { specName: 'mobile-zone-10', viewport: { width: 390, height: 844 }, lang: 'zh', filename: 'mobile-390x844-zone-10-zh.png', zone: 'd7_plus', layout: 'bottom-dock' },
    ];
    const results = [];
    for (const spec of specs) results.push(await runCase(browser, origin, outputDir, spec));
    const legacy = await runLegacyCase(browser, origin, outputDir);
    const lifecycle = await runLifecycleCase(browser, origin);
    const failures = results.flatMap(assertCase).concat(legacy.failures, lifecycle.failures);
    const report = {
      ok: failures.length === 0,
      source_root: repoRoot,
      runtime_origin: origin,
      results,
      legacy,
      lifecycle,
      failures,
    };
    await fs.writeFile(path.join(outputDir, 'e10-vs1e-visual-contract.json'), JSON.stringify(report, null, 2));
    if (failures.length) throw new Error(failures.join('\n'));
    process.stdout.write(JSON.stringify({ ok: true, output_dir: outputDir, screenshots: results.length + 1 }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
