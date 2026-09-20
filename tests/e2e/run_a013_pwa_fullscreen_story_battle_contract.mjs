/*
 * A_E10_PWA_FULLSCREEN_STORY_AND_BATTLE_LAYOUT_CORRECTIVE_013 -- contract.
 *
 * Owner evidence (installed iPad PWA, 1640x2360 portrait / 2360x1640 landscape layout
 * viewport on an 820x1180 / 1180x820 pt screen):
 *
 *   1. The story / cinematic frame was a 900x560 box (38-55% of the viewport).
 *   2. In portrait the world map stayed on screen while a question was active (the
 *      portrait mirror omitted the native "#welcome-state.hidden hides the map" rule),
 *      the battle header and VS card sat over the map, and the board was pushed below
 *      the fold -- the Owner had to rotate to landscape to answer.
 *   3. The landscape battle was capped at ~59% of the width / ~50% of the height.
 *
 * Every assertion below runs the real E9/E10 shell in a real engine, booted the way
 * Production boots it (no query flags; see e10_production_boot_fixture.mjs), through
 * the UNMODIFIED iPad classifier, at the Owner-evidence viewports plus representative
 * iPad and desktop viewports.  Chromium is NOT native iPad WebKit: this proves layout
 * geometry and state, and it does not replace the Owner's real-device acceptance.
 *
 * Optional: A013_CAPTURE_DIR=<dir> saves screenshots + measurements.json (the Owner
 * review package is generated from exactly these runs).
 */
'use strict';

import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  installProductionBootRoutes, installBattleRoutes, IPAD_VIEWPORTS, ipadInitScript, MACINTOSH_IPAD_UA,
  PRODUCTION_SHELL_QUERY, readBootIdentity, isCurrentE10, realBootstrap, ZONE_KEYS,
} from './e10_production_boot_fixture.mjs';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.E10_PLAYWRIGHT_CORE || 'playwright-core');
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(process.env.E10_E2E_REPO_ROOT || path.resolve(__dirname, '..', '..'));
const chromePath = [
  process.env.CHROME_BIN,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find((candidate) => fssync.existsSync(candidate));
if (!chromePath) throw new Error('No Chrome/Edge executable found');
const captureDir = process.env.A013_CAPTURE_DIR ? path.resolve(process.env.A013_CAPTURE_DIR) : null;
if (captureDir) fssync.mkdirSync(captureDir, { recursive: true });

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8', '.mjs': 'application/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.mp3': 'audio/mpeg' };
async function startStaticServer(rootDir) {
  const server = http.createServer(async (req, res) => {
    try {
      let rel = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
      if (rel === '/') rel = '/index.html';
      const abs = path.resolve(rootDir, `.${rel}`);
      const stat = abs.startsWith(rootDir) ? await fs.stat(abs).catch(() => null) : null;
      if (!stat?.isFile()) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(abs).toLowerCase()] || 'application/octet-stream', 'Cache-Control': 'no-store' });
      fssync.createReadStream(abs).pipe(res);
    } catch { res.writeHead(500); res.end(); }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

const failures = [];
let passed = 0;
const check = (label, ok, detail = '') => {
  if (ok) { passed += 1; console.log(`  PASS  ${label}`); } else { failures.push(`${label}${detail ? ` -- ${detail}` : ''}`); console.error(`  FAIL  ${label}${detail ? ` -- ${detail}` : ''}`); }
};

const LOCKED = 'locked';
// Zone 1 cleared, Zone 2 current: the Owner's own account shape.
const ZONE_STATES = ['completed', 'unlocked', LOCKED, LOCKED, LOCKED, LOCKED, LOCKED, LOCKED, LOCKED, LOCKED];
const STORY_ZONE = 'k26_30';
const BATTLE_TOPIC = '3史萊姆平原';

// The viewport classes the Owner evidence names, plus representative iPad / desktop ones.
const MODES = [
  { name: 'PWA_PORTRAIT', kind: 'pwa-portrait' },
  { name: 'PWA_LANDSCAPE', kind: 'pwa-landscape' },
  { name: 'EVID_PORTRAIT', kind: 'pwa-portrait' },
  { name: 'EVID_LANDSCAPE', kind: 'wide-landscape', boardFloor: 752 },
  { name: 'PRO13_PWA_PORTRAIT', kind: 'pwa-portrait' },
  { name: 'PRO13_PWA_LANDSCAPE', kind: 'pwa-landscape' },
  { name: 'SAFARI_PORTRAIT', kind: 'safari-portrait', boardFloor: 728 },
  { name: 'SAFARI_LANDSCAPE', kind: 'safari-landscape', boardFloor: 582 },
  { name: 'DESKTOP', kind: 'desktop', boardFloor: 765 },
];

const onlyModes = process.env.A013_MODES ? new Set(process.env.A013_MODES.split(',')) : null;
const RUN_MODES = onlyModes ? MODES.filter((mode) => onlyModes.has(mode.name)) : MODES;

const rectOf = `(sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect(); const c = getComputedStyle(e); return { l: b.left, t: b.top, w: b.width, h: b.height, r: b.right, b: b.bottom, display: c.display }; }`;
const inside = (inner, outer, tol = 1.5) => !!inner && !!outer && inner.l >= outer.l - tol && inner.t >= outer.t - tol && inner.r <= outer.r + tol && inner.b <= outer.b + tol;
const pct = (a, b) => `${(100 * a / b).toFixed(1)}%`;
const bootFailures = [];
let bootChecked = 0;
const measurements = [];

async function openGame(browser, origin, modeName, { seen = true } = {}) {
  const m = IPAD_VIEWPORTS[modeName];
  const page = await browser.newPage({ viewport: m.vp, deviceScaleFactor: m.dsf, hasTouch: m.touch !== false, userAgent: m.touch === false ? undefined : MACINTOSH_IPAD_UA });
  const log = { requests: [], errors: [] };
  page.on('request', (r) => { if (/\/api\//.test(r.url())) log.requests.push({ method: r.method(), path: new URL(r.url()).pathname }); });
  page.on('pageerror', (e) => log.errors.push(String(e.message).slice(0, 160)));
  await page.addInitScript(ipadInitScript(m));
  await installProductionBootRoutes(page, { bootstrap: realBootstrap(ZONE_STATES, { seenIntro: seen ? ZONE_KEYS : [] }) });
  await installBattleRoutes(page, { topic: BATTLE_TOPIC });
  await page.goto(`${origin}/index.html${PRODUCTION_SHELL_QUERY}`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#e9-adventure-shell', { timeout: 20000 });
  await page.waitForFunction(() => window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ === true, { timeout: 20000 });
  await page.waitForTimeout(2500);
  bootChecked += 1;
  const boot = await readBootIdentity(page);
  if (!isCurrentE10(boot)) bootFailures.push(`${modeName}: ${JSON.stringify(boot)}`);
  return { page, log, m };
}

const mapSnapshot = (page) => page.evaluate(`(() => { const R = ${rectOf}; const st = document.querySelector('#e9-world-stage-slot'); const s = st && st.__e9WorldStageState; const dr = document.querySelector('#e9-right-cards-slot');
  return { shell: R('#e9-adventure-shell'), stage: R('#e9-map-stage'), selected: s ? s.selectedZoneKey : null, scroll: [Math.round(scrollX), Math.round(scrollY)],
    drawer: dr ? dr.className : null, owner: document.body.dataset.adventureShellOwner || null, welcomeHidden: !!document.querySelector('#welcome-state.hidden') }; })()`);

const safeAreaOffsets = (page) => page.evaluate(() => {
  const probe = document.createElement('div');
  probe.style.cssText = 'position:fixed;visibility:hidden;padding:env(safe-area-inset-top,0px) env(safe-area-inset-right,0px) env(safe-area-inset-bottom,0px) env(safe-area-inset-left,0px)';
  document.body.appendChild(probe);
  const c = getComputedStyle(probe);
  const out = { top: c.paddingTop, right: c.paddingRight, bottom: c.paddingBottom, left: c.paddingLeft };
  probe.remove();
  return out;
});

async function openReplayStory(page) {
  await page.evaluate((zone) => document.querySelector(`[data-zone="${zone}"]`).click(), STORY_ZONE);
  await page.waitForTimeout(2000);
  // Side-panel surfaces (landscape / desktop) keep the zone card in a drawer.
  await page.evaluate(() => {
    const toggle = document.querySelector('#e9-right-drawer-toggle');
    const slot = document.querySelector('#e9-right-cards-slot');
    if (toggle && slot && !slot.classList.contains('is-drawer-open') && toggle.getBoundingClientRect().width > 0) toggle.click();
  });
  await page.waitForTimeout(800);
}
const clickReplay = (page) => page.evaluate(() => {
  const cands = Array.from(new Set([...document.querySelectorAll('#e9-world-stage-details-replay, [data-e10-zone-replay]'), ...Array.from(document.querySelectorAll('button')).filter((b) => /重溫故事|Replay Story/.test(b.textContent || ''))]));
  const visible = cands.filter((el) => { const b = el.getBoundingClientRect(); if (el.hidden || el.disabled || b.width <= 0) return false; const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return hit === el || el.contains(hit); });
  if (!visible.length) return false;
  visible[0].click();
  return true;
});

const storyMetrics = (page) => page.evaluate(`(() => { const R = ${rectOf}; const ov = document.querySelector('#boss-cinematic'); const btns = Array.from(document.querySelectorAll('#boss-cinematic .intro-skip-btn, #boss-cinematic .intro-replay-btn')).map((b) => { const r = b.getBoundingClientRect(); return { l: r.left, t: r.top, w: r.width, h: r.height, r: r.right, b: r.bottom }; });
  const img = document.querySelector('#boss-cinematic .film-shot.active img'); const ic = img && getComputedStyle(img); const content = document.querySelector('#boss-cinematic .boss-cinematic-content');
  return { vw: innerWidth, vh: innerHeight, shown: !!(ov && ov.classList.contains('show')), aria: ov && ov.getAttribute('aria-hidden'), count: document.querySelectorAll('#boss-cinematic').length,
    scene: R('#boss-cinematic .boss-cinematic-scene'), controls: R('#boss-cinematic .intro-film-controls'), closeX: R('#boss-cinematic-close-x'), content: R('#boss-cinematic .boss-cinematic-content'), btns,
    lineFont: parseFloat(getComputedStyle(document.querySelector('#boss-cinematic .boss-cinematic-line')).fontSize), contentClipped: content ? content.scrollHeight - content.clientHeight : null,
    fit: ic ? ic.objectFit : null, docScrollW: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) }; })()`);

async function runStory(browser, origin, mode) {
  const { page, log, m } = await openGame(browser, origin, mode.name);
  const label = `${mode.name} story`;
  const before = await mapSnapshot(page);
  await openReplayStory(page);
  const beforeOpen = await mapSnapshot(page);
  const requestsBefore = log.requests.length;
  const opened = await clickReplay(page);
  check(`${label}: Replay Story opens the story overlay`, opened);
  await page.waitForTimeout(3000);
  const s = await storyMetrics(page);
  check(`${label}: overlay is showing`, s.shown === true);
  const sc = s.scene;
  const portrait = s.vh > s.vw;
  const wFrac = sc.w / s.vw;
  const hFrac = sc.h / s.vh;
  if (portrait) {
    check(`${label}: portrait story shell is near-fullscreen (>=92% W and >=92% H)`, wFrac >= 0.92 && hFrac >= 0.92, `${pct(sc.w, s.vw)} x ${pct(sc.h, s.vh)} of ${s.vw}x${s.vh}`);
  } else {
    const ratio = sc.w / sc.h;
    check(`${label}: landscape story shell is the largest 16:9 frame the viewport allows (>=92% of the limiting dimension)`, wFrac >= 0.92 || hFrac >= 0.92, `${pct(sc.w, s.vw)} x ${pct(sc.h, s.vh)} of ${s.vw}x${s.vh}`);
    check(`${label}: landscape story keeps its 16:9 frame (no crop, no stretch)`, Math.abs(ratio - 16 / 9) / (16 / 9) <= 0.006, `ratio=${ratio.toFixed(4)}`);
  }
  const viewport = { l: 0, t: 0, r: s.vw, b: s.vh };
  check(`${label}: shell stays inside the viewport`, inside(sc, viewport), JSON.stringify(sc));
  check(`${label}: controls, close and subtitle stay inside the shell and the viewport`,
    inside(s.controls, sc) && inside(s.closeX, sc) && inside(s.content, sc) && inside(s.controls, viewport) && inside(s.closeX, viewport) && inside(s.content, viewport),
    JSON.stringify({ controls: s.controls, closeX: s.closeX, content: s.content }));
  check(`${label}: touch targets are >=44px (skip / replay / close)`, s.btns.length >= 2 && s.btns.every((b) => b.h >= 43.5 && b.w >= 43.5) && s.closeX.w >= 43.5 && s.closeX.h >= 43.5, JSON.stringify({ btns: s.btns.map((b) => [Math.round(b.w), Math.round(b.h)]), closeX: [s.closeX.w, s.closeX.h] }));
  check(`${label}: subtitle is readable (>=14px) and not clipped`, s.lineFont >= 14 && (s.contentClipped === null || s.contentClipped <= 1), `font=${s.lineFont} clipped=${s.contentClipped}`);
  check(`${label}: story art keeps its aspect ratio (object-fit is contain or cover, never fill)`, s.fit === 'contain' || s.fit === 'cover', `fit=${s.fit}`);
  check(`${label}: no horizontal overflow`, s.docScrollW <= s.vw + 1, `scrollWidth=${s.docScrollW} vw=${s.vw}`);
  const safe = await safeAreaOffsets(page);
  const shot = captureDir ? `${mode.name}_story.png` : null;
  if (captureDir) await page.screenshot({ path: path.join(captureDir, shot) });
  measurements.push({ mode: mode.name, viewport: `${s.vw}x${s.vh}`, phase: 'story', shell: [Math.round(sc.w), Math.round(sc.h)], shellPctW: +(100 * wFrac).toFixed(1), shellPctH: +(100 * hFrac).toFixed(1), safeArea: safe, capture: shot });
  // Close restores the exact prior Adventure state.
  await page.locator('#boss-cinematic-close-x').click({ timeout: 8000 });
  await page.waitForTimeout(1500);
  const closed = await storyMetrics(page);
  const after = await mapSnapshot(page);
  check(`${label}: closing hides the overlay (no stuck overlay)`, closed.shown === false && closed.aria === 'true' && closed.count === 1, JSON.stringify({ shown: closed.shown, aria: closed.aria, count: closed.count }));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  check(`${label}: closing restores the exact prior Adventure state (selection, scroll, shell, stage, drawer, owner)`,
    beforeOpen.selected === after.selected && same(beforeOpen.scroll, after.scroll) && same(beforeOpen.shell, after.shell) && same(beforeOpen.stage, after.stage) && beforeOpen.drawer === after.drawer && beforeOpen.owner === after.owner && before.owner === after.owner,
    JSON.stringify({ beforeOpen, after }));
  const reopened = await clickReplay(page);
  await page.waitForTimeout(2000);
  const again = await storyMetrics(page);
  check(`${label}: the story can be opened again after closing (no stale listener, still one overlay)`, reopened && again.shown === true && again.count === 1);
  const writes = log.requests.slice(requestsBefore).filter((r) => !['GET', 'HEAD', 'OPTIONS'].includes(r.method));
  check(`${label}: Replay Story is presentation-only (REPLAY_WRITE_REQUESTS=0)`, writes.length === 0, JSON.stringify(writes.slice(0, 3)));
  check(`${label}: no page errors`, log.errors.length === 0, log.errors.slice(0, 2).join(' | '));
  await page.close();
  return { replayWrites: writes.length };
}

// The first-entry film ends in a READY card (kicker / title / books / line / rules) with the primary CTA
// positioned OUTSIDE the card box (bottom: calc(100% + 12px)).  A clip on the card hides that CTA and
// strands the player, so the ready state is asserted on its own: an unseen opening is entered, the film
// plays, and the natural end-state class is applied to the running overlay.
async function runReadyCard(browser, origin, mode) {
  const { page, log } = await openGame(browser, origin, mode.name, { seen: false });
  const label = `${mode.name} story ready card`;
  await page.evaluate(() => document.querySelector('[data-zone="k21_25"]').click());
  await page.waitForFunction(() => !!document.querySelector('#boss-cinematic.show.intro-film'), { timeout: 15000 });
  await page.waitForTimeout(1500);
  await page.evaluate(() => document.querySelector('#boss-cinematic').classList.add('ready'));
  await page.waitForTimeout(1500);
  const r = await page.evaluate(`(() => { const R = ${rectOf}; const btn = document.querySelector('#boss-cinematic .boss-cinematic-btn'); const c = document.querySelector('#boss-cinematic .boss-cinematic-content'); const cs = btn && getComputedStyle(btn); const cc = c && getComputedStyle(c);
    const b = btn && btn.getBoundingClientRect(); const hit = b && b.width > 0 ? document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2) : null;
    return { vw: innerWidth, vh: innerHeight, scene: R('#boss-cinematic .boss-cinematic-scene'), content: R('#boss-cinematic .boss-cinematic-content'), btn: R('#boss-cinematic .boss-cinematic-btn'),
      btnOpacity: cs && cs.opacity, btnPointer: cs && cs.pointerEvents, btnDisplay: cs && cs.display, hitsBtn: !!(hit && btn && (hit === btn || btn.contains(hit))),
      overflowY: cc && cc.overflowY, scrollH: c && c.scrollHeight, clientH: c && c.clientHeight, cls: document.querySelector('#boss-cinematic').className }; })()`);
  check(`${label}: the film is in its ready state`, /\bready\b/.test(r.cls), r.cls);
  const viewport = { l: 0, t: 0, r: r.vw, b: r.vh };
  check(`${label}: the primary CTA has a box, is opaque and takes pointer events`, !!r.btn && r.btn.w > 0 && r.btn.h > 0 && r.btnDisplay !== 'none' && Number(r.btnOpacity) === 1 && r.btnPointer !== 'none', JSON.stringify({ btn: r.btn, op: r.btnOpacity, pe: r.btnPointer }));
  check(`${label}: the primary CTA is inside the scene and the viewport`, inside(r.btn, r.scene) && inside(r.btn, viewport), JSON.stringify({ btn: r.btn, scene: r.scene }));
  check(`${label}: the primary CTA is not clipped or covered (a hit-test at its centre returns the CTA)`, r.hitsBtn === true, `overflowY(card)=${r.overflowY} card=${JSON.stringify(r.content)}`);
  check(`${label}: the ready card is inside the scene and not clipped (no overflow clip, or nothing overflowing)`, inside(r.content, r.scene) && (r.overflowY === 'visible' || r.scrollH <= r.clientH + 1), JSON.stringify({ content: r.content, overflowY: r.overflowY, scrollH: r.scrollH, clientH: r.clientH }));
  const shot = captureDir ? `${mode.name}_story_ready.png` : null;
  if (captureDir) await page.screenshot({ path: path.join(captureDir, shot) });
  check(`${label}: no page errors`, log.errors.length === 0, log.errors.slice(0, 2).join(' | '));
  await page.close();
}

const battleMetrics = (page) => page.evaluate(`(() => { const R = ${rectOf}; const vw = innerWidth, vh = innerHeight; const root = document.scrollingElement;
  const shown = (sel) => { const e = document.querySelector(sel); if (!e) return 0; const c = getComputedStyle(e); const r = e.getBoundingClientRect(); return (c.display !== 'none' && c.visibility !== 'hidden' && r.width > 0 && r.height > 0) ? 1 : 0; };
  const cv = R('#board-canvas-wrap'); const hit = (x, y) => { const e = document.elementFromPoint(x, y); return !!(e && e.closest('#board-canvas-wrap')); };
  const pts = cv ? [[.5, .5], [.1, .1], [.9, .1], [.1, .9], [.9, .9]].map(([fx, fy]) => hit(cv.l + cv.w * fx, cv.t + cv.h * fy)) : [];
  const btn = R('#board-col > .btn-row'); const btnHit = btn ? (() => { const e = document.elementFromPoint(btn.l + btn.w / 2, btn.t + btn.h / 2); return !!(e && e.closest('.btn-row')); })() : false;
  return { vw, vh, canvas: cv, anchor: R('.quiz-board-anchor'), btnRow: btn, btnHit, sideCol: R('#side-col'), arena: R('#battle-arena'), today: R('#today-mini'), header: R('.q-header'),
    scrollH: Math.max(root.scrollHeight, document.body.scrollHeight), scrollW: Math.max(root.scrollWidth, document.documentElement.scrollWidth),
    mapVisible: ['#e9-adventure-shell', '#e9-map-stage', '#e9-top-hud-slot', '#e9-world-stage-slot', '#e9-bottom-dock-slot', '#e9-left-nav-slot', '#e9-right-cards-slot'].reduce((n, s) => n + shown(s), 0),
    welcomeDisplay: getComputedStyle(document.querySelector('#welcome-state')).display, boardHits: pts,
    dup: { board: document.querySelectorAll('#board-canvas-wrap').length, combatRow: document.querySelectorAll('[data-a032-combat-surface]').length, monsterPanel: document.querySelectorAll('#monster-panel').length, shell: document.querySelectorAll('#e9-adventure-shell').length },
    owner: document.body.dataset.adventureShellOwner || null }; })()`);

async function runBattle(browser, origin, mode) {
  const { page, log, m } = await openGame(browser, origin, mode.name);
  const label = `${mode.name} battle`;
  const before = await mapSnapshot(page);
  const mapBeforeShot = captureDir ? `${mode.name}_map_before_battle.png` : null;
  if (captureDir) await page.screenshot({ path: path.join(captureDir, mapBeforeShot) });
  await page.getByRole('button', { name: /繼續冒險/ }).first().click({ timeout: 10000 });
  await page.waitForSelector('#board-canvas-wrap canvas', { state: 'visible', timeout: 15000 });
  await page.waitForTimeout(2500);
  const b = await battleMetrics(page);
  const cv = b.canvas;
  const viewport = { l: 0, t: 0, r: b.vw, b: b.vh };
  const pwa = mode.kind.startsWith('pwa');
  check(`${label}: the question / battle surface owns the shell (owner=e10-battle)`, b.owner === 'e10-battle', `owner=${b.owner}`);
  check(`${label}: PORTRAIT_MAP_VISIBLE_DURING_BATTLE=0 (no map, HUD, dock, nav or drawer is laid out behind the battle)`, b.mapVisible === 0, `visible map elements=${b.mapVisible}`);
  check(`${label}: the world-map container is hidden (#welcome-state display:none)`, b.welcomeDisplay === 'none', b.welcomeDisplay);
  check(`${label}: the board is a square canvas (never stretched)`, !!cv && Math.abs(cv.w - cv.h) <= 1.5, JSON.stringify(cv));
  check(`${label}: the board is fully inside the viewport`, inside(cv, viewport), JSON.stringify({ cv, vw: b.vw, vh: b.vh }));
  check(`${label}: nothing covers the board (centre + four inner points hit-test to the board)`, b.boardHits.length === 5 && b.boardHits.every(Boolean), JSON.stringify(b.boardHits));
  check(`${label}: the answer controls are inside the viewport and hit-test to the buttons (no rotation, no scroll)`, inside(b.btnRow, viewport) && b.btnHit, JSON.stringify({ btnRow: b.btnRow, hit: b.btnHit }));
  check(`${label}: no horizontal overflow`, b.scrollW <= b.vw + 1, `scrollWidth=${b.scrollW} vw=${b.vw}`);
  check(`${label}: no duplicate battle surface (one board, one combat row, one monster panel, one shell)`, b.dup.board === 1 && b.dup.combatRow === 1 && b.dup.monsterPanel === 1 && b.dup.shell === 1, JSON.stringify(b.dup));
  const portrait = b.vh > b.vw;
  if (mode.kind === 'pwa-portrait') {
    check(`${label}: PORTRAIT_BOARD_USABLE -- the board takes >=78% of the width`, cv.w / b.vw >= 0.78, `board=${Math.round(cv.w)} = ${pct(cv.w, b.vw)} of ${b.vw}`);
    check(`${label}: PORTRAIT_ROTATION_REQUIRED=NO -- title, board, controls and the Player/Monster HP rows are all on the first screen`, !!b.arena && b.arena.b <= b.vh && !!b.header && b.header.t >= 0, `arenaBottom=${b.arena && Math.round(b.arena.b)} vh=${b.vh}`);
    const reach = await page.evaluate(() => { const t = document.querySelector('#today-mini'); if (!t) return null; t.scrollIntoView({ block: 'end' }); const r = t.getBoundingClientRect(); const out = { bottom: r.bottom, vh: innerHeight }; window.scrollTo(0, 0); document.querySelectorAll('main, .practice').forEach((e) => { e.scrollTop = 0; }); return out; });
    check(`${label}: the rest of the HUD (progress) is reachable by scrolling`, !!reach && reach.bottom <= reach.vh + 1, JSON.stringify(reach));
  }
  if (mode.kind === 'pwa-landscape') {
    check(`${label}: LANDSCAPE_BATTLE_ENLARGED -- the board fills >=66% of the viewport height (was ~50%)`, cv.h / b.vh >= 0.66, `board=${Math.round(cv.h)} = ${pct(cv.h, b.vh)} of ${b.vh}`);
    check(`${label}: the whole battle composition fits the viewport (no vertical scroll)`, b.scrollH <= b.vh + 1, `scrollHeight=${b.scrollH} vh=${b.vh}`);
    const left = b.anchor.l;
    const right = b.vw - b.sideCol.r;
    check(`${label}: no large dead side margins (<=10% of the width each)`, left <= 0.10 * b.vw && right <= 0.10 * b.vw, `left=${Math.round(left)} right=${Math.round(right)} vw=${b.vw}`);
    check(`${label}: the Player/Monster HUD stays beside the board`, b.sideCol.l >= b.anchor.r - 1 && b.sideCol.t < b.anchor.b, JSON.stringify({ side: b.sideCol, anchor: b.anchor }));
  }
  if (mode.boardFloor) {
    check(`${label}: regression lock -- the board is not smaller than the pre-corrective ${mode.boardFloor}px`, cv.w >= mode.boardFloor - 1, `board=${Math.round(cv.w)}`);
  }
  if (mode.kind === 'wide-landscape') {
    check(`${label}: board fills >=65% of the height (same or better than before)`, cv.h / b.vh >= 0.65, pct(cv.h, b.vh));
  }
  const safe = await safeAreaOffsets(page);
  const battleShot = captureDir ? `${mode.name}_battle.png` : null;
  if (captureDir) await page.screenshot({ path: path.join(captureDir, battleShot) });
  const requestsBefore = log.requests.length;
  await page.locator('#btn-return-map').click({ timeout: 8000 });
  await page.waitForTimeout(3000);
  const after = await mapSnapshot(page);
  const same = (x, y) => JSON.stringify(x) === JSON.stringify(y);
  check(`${label}: leaving the battle restores the exact map (shell, stage, selection, scroll, owner e10-map, map visible)`,
    same(before.shell, after.shell) && same(before.stage, after.stage) && before.selected === after.selected && same(before.scroll, after.scroll) && after.owner === 'e10-map' && after.welcomeHidden === false,
    JSON.stringify({ before, after }));
  const mapShot = captureDir ? `${mode.name}_map_after_exit.png` : null;
  if (captureDir) await page.screenshot({ path: path.join(captureDir, mapShot) });
  await page.getByRole('button', { name: /繼續冒險/ }).first().click({ timeout: 10000 });
  await page.waitForSelector('#board-canvas-wrap canvas', { state: 'visible', timeout: 15000 });
  await page.waitForTimeout(1500);
  const b2 = await battleMetrics(page);
  check(`${label}: entering the battle a second time creates no duplicate surface`, b2.dup.board === 1 && b2.dup.combatRow === 1 && b2.dup.monsterPanel === 1 && b2.dup.shell === 1 && b2.mapVisible === 0, JSON.stringify({ dup: b2.dup, mapVisible: b2.mapVisible }));
  check(`${label}: no page errors`, log.errors.length === 0, log.errors.slice(0, 2).join(' | '));
  void requestsBefore;
  measurements.push({
    mode: mode.name, viewport: `${b.vw}x${b.vh}`, phase: 'battle', board: [Math.round(cv.w), Math.round(cv.h)], boardPctW: +(100 * cv.w / b.vw).toFixed(1), boardPctH: +(100 * cv.h / b.vh).toFixed(1),
    deadMarginLeft: pwa || mode.kind === 'wide-landscape' ? Math.round(b.anchor.l) : null, deadMarginRight: Math.round(b.vw - Math.max(b.sideCol.r, b.anchor.r)), deadMarginBottom: Math.round(b.vh - Math.max(b.btnRow.b, cv.b)),
    hudArenaBottom: Math.round(b.arena.b), scrollHeight: Math.round(b.scrollH), mapVisibleDuringBattle: b.mapVisible, duplicateBattleSurfaces: b.dup.board + b.dup.combatRow + b.dup.monsterPanel + b.dup.shell - 4, safeArea: safe, orientation: portrait ? 'portrait' : 'landscape',
    captures: { mapBeforeBattle: mapBeforeShot, battle: battleShot, mapAfterExit: mapShot },
  });
  await page.close();
  return { mapVisible: b.mapVisible };
}

const { server, origin } = await startStaticServer(repoRoot);
const browser = await chromium.launch({ executablePath: chromePath });
let replayWrites = 0;
let maxMapVisible = 0;
try {
  for (const mode of RUN_MODES) {
    console.log(`\n== ${mode.name} ${IPAD_VIEWPORTS[mode.name].vp.width}x${IPAD_VIEWPORTS[mode.name].vp.height}`);
    replayWrites += (await runStory(browser, origin, mode)).replayWrites;
    await runReadyCard(browser, origin, mode);
    maxMapVisible = Math.max(maxMapVisible, (await runBattle(browser, origin, mode)).mapVisible);
  }
} finally {
  await browser.close();
  server.close();
}

check(`E10 boot identity: every one of the ${bootChecked} pages booted the current E10 runtime (no legacy map, no query flags, runtime ready)`, bootFailures.length === 0, bootFailures.slice(0, 2).join(' | '));
check('REPLAY_WRITE_REQUESTS=0 across every story flow', replayWrites === 0, `writes=${replayWrites}`);
check('PORTRAIT_MAP_VISIBLE_DURING_BATTLE=0 across every mode', maxMapVisible === 0, `max=${maxMapVisible}`);

if (captureDir) {
  fssync.writeFileSync(path.join(captureDir, 'measurements.json'), JSON.stringify({ generatedBy: 'run_a013_pwa_fullscreen_story_battle_contract.mjs', measurements, passed, failed: failures.length }, null, 2));
}
console.log(`\n${passed} passed, ${failures.length} failed`);
if (failures.length) {
  console.error(`\n${failures.length} A013 fullscreen assertion(s) failed:`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log('\nAll A013 fullscreen story + battle assertions passed.');
