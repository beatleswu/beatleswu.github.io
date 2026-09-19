/*
 * A_PWA_REAL_IPAD_SHELL_GEOMETRY_CLOSURE_003 -- real Adventure Shell geometry.
 *
 * The prior iPad correctives were verified by asserting that elements existed
 * and that a device-classification predicate returned the right boolean. Both
 * held while the owner's real device still rendered a broken layout, because
 * neither measured anything. This contract measures the rendered box model in
 * a real engine instead:
 *
 *   PORTRAIT  the shell must track its content height. It previously carried
 *             min-height:100dvh, so on the affected device's 1640x2360
 *             misreported viewport it ran the full 2360px while the HUD, map
 *             and detail flow only reached ~1070px -- the owner-reported dead
 *             brown region. The selected-zone/current-task surfaces also kept
 *             desktop side-rail geometry (a ~350-360px box taken out of flow
 *             and pinned to an edge), which is why the card sat in a narrow
 *             column with the rest of the row empty.
 *
 *   LANDSCAPE the shell must use the viewport it is given. Its width cap is
 *             an anti-upscale guard for desktop monitors, but the affected
 *             device reports ~2360 CSS px, so the cap pinned a fixed 1920x1080
 *             canvas which was then centred -- the brown bands above and below
 *             the map. Measured at exactly 1920x1080 at x=220,y=280 before the
 *             fix.
 *
 * The misreporting itself cannot be reproduced in Chromium (it is an OS/WebKit
 * disagreement), so portrait runs with the same html[data-go-portrait-tablet-
 * override] attribute the real device sets, pinned deterministically here.
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

const SHELL_QUERY = '?lang=zh&E9_DEBUG=1&e9Shell=1&e9TopHud=1&e9LeftNav=1&e9RightCards=1'
  + '&e9BottomDock=1&e9WorldStage=1';

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

const ZONE_KEYS = ['k26_30', 'k21_25', 'k16_20', 'k11_15', 'k6_10', 'k1_5', 'd1_2', 'd3_4', 'd5_6', 'd7_plus'];
function zoneFixture() {
  return ZONE_KEYS.map((key, index) => ({
    key,
    name: `Zone ${index + 1}`,
    name_en: `Zone ${index + 1}`,
    status: index <= 7 ? 'unlocked' : 'locked',
    unlocked: index <= 7,
    can_enter: index <= 7,
    cleared: index < 2,
    completed: index < 2,
    stars: index < 2 ? 1 : 0,
    seen: index < 2 ? 30 : 419,
    total: 2287,
    boss: { available: index <= 7 },
  }));
}

// Hardware signals for a real installed iPad, injected before any page script
// runs so the UNMODIFIED computeOverride() in index.html's <head> makes the
// decision itself. This is the only way to exercise the whole chain
// (classifier -> data-go-portrait-tablet-override -> CSS) in Chromium: the
// OS/WebKit disagreement cannot be reproduced, but every input the classifier
// reads is a plain property that can be defined. Rotation is modelled by
// flipping the physical screen and its orientation, exactly what an iPad's
// hardware does, while the layout viewport is resized separately -- which is
// how the affected device ends up with a layout viewport that disagrees.
const REAL_IPAD_INIT = `
(function () {
  var state = { w: 820, h: 1180, type: 'portrait-primary' };
  window.__geoDevice = state;
  function def(target, key, getter) {
    try { Object.defineProperty(target, key, { configurable: true, get: getter }); } catch (e) {}
  }
  def(navigator, 'maxTouchPoints', function () { return 5; });
  def(navigator, 'standalone', function () { return true; });
  def(screen, 'width', function () { return state.w; });
  def(screen, 'height', function () { return state.h; });
  try {
    def(screen.orientation, 'type', function () { return state.type; });
  } catch (e) {}
})();
`;

async function rotateRealDevice(page, orientation) {
  await page.evaluate((next) => {
    const s = window.__geoDevice;
    if (next === 'landscape') { s.w = 1180; s.h = 820; s.type = 'landscape-primary'; }
    else { s.w = 820; s.h = 1180; s.type = 'portrait-primary'; }
  }, orientation);
}

async function openShell(browser, origin, { width, height, touch, portraitOverride, realDevice }) {
  const page = await browser.newPage({
    viewport: { width, height },
    deviceScaleFactor: 1,
    hasTouch: !!touch || !!realDevice,
    // A Macintosh UA + touch points is the desktop-site-mode iPad signature
    // the classifier keys on.
    ...(realDevice ? { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15' } : {}),
  });
  if (realDevice) await page.addInitScript(REAL_IPAD_INIT);
  // Playwright matches the most recently registered route first, so the
  // catch-all is registered before the specific responses it must not shadow.
  await page.route('**/api/**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: '{}',
  }));
  await page.route('**/api/auth/me', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      logged_in: true, user_id: 7, username: 'geometry_fixture',
      display_name: 'Geometry Fixture', is_admin: false, is_premium: true,
      needs_onboarding_choice: false, tour_done: true,
    }),
  }));
  await page.route('**/api/adventure/bootstrap**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ zones: zoneFixture(), cinematics: {} }),
  }));
  await page.goto(`${origin}/index.html${SHELL_QUERY}`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#e9-adventure-shell', { timeout: 15000 });
  await page.waitForTimeout(2200);
  if (portraitOverride) await applyPortraitOverride(page);
  return page;
}

// The real device sets this from index.html's hardware check; desktop
// Chromium never will. index.html also recomputes the attribute on resize and
// drops it here (its predicate is correctly false for this engine), so the
// affected path is pinned and then re-asserted, otherwise the orientation
// transition case would silently measure the unaffected layout instead.
async function applyPortraitOverride(page) {
  await page.evaluate(() => {
    const html = document.documentElement;
    const assert = () => {
      if (!html.hasAttribute('data-go-portrait-tablet-override')) {
        html.setAttribute('data-go-portrait-tablet-override', '');
      }
    };
    assert();
    if (!window.__geometryOverridePin) {
      window.__geometryOverridePin = new MutationObserver(assert);
      window.__geometryOverridePin.observe(html, { attributes: true, attributeFilter: ['data-go-portrait-tablet-override'] });
    }
  });
  await page.waitForTimeout(400);
}

// Rotating to landscape is not the misreported-portrait case, so the pin has
// to be released as well as the attribute cleared -- otherwise the observer
// above re-asserts it and the landscape leg measures the portrait layout.
async function releasePortraitOverride(page) {
  await page.evaluate(() => {
    if (window.__geometryOverridePin) {
      window.__geometryOverridePin.disconnect();
      delete window.__geometryOverridePin;
    }
    document.documentElement.removeAttribute('data-go-portrait-tablet-override');
  });
  await page.waitForTimeout(400);
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
      diagnosticTrigger: rect('#go-pwa-diagnostic-trigger'),
    };
  });
}

const failures = [];
function check(label, condition, detail) {
  if (condition) { console.log(`  PASS  ${label}`); return; }
  failures.push(`${label} -- ${detail}`);
  console.log(`  FAIL  ${label} -- ${detail}`);
}

function assertPortraitGeometry(name, m) {
  const { shell, mapStage, rightCards, vh, vw } = m;
  check(`${name}: shell renders`, !!shell, 'no #e9-adventure-shell box');
  if (!shell) return;
  // The regression: min-height:100dvh made the shell exactly the viewport
  // height regardless of content.
  check(`${name}: shell height tracks content, not the viewport`,
    shell.h < vh * 0.92,
    `shell h=${shell.h} is >=92% of viewport h=${vh} (the 100dvh dead-space regression)`);
  check(`${name}: map uses the tablet width`,
    mapStage && mapStage.w >= vw * 0.9,
    `map w=${mapStage && mapStage.w} vs viewport w=${vw}`);
  if (rightCards && rightCards.h > 0) {
    check(`${name}: current-task cards are in normal flow`,
      rightCards.position === 'static' || rightCards.position === 'relative',
      `position=${rightCards.position} (a fixed/absolute desktop rail breaks the vertical flow)`);
    check(`${name}: current-task cards use a tablet measure, not a 360px desktop rail`,
      rightCards.w >= 600,
      `cards w=${rightCards.w}`);
    check(`${name}: current-task cards follow the map`,
      mapStage && rightCards.y >= mapStage.bottom - 4,
      `cards y=${rightCards.y} vs map bottom=${mapStage && mapStage.bottom}`);
    const emptyBelow = shell.bottom - rightCards.bottom;
    check(`${name}: no giant dead region under the flow`,
      emptyBelow < vh * 0.25,
      `${emptyBelow}px of empty shell below the last card (viewport ${vh})`);
  }
  if (m.details && m.details.h > 0) {
    check(`${name}: zone detail card uses a tablet measure`,
      m.details.w >= 600,
      `details w=${m.details.w}`);
  }
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
  console.log('IPAD_PORTRAIT (misreported 1640x2360, override active)');
  {
    const page = await openShell(browser, origin, { width: 1640, height: 2360, touch: true, portraitOverride: true });
    assertPortraitGeometry('IPAD_PORTRAIT', await measure(page));
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

  // An orientation change must re-resolve geometry without a reload: the PWA
  // is a single long-lived document and the owner rotates the device in place.
  console.log('ORIENTATION_TRANSITION (portrait -> landscape -> portrait, no reload)');
  {
    const page = await openShell(browser, origin, { width: 1640, height: 2360, touch: true, portraitOverride: true });
    assertPortraitGeometry('TRANSITION/portrait-1', await measure(page));

    await page.setViewportSize({ width: 2360, height: 1640 });
    // Landscape is not the misreported-portrait case, so the device would not
    // be asserting the override here either.
    await releasePortraitOverride(page);
    await page.waitForTimeout(700);
    assertLandscapeGeometry('TRANSITION/landscape', await measure(page), { expectFill: true });

    await page.setViewportSize({ width: 1640, height: 2360 });
    await applyPortraitOverride(page);
    await page.waitForTimeout(700);
    assertPortraitGeometry('TRANSITION/portrait-2', await measure(page));
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
    assertPortraitGeometry('CHAIN/portrait-1', await measure(page));

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
    assertPortraitGeometry('CHAIN/portrait-2', await measure(page));
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
    const page = await openShell(browser, origin, { width: 1640, height: 2360, touch: true, portraitOverride: true });
    const m = await measure(page);
    check('DIAGNOSTIC: no trigger surface for a normal player',
      !m.diagnosticTrigger,
      'the invisible diagnostic trigger is still mounted without ?pwa_diag=1');
    await page.close();

    const optIn = await browser.newPage({ viewport: { width: 1640, height: 2360 }, hasTouch: true });
    await optIn.route('**/api/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
    await optIn.route('**/api/auth/me', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        logged_in: true, user_id: 7, username: 'geometry_fixture',
        display_name: 'Geometry Fixture', is_admin: false, is_premium: true,
        needs_onboarding_choice: false, tour_done: true,
      }),
    }));
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

if (failures.length) {
  console.error(`\n${failures.length} geometry assertion(s) failed:`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log('\nAll Adventure Shell geometry assertions passed.');
