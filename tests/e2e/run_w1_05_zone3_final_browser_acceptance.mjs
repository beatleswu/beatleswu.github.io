// W1_05 final Zone 3 browser acceptance harness.
//
// This runner is intentionally target-agnostic and real-browser driven. It
// does not mock the application API, does not reset account state, and does
// not claim physical-device or human-perceptual acceptance. The final
// integrated candidate supplies isolated seeded accounts through env vars;
// --describe is safe to run before that candidate exists.

import fssync from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright-core';

export const ZONE3_KEY = 'k16_20';
export const PHYSICAL_DEVICE_ACCEPTANCE = 'NOT_PERFORMED';

export const VIEWPORTS = Object.freeze({
  desktop: Object.freeze({ width: 1920, height: 1080, label: 'desktop' }),
  ipad_landscape: Object.freeze({ width: 1180, height: 820, label: 'iPad landscape' }),
  ipad_portrait: Object.freeze({ width: 820, height: 1180, label: 'iPad portrait' }),
  mobile_portrait: Object.freeze({ width: 390, height: 844, label: 'mobile portrait' }),
});

export const LOCALES = Object.freeze({
  'zh-TW': Object.freeze({ appLang: 'zh', htmlLang: 'zh-TW' }),
  'en-US': Object.freeze({ appLang: 'en', htmlLang: 'en' }),
});

export const RESPONSIVE_ART_CONTRACT = Object.freeze({
  accepted_rows: '10/10',
  owner_source_art_changed: 'NO',
  custom_object_positions: Object.freeze({
    SHOT09: '58% 50%',
    SHOT10: '58% 50%',
  }),
  physical_device_acceptance: PHYSICAL_DEVICE_ACCEPTANCE,
});

export const SCENARIOS = Object.freeze([
  Object.freeze({ id: 'first_entry_zh_TW', account: 'ZH', locale: 'zh-TW', action: 'first_entry' }),
  Object.freeze({ id: 'first_entry_en_US', account: 'EN', locale: 'en-US', action: 'first_entry' }),
  Object.freeze({ id: 'locale_switch', account: 'ZH', locale: 'zh-TW', action: 'locale_switch' }),
  Object.freeze({ id: 'replay', account: 'REPLAY', locale: 'zh-TW', action: 'replay' }),
  Object.freeze({ id: 'reduced_motion', account: 'ZH', locale: 'zh-TW', action: 'reduced_motion' }),
  Object.freeze({ id: 'global_mute', account: 'ZH', locale: 'zh-TW', action: 'global_mute' }),
  Object.freeze({ id: 'cinematic_lifecycle', account: 'ZH', locale: 'zh-TW', action: 'cinematic_lifecycle' }),
  Object.freeze({ id: 'route_exit_cleanup', account: 'REPLAY', locale: 'zh-TW', action: 'route_exit_cleanup' }),
  Object.freeze({ id: 'presentation_failure_noop', account: 'EN', locale: 'en-US', action: 'presentation_failure_noop' }),
  Object.freeze({ id: 'final_state_return', account: 'REPLAY', locale: 'zh-TW', action: 'final_state_return' }),
]);

const E9_QUERY = '?E9_DEBUG=1&e9Shell=1&e9TopHud=1&e9LeftNav=1&e9RightCards=1&e9BottomDock=1&e9WorldStage=1';
const PAGE_TIMEOUT_MS = 20000;
const MAX_PRESENTATION_DISMISS_CLICKS = 24;
const CANDIDATE_ENV = 'E2E_ZONE3_FINAL_CANDIDATE_ID';
const PRODUCTION_HOST = 'godokoro.com';
const PRODUCTION_IP = '152.69.200.105';
const ZONE3_IMAGE_PATTERN = /\/assets\/(?:e10\/art\/zone3\/|storyboards\/(?:go_goblin_cave_|zone3[_-]))/i;

function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}

export function buildRunMatrix() {
  return SCENARIOS.flatMap((scenario) => Object.entries(VIEWPORTS).map(([viewport, dimensions]) => ({
    scenario: scenario.id,
    account: scenario.account,
    locale: scenario.locale,
    action: scenario.action,
    viewport,
    width: dimensions.width,
    height: dimensions.height,
    physical_device_acceptance: PHYSICAL_DEVICE_ACCEPTANCE,
  })));
}

export function assertViewportEvidence(row) {
  requireValue(row && row.physical_device_acceptance === PHYSICAL_DEVICE_ACCEPTANCE,
    'browser viewport evidence must remain explicitly non-physical-device evidence');
  requireValue(row.physical_device_claim !== true,
    'negative control: browser viewport cannot claim physical-device acceptance');
  return true;
}

export function describeMatrix() {
  const rows = buildRunMatrix();
  rows.forEach(assertViewportEvidence);
  return {
    contract: 'w1_05_zone3_final_browser_acceptance',
    zone_key: ZONE3_KEY,
    candidate_required: CANDIDATE_ENV,
    scenario_count: SCENARIOS.length,
    viewport_count: Object.keys(VIEWPORTS).length,
    case_count: rows.length,
    scenarios: SCENARIOS.map((scenario) => scenario.id),
    viewports: VIEWPORTS,
    locales: LOCALES,
    responsive_art_contract: RESPONSIVE_ART_CONTRACT,
    physical_device_acceptance: PHYSICAL_DEVICE_ACCEPTANCE,
    viewport_emulation_is_physical_acceptance: false,
    execution: 'NOT_RUN_FINAL_INTEGRATED_CANDIDATE_REQUIRED',
  };
}

function chromePath() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const found = candidates.find((candidate) => fssync.existsSync(candidate));
  requireValue(found, 'No Chrome/Edge executable found. Set CHROME_BIN.');
  return found;
}

function credentials(account) {
  const username = process.env[`E2E_ZONE3_${account}_USERNAME`];
  const password = process.env[`E2E_ZONE3_${account}_PASSWORD`];
  requireValue(username && password, `missing E2E_ZONE3_${account}_USERNAME/PASSWORD`);
  return { username, password };
}

function normalizeHost(hostname) {
  return String(hostname || '').toLowerCase().replace(/\.+$/, '');
}

function guardTarget(rawUrl) {
  let target;
  try {
    target = new URL(rawUrl);
  } catch {
    throw new Error('E2E_BASE_URL must be an absolute URL');
  }
  const host = normalizeHost(target.hostname);
  if (host === PRODUCTION_HOST || host.endsWith(`.${PRODUCTION_HOST}`)) {
    throw new Error(`refusing production hostname ${host}`);
  }
  if (host === PRODUCTION_IP) {
    throw new Error(`refusing known production IP ${host}`);
  }
  return target.origin;
}

async function guardPage(page, context) {
  const origin = guardTarget(page.url());
  requireValue(origin === guardTarget(origin), `${context}: unexpected page origin`);
  return origin;
}

function addBrowserErrorMonitor(page, sink) {
  page.on('console', (message) => {
    if (message.type() === 'error') sink.push({ kind: 'console.error', text: message.text() });
  });
  page.on('pageerror', (error) => sink.push({
    kind: 'pageerror',
    text: String(error && error.message || error),
  }));
  page.on('requestfailed', (request) => sink.push({
    kind: 'requestfailed',
    url: request.url(),
    error: request.failure()?.errorText || 'unknown',
  }));
}

async function loginAndOpen(page, origin, account, locale) {
  const language = LOCALES[locale];
  const creds = credentials(account);
  await page.goto(`${origin}/login?lang=${language.appLang}`, {
    waitUntil: 'domcontentloaded',
    timeout: PAGE_TIMEOUT_MS,
  });
  await guardPage(page, 'login navigation');
  await page.locator('#username').fill(creds.username);
  await page.locator('#password').fill(creds.password);
  await page.locator('#login-btn').click();
  await page.waitForFunction(() => location.pathname !== '/login', { timeout: PAGE_TIMEOUT_MS });
  await guardPage(page, 'post-login navigation');
  await page.goto(`${origin}/${E9_QUERY}&lang=${language.appLang}`, {
    waitUntil: 'domcontentloaded',
    timeout: PAGE_TIMEOUT_MS,
  });
  await guardPage(page, 'Zone 3 page navigation');
  await page.locator('#e9-world-stage-slot').waitFor({ state: 'attached', timeout: PAGE_TIMEOUT_MS });
  await page.locator(`#e9-world-stage-slot [data-zone="${ZONE3_KEY}"]`).waitFor({
    state: 'attached',
    timeout: PAGE_TIMEOUT_MS,
  });
  await page.waitForFunction((expected) => (
    document.documentElement.lang === expected
    || document.documentElement.lang === expected.slice(0, 2)
  ), language.htmlLang, { timeout: PAGE_TIMEOUT_MS });
}

async function selectZone3(page) {
  const tile = page.locator(`#e9-world-stage-slot [data-zone="${ZONE3_KEY}"]`);
  await tile.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
  await tile.click();
  await page.waitForFunction((key) => {
    const root = document.getElementById('e9-world-stage-slot');
    return root?.__e9WorldStageState?.selectedZoneKey === key;
  }, ZONE3_KEY, { timeout: PAGE_TIMEOUT_MS });
}

async function waitForCinematic(page) {
  await page.waitForFunction((key) => {
    const overlay = document.getElementById('boss-cinematic');
    return overlay?.classList.contains('show') && overlay.dataset.zoneKey === key;
  }, ZONE3_KEY, { timeout: PAGE_TIMEOUT_MS });
}

async function openFirstEntry(page) {
  await selectZone3(page);
  await waitForCinematic(page);
}

async function visibleLocator(page, selectors) {
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    if (await locator.count() && await locator.isVisible()) return locator;
  }
  throw new Error(`no visible locator matched: ${selectors.join(', ')}`);
}

async function openReplay(page) {
  await selectZone3(page);
  const replay = await visibleLocator(page, [
    '#e9-world-stage-details-replay',
    '[data-e10-zone-replay]',
  ]);
  requireValue(await replay.isEnabled(), 'Zone 3 replay control is disabled');
  await replay.click();
  await waitForCinematic(page);
}

async function readCinematic(page) {
  return page.evaluate((key) => {
    const overlay = document.getElementById('boss-cinematic');
    const activeShots = Array.from(document.querySelectorAll('#intro-film-stage .film-shot.active')).length;
    return {
      visible: !!overlay && overlay.classList.contains('show'),
      zoneKey: overlay?.dataset.zoneKey || null,
      ariaHidden: overlay?.getAttribute('aria-hidden') || null,
      activeShots,
      title: document.getElementById('boss-cinematic-title')?.textContent?.trim() || '',
      line: document.getElementById('boss-cinematic-line')?.textContent?.trim() || '',
      zoneKeyMatches: overlay?.dataset.zoneKey === key,
    };
  }, ZONE3_KEY);
}

async function dismissCinematic(page) {
  for (let index = 0; index < MAX_PRESENTATION_DISMISS_CLICKS; index += 1) {
    const showing = await page.locator('#boss-cinematic.show').count();
    if (!showing) break;
    const skip = page.locator('.intro-skip-btn:visible').first();
    if (await skip.count()) {
      await skip.click();
      continue;
    }
    const close = page.locator('.boss-cinematic-close-x:visible').first();
    if (await close.count()) {
      await close.click();
      continue;
    }
    throw new Error('cinematic is showing but no visible dismissal control exists');
  }
  await page.waitForFunction(() => !document.getElementById('boss-cinematic')?.classList.contains('show'), {
    timeout: PAGE_TIMEOUT_MS,
  });
}

async function adventureStateFingerprint(page) {
  return page.evaluate(async () => {
    const response = await fetch('/api/adventure/bootstrap', { credentials: 'include' });
    if (!response.ok) throw new Error(`adventure bootstrap fingerprint failed: HTTP ${response.status}`);
    const body = await response.json();
    return JSON.stringify({
      current_zone_key: body.current_zone_key ?? null,
      zones: Array.isArray(body.zones) ? body.zones.map((zone) => ({
        key: zone?.key ?? null,
        status: zone?.status ?? null,
        stars: zone?.stars ?? null,
        cleared: zone?.cleared ?? null,
        unlocked: zone?.unlocked ?? null,
      })) : [],
    });
  });
}

async function runWithWriteTrace(page, action) {
  const writes = [];
  const onRequest = (request) => {
    if (request.method() !== 'GET' && request.method() !== 'HEAD') {
      writes.push({ method: request.method(), url: new URL(request.url()).pathname });
    }
  };
  page.on('request', onRequest);
  try {
    return { result: await action(), writes };
  } finally {
    page.off('request', onRequest);
  }
}

async function assertVisibleCinematic(page) {
  const snapshot = await readCinematic(page);
  requireValue(snapshot.visible && snapshot.zoneKeyMatches && snapshot.ariaHidden === 'false',
    `Zone 3 cinematic lifecycle invalid: ${JSON.stringify(snapshot)}`);
  requireValue(snapshot.activeShots === 1, `expected exactly one active Zone 3 shot: ${JSON.stringify(snapshot)}`);
  requireValue(snapshot.title || snapshot.line, 'Zone 3 cinematic has no visible context text');
  return snapshot;
}

async function runScenario(page, scenario) {
  if (scenario.action === 'first_entry') {
    await openFirstEntry(page);
    return { cinematic: await assertVisibleCinematic(page), state: 'first_entry_open' };
  }
  if (scenario.action === 'locale_switch') {
    const initial = await page.evaluate(() => document.documentElement.lang);
    const en = page.locator('#lang-switcher-index [data-lang="en"]').first();
    const zh = page.locator('#lang-switcher-index [data-lang="zh"]').first();
    await en.click();
    await page.waitForFunction(() => document.documentElement.lang === 'en');
    const afterEnglish = await page.evaluate(() => document.documentElement.lang);
    await zh.click();
    await page.waitForFunction(() => document.documentElement.lang === 'zh-TW');
    const afterChinese = await page.evaluate(() => document.documentElement.lang);
    requireValue(initial === 'zh-TW' && afterEnglish === 'en' && afterChinese === 'zh-TW',
      `locale switch did not round-trip zh-TW -> en-US -> zh-TW: ${initial}/${afterEnglish}/${afterChinese}`);
    return { initial, afterEnglish, afterChinese };
  }
  if (scenario.action === 'replay') {
    await openReplay(page);
    const cinematic = await assertVisibleCinematic(page);
    const before = await adventureStateFingerprint(page);
    const traced = await runWithWriteTrace(page, async () => {
      await dismissCinematic(page);
      return await adventureStateFingerprint(page);
    });
    requireValue(traced.writes.length === 0, `replay issued domain writes: ${JSON.stringify(traced.writes)}`);
    requireValue(before === traced.result, 'replay changed authoritative progression fingerprint');
    return { cinematic, replay_writes: traced.writes, returned_to_zone_card: true };
  }
  if (scenario.action === 'reduced_motion') {
    const motion = await page.evaluate(() => ({
      prefersReducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      documentScrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
      stageTransition: getComputedStyle(document.getElementById('adventure-stage') || document.body).transitionDuration,
      stageAnimation: getComputedStyle(document.getElementById('adventure-stage') || document.body).animationDuration,
    }));
    requireValue(motion.prefersReducedMotion, 'reduced-motion media preference was not active');
    requireValue(motion.documentScrollBehavior !== 'smooth', 'reduced-motion path still requires smooth document scrolling');
    return motion;
  }
  if (scenario.action === 'global_mute') {
    let settings;
    try {
      settings = await visibleLocator(page, [
        '[data-e10-command="settings"]',
        '[data-e10-nav-key="settings"]',
      ]);
    } catch {
      const more = await visibleLocator(page, [
        '[data-e10-vs1f-nav="more"]',
        '.e10-more-trigger',
      ]);
      await more.click();
      settings = await visibleLocator(page, [
        '#e10-all-features-overlay [data-e10-command="settings"]',
        '#e10-all-features-overlay [data-e10-nav-key="settings"]',
      ]);
    }
    await settings.click();
    await page.locator('#e10-settings-overlay').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
    const sound = await visibleLocator(page, ['#e10-settings-sound']);
    const initiallyChecked = await sound.isChecked();
    if (!initiallyChecked) await sound.check();
    await sound.uncheck();
    const muted = await page.evaluate(() => ({
      muted: !!window.SFX?.muted,
      checked: !!document.getElementById('e10-settings-sound')?.checked,
    }));
    requireValue(muted.muted && muted.checked === false, `global mute did not reach SFX authority: ${JSON.stringify(muted)}`);
    return muted;
  }
  if (scenario.action === 'cinematic_lifecycle') {
    await openFirstEntry(page);
    const started = await assertVisibleCinematic(page);
    await dismissCinematic(page);
    const after = await readCinematic(page);
    requireValue(after.visible === false && after.ariaHidden === 'true',
      `cinematic did not close cleanly: ${JSON.stringify(after)}`);
    return { started, after };
  }
  if (scenario.action === 'route_exit_cleanup') {
    await openReplay(page);
    await assertVisibleCinematic(page);
    const cleanup = await page.evaluate(() => {
      if (!window.E9 || typeof window.E9.destroyShell !== 'function') {
        throw new Error('E9 lifecycle destroy API is unavailable');
      }
      window.E9.destroyShell();
      return {
        activeShell: window.E9.getActiveShell(),
        overlayShowing: document.getElementById('boss-cinematic')?.classList.contains('show') === true,
        audioStillPlaying: Array.from(document.querySelectorAll('audio')).some((audio) => !audio.paused && !audio.muted && audio.volume > 0),
        worldStageMounted: !!document.querySelector('#e9-world-stage-slot [data-zone]'),
      };
    });
    requireValue(cleanup.activeShell === 'legacy' && !cleanup.overlayShowing
      && !cleanup.audioStillPlaying && !cleanup.worldStageMounted,
      `route exit cleanup failed: ${JSON.stringify(cleanup)}`);
    return cleanup;
  }
  if (scenario.action === 'presentation_failure_noop') {
    const writes = await runWithWriteTrace(page, async () => {
      await selectZone3(page);
      await page.waitForFunction(() => (
        document.querySelector('#intro-film-stage [data-z3-image-load="failed_presentation_only"]')
        || document.querySelector('#intro-film-stage .z3-image-load-failed')
      ), { timeout: PAGE_TIMEOUT_MS });
      return page.evaluate(() => ({
        overlayShowing: document.getElementById('boss-cinematic')?.classList.contains('show') === true,
        presentationFailure: !!document.querySelector(
          '#intro-film-stage [data-z3-image-load="failed_presentation_only"], #intro-film-stage .z3-image-load-failed'
        ),
        dismissalAvailable: !!document.querySelector(
          '#boss-cinematic.show .intro-skip-btn, #boss-cinematic.show .boss-cinematic-close-x'
        ),
        path: location.pathname,
      }));
    });
    requireValue(writes.result.presentationFailure === true,
      'missing Zone 3 presentation asset did not remain a presentation-only failure');
    requireValue(writes.result.dismissalAvailable === true,
      'presentation failure removed the cinematic dismissal path and blocked gameplay handoff');
    requireValue(writes.result.path === '/', `presentation failure changed route: ${writes.result.path}`);
    requireValue(writes.writes.length === 0, `presentation failure issued a domain write: ${JSON.stringify(writes.writes)}`);
    return writes;
  }
  if (scenario.action === 'final_state_return') {
    await openReplay(page);
    await assertVisibleCinematic(page);
    await dismissCinematic(page);
    const state = await page.evaluate((key) => ({
      overlayShowing: document.getElementById('boss-cinematic')?.classList.contains('show') === true,
      selectedZoneKey: document.getElementById('e9-world-stage-slot')?.__e9WorldStageState?.selectedZoneKey || null,
      zoneCardReachable: !!document.querySelector(`#e9-world-stage-slot [data-zone="${key}"]`),
    }), ZONE3_KEY);
    requireValue(!state.overlayShowing && state.selectedZoneKey === ZONE3_KEY && state.zoneCardReachable,
      `final-state return did not restore Zone 3 card: ${JSON.stringify(state)}`);
    return { ...state, returned_to_zone_card: true };
  }
  throw new Error(`unknown Zone 3 browser scenario ${scenario.action}`);
}

async function runCase(browser, origin, scenario, viewport, dimensions, report) {
  const context = await browser.newContext({
    viewport: { width: dimensions.width, height: dimensions.height },
    reducedMotion: scenario.action === 'reduced_motion' ? 'reduce' : 'no-preference',
  });
  const page = await context.newPage();
  addBrowserErrorMonitor(page, report.browser_errors);
  let missingAssetHits = 0;
  if (scenario.action === 'presentation_failure_noop') {
    await page.route('**/*', async (route) => {
      const requestUrl = new URL(route.request().url());
      if (ZONE3_IMAGE_PATTERN.test(requestUrl.pathname) && /\.(?:webp|png|jpe?g)$/i.test(requestUrl.pathname)) {
        missingAssetHits += 1;
        await route.fulfill({ status: 404, body: 'intentional Wave 1 missing-asset negative control' });
        return;
      }
      await route.continue();
    });
  }
  const result = {
    scenario: scenario.id,
    viewport,
    width: dimensions.width,
    height: dimensions.height,
    locale: scenario.locale,
    physical_device_acceptance: PHYSICAL_DEVICE_ACCEPTANCE,
  };
  try {
    await loginAndOpen(page, origin, scenario.account, scenario.locale);
    const evidence = await runScenario(page, scenario);
    if (scenario.action === 'presentation_failure_noop') {
      requireValue(missingAssetHits > 0, 'missing-asset negative control did not intercept a Zone 3 image request');
      evidence.missing_asset_hits = missingAssetHits;
    }
    assertViewportEvidence(result);
    result.status = 'PASS';
    result.evidence = evidence;
  } catch (error) {
    result.status = 'FAIL';
    result.error = String(error && error.message || error);
  } finally {
    await context.close();
  }
  return result;
}

function requiredCandidatePreconditions() {
  requireValue(process.env[CANDIDATE_ENV], `${CANDIDATE_ENV} is required for --run`);
  guardTarget(process.env.E2E_BASE_URL || 'http://localhost:5000');
  ['ZH', 'EN', 'REPLAY'].forEach(credentials);
}

async function main() {
  const args = new Set(process.argv.slice(2));
  if (args.has('--describe')) {
    console.log(JSON.stringify(describeMatrix(), null, 2));
    return 0;
  }
  if (!args.has('--run')) {
    console.log(JSON.stringify({ usage: 'node run_w1_05_zone3_final_browser_acceptance.mjs --describe|--run' }, null, 2));
    return 2;
  }

  const report = {
    contract: 'w1_05_zone3_final_browser_acceptance',
    candidate_id: process.env[CANDIDATE_ENV] || null,
    base_url: null,
    zone_key: ZONE3_KEY,
    physical_device_acceptance: PHYSICAL_DEVICE_ACCEPTANCE,
    browser_viewport_evidence_only: true,
    browser_errors: [],
    cases: [],
  };
  try {
    requiredCandidatePreconditions();
    report.base_url = guardTarget(process.env.E2E_BASE_URL || 'http://localhost:5000');
  } catch (error) {
    report.status = 'BLOCKED_FINAL_CANDIDATE_PRECONDITION';
    report.error = String(error && error.message || error);
    console.log(JSON.stringify(report, null, 2));
    return 2;
  }

  const browser = await chromium.launch({ headless: true, executablePath: chromePath() });
  try {
    for (const scenario of SCENARIOS) {
      for (const [viewport, dimensions] of Object.entries(VIEWPORTS)) {
        report.cases.push(await runCase(browser, report.base_url, scenario, viewport, dimensions, report));
      }
    }
  } finally {
    await browser.close();
  }

  const failed = report.cases.filter((item) => item.status === 'FAIL');
  report.tests_collected = report.cases.length;
  report.tests_passed = report.cases.length - failed.length;
  report.tests_failed = failed.length;
  report.tests_skipped = 0;
  report.complete = failed.length === 0 && report.cases.length === buildRunMatrix().length;
  report.status = report.complete && report.browser_errors.length === 0 ? 'PASS' : 'FAIL';
  console.log(JSON.stringify(report, null, 2));
  return report.status === 'PASS' ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().then((code) => process.exit(code)).catch((error) => {
    console.error(error && error.stack ? error.stack : String(error));
    process.exit(1);
  });
}
