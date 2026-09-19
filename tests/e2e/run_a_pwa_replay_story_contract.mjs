/*
 * A_PWA_PORTRAIT_AND_REPLAY_CORRECTIVE_CANDIDATE_005 -- Replay Story contract.
 *
 * Product contract (Coordinator decisions 1-3):
 *
 *   Replay Story is PRESENTATION ONLY, and its availability is the story
 *   model's answer to "is at least one replayable segment CURRENTLY UNLOCKED for
 *   this zone?", for a zone that has an authoritative record and is not locked.
 *   Whether the zone is cleared is not a condition, and a placement-skipped zone
 *   gets no special case: the model already unlocks a zone's opening on entry
 *   access and everything from post-clear on only after an authoritative clear.
 *
 * This runs the real E9 shell in a real engine in every mode the product
 * ships -- desktop browser, iPad Safari (portrait + landscape) and the installed
 * iPad PWA (portrait + landscape, driven through the unmodified classifier) --
 * and asserts, per mode, that the affordance is present or absent exactly as
 * the contract says and that the answer is identical across all modes.
 *
 * It also proves the negative space that matters for a presentation-only
 * feature: a Replay click issues no mutating request and writes no storage.
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

// No E9 flags in the URL: the shell boots the way Production boots it, from the
// /api/auth/me rollout decision (see e10_production_boot_fixture.mjs).
const SHELL_QUERY = PRODUCTION_SHELL_QUERY;
const ZONE4_MANIFEST_PATH = '/ZONE4_RUNTIME_MANIFEST.json';
const ZONE3 = 'k16_20';
const ZONE4 = 'k11_15';
const ZONE5 = 'k6_10';
const ZONE_LABEL = { [ZONE3]: 'Zone 3', [ZONE4]: 'Zone 4', [ZONE5]: 'Zone 5' };

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

// Zones 1 and 2 are cleared and Zones 3 and 4 take the state under test. Zone 5 is
// what the server would make current next. The payload is the REAL bootstrap shape
// (see e10_production_boot_fixture.mjs).
const L = 'locked';
const STATE_ZONES = {
  LOCKED: ['completed', 'completed', L, L, L, L, L, L, L, L],
  // The ordinary player: Zone 3 is the open current zone, nothing skipped or cleared.
  PROGRESSING: ['completed', 'completed', 'unlocked', L, L, L, L, L, L, L],
  SKIPPED_BY_PLACEMENT: ['completed', 'completed', 'skipped', 'skipped', 'unlocked', L, L, L, L, L],
  CLEARED: ['completed', 'completed', 'completed', 'completed', 'unlocked', L, L, L, L, L],
  // Zone 3's Lord is ready (real threshold met): its boss-ready segment is
  // legitimately unlocked in addition to the opening. Selecting a Lord-ready zone
  // whose film has not been seen launches the Lord card / first-entry overlay (the
  // shipped behaviour), so only Zone 3 is asserted in this state.
  BOSS_READY: ['completed', 'completed', 'bossready', 'unlocked', 'unlocked', L, L, L, L, L],
  // Not emitted by the real server; proves the model, not the status label, decides.
  ACCESSIBLE_NO_UNLOCKED_STORY: ['completed', 'completed', 'unlocked_no_entry', 'unlocked_no_entry', L, L, L, L, L, L],
};
const bootstrapFor = (state) => {
  const zones = STATE_ZONES[state];
  if (!zones) throw new Error(`unknown state ${state}`);
  // The openings are marked seen so selecting a zone shows its CARD instead of launching
  // the first-entry film (shipped behaviour, and it would cover the button). Not in
  // BOSS_READY: there the film flow is what loads the legacy map's raw zone records, and
  // without it the story model reads the E9-normalized record, which carries no `boss`
  // block, so a Lord-ready zone's boss-ready segment stays locked (fails closed). That is
  // pre-existing unlock behaviour, out of scope here and recorded rather than changed.
  return realBootstrap(zones, { seenIntro: state === 'BOSS_READY' ? [] : [ZONE3, ZONE4, ZONE5] });
};

function realIpadInit({ w, h, type, standalone }) {
  return `(function(){var state={w:${w},h:${h},type:'${type}'};window.__geoDevice=state;
  function def(t,k,g){try{Object.defineProperty(t,k,{configurable:true,get:g});}catch(e){}}
  def(navigator,'maxTouchPoints',function(){return 5;});
  def(navigator,'standalone',function(){return ${standalone ? 'true' : 'false'};});
  def(screen,'width',function(){return state.w;});def(screen,'height',function(){return state.h;});
  try{def(screen.orientation,'type',function(){return state.type;});}catch(e){}
  })();`;
}

const IPAD_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15';

const PORTRAIT_MODES = new Set(['IPAD_SAFARI_PORTRAIT', 'PWA_PORTRAIT']);
const MODES = {
  DESKTOP_BROWSER: { width: 1440, height: 900, dsf: 1, ipad: null },
  IPAD_SAFARI_PORTRAIT: { width: 820, height: 1180, dsf: 2, ipad: { w: 820, h: 1180, type: 'portrait-primary', standalone: false } },
  IPAD_SAFARI_LANDSCAPE: { width: 1180, height: 820, dsf: 2, ipad: { w: 1180, h: 820, type: 'landscape-primary', standalone: false } },
  PWA_PORTRAIT: { width: 1640, height: 2360, dsf: 1, ipad: { w: 820, h: 1180, type: 'portrait-primary', standalone: true } },
  PWA_LANDSCAPE: { width: 2360, height: 1640, dsf: 1, ipad: { w: 1180, h: 820, type: 'landscape-primary', standalone: true } },
};

// Records everything the page sends so a "presentation only" claim can be
// checked against what actually went over the wire.
async function openShell(browser, origin, mode, state, { zone4Manifest = 'pass' } = {}) {
  const page = await browser.newPage({
    viewport: { width: mode.width, height: mode.height },
    deviceScaleFactor: mode.dsf,
    hasTouch: !!mode.ipad,
    ...(mode.ipad ? { userAgent: IPAD_UA } : {}),
  });
  if (mode.ipad) await page.addInitScript(realIpadInit(mode.ipad));
  const log = { requests: [], manifestRequests: 0 };
  page.on('request', (req) => {
    log.requests.push({ method: req.method(), url: req.url() });
    if (req.url().includes(ZONE4_MANIFEST_PATH)) log.manifestRequests += 1;
  });
  await installProductionBootRoutes(page, { bootstrap: bootstrapFor(state) });
  if (zone4Manifest === 'fail') {
    await page.route(`**${ZONE4_MANIFEST_PATH}*`, (route) => route.fulfill({ status: 500, body: 'unavailable' }));
  }
  await page.goto(`${origin}/index.html${SHELL_QUERY}`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#e9-adventure-shell', { timeout: 15000 });
  await page.waitForTimeout(2200);
  // Only evidence about the CURRENT E10 UI if the page really booted it.
  const boot = await readBootIdentity(page);
  if (!isCurrentE10(boot)) bootFailures.push(`${state}/${mode.width}x${mode.height}: ${JSON.stringify(boot)}`);
  bootChecked += 1;
  return { page, log };
}

async function selectZone(page, key) {
  await page.evaluate((k) => {
    const tile = document.querySelector(`[data-zone="${k}"]`);
    if (tile) tile.click();
  }, key);
  // Side-panel surfaces (desktop, landscape) keep the zone card in a drawer that
  // starts collapsed; a player opens it with its handle. Portrait and mobile own
  // the card in the page flow and have no drawer to open.
  await page.evaluate(() => {
    const owner = document.querySelector('[data-e10-detail-owner]');
    const toggle = document.querySelector('#e9-right-drawer-toggle');
    if (owner && owner.getAttribute('data-e10-detail-owner') === 'side-panel'
        && toggle && toggle.getAttribute('aria-expanded') !== 'true') toggle.click();
  });
}

const drawerOpen = (page) => page.evaluate(() => {
  const slot = document.querySelector('#e9-right-cards-slot');
  return !!slot && slot.classList.contains('is-drawer-open');
});

// Whether ANY Replay Story affordance is actually presented to the player, on
// whichever surface this mode uses (portrait selected-zone card or landscape
// drawer). Presented means not hidden, not disabled and laid out with a box.
function readReplay(page, key) {
  return page.evaluate((zoneKey) => {
    const present = (el) => {
      if (!el) return false;
      const box = el.getBoundingClientRect();
      return el.hidden !== true && el.disabled !== true && box.width > 0 && box.height > 0;
    };
    const details = document.querySelector('#e9-world-stage-details-replay');
    const drawer = document.querySelector('[data-e10-zone-replay]');
    let segments = null;
    try {
      const zone = _zoneForCinematic(zoneKey);
      segments = _cinematicReplay().replaySequence(zone).map((segment) => segment.phase);
    } catch (error) { segments = `error: ${error.message}`; }
    // The surfaces update on selection, so a read taken straight after a click
    // could still show the previous zone's button. Report which zone each
    // surface is currently showing so callers only trust a settled read.
    let drawerZone = null;
    for (let node = drawer; node && !drawerZone; node = node.parentElement) {
      if (node.__e10SelectedZoneKey) drawerZone = node.__e10SelectedZoneKey;
    }
    const stageRoot = document.querySelector('#e9-world-stage-slot') || document.querySelector('#adventure-stage');
    const stageState = stageRoot && stageRoot.__e9WorldStageState;
    // WHERE the button is, judged the way a player experiences it: it must be laid
    // out AND the topmost thing at its centre (a full-screen film overlay covering it
    // does not count as visible).
    const candidates = new Set([
      ...document.querySelectorAll('#e9-world-stage-details-replay, [data-e10-zone-replay]'),
      ...Array.from(document.querySelectorAll('button')).filter((b) => /重溫故事|Replay Story/.test(b.textContent || '')),
    ]);
    const card = document.querySelector('#e9-world-stage-details');
    const map = document.querySelector('#e9-map-stage');
    const slot = document.querySelector('#e9-right-cards-slot');
    const cardBox = card ? card.getBoundingClientRect() : null;
    const mapBox = map ? map.getBoundingClientRect() : null;
    const visible = Array.from(candidates).filter((el) => {
      const b = el.getBoundingClientRect();
      if (el.hidden || el.disabled || b.width <= 0 || b.height <= 0) return false;
      const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
      return hit === el || el.contains(hit);
    }).map((el) => {
      const b = el.getBoundingClientRect();
      return {
        inCard: !!card && card.contains(el),
        inDrawer: !!slot && slot.contains(el),
        inMapSubtree: !!map && map.contains(el),
        overlapsMap: !!mapBox && !(b.bottom <= mapBox.top || b.top >= mapBox.bottom || b.right <= mapBox.left || b.left >= mapBox.right),
        insideCardBox: !!cardBox && b.left >= cardBox.left - 1 && b.right <= cardBox.right + 1 && b.top >= cardBox.top - 1 && b.bottom <= cardBox.bottom + 1,
        belowMap: !!mapBox && b.top >= mapBox.bottom - 1,
      };
    });
    const placement = {
      overlayShowing: !!document.querySelector('#boss-cinematic.show'),
      visibleCount: visible.length,
      // Portrait: exactly the buttons that sit inside the selected-zone card, below the map.
      cardCount: visible.filter((v) => v.inCard && v.insideCardBox && v.belowMap && !v.overlapsMap).length,
      // Anywhere a player would read as a floating map overlay: inside the map subtree,
      // over the map art, or outside both the card and the drawer.
      mapOverlayCount: visible.filter((v) => v.inMapSubtree || (v.inCard && v.overlapsMap) || (!v.inCard && !v.inDrawer)).length,
      drawerCount: visible.filter((v) => v.inDrawer).length,
    };
    return {
      placement,
      settled: (stageState && stageState.selectedZoneKey) === zoneKey && drawerZone === zoneKey,
      presented: present(details) || present(drawer),
      predicate: window.E9.zoneReplayStoryAvailable(zoneKey),
      segments,
      provider: window.Zone4CinematicContent && window.Zone4CinematicContent.isReady
        ? window.Zone4CinematicContent.isReady() : null,
    };
  }, key);
}

async function waitFor(page, key, predicate, timeoutMs = 6000) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    last = await readReplay(page, key);
    if (last.settled && predicate(last)) return last;
    await page.waitForTimeout(150);
  }
  return last;
}

const failures = [];
let bootChecked = 0;
const bootFailures = [];
function check(label, condition, detail) {
  if (condition) { console.log(`  PASS  ${label}`); return; }
  failures.push(`${label} -- ${detail}`);
  console.log(`  FAIL  ${label} -- ${detail}`);
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// The contract for each (state, zone): is Replay presented, and which segments
// does the model unlock. EVERY zone declares a pre-play segment (Zone 3: pre-play,
// boss-ready, post-clear; Zone 4: pre-play, post-clear; Zones 5-10: pre-play), and
// entry access unlocks it -- so an accessible zone offers Replay whether or not it
// was cleared or skipped past. Boss-ready needs a met Lord threshold; post-clear
// and later need an authoritative clear.
const NOTHING = { present: false, segments: [] };
const OPENING = { present: true, segments: ['pre_play'] };
const EXPECT = {
  LOCKED: { [ZONE3]: NOTHING, [ZONE4]: NOTHING },
  SKIPPED_BY_PLACEMENT: { [ZONE3]: OPENING, [ZONE4]: OPENING, [ZONE5]: OPENING },
  BOSS_READY: { [ZONE3]: { present: true, segments: ['pre_play', 'boss_ready'] } },
  CLEARED: {
    [ZONE3]: { present: true, segments: ['pre_play', 'boss_ready', 'post_clear'] },
    [ZONE4]: { present: true, segments: ['pre_play', 'post_clear'] },
    [ZONE5]: OPENING,
  },
  ACCESSIBLE_NO_UNLOCKED_STORY: { [ZONE3]: NOTHING, [ZONE4]: NOTHING },
};

const { server, origin } = await startStaticServer(repoRoot);
const browser = await chromium.launch({ executablePath: chromePath });
const matrix = {}; // state -> zone -> mode -> presented

try {
  for (const [state, expected] of Object.entries(EXPECT)) {
    matrix[state] = Object.fromEntries(Object.keys(expected).map((key) => [key, {}]));
    console.log(`STATE ${state}`);
    for (const [modeName, mode] of Object.entries(MODES)) {
      const { page } = await openShell(browser, origin, mode, state);
      for (const [key, want] of Object.entries(expected)) {
        await selectZone(page, key);
        // Zone 4's provider loads lazily; give the deterministic refresh time
        // to land before the answer is read.
        const result = await waitFor(page, key,
          (r) => r.presented === want.present && same(r.segments, want.segments), 6000);
        matrix[state][key][modeName] = result.presented;
        check(`${modeName} ${state} ${ZONE_LABEL[key]}: Replay ${want.present ? 'presented' : 'hidden'}`,
          result.presented === want.present,
          `presented=${result.presented} predicate=${result.predicate} segments=${JSON.stringify(result.segments)}`);
        check(`${modeName} ${state} ${ZONE_LABEL[key]}: replay contents are exactly the unlocked segments`,
          same(result.segments, want.segments),
          `segments=${JSON.stringify(result.segments)} expected=${JSON.stringify(want.segments)}`);
        // Placement follows the form factor. STATE is shared; the DOM anchor is not.
        const pl = result.placement;
        if (pl.overlayShowing) continue; // a Lord/first-entry film owns the screen (shipped behaviour)
        const portrait = PORTRAIT_MODES.has(modeName);
        check(`${modeName} ${state} ${ZONE_LABEL[key]}: REPLAY_MAP_OVERLAY_COUNT=0`,
          pl.mapOverlayCount === 0, `mapOverlayCount=${pl.mapOverlayCount} (${JSON.stringify(pl)})`);
        if (portrait) {
          check(`${modeName} ${state} ${ZONE_LABEL[key]}: REPLAY_CARD_COUNT=${want.present ? 1 : 0} (inside the selected-zone card, below the map)`,
            pl.cardCount === (want.present ? 1 : 0), `cardCount=${pl.cardCount} (${JSON.stringify(pl)})`);
          check(`${modeName} ${state} ${ZONE_LABEL[key]}: no Replay button in the drawer on a portrait surface`,
            pl.drawerCount === 0, `drawerCount=${pl.drawerCount}`);
        } else {
          check(`${modeName} ${state} ${ZONE_LABEL[key]}: the Replay stays in the right-hand drawer (${want.present ? 1 : 0})`,
            pl.drawerCount === (want.present ? 1 : 0) && pl.cardCount === 0, `drawerCount=${pl.drawerCount} cardCount=${pl.cardCount}`);
        }
      }
      await page.close();
    }
    for (const key of Object.keys(expected)) {
      const values = Object.values(matrix[state][key]);
      check(`${state} ${ZONE_LABEL[key]}: the answer is identical in every mode`,
        values.every((v) => v === values[0]), JSON.stringify(matrix[state][key]));
    }
  }

  // LANDSCAPE HARD LOCK. The right-hand zone card is a drawer that starts collapsed
  // and that the shipped code opens on its own only for a CLEARED zone that has a
  // story. Replay availability no longer implies "cleared", and an earlier revision
  // let that widen the auto-open to every accessible zone -- the drawer then opened
  // on first load and covered the map, a change to the accepted landscape
  // presentation. This block pins the shipped behaviour, so it must also pass on the
  // previous sources.
  console.log('LANDSCAPE DRAWER DEFAULT STATE (must match the shipped presentation)');
  for (const modeName of ['DESKTOP_BROWSER', 'IPAD_SAFARI_LANDSCAPE', 'PWA_LANDSCAPE']) {
    for (const [state, afterSelect] of [['PROGRESSING', false], ['SKIPPED_BY_PLACEMENT', false], ['CLEARED', true]]) {
      const { page } = await openShell(browser, origin, MODES[modeName], state);
      const initial = await drawerOpen(page);
      check(`${modeName} ${state}: the drawer starts collapsed on first load`, initial === false, `open=${initial}`);
      for (const key of [ZONE3, ZONE4]) {
        // Select only -- do not press the handle -- to observe what selection alone does.
        await page.evaluate((k) => { const t = document.querySelector(`[data-zone="${k}"]`); if (t) t.click(); }, key);
        await page.waitForTimeout(700);
        const open = await drawerOpen(page);
        check(`${modeName} ${state} ${ZONE_LABEL[key]}: selecting the zone ${afterSelect ? 'opens' : 'does not open'} the drawer`,
          open === afterSelect, `open=${open}`);
      }
      await page.close();
    }
  }

  // The hard "cleared" gate is gone and nothing replaced it with a
  // placement-specific rule: a zone that is accessible but has nothing unlocked
  // stays hidden, while the placement-skipped zone with an unlocked opening
  // shows -- both decided by the model, not by how the zone was reached.
  console.log('E9-only authoritative snapshot (legacy map progress absent)');
  {
    const { page } = await openShell(browser, origin, MODES.PWA_LANDSCAPE, 'SKIPPED_BY_PLACEMENT');
    const cleared = await page.evaluate(() => {
      try { _adventureProgress = []; return true; } catch (error) { return false; }
    });
    await selectZone(page, ZONE3);
    await page.waitForTimeout(600);
    const r = await readReplay(page, ZONE3);
    check('E9-only snapshot: the legacy progress array could be emptied for this check', cleared, 'could not reset _adventureProgress');
    check('E9-only snapshot: a placement-skipped Zone 3 still answers from the model (opening unlocked)',
      r.predicate === true && same(r.segments, ['pre_play']),
      `predicate=${r.predicate} segments=${JSON.stringify(r.segments)}`);
    await page.close();
  }

  // Zone 4 provider: not ready at first, loads once, refreshes the card.
  console.log('ZONE4 provider lazy load -> deterministic refresh (E)');
  for (const modeName of ['PWA_PORTRAIT', 'PWA_LANDSCAPE']) {
    const { page, log } = await openShell(browser, origin, MODES[modeName], 'CLEARED');
    const before = await readReplay(page, ZONE4);
    check(`${modeName}: Zone 4 provider is NOT loaded before the zone is selected`, before.provider === false,
      `provider=${before.provider}`);
    await selectZone(page, ZONE4);
    const after = await waitFor(page, ZONE4, (r) => r.presented === true, 6000);
    const pz = after.placement;
    if (!pz.overlayShowing) {
      check(`${modeName}: after the lazy Zone 4 provider settles, the Replay is in the ${PORTRAIT_MODES.has(modeName) ? 'selected-zone card' : 'drawer'} and not over the map`,
        pz.mapOverlayCount === 0 && (PORTRAIT_MODES.has(modeName) ? pz.cardCount === 1 : pz.drawerCount === 1), JSON.stringify(pz));
    }
    check(`${modeName}: selecting Zone 4 loads its provider and Replay appears without another interaction`,
      after.presented === true && after.provider === true,
      `presented=${after.presented} provider=${after.provider}`);
    await page.waitForTimeout(1200);
    check(`${modeName}: exactly one manifest request (no loop, no duplicate load)`, log.manifestRequests === 1,
      `manifest requests=${log.manifestRequests}`);
    const others = log.requests.filter((r) => /\/assets\/e10\/audio\//.test(r.url));
    check(`${modeName}: no unrelated cinematic assets are preloaded`, others.length === 0,
      `${others.length} audio requests: ${others.slice(0, 2).map((r) => r.url).join(', ')}`);
    await page.close();
  }

  // F. Provider load failure: fail closed, no mutation, bounded retries.
  console.log('ZONE4 provider load failure (F)');
  for (const modeName of ['PWA_PORTRAIT', 'PWA_LANDSCAPE']) {
    const { page, log } = await openShell(browser, origin, MODES[modeName], 'CLEARED', { zone4Manifest: 'fail' });
    await selectZone(page, ZONE4);
    await page.waitForTimeout(1800);
    const r = await readReplay(page, ZONE4);
    check(`${modeName}: a failed provider load leaves Replay hidden`, r.presented === false && r.provider === false,
      `presented=${r.presented} provider=${r.provider}`);
    check(`${modeName}: a failed load is not retried in a loop`, log.manifestRequests === 1,
      `manifest requests=${log.manifestRequests} after 1.8s idle`);
    const mutating = log.requests.filter((q) => !['GET', 'HEAD', 'OPTIONS'].includes(q.method) && !/\/api\/(auth|adventure\/bootstrap)/.test(q.url));
    check(`${modeName}: a failed load sends no mutating request`, mutating.length === 0,
      JSON.stringify(mutating.slice(0, 3)));
    await page.close();
  }

  // Presentation only: click Replay on a placement-skipped zone and compare
  // everything that could carry state.
  console.log('PRESENTATION ONLY: a Replay click mutates nothing');
  for (const modeName of ['PWA_PORTRAIT', 'PWA_LANDSCAPE']) {
    const { page, log } = await openShell(browser, origin, MODES[modeName], 'SKIPPED_BY_PLACEMENT');
    await selectZone(page, ZONE3);
    const shown = await waitFor(page, ZONE3, (r) => r.presented === true, 4000);
    check(`${modeName}: Replay is presented on the placement-skipped zone before the click`, shown.presented === true,
      JSON.stringify(shown));
    const snapshot = () => page.evaluate(() => ({
      local: JSON.stringify(Object.keys(localStorage).sort().map((k) => [k, localStorage.getItem(k)])),
      session: JSON.stringify(Object.keys(sessionStorage).sort().map((k) => [k, sessionStorage.getItem(k)])),
    }));
    const before = await snapshot();
    const requestsBefore = log.requests.length;
    await page.evaluate(() => {
      const details = document.querySelector('#e9-world-stage-details-replay');
      const drawer = document.querySelector('[data-e10-zone-replay]');
      const target = [details, drawer].find((el) => el && !el.hidden && el.getBoundingClientRect().width > 0);
      if (target) target.click();
    });
    await page.waitForTimeout(2500);
    const after = await snapshot();
    const sent = log.requests.slice(requestsBefore).filter((q) => !['GET', 'HEAD', 'OPTIONS'].includes(q.method));
    check(`${modeName}: no mutating request after a Replay click`, sent.length === 0, JSON.stringify(sent.slice(0, 3)));
    check(`${modeName}: localStorage is unchanged by a Replay click`, before.local === after.local, `${before.local} -> ${after.local}`);
    check(`${modeName}: sessionStorage is unchanged by a Replay click`, before.session === after.session, `${before.session} -> ${after.session}`);
    await page.close();
  }
} finally {
  await browser.close();
  server.close();
}

check(`E10 boot identity: every one of the ${bootChecked} pages booted the current E10 runtime (no legacy map, no query flags, runtime ready)`,
  bootFailures.length === 0, bootFailures.slice(0, 2).join(' | '));

if (failures.length) {
  console.error(`\n${failures.length} Replay Story assertion(s) failed:`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log('\nAll Replay Story assertions passed.');
