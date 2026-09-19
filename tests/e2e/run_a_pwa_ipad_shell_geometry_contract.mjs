/*
 * A_PWA_REAL_IPAD_SHELL_GEOMETRY_CLOSURE_003 -- real Adventure Shell geometry.
 *
 * The prior iPad correctives were verified by asserting that elements existed
 * and that a device-classification predicate returned the right boolean. Both
 * held while the owner's real device still rendered a broken layout, because
 * neither measured anything. This contract measures the rendered box model in
 * a real engine instead:
 *
 *   PORTRAIT  the installed-PWA portrait composition must match Safari's
 *             portrait composition on the same iPad. The affected device's
 *             layout viewport is ~2x its physical screen, so every native
 *             portrait-tablet rule (gated on max-width: 1279px) is skipped and
 *             the page used to render a ~46%-wide single-column task card, a
 *             shell that stopped short of the fixed bottom bar, and a large
 *             dead region between them (A_PWA_POST_OWNER_UAT_DIAGNOSTIC_004).
 *             The contract therefore measures Safari portrait in the same run
 *             and compares RATIOS -- widths and heights relative to the
 *             viewport, the card's grid mode, the content-to-bar gap -- rather
 *             than asserting any pixel constant. An earlier version asserted
 *             "shell height < 92% of the viewport", which is the opposite of
 *             Safari's behaviour (the native shell fills the viewport above
 *             the bar) and produced the dead region; it is deliberately gone.
 *
 *   LANDSCAPE the shell must use the viewport it is given. Its width cap is
 *             an anti-upscale guard for desktop monitors, but the affected
 *             device reports ~2360 CSS px, so the cap pinned a fixed 1920x1080
 *             canvas which was then centred -- the brown bands above and below
 *             the map. Measured at exactly 1920x1080 at x=220,y=280 before the
 *             fix.
 *
 * The OS/WebKit viewport disagreement itself cannot be reproduced in Chromium,
 * but every input the classifier reads is a plain property. The iPad scenarios
 * therefore define the hardware signals (Macintosh UA, touch points, standalone,
 * physical screen size and orientation) before any page script runs, so the
 * UNMODIFIED computeOverride() decides for itself and the whole chain
 * (classifier -> attribute -> CSS) is exercised, including across a rotation.
 * Touch scenarios run with hasTouch so (hover: none)/(pointer: coarse) resolve
 * as they do on the device; the desktop scenarios deliberately do not, which
 * is what proves the desktop cap is still in force.
 */
'use strict';

import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { installProductionBootRoutes, PRODUCTION_SHELL_QUERY, readBootIdentity, isCurrentE10, realBootstrap } from './e10_production_boot_fixture.mjs';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.E10_PLAYWRIGHT_CORE || 'playwright-core');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(process.env.E10_E2E_REPO_ROOT || path.resolve(__dirname, '..', '..'));
const chromeCandidates = [
  process.env.CHROME_BIN,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean);
const chromePath = chromeCandidates.find((candidate) => fssync.existsSync(candidate));
if (!chromePath) throw new Error('No Chrome/Edge executable found');

// The URL a real player opens: no E9 flags. The E10 shell is enabled the way
// Production enables it, from the /api/auth/me rollout decision (see
// e10_production_boot_fixture.mjs for why a query override is not the same path).
const SHELL_QUERY = PRODUCTION_SHELL_QUERY;

function contentTypeFor(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.jpg': 'image/jpeg',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

async function startStaticServer(rootDir) {
  const server = http.createServer(async (req, res) => {
    try {
      let rel = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
      if (rel === '/') rel = '/index.html';
      const abs = path.resolve(rootDir, `.${rel}`);
      if (!abs.startsWith(rootDir)) { res.writeHead(404); res.end(); return; }
      const stat = await fs.stat(abs).catch(() => null);
      if (!stat?.isFile()) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': contentTypeFor(abs) });
      fssync.createReadStream(abs).pipe(res);
    } catch {
      res.writeHead(500); res.end();
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

// Zones 1-2 cleared, 3-8 open, 9-10 locked -- in the REAL bootstrap shape (real names,
// boss blocks, stages), not a hand-made subset.
const GEOMETRY_ZONE_STATES = ['completed', 'completed', 'unlocked', 'unlocked', 'unlocked', 'unlocked', 'unlocked', 'unlocked', 'locked', 'locked'];
const geometryBootstrap = () => realBootstrap(GEOMETRY_ZONE_STATES);

// Hardware signals for a real installed iPad, injected before any page script
// runs so the UNMODIFIED computeOverride() in index.html's <head> makes the
// decision itself. This is the only way to exercise the whole chain
// (classifier -> data-go-portrait-tablet-override -> CSS) in Chromium: the
// OS/WebKit disagreement cannot be reproduced, but every input the classifier
// reads is a plain property that can be defined. Rotation is modelled by
// flipping the physical screen and its orientation, exactly what an iPad's
// hardware does, while the layout viewport is resized separately -- which is
// how the affected device ends up with a layout viewport that disagrees.
function realIpadInit(standalone) {
  return `
(function () {
  var state = { w: 820, h: 1180, type: 'portrait-primary' };
  window.__geoDevice = state;
  function def(target, key, getter) {
    try { Object.defineProperty(target, key, { configurable: true, get: getter }); } catch (e) {}
  }
  def(navigator, 'maxTouchPoints', function () { return 5; });
  def(navigator, 'standalone', function () { return ${standalone ? 'true' : 'false'}; });
  def(screen, 'width', function () { return state.w; });
  def(screen, 'height', function () { return state.h; });
  try {
    def(screen.orientation, 'type', function () { return state.type; });
  } catch (e) {}
})();
`;
}

async function rotateRealDevice(page, orientation) {
  await page.evaluate((next) => {
    const s = window.__geoDevice;
    if (next === 'landscape') { s.w = 1180; s.h = 820; s.type = 'landscape-primary'; }
    else { s.w = 820; s.h = 1180; s.type = 'portrait-primary'; }
  }, orientation);
}

async function openShell(browser, origin, { width, height, touch, realDevice, standalone = true, dsf = 1 }) {
  const page = await browser.newPage({
    viewport: { width, height },
    deviceScaleFactor: dsf,
    hasTouch: !!touch || !!realDevice,
    // A Macintosh UA + touch points is the desktop-site-mode iPad signature
    // the classifier keys on.
    ...(realDevice ? { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15' } : {}),
  });
  if (realDevice) await page.addInitScript(realIpadInit(standalone));
  await installProductionBootRoutes(page, { bootstrap: geometryBootstrap() });
  await page.goto(`${origin}/index.html${SHELL_QUERY}`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#e9-adventure-shell', { timeout: 15000 });
  await page.waitForTimeout(2200);
  // This contract only counts as evidence about the CURRENT E10 UI if the page
  // really booted it: E10 presentation, no legacy map nodes, a ready runtime.
  const boot = await readBootIdentity(page);
  if (!isCurrentE10(boot)) bootFailures.push(`${width}x${height}: ${JSON.stringify(boot)}`);
  bootChecked += 1;
  return page;
}

async function measure(page) {
  return page.evaluate(() => {
    const rect = (selector) => {
      const el = document.querySelector(selector);
      if (!el) return null;
      const box = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return {
        x: Math.round(box.x), y: Math.round(box.y),
        w: Math.round(box.width), h: Math.round(box.height),
        bottom: Math.round(box.bottom),
        display: cs.display, position: cs.position, minHeight: cs.minHeight,
      };
    };
    return {
      vw: window.innerWidth,
      vh: window.innerHeight,
      skin: document.body.getAttribute('data-e10-visual-skin'),
      shell: rect('#e9-adventure-shell'),
      mapStage: rect('#e9-map-stage'),
      rightCards: rect('#e9-right-cards-slot'),
      details: rect('#e9-world-stage-details'),
      note: rect('.e9-stage__note'),
      dock: rect('#e9-left-nav-slot'),
      diagnosticTrigger: rect('#go-pwa-diagnostic-trigger'),
      docScrollHeight: (document.scrollingElement || document.documentElement).scrollHeight,
      detailsGridColumns: (() => {
        const el = document.querySelector('#e9-world-stage-details');
        if (!el) return 0;
        const cols = getComputedStyle(el).gridTemplateColumns;
        return cols && cols !== 'none' ? cols.split(' ').length : 0;
      })(),
    };
  });
}

const failures = [];
let bootChecked = 0;
const bootFailures = [];
function check(label, condition, detail) {
  if (condition) { console.log(`  PASS  ${label}`); return; }
  failures.push(`${label} -- ${detail}`);
  console.log(`  FAIL  ${label} -- ${detail}`);
}

// Composition ratios, all relative to the viewport, so Safari (820x1180) and the
// installed PWA (1640x2360) are directly comparable without any pixel constant.
function composition(m) {
  const { vw, vh, mapStage, details, note, dock, shell } = m;
  const contentBottom = Math.max(details ? details.bottom : 0, note ? note.bottom : 0);
  return {
    mapWidth: mapStage ? mapStage.w / vw : 0,
    detailWidth: details ? details.w / vw : 0,
    detailHeight: details ? details.h / vh : 0,
    contentBottom: contentBottom / vh,
    contentToDockGap: dock ? (dock.y - contentBottom) / vh : 0,
    dockBottomGap: dock ? (vh - dock.bottom) / vh : 0,
    scrollOverflow: Math.max(0, m.docScrollHeight - vh) / vh,
    shellFill: shell ? shell.h / vh : 0,
    gridColumns: m.detailsGridColumns,
    detailsDisplay: details ? details.display : null,
  };
}

const fmt = (n) => (typeof n === 'number' ? n.toFixed(3) : String(n));

function assertPortraitParity(name, m, ref) {
  check(`${name}: shell renders`, !!m.shell, 'no #e9-adventure-shell box');
  if (!m.shell || !m.details || !m.dock) {
    check(`${name}: measured surfaces exist`, false, 'missing shell/details/dock');
    return;
  }
  const c = composition(m);
  const r = composition(ref);
  const within = (label, actual, expected, tol) => check(
    `${name}: ${label} ~ Safari reference`,
    Math.abs(actual - expected) <= tol,
    `${fmt(actual)} vs Safari ${fmt(expected)} (tolerance ${tol})`);
  within('map width ratio', c.mapWidth, r.mapWidth, 0.06);
  within('detail card width ratio', c.detailWidth, r.detailWidth, 0.06);
  within('detail card height ratio', c.detailHeight, r.detailHeight, 0.08);
  within('content occupancy of the viewport', c.contentBottom, r.contentBottom, 0.08);
  check(`${name}: detail card keeps the portrait grid layout`,
    c.detailsDisplay === 'grid' && c.gridColumns >= 2,
    `display=${c.detailsDisplay} columns=${c.gridColumns} (Safari: display=${r.detailsDisplay} columns=${r.gridColumns})`);
  // No large dead region: the last content ends close to the fixed bottom bar,
  // exactly as in Safari, instead of stopping a large fraction of the viewport
  // short of it.
  check(`${name}: no large dead space between the content and the bottom bar`,
    c.contentToDockGap <= Math.max(0.06, r.contentToDockGap + 0.05),
    `gap=${fmt(c.contentToDockGap)} of viewport height (Safari ${fmt(r.contentToDockGap)})`);
  check(`${name}: content is not buried under the bottom bar`,
    c.contentToDockGap >= -0.05,
    `gap=${fmt(c.contentToDockGap)} of viewport height`);
  check(`${name}: bottom bar sits at the viewport bottom like Safari`,
    Math.abs(c.dockBottomGap - r.dockBottomGap) <= 0.02,
    `${fmt(c.dockBottomGap)} vs Safari ${fmt(r.dockBottomGap)}`);
  check(`${name}: page scroll overflow is bounded`,
    c.scrollOverflow <= Math.max(0.04, r.scrollOverflow + 0.04),
    `${fmt(c.scrollOverflow)} of viewport height (Safari ${fmt(r.scrollOverflow)})`);
}

function assertLandscapeGeometry(name, m, { expectFill }) {
  const { shell, vw, vh } = m;
  check(`${name}: shell renders`, !!shell, 'no #e9-adventure-shell box');
  if (!shell) return;
  const ratio = shell.w / shell.h;
  check(`${name}: 16/9 preserved`,
    Math.abs(ratio - 16 / 9) < 0.02,
    `ratio=${ratio.toFixed(3)}`);
  if (!expectFill) return;
  // The regression: a hard 1920px art cap pinned a fixed desktop canvas in a
  // much larger viewport, then centred it.
  check(`${name}: shell consumes the available width`,
    shell.w >= vw * 0.97,
    `shell w=${shell.w} vs viewport w=${vw} (a fixed desktop canvas letterboxed in a larger viewport)`);
  const band = Math.max(0, shell.y);
  check(`${name}: no arbitrary top band beyond the aspect-fit minimum`,
    band <= Math.max(8, (vh - vw * 9 / 16) / 2 + 12),
    `top band=${band}px, viewport ${vw}x${vh}`);
  const bottomBand = Math.max(0, vh - shell.bottom);
  check(`${name}: no arbitrary bottom band beyond the aspect-fit minimum`,
    bottomBand <= Math.max(8, (vh - vw * 9 / 16) / 2 + 12),
    `bottom band=${bottomBand}px, viewport ${vw}x${vh}`);
}

const { server, origin } = await startStaticServer(repoRoot);
const browser = await chromium.launch({ executablePath: chromePath });

try {
  // The reference every portrait assertion compares against: Safari on the same
  // iPad (honest 820x1180 viewport, not installed, so no override attribute).
  console.log('SAFARI_PORTRAIT_REFERENCE (820x1180 @2x, browser tab)');
  let safariRef = null;
  {
    const page = await openShell(browser, origin, { width: 820, height: 1180, realDevice: true, standalone: false, dsf: 2 });
    safariRef = await measure(page);
    const overrideAttr = await page.evaluate(() => document.documentElement.hasAttribute('data-go-portrait-tablet-override'));
    check('SAFARI_REFERENCE: the classifier does not fire in a browser tab', !overrideAttr,
      'data-go-portrait-tablet-override is set for a non-installed page');
    check('SAFARI_REFERENCE: detail card is the native two-column grid',
      safariRef.details && safariRef.details.display === 'grid' && safariRef.detailsGridColumns >= 2,
      `display=${safariRef.details && safariRef.details.display} columns=${safariRef.detailsGridColumns}`);
    await page.close();
  }

  console.log('IPAD_PWA_PORTRAIT (installed, layout viewport 1640x2360 on an 820x1180 screen)');
  {
    const page = await openShell(browser, origin, { width: 1640, height: 2360, realDevice: true, standalone: true, dsf: 1 });
    assertPortraitParity('IPAD_PWA_PORTRAIT', await measure(page), safariRef);
    await page.close();
  }

  console.log('IPAD_PORTRAIT_HONEST (820x1180)');
  {
    const page = await openShell(browser, origin, { width: 820, height: 1180, touch: true });
    const m = await measure(page);
    check('IPAD_PORTRAIT_HONEST: shell renders', !!m.shell, 'missing shell');
    check('IPAD_PORTRAIT_HONEST: shell stays within the viewport width',
      m.shell && m.shell.w <= m.vw, `shell w=${m.shell && m.shell.w} vs ${m.vw}`);
    await page.close();
  }

  console.log('IPAD_LANDSCAPE (misreported 2360x1640)');
  {
    const page = await openShell(browser, origin, { width: 2360, height: 1640, touch: true });
    assertLandscapeGeometry('IPAD_LANDSCAPE', await measure(page), { expectFill: true });
    await page.close();
  }

  console.log('PHONE (390x844)');
  {
    const page = await openShell(browser, origin, { width: 390, height: 844, touch: true });
    const m = await measure(page);
    check('PHONE: shell renders', !!m.shell, 'missing shell');
    check('PHONE: shell stays within the viewport width',
      m.shell && m.shell.w <= m.vw, `shell w=${m.shell && m.shell.w} vs ${m.vw}`);
    await page.close();
  }

  console.log('DESKTOP (1440x900, fine pointer)');
  {
    const page = await openShell(browser, origin, { width: 1440, height: 900, touch: false });
    const m = await measure(page);
    check('DESKTOP: shell renders', !!m.shell, 'missing shell');
    check('DESKTOP: 16/9 preserved',
      m.shell && Math.abs(m.shell.w / m.shell.h - 16 / 9) < 0.02,
      `ratio=${m.shell && (m.shell.w / m.shell.h).toFixed(3)}`);
    await page.close();
  }

  // The art cap exists so a large desktop monitor never upscales the master
  // art. Touch tablets opt out of it; a fine-pointer desktop must not.
  console.log('DESKTOP_LARGE (2560x1440, fine pointer) -- art cap must still hold');
  {
    const page = await openShell(browser, origin, { width: 2560, height: 1440, touch: false });
    const m = await measure(page);
    check('DESKTOP_LARGE: 1920px art cap still applies',
      m.shell && m.shell.w <= 1920,
      `shell w=${m.shell && m.shell.w} exceeded the desktop art cap`);
    await page.close();
  }

  // Same rotation, but nothing is pinned: the live computeOverride() in
  // index.html decides from the injected hardware signals, so this covers the
  // whole chain (classifier -> attribute -> CSS) including its recompute on
  // resize, which is what a real rotation triggers.
  console.log('REAL_CLASSIFIER_CHAIN (unmodified computeOverride, portrait -> landscape -> portrait)');
  {
    const page = await openShell(browser, origin, { width: 1640, height: 2360, realDevice: true });
    const override = () => page.evaluate(() => document.documentElement.hasAttribute('data-go-portrait-tablet-override'));

    check('CHAIN/portrait-1: classifier sets the override itself', await override(),
      'computeOverride() did not set data-go-portrait-tablet-override for a portrait iPad PWA');
    assertPortraitParity('CHAIN/portrait-1', await measure(page), safariRef);

    await rotateRealDevice(page, 'landscape');
    await page.setViewportSize({ width: 2360, height: 1640 });
    await page.waitForTimeout(900);
    check('CHAIN/landscape: classifier drops the override', !(await override()),
      'the portrait override survived a rotation to landscape');
    assertLandscapeGeometry('CHAIN/landscape', await measure(page), { expectFill: true });

    await rotateRealDevice(page, 'portrait');
    await page.setViewportSize({ width: 1640, height: 2360 });
    await page.waitForTimeout(900);
    check('CHAIN/portrait-2: classifier re-applies the override', await override(),
      'computeOverride() did not re-set the override after rotating back to portrait');
    assertPortraitParity('CHAIN/portrait-2', await measure(page), safariRef);
    await page.close();
  }

  console.log('REAL_CLASSIFIER_CHAIN_HONEST (820x1180 viewport agrees with the screen)');
  {
    const page = await openShell(browser, origin, { width: 820, height: 1180, realDevice: true });
    const m = await measure(page);
    check('CHAIN_HONEST: shell stays within the viewport width',
      m.shell && m.shell.w <= m.vw, `shell w=${m.shell && m.shell.w} vs ${m.vw}`);
    await page.close();
  }

  console.log('DIAGNOSTIC default visibility');
  {
    const page = await openShell(browser, origin, { width: 1640, height: 2360, realDevice: true });
    const m = await measure(page);
    check('DIAGNOSTIC: no trigger surface for a normal player',
      !m.diagnosticTrigger,
      'the invisible diagnostic trigger is still mounted without ?pwa_diag=1');
    await page.close();

    const optIn = await browser.newPage({ viewport: { width: 1640, height: 2360 }, hasTouch: true });
    await installProductionBootRoutes(optIn, { bootstrap: geometryBootstrap() });
    await optIn.goto(`${origin}/index.html${SHELL_QUERY}&pwa_diag=1`, { waitUntil: 'domcontentloaded' });
    await optIn.waitForTimeout(2200);
    const hasTrigger = await optIn.evaluate(() => !!document.querySelector('#go-pwa-diagnostic-trigger'));
    check('DIAGNOSTIC: ?pwa_diag=1 still opts in', hasTrigger, 'opt-in did not mount the trigger');
    await optIn.close();
  }
} finally {
  await browser.close();
  server.close();
}

check(`E10 boot identity: every one of the ${bootChecked} pages booted the current E10 runtime (no legacy map, no query flags, runtime ready)`,
  bootFailures.length === 0, bootFailures.slice(0, 2).join(' | '));

if (failures.length) {
  console.error(`\n${failures.length} geometry assertion(s) failed:`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log('\nAll Adventure Shell geometry assertions passed.');
