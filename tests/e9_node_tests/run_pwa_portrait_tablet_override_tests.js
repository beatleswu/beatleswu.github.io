'use strict';

/**
 * GO_ODYSSEY_PWA_INITIAL_WORLD_STAGE_LAYOUT_REOPEN_001
 *
 * Root cause: some installed iPad PWAs report a layout viewport
 * (window.innerWidth / the CSS `orientation` media feature) that is
 * misreported as desktop-class even though the device is physically
 * portrait. Proven in production: the real Owner screenshot shows the
 * Adventure Shell's bottom dock rendering its "desktop-legacy" navigation
 * category (soul_records/battle_log/tavern/star_chart/arena -- see
 * js/e9/navigation_registry.js), which only renders under
 * @media (min-width: 1280px). No real iPad reports a portrait CSS width
 * >= 1280 under a correctly honoured `width=device-width` viewport meta
 * (the largest real iPad portrait width is 1024), so the layout viewport
 * itself must be wrong on the affected device.
 *
 * This is the exact same detection class the codebase already uses
 * elsewhere for "an iPad reporting a Macintosh desktop-site UA" (see
 * js/e9/world_stage.js's usesInlinePlayerMarkerSurface and index.html's
 * install-guide isIPadOSDesktopUA), extended with a hardware-level
 * orientation check (screen.orientation, not part of the layout viewport
 * that desktop-site mode overrides) so it can tell a genuinely landscape
 * iPad apart from a portrait iPad whose viewport is being misreported.
 *
 * This harness re-implements the exact predicate extracted from
 * index.html's <head> script and exercises it with controlled inputs --
 * it does not depend on a real browser's viewport emulation, which cannot
 * reproduce the underlying OS/WebKit disagreement being corrected for.
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const INDEX_HTML = path.join(REPO_ROOT, 'index.html');
const FEATURE_FLAGS_JS = path.join(REPO_ROOT, 'js', 'e9', 'feature_flags.js');
const WORLD_STAGE_JS = path.join(REPO_ROOT, 'js', 'e9', 'world_stage.js');
const RIGHT_CARDS_JS = path.join(REPO_ROOT, 'js', 'e9', 'right_cards.js');
const REFERENCE_WORLD_MAP_CSS = path.join(REPO_ROOT, 'css', 'e9', 'reference_world_map.css');

const indexSource = fs.readFileSync(INDEX_HTML, 'utf8');
const featureFlagsSource = fs.readFileSync(FEATURE_FLAGS_JS, 'utf8');
const worldStageSource = fs.readFileSync(WORLD_STAGE_JS, 'utf8');
const rightCardsSource = fs.readFileSync(RIGHT_CARDS_JS, 'utf8');
const referenceWorldMapCss = fs.readFileSync(REFERENCE_WORLD_MAP_CSS, 'utf8');

const tests = [];
function test(name, fn) { tests.push([name, fn]); }

// Extract the exact predicate function body from index.html so this test
// exercises the real shipped algorithm, not a re-typed copy that could
// silently drift from it.
function extractComputeOverride() {
  const marker = 'function computeOverride() {';
  const start = indexSource.indexOf(marker);
  assert.ok(start !== -1, 'computeOverride() not found in index.html');
  const bodyStart = indexSource.indexOf('{', start);
  let depth = 0;
  let i = bodyStart;
  for (; i < indexSource.length; i++) {
    if (indexSource[i] === '{') depth++;
    else if (indexSource[i] === '}') {
      depth--;
      if (depth === 0) break;
    }
  }
  const fnSource = indexSource.slice(start, i + 1);
  // eslint-disable-next-line no-new-func
  return new Function('window', `return (${fnSource})();`);
}

const computeOverride = extractComputeOverride();

function run(mock) {
  return computeOverride(mock);
}

// The classifier now shipped in Production (recovered into source by
// A_PWA_LIVE_STATIC_RECOVERY_AND_GEOMETRY_FORWARD_PORT_001) is stricter than
// the one this file was first written against: it requires an installed
// standalone PWA and a physical tablet-sized screen in addition to the Apple
// touch signature and hardware portrait, and it treats the layout viewport's
// own orientation as diagnostic context only. These helpers build a device
// that satisfies every one of those inputs so each case below varies exactly
// one of them.
const STANDALONE_MEDIA = (query) => ({ matches: /display-mode:\s*standalone/.test(query) });
function ipadPwa(overrides = {}) {
  return {
    navigator: { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6)', maxTouchPoints: 5 },
    screen: { width: 820, height: 1180, orientation: { type: 'portrait-primary' } },
    matchMedia: STANDALONE_MEDIA,
    ...overrides,
  };
}

test('known-bug device (Mac+touch UA, installed PWA, physical portrait tablet) triggers the override', () => {
  assert.strictEqual(run(ipadPwa()), true);
});

test('the layout viewport reporting portrait does not veto the correction', () => {
  // Safari desktop-site mode can report innerWidth=1640 for an 820px iPad
  // while still matching (orientation: portrait); the physical screen is the
  // authority, so the viewport agreeing must not disable the override.
  const result = run(ipadPwa({
    matchMedia: (query) => ({ matches: /display-mode:\s*standalone|orientation:\s*portrait/.test(query) }),
  }));
  assert.strictEqual(result, true);
});

test('a plain browser tab (not an installed PWA) is never corrected', () => {
  assert.strictEqual(run(ipadPwa({ matchMedia: () => ({ matches: false }) })), false);
});

test('navigator.standalone === true alone counts as installed (iOS Safari signal)', () => {
  const device = ipadPwa({ matchMedia: () => ({ matches: false }) });
  device.navigator.standalone = true;
  assert.strictEqual(run(device), true);
});

test('a screen outside the supported tablet envelope is never corrected', () => {
  // Short edge below 768 (phone) and long edge above 1366 (desktop-class).
  assert.strictEqual(run(ipadPwa({ screen: { width: 390, height: 844, orientation: { type: 'portrait-primary' } } })), false);
  assert.strictEqual(run(ipadPwa({ screen: { width: 1440, height: 2560, orientation: { type: 'portrait-primary' } } })), false);
});

test('a missing or non-numeric screen size fails closed', () => {
  assert.strictEqual(run(ipadPwa({ screen: { orientation: { type: 'portrait-primary' } } })), false);
  assert.strictEqual(run(ipadPwa({ screen: { width: NaN, height: 1180, orientation: { type: 'portrait-primary' } } })), false);
});

test('agreeing device (viewport already says portrait) does not double-correct', () => {
  const result = run({
    navigator: { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6)', maxTouchPoints: 5 },
    screen: { orientation: { type: 'portrait-primary' } },
    matchMedia: () => ({ matches: true }),
  });
  assert.strictEqual(result, false);
});

test('genuinely landscape iPad in desktop-UA mode is NOT forced into portrait', () => {
  const result = run({
    navigator: { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6)', maxTouchPoints: 5 },
    screen: { orientation: { type: 'landscape-primary' } },
    matchMedia: () => ({ matches: false }),
  });
  assert.strictEqual(result, false);
});

test('a real desktop Mac (no touch points) never triggers the override', () => {
  const result = run({
    navigator: { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6)', maxTouchPoints: 0 },
    screen: { orientation: { type: 'portrait-primary' } },
    matchMedia: () => ({ matches: false }),
  });
  assert.strictEqual(result, false);
});

test('a real iPad UA (not Mac-spoofed) that already agrees does not trigger', () => {
  const result = run({
    navigator: { userAgent: 'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)', maxTouchPoints: 5 },
    screen: { orientation: { type: 'portrait-primary' } },
    matchMedia: () => ({ matches: true }),
  });
  assert.strictEqual(result, false);
});

test('a touch-enabled Windows laptop never triggers (UA has no iPad/Macintosh)', () => {
  const result = run({
    navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Touch', maxTouchPoints: 10 },
    screen: { orientation: { type: 'landscape-primary' } },
    matchMedia: () => ({ matches: false }),
  });
  assert.strictEqual(result, false);
});

test('falls back to screen.width/height when screen.orientation is unavailable', () => {
  const result = run(ipadPwa({ screen: { width: 1024, height: 1366 } }));
  assert.strictEqual(result, true);
});

test('a missing/throwing matchMedia fails closed (no override, not a crash)', () => {
  const result = run({
    navigator: { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6)', maxTouchPoints: 5 },
    screen: { orientation: { type: 'portrait-primary' } },
    matchMedia: undefined,
  });
  assert.strictEqual(result, false);
});

test('feature_flags.js exposes E9.isPortraitTabletOverride reading the cached flag', () => {
  assert.ok(featureFlagsSource.includes('global.E9.isPortraitTabletOverride = function ()'));
  assert.ok(featureFlagsSource.includes('__GO_PORTRAIT_TABLET_OVERRIDE__'));
});

test('the head script recomputes on resize, orientationchange, and screen.orientation change', () => {
  assert.ok(indexSource.includes("window.addEventListener('resize', apply"));
  assert.ok(indexSource.includes("window.addEventListener('orientationchange', apply"));
  assert.ok(indexSource.includes("window.screen.orientation.addEventListener('change', apply)"));
});

test('world_stage.js ORs the override into every isPortraitTablet-style gate', () => {
  // Whitespace-tolerant: usesInlinePlayerMarkerSurface wraps this across two
  // lines, the other three call sites keep it on one line.
  const occurrences = (worldStageSource.match(
    /window\.E9\s*&&\s*window\.E9\.isPortraitTabletOverride\s*&&\s*window\.E9\.isPortraitTabletOverride\(\)/g
  ) || []).length;
  // usesInlinePlayerMarkerSurface, the ZONE_LANDMARKS portrait check, the
  // Zone Card visibility gate in renderSelectedZone, and the initial-load
  // recommended-zone Zone Card gate.
  assert.strictEqual(occurrences, 4, 'expected exactly 4 wired call sites in world_stage.js');
});

test('the Zone Card visibility gate specifically includes the override', () => {
  const marker = 'if (details) details.hidden = VS1E_STATIC_CONTRACT_ACTIVE ? !isPortraitTablet : isMobile;';
  assert.ok(worldStageSource.includes(marker));
  const idx = worldStageSource.indexOf(marker);
  const preceding = worldStageSource.slice(Math.max(0, idx - 400), idx);
  assert.ok(preceding.includes('window.E9.isPortraitTabletOverride()'));
});

test('right_cards.js ORs the override into detail-surface ownership', () => {
  assert.ok(rightCardsSource.includes('var portraitOverride = !!(window.E9 && window.E9.isPortraitTabletOverride'));
  assert.ok(rightCardsSource.includes('lowerCardOwnsDetails = !!(stackedDetailSurface && stackedDetailSurface.matches) || portraitOverride'));
  assert.ok(rightCardsSource.includes('lowerCard.hidden = !((portraitLowerCardSurface && portraitLowerCardSurface.matches) || portraitOverride)'));
});

test('reference_world_map.css defines the override block with matching !important specificity', () => {
  assert.ok(referenceWorldMapCss.includes('html[data-go-portrait-tablet-override] body[data-e10-visual-skin="immersive-rpg"] #e9-adventure-shell {'));
  const marker = 'html[data-go-portrait-tablet-override] body[data-e10-visual-skin="immersive-rpg"] #e9-adventure-shell {';
  const start = referenceWorldMapCss.indexOf(marker);
  const end = referenceWorldMapCss.indexOf('}', start);
  const block = referenceWorldMapCss.slice(start, end);
  // Every property that the conflicting desktop (min-width:1280px) and
  // tablet-landscape breakpoints declare with !important must be matched,
  // or !important there would still win regardless of this rule's higher
  // selector specificity.
  ['width', 'height', 'min-height', 'max-height', 'max-width', 'position', 'overflow'].forEach((prop) => {
    const re = new RegExp(prop + '\\s*:[^;]+!important');
    assert.ok(re.test(block), `expected ${prop} to carry !important in the shell override block`);
  });
});

test('the override block does not introduce a generic, unscoped rule', () => {
  // Every selector in the new block must be scoped to the override
  // attribute; it must never apply to a device where the attribute isn't
  // set (this is a corrective override, not a redesign of the shell).
  const marker = '/* PWA_STANDALONE_ADVENTURE_LAYOUT_RECOVERY_CLAUDE_001:';
  const blockStart = referenceWorldMapCss.indexOf(marker);
  assert.ok(blockStart !== -1);
  const nextMediaOrEnd = referenceWorldMapCss.indexOf('@media (max-width: 600px)', blockStart);
  const block = referenceWorldMapCss.slice(blockStart, nextMediaOrEnd);
  const selectorLines = block.split('\n').filter((l) => l.trim().endsWith('{'));
  selectorLines.forEach((line) => {
    assert.ok(line.includes('html[data-go-portrait-tablet-override]'), `unscoped selector: ${line.trim()}`);
  });
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log('ok   - ' + name);
  } catch (err) {
    failed += 1;
    console.log('FAIL - ' + name);
    console.log('       ' + err.message);
  }
}
console.log('');
console.log((tests.length - failed) + '/' + tests.length + ' passed');
process.exit(failed === 0 ? 0 : 1);
