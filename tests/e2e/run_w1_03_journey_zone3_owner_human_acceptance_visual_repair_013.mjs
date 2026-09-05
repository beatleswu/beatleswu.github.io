// Targeted W1-03 owner-acceptance visual repair checks.
//
// This runner is intentionally narrower than the W1-05 40-case matrix. It
// proves the replay presentation-only boundary and the Zone 3 Lord
// rechallenge art binding at all four Chromium viewport layouts, in both
// supported locales, without starting a Lord attempt.
'use strict';

import fssync from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { chromium } from 'playwright-core';

const ZONE3_KEY = 'k16_20';
const PAGE_TIMEOUT_MS = 20000;
const E9_QUERY = '?E9_DEBUG=1&e9Shell=1&e9TopHud=1&e9LeftNav=1&e9RightCards=1&e9BottomDock=1&e9WorldStage=1';
const LORD_ART_PATH = '/assets/e10/art/zone3/lord_trial/zone3_lord_02_challenge_backplate.webp';
const REPLAY_HIDDEN_SELECTORS = Object.freeze([
  '#boss-cinematic-kicker',
  '#boss-cinematic-title',
  '#boss-cinematic-books',
  '#boss-cinematic-progress',
  '#boss-cinematic-monster',
  '#boss-cinematic-rules',
  '#boss-reward-presentation',
]);
const VIEWPORTS = Object.freeze({
  desktop: Object.freeze({ width: 1920, height: 1080 }),
  ipad_landscape: Object.freeze({ width: 1180, height: 820 }),
  ipad_portrait: Object.freeze({ width: 820, height: 1180 }),
  mobile_portrait: Object.freeze({ width: 390, height: 844 }),
});
const LOCALES = Object.freeze([
  Object.freeze({ id: 'zh-TW', appLang: 'zh', htmlLang: 'zh-TW' }),
  Object.freeze({ id: 'en-US', appLang: 'en', htmlLang: 'en' }),
]);
const EVIDENCE_DIR = path.resolve(
  process.env.E2E_EVIDENCE_DIR
    || 'tests/e2e/evidence/w1_03_journey_zone3_owner_human_acceptance_visual_repair_013',
);
const ZONE3_IMAGE_PATTERN = /\/assets\/e10\/art\/zone3\/cinematic\/zone3_shot\d+\.webp$/i;

function requireValue(value, message) {
  if (!value) throw new Error(message);
}

function origin() {
  const value = process.env.E2E_BASE_URL;
  requireValue(value, 'E2E_BASE_URL is required');
  const url = new URL(value);
  if (url.hostname === 'godokoro.com'
      || url.hostname.endsWith('.godokoro.com')
      || url.hostname === '152.69.200.105') {
    throw new Error(`refusing production target ${url.hostname}`);
  }
  return url.origin;
}

function credentials(account = 'REPLAY') {
  const username = process.env[`E2E_ZONE3_${account}_USERNAME`];
  const password = process.env[`E2E_ZONE3_${account}_PASSWORD`];
  requireValue(username && password, `missing E2E_ZONE3_${account}_USERNAME/PASSWORD`);
  return { username, password };
}

function chromePath() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const found = candidates.find((item) => fssync.existsSync(item));
  requireValue(found, 'No Chrome/Edge executable found. Set CHROME_BIN.');
  return found;
}

function installOwnerReplayAudit(page) {
  return page.addInitScript(({ zoneKey, hiddenSelectors }) => {
    const state = {
      replayContextObserved: false,
      badVisibleFirstClearFields: [],
      exactSealTextVisible: false,
    };
    window.__w103OwnerVisualReplayAudit = state;
    const isVisible = (element) => {
      if (!element) return false;
      const style = getComputedStyle(element);
      return style.display !== 'none'
        && style.visibility !== 'hidden'
        && element.getClientRects().length > 0;
    };
    const inspect = () => {
      const overlay = document.getElementById('boss-cinematic');
      if (!overlay || overlay.dataset.zoneKey !== zoneKey
          || overlay.dataset.zone3PresentationOnly !== 'true'
          || !overlay.classList.contains('show')) return;
      state.replayContextObserved = true;
      const bad = hiddenSelectors.filter((selector) => isVisible(document.querySelector(selector)));
      if (bad.length) state.badVisibleFirstClearFields = Array.from(new Set(bad));
      const title = document.getElementById('boss-cinematic-title');
      state.exactSealTextVisible = isVisible(title)
        && /領主封印已解除|boss seal broken/i.test(title.textContent || '');
    };
    window.__w103InspectOwnerReplay = inspect;
    new MutationObserver(inspect).observe(document, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['class', 'style', 'hidden', 'data-zone-key', 'data-zone3-replay', 'data-zone3-presentation-only'],
    });
    inspect();
  }, { zoneKey: ZONE3_KEY, hiddenSelectors: REPLAY_HIDDEN_SELECTORS });
}

async function loginAndOpen(page, locale, account = 'REPLAY') {
  const creds = credentials(account);
  const base = origin();
  await page.goto(`${base}/login?lang=${locale.appLang}`, {
    waitUntil: 'domcontentloaded',
    timeout: PAGE_TIMEOUT_MS,
  });
  await page.locator('#username').fill(creds.username);
  await page.locator('#password').fill(creds.password);
  await page.locator('#login-btn').click();
  await page.waitForFunction(() => location.pathname !== '/login', { timeout: PAGE_TIMEOUT_MS });
  await page.goto(`${base}/${E9_QUERY}&lang=${locale.appLang}`, {
    waitUntil: 'domcontentloaded',
    timeout: PAGE_TIMEOUT_MS,
  });
  await page.locator('#e9-world-stage-slot').waitFor({ state: 'attached', timeout: PAGE_TIMEOUT_MS });
  await page.locator(`#e9-world-stage-slot [data-zone="${ZONE3_KEY}"]`)
    .waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
  await page.waitForFunction(
    (expected) => document.documentElement.lang === expected
      || document.documentElement.lang === expected.slice(0, 2),
    locale.htmlLang,
    { timeout: PAGE_TIMEOUT_MS },
  );
}

async function selectZone3(page) {
  const tile = page.locator(`#e9-world-stage-slot [data-zone="${ZONE3_KEY}"]`);
  await tile.click();
  await page.waitForFunction((key) => {
    const root = document.getElementById('e9-world-stage-slot');
    const overlay = document.getElementById('boss-cinematic');
    const zone = root?.__e9WorldStageState?.zones?.find((item) => item?.key === key);
    return root?.__e9WorldStageState?.selectedZoneKey === key
      && (zone?.cleared === true
        || overlay?.classList.contains('show') === true
        || document.documentElement.dataset.zone3PresentationFailsafe === 'reached');
  }, ZONE3_KEY, { timeout: PAGE_TIMEOUT_MS });
}

async function bootstrapFingerprint(page) {
  return page.evaluate(async () => {
    const response = await fetch('/api/adventure/bootstrap', { credentials: 'include' });
    if (!response.ok) throw new Error(`bootstrap fingerprint failed: HTTP ${response.status}`);
    const body = await response.json();
    return JSON.stringify({
      current_zone_key: body.current_zone_key ?? null,
      zones: (body.zones || []).map((zone) => ({
        key: zone?.key ?? null,
        status: zone?.status ?? null,
        stars: zone?.stars ?? null,
        cleared: zone?.cleared ?? null,
        unlocked: zone?.unlocked ?? null,
      })),
    });
  });
}

async function waitForReplayPresentation(page) {
  await page.waitForFunction((key) => {
    const overlay = document.getElementById('boss-cinematic');
    return overlay?.classList.contains('show')
      && overlay.dataset.zoneKey === key
      && overlay.dataset.zone3Replay === 'true'
      && overlay.dataset.zone3PresentationOnly === 'true'
      && (overlay.classList.contains('ready')
        || document.querySelectorAll('#intro-film-stage .film-shot.active').length === 1);
  }, ZONE3_KEY, { timeout: PAGE_TIMEOUT_MS });
  await page.evaluate(() => window.__w103InspectOwnerReplay?.());
}

async function replayOverlayState(page) {
  return page.evaluate((hiddenSelectors) => {
    const overlay = document.getElementById('boss-cinematic');
    const visible = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return false;
      const style = getComputedStyle(element);
      return style.display !== 'none'
        && style.visibility !== 'hidden'
        && element.getClientRects().length > 0;
    };
    return {
      className: overlay?.className || '',
      dataset: overlay ? { ...overlay.dataset } : {},
      activeShots: document.querySelectorAll('#intro-film-stage .film-shot.active').length,
      visibleFirstClearFields: hiddenSelectors.filter(visible),
      sealTextVisible: visible('#boss-cinematic-title')
        && /領主封印已解除|boss seal broken/i.test(document.getElementById('boss-cinematic-title')?.textContent || ''),
    };
  }, REPLAY_HIDDEN_SELECTORS);
}

async function dismissReplay(page) {
  for (let index = 0; index < 24; index += 1) {
    if (!(await page.locator('#boss-cinematic.show').count())) return;
    const skip = page.locator('.intro-skip-btn:visible').first();
    if (await skip.count()) {
      await skip.click({ timeout: PAGE_TIMEOUT_MS });
      continue;
    }
    const gesture = page.locator('#boss-cinematic-btn:visible').first();
    if (await gesture.count() && await gesture.isEnabled()) {
      await gesture.click({ timeout: PAGE_TIMEOUT_MS });
      continue;
    }
    const close = page.locator('.boss-cinematic-close-x:visible').first();
    if (await close.count()) {
      await close.click({ timeout: PAGE_TIMEOUT_MS });
      continue;
    }
    throw new Error('replay overlay has no visible dismissal control');
  }
  await page.waitForFunction(() => !document.getElementById('boss-cinematic')?.classList.contains('show'), {
    timeout: PAGE_TIMEOUT_MS,
  });
}

async function runReplayCase(browser, viewportId, viewport, locale, shouldCapture) {
  const context = await browser.newContext({ viewport, serviceWorkers: 'block' });
  const page = await context.newPage();
  const writes = [];
  page.on('request', (request) => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });
  try {
    await installOwnerReplayAudit(page);
    await loginAndOpen(page, locale);
    writes.length = 0;
    const before = await bootstrapFingerprint(page);
    await selectZone3(page);
    const replay = page.locator('#e9-world-stage-details-replay:visible, [data-e10-zone-replay]:visible').first();
    await replay.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
    requireValue(await replay.isEnabled(), `replay disabled at ${viewportId}/${locale.id}`);
    await replay.click();
    await waitForReplayPresentation(page);
    const state = await replayOverlayState(page);
    requireValue(state.dataset.zone3PresentationOnly === 'true', `missing replay-only context at ${viewportId}/${locale.id}`);
    requireValue(state.visibleFirstClearFields.length === 0, `first-clear fields visible at ${viewportId}/${locale.id}: ${state.visibleFirstClearFields.join(',')}`);
    requireValue(state.sealTextVisible === false, `first-clear seal text visible at ${viewportId}/${locale.id}`);
    requireValue(Number(state.activeShots) > 0 || state.className.includes('ready'), `replay did not reach presentation at ${viewportId}/${locale.id}`);
    if (shouldCapture) {
      await page.screenshot({ path: path.join(EVIDENCE_DIR, `replay-${locale.id}-${viewportId}.png`), fullPage: false });
    }
    await dismissReplay(page);
    const after = await bootstrapFingerprint(page);
    requireValue(before === after, `replay changed authoritative state at ${viewportId}/${locale.id}`);
    requireValue(writes.length === 0, `replay issued mutation requests at ${viewportId}/${locale.id}: ${writes.join(', ')}`);
    return { viewportId, locale: locale.id, state, mutationCount: writes.length };
  } finally {
    await context.close();
  }
}

async function runLordCase(browser, viewportId, viewport, locale, shouldCapture) {
  const context = await browser.newContext({ viewport, serviceWorkers: 'block' });
  const page = await context.newPage();
  const writes = [];
  page.on('request', (request) => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });
  try {
    await loginAndOpen(page, locale);
    writes.length = 0;
    const before = await bootstrapFingerprint(page);
    await selectZone3(page);
    await page.waitForFunction(() => Array.from(document.querySelectorAll('button')).some((button) => {
      const rect = button.getBoundingClientRect();
      const style = getComputedStyle(button);
      return rect.width > 0 && rect.height > 0
        && style.display !== 'none'
        && style.visibility !== 'hidden'
        && /再次挑戰領主|Challenge the Lord|Challenge this boss again/i.test(button.textContent || '');
    }), { timeout: PAGE_TIMEOUT_MS });
    const lord = page.locator('button:visible').filter({ hasText: /再次挑戰領主|Challenge the Lord|Challenge this boss again/i }).first();
    await lord.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
    await lord.click();
    await page.locator('#boss-cinematic.phase-zone3-lord-card.show').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
    // A CSS background is not represented by an <img> element, so wait for
    // the browser's completed resource entry before taking Owner evidence.
    // This prevents a screenshot of the correctly bound card taken one paint
    // too early, while keeping the runtime binding itself unchanged.
    await page.waitForFunction((artPath) => performance.getEntriesByType('resource').some((entry) => {
      try { return new URL(entry.name).pathname === artPath; } catch { return false; }
    }), LORD_ART_PATH, { timeout: PAGE_TIMEOUT_MS });
    const state = await page.evaluate((artPath) => {
      const overlay = document.getElementById('boss-cinematic');
      const scene = document.querySelector('#boss-cinematic .boss-cinematic-scene');
      const style = scene ? getComputedStyle(scene) : null;
      const rect = scene?.getBoundingClientRect();
      const controls = ['#boss-cinematic-cancel-btn', '#boss-cinematic-btn'].map((selector) => {
        const element = document.querySelector(selector);
        const buttonRect = element?.getBoundingClientRect();
        const buttonStyle = element ? getComputedStyle(element) : null;
        return {
          selector,
          visible: Boolean(element && buttonRect && buttonRect.width > 0 && buttonRect.height > 0
            && buttonStyle?.visibility !== 'hidden' && buttonStyle?.display !== 'none'),
          enabled: element ? !element.disabled : false,
          width: buttonRect?.width || 0,
          height: buttonRect?.height || 0,
        };
      });
      return {
        className: overlay?.className || '',
        dataset: overlay ? { ...overlay.dataset } : {},
        backgroundImage: style?.backgroundImage || '',
        sceneRect: rect ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height } : null,
        viewport: { width: window.innerWidth, height: window.innerHeight },
        controls,
        artBound: style?.backgroundImage?.includes(artPath) === true,
        artResourceLoaded: performance.getEntriesByType('resource').some((entry) => {
          try { return new URL(entry.name).pathname === artPath; } catch { return false; }
        }),
      };
    }, LORD_ART_PATH);
    requireValue(state.artBound, `canonical Lord art not bound at ${viewportId}/${locale.id}: ${state.backgroundImage}`);
    requireValue(state.artResourceLoaded, `canonical Lord art did not finish loading at ${viewportId}/${locale.id}`);
    requireValue(state.dataset.zone3LordAsset === LORD_ART_PATH, `Lord asset dataset mismatch at ${viewportId}/${locale.id}`);
    requireValue(state.controls.every((control) => control.visible && control.enabled && control.height >= 40), `Lord controls not usable at ${viewportId}/${locale.id}: ${JSON.stringify(state.controls)}`);
    requireValue(state.sceneRect && state.sceneRect.width > 0 && state.sceneRect.height > 0
      && state.sceneRect.x >= -1 && state.sceneRect.y >= -1
      && state.sceneRect.x + state.sceneRect.width <= state.viewport.width + 1
      && state.sceneRect.y + state.sceneRect.height <= state.viewport.height + 1,
    `Lord art card is outside viewport at ${viewportId}/${locale.id}: ${JSON.stringify(state.sceneRect)}`);
    if (shouldCapture) {
      await page.screenshot({ path: path.join(EVIDENCE_DIR, `lord-rechallenge-${locale.id}-${viewportId}.png`), fullPage: false });
    }
    await page.locator('#boss-cinematic-cancel-btn:visible').click();
    await page.waitForFunction(() => !document.getElementById('boss-cinematic')?.classList.contains('show'), {
      timeout: PAGE_TIMEOUT_MS,
    });
    const after = await bootstrapFingerprint(page);
    requireValue(before === after, `opening Lord confirmation changed authoritative state at ${viewportId}/${locale.id}`);
    requireValue(writes.length === 0, `Lord confirmation issued mutation requests at ${viewportId}/${locale.id}: ${writes.join(', ')}`);
    return { viewportId, locale: locale.id, state, mutationCount: writes.length };
  } finally {
    await context.close();
  }
}

async function runRepeatedReplay(browser) {
  const viewportId = 'desktop';
  const locale = LOCALES[0];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewportId], serviceWorkers: 'block' });
  const page = await context.newPage();
  try {
    await installOwnerReplayAudit(page);
    await loginAndOpen(page, locale);
    const before = await bootstrapFingerprint(page);
    for (let cycle = 1; cycle <= 3; cycle += 1) {
      await selectZone3(page);
      const replay = page.locator('#e9-world-stage-details-replay:visible, [data-e10-zone-replay]:visible').first();
      await replay.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
      await replay.click();
      await waitForReplayPresentation(page);
      const state = await replayOverlayState(page);
      requireValue(state.visibleFirstClearFields.length === 0 && state.sealTextVisible === false,
        `repeated replay leaked first-clear overlay on cycle ${cycle}`);
      await dismissReplay(page);
    }
    const after = await bootstrapFingerprint(page);
    requireValue(before === after, 'three story replays changed authoritative state');
    return 3;
  } finally {
    await context.close();
  }
}

async function installUnseenZone3BootstrapFixture(page) {
  // The fixture keeps the live server response and changes only the
  // presentation-seen bit needed to exercise the accepted first-entry
  // negative control. It does not manufacture unlock, clear, reward, or
  // gameplay authority.
  await page.route('**/api/adventure/bootstrap**', async (route) => {
    const response = await route.fetch();
    if (!response.ok()) {
      await route.fulfill({ response });
      return;
    }
    const body = await response.json();
    const cinematics = body.cinematics && typeof body.cinematics === 'object'
      ? { ...body.cinematics }
      : {};
    cinematics.e10_zone3_intro_v1 = {
      ...(cinematics.e10_zone3_intro_v1 || {}),
      seen: false,
      seen_at: null,
    };
    await route.fulfill({ response, body: JSON.stringify({ ...body, cinematics }) });
  });
}

async function runPresentationFailureCase(browser, viewportId, viewport) {
  const context = await browser.newContext({ viewport, serviceWorkers: 'block' });
  const page = await context.newPage();
  let missingAssetHits = 0;
  const writes = [];
  page.on('request', (request) => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });
  await installUnseenZone3BootstrapFixture(page);
  await context.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url());
    if (ZONE3_IMAGE_PATTERN.test(requestUrl.pathname)) {
      missingAssetHits += 1;
      await route.fulfill({
        status: 404,
        contentType: 'text/plain',
        body: 'intentional owner-acceptance presentation negative control',
      });
      return;
    }
    await route.continue();
  });
  try {
    await loginAndOpen(page, LOCALES[1], 'PLAYER');
    writes.length = 0;
    await selectZone3(page);
    try {
      await page.waitForFunction(() => document.documentElement.dataset.zone3PresentationFailsafe === 'reached', {
        timeout: PAGE_TIMEOUT_MS,
      });
    } catch (error) {
      let state = null;
      let stateError = null;
      try {
        state = await page.evaluate((zoneKey) => ({
          path: location.pathname,
          overlay: document.getElementById('boss-cinematic')
            ? { className: document.getElementById('boss-cinematic').className, dataset: { ...document.getElementById('boss-cinematic').dataset } }
            : null,
          selectedZoneKey: document.getElementById('e9-world-stage-slot')?.__e9WorldStageState?.selectedZoneKey || null,
          zone3: document.getElementById('e9-world-stage-slot')?.__e9WorldStageState?.zones?.find((zone) => zone?.key === zoneKey) || null,
          zone3Resources: performance.getEntriesByType('resource').map((entry) => entry.name).filter((name) => name.includes('/assets/e10/art/zone3/')),
        }), ZONE3_KEY);
      } catch (stateReadError) {
        stateError = String(stateReadError?.message || stateReadError);
      }
      throw new Error(`presentation negative control did not reach fail-safe at ${viewportId}: ${JSON.stringify(state)} stateError=${stateError}; ${error.message}`);
    }
    const result = await page.evaluate(() => ({
      failsafe: document.documentElement.dataset.zone3PresentationFailsafe || null,
      overlayShowing: document.getElementById('boss-cinematic')?.classList.contains('show') === true,
      overlayAriaHidden: document.getElementById('boss-cinematic')?.getAttribute('aria-hidden') || null,
      activeShots: document.querySelectorAll('#intro-film-stage .film-shot.active').length,
      timers: typeof _introFilmTimers !== 'undefined' ? _introFilmTimers.length : null,
      speechTimers: typeof _introSpeechTimers !== 'undefined' ? _introSpeechTimers.length : null,
    }));
    requireValue(missingAssetHits > 0, `negative control intercepted no Zone 3 image at ${viewportId}`);
    requireValue(result.failsafe === 'reached' && result.overlayShowing === false
      && result.overlayAriaHidden === 'true' && result.activeShots === 0,
    `presentation failure did not fail closed at ${viewportId}: ${JSON.stringify(result)}`);
    requireValue(writes.length === 0, `presentation failure issued mutation requests at ${viewportId}: ${writes.join(', ')}`);
    return { viewportId, missingAssetHits, result, mutationCount: writes.length };
  } finally {
    await context.close();
  }
}

async function main() {
  fssync.mkdirSync(EVIDENCE_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: chromePath() });
  const replayResults = [];
  const lordResults = [];
  const presentationFailureOnly = process.env.E2E_PRESENTATION_FAILURE_ONLY === '1';
  try {
    if (!presentationFailureOnly) {
      for (const locale of LOCALES) {
        for (const [viewportId, viewport] of Object.entries(VIEWPORTS)) {
          replayResults.push(await runReplayCase(
            browser,
            viewportId,
            viewport,
            locale,
            viewportId === 'ipad_portrait' || viewportId === 'ipad_landscape',
          ));
        }
      }
      for (const locale of LOCALES) {
        for (const [viewportId, viewport] of Object.entries(VIEWPORTS)) {
          lordResults.push(await runLordCase(
            browser,
            viewportId,
            viewport,
            locale,
            viewportId === 'ipad_portrait' || viewportId === 'ipad_landscape',
          ));
        }
      }
    }
    const repeatedReplayCount = presentationFailureOnly ? 0 : await runRepeatedReplay(browser);
    const presentationFailureResults = [];
    for (const [viewportId, viewport] of Object.entries(VIEWPORTS)) {
      presentationFailureResults.push(await runPresentationFailureCase(browser, viewportId, viewport));
    }
    console.log(JSON.stringify({
      replayCaseCount: replayResults.length,
      lordCaseCount: lordResults.length,
      repeatedReplayCount,
      presentationFailureCaseCount: presentationFailureResults.length,
      presentationFailureInterceptedCount: presentationFailureResults.reduce((sum, item) => sum + item.missingAssetHits, 0),
      replayMutationCount: replayResults.reduce((sum, item) => sum + item.mutationCount, 0),
      lordMutationCount: lordResults.reduce((sum, item) => sum + item.mutationCount, 0),
      presentationFailureMutationCount: presentationFailureResults.reduce((sum, item) => sum + item.mutationCount, 0),
      evidenceDir: EVIDENCE_DIR,
      ownerEvidence: [
        path.join(EVIDENCE_DIR, 'replay-zh-TW-ipad_portrait.png'),
        path.join(EVIDENCE_DIR, 'lord-rechallenge-zh-TW-ipad_portrait.png'),
      ],
    }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
