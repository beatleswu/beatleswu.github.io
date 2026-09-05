// Focused W1-03 repair runner for the four authoritative Zone 3 failures.
//
// This is deliberately smaller than the W1-05 40-case matrix: it exercises
// replay, route-exit cleanup, presentation-failure no-op, and final-state
// return once at each of the four required Chromium viewport layouts.  The
// W1-05 runner remains the final integrated acceptance authority.
'use strict';

import fssync from 'node:fs';
import process from 'node:process';
import { chromium } from 'playwright-core';

const ZONE3_KEY = 'k16_20';
const PAGE_TIMEOUT_MS = 20000;
const MAX_DISMISS_CLICKS = 24;
const E9_QUERY = '?E9_DEBUG=1&e9Shell=1&e9TopHud=1&e9LeftNav=1&e9RightCards=1&e9BottomDock=1&e9WorldStage=1';
const VIEWPORTS = Object.freeze({
  desktop: Object.freeze({ width: 1920, height: 1080 }),
  ipad_landscape: Object.freeze({ width: 1180, height: 820 }),
  ipad_portrait: Object.freeze({ width: 820, height: 1180 }),
  mobile_portrait: Object.freeze({ width: 390, height: 844 }),
});
const CASES = Object.freeze([
  Object.freeze({ id: 'replay', account: 'REPLAY', locale: 'zh-TW' }),
  Object.freeze({ id: 'route_exit_cleanup', account: 'REPLAY', locale: 'zh-TW' }),
  Object.freeze({ id: 'presentation_failure_noop', account: 'EN', locale: 'en-US' }),
  Object.freeze({ id: 'final_state_return', account: 'REPLAY', locale: 'zh-TW' }),
]);
const PREVIOUSLY_PASSING_CASES = Object.freeze([
  Object.freeze({ id: 'first_entry_zh_TW', account: 'ZH', locale: 'zh-TW' }),
  Object.freeze({ id: 'first_entry_en_US', account: 'EN', locale: 'en-US' }),
  Object.freeze({ id: 'locale_switch', account: 'ZH', locale: 'zh-TW' }),
  Object.freeze({ id: 'reduced_motion', account: 'ZH', locale: 'zh-TW' }),
  Object.freeze({ id: 'global_mute', account: 'ZH', locale: 'zh-TW' }),
  Object.freeze({ id: 'cinematic_lifecycle', account: 'ZH', locale: 'zh-TW' }),
]);
const INCLUDE_PREVIOUSLY_PASSING = process.env.E2E_INCLUDE_PREVIOUS_PASSING === '1';
const CASE_FILTER = process.env.E2E_CASE_FILTER
  ? new Set(process.env.E2E_CASE_FILTER.split(',').map((value) => value.trim()).filter(Boolean))
  : null;
const VIEWPORT_FILTER = process.env.E2E_VIEWPORT_FILTER
  ? new Set(process.env.E2E_VIEWPORT_FILTER.split(',').map((value) => value.trim()).filter(Boolean))
  : null;
const ZONE3_IMAGE_PATTERN = /\/assets\/e10\/art\/zone3\/cinematic\/zone3_shot\d+\.webp$/i;

function requireValue(value, message) {
  if (!value) throw new Error(message);
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

function origin() {
  const value = process.env.E2E_BASE_URL;
  requireValue(value, 'E2E_BASE_URL is required');
  const url = new URL(value);
  if (url.hostname === 'godokoro.com' || url.hostname.endsWith('.godokoro.com') || url.hostname === '152.69.200.105') {
    throw new Error(`refusing production target ${url.hostname}`);
  }
  return url.origin;
}

function credentials(account) {
  const username = process.env[`E2E_ZONE3_${account}_USERNAME`];
  const password = process.env[`E2E_ZONE3_${account}_PASSWORD`];
  requireValue(username && password, `missing E2E_ZONE3_${account}_USERNAME/PASSWORD`);
  return { username, password };
}

function browserErrors(page, sink) {
  page.on('pageerror', (error) => sink.push({ kind: 'pageerror', text: String(error?.message || error) }));
  page.on('console', (message) => {
    if (message.type() === 'error') sink.push({ kind: 'console.error', text: message.text() });
  });
  page.on('requestfailed', (request) => sink.push({
    kind: 'requestfailed',
    url: request.url(),
    error: request.failure()?.errorText || 'unknown',
  }));
}

async function loginAndOpen(page, account, locale) {
  const appLang = locale === 'en-US' ? 'en' : 'zh';
  const htmlLang = locale === 'en-US' ? 'en' : 'zh-TW';
  const creds = credentials(account);
  const base = origin();
  await page.goto(`${base}/login?lang=${appLang}`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
  await page.locator('#username').fill(creds.username);
  await page.locator('#password').fill(creds.password);
  await page.locator('#login-btn').click();
  await page.waitForFunction(() => location.pathname !== '/login', { timeout: PAGE_TIMEOUT_MS });
  await page.goto(`${base}/${E9_QUERY}&lang=${appLang}`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
  await page.locator('#e9-world-stage-slot').waitFor({ state: 'attached', timeout: PAGE_TIMEOUT_MS });
  await page.locator(`#e9-world-stage-slot [data-zone="${ZONE3_KEY}"]`).waitFor({ state: 'attached', timeout: PAGE_TIMEOUT_MS });
  await page.waitForFunction((expected) => document.documentElement.lang === expected || document.documentElement.lang === expected.slice(0, 2), htmlLang, { timeout: PAGE_TIMEOUT_MS });
}

async function dismissUnrelatedCinematic(page) {
  for (let index = 0; index < MAX_DISMISS_CLICKS; index += 1) {
    const state = await page.evaluate(() => {
      const overlay = document.getElementById('boss-cinematic');
      return {
        showing: overlay?.classList.contains('show') === true,
        zoneKey: overlay?.dataset.zoneKey || null,
      };
    });
    if (!state.showing || state.zoneKey === ZONE3_KEY) return;
    const skip = page.locator('.intro-skip-btn:visible').first();
    if (await skip.count() && await skip.isVisible()) {
      try {
        await skip.click({ timeout: PAGE_TIMEOUT_MS });
        continue;
      } catch {
        continue;
      }
    }
    const close = page.locator('.boss-cinematic-close-x:visible').first();
    if (await close.count() && await close.isVisible()) {
      try {
        await close.click({ timeout: PAGE_TIMEOUT_MS });
        continue;
      } catch {
        continue;
      }
    }
    const cancel = page.locator('#boss-cinematic-cancel-btn:visible').first();
    if (await cancel.count() && await cancel.isVisible()) {
      try {
        await cancel.click({ timeout: PAGE_TIMEOUT_MS });
        continue;
      } catch {
        continue;
      }
    }
    throw new Error(`unrelated cinematic blocked Zone 3 selection: ${JSON.stringify(state)}`);
  }
  await page.waitForFunction((key) => {
    const overlay = document.getElementById('boss-cinematic');
    return !overlay?.classList.contains('show') || overlay.dataset.zoneKey === key;
  }, ZONE3_KEY, { timeout: PAGE_TIMEOUT_MS });
}

async function selectZone3(page) {
  const tile = page.locator(`#e9-world-stage-slot [data-zone="${ZONE3_KEY}"]`);
  await tile.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
  await dismissUnrelatedCinematic(page);
  await tile.click();
  await page.waitForFunction((key) => document.getElementById('e9-world-stage-slot')?.__e9WorldStageState?.selectedZoneKey === key, ZONE3_KEY, { timeout: PAGE_TIMEOUT_MS });
  try {
    await page.waitForFunction((key) => {
      const root = document.getElementById('e9-world-stage-slot');
      const state = root?.__e9WorldStageState;
      const overlay = document.getElementById('boss-cinematic');
      const zone = state?.zones?.find((item) => item?.key === key);
      return state?.selectedZoneKey === key
        && ((zone?.cleared === true || zone?.status === 'completed')
          || overlay?.classList.contains('show')
          || state.zone3EntryInFlight === true
          || document.documentElement.dataset.zone3PresentationFailsafe === 'reached');
    }, ZONE3_KEY, { timeout: PAGE_TIMEOUT_MS });
  } catch (error) {
    const state = await page.evaluate(() => {
      const root = document.getElementById('e9-world-stage-slot');
      const overlay = document.getElementById('boss-cinematic');
      return {
        rootState: root?.__e9WorldStageState ? { ...root.__e9WorldStageState } : null,
        overlay: overlay ? { className: overlay.className, dataset: { ...overlay.dataset } } : null,
        readyState: document.readyState,
      };
    }).catch(() => null);
    throw new Error(`Zone 3 selection did not reach a stable presentation state: ${JSON.stringify(state)}; ${error.message}`);
  }
  await dismissUnrelatedCinematic(page);
}

async function waitForActiveCinematic(page) {
  try {
    await page.waitForFunction((key) => {
      const overlay = document.getElementById('boss-cinematic');
      return overlay?.classList.contains('show')
        && overlay.dataset.zoneKey === key
        && overlay.getAttribute('aria-hidden') === 'false'
        && document.querySelectorAll('#intro-film-stage .film-shot.active').length === 1;
    }, ZONE3_KEY, { timeout: PAGE_TIMEOUT_MS });
  } catch (error) {
    const state = await page.evaluate(() => {
      const overlay = document.getElementById('boss-cinematic');
      const internals = window.eval(`({
        introAudioUnlocked: typeof _introAudioUnlocked !== 'undefined' ? _introAudioUnlocked : null,
        introAudioUnlockPromise: typeof _introAudioUnlockPromise !== 'undefined' ? Boolean(_introAudioUnlockPromise) : null,
        introFilmRunId: typeof _introFilmRunId !== 'undefined' ? _introFilmRunId : null,
        sequenceRunId: typeof _zoneCinematicSequenceRunId !== 'undefined' ? _zoneCinematicSequenceRunId : null,
        presentationOnly: typeof _zoneCinematicPresentationOnly !== 'undefined' ? _zoneCinematicPresentationOnly : null,
      })`);
      return {
        overlayShowing: overlay?.classList.contains('show') === true,
        overlayDataset: overlay ? { ...overlay.dataset } : null,
        ariaHidden: overlay?.getAttribute('aria-hidden') || null,
        activeShots: document.querySelectorAll('#intro-film-stage .film-shot.active').length,
        pendingButton: document.getElementById('boss-cinematic-btn')?.textContent || null,
        replayControl: Array.from(document.querySelectorAll('[data-e10-zone-replay]')).find((item) => item.offsetWidth || item.offsetHeight || item.getClientRects().length)?.outerHTML?.slice(0, 500) || null,
        internals,
      };
    }).catch(() => null);
    throw new Error(`cinematic did not become active: ${JSON.stringify(state)}; ${error.message}`);
  }
}

async function waitForZone3EntryOverlay(page) {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      await page.waitForFunction(() => (
        document.getElementById('boss-cinematic')?.classList.contains('show')
        || document.documentElement.dataset.zone3PresentationFailsafe === 'reached'
      ), { timeout: PAGE_TIMEOUT_MS });
    } catch (error) {
      const state = await page.evaluate(() => ({
        root: document.getElementById('e9-world-stage-slot')?.__e9WorldStageState || null,
        overlay: document.getElementById('boss-cinematic') ? { className: document.getElementById('boss-cinematic').className, dataset: { ...document.getElementById('boss-cinematic').dataset } } : null,
      })).catch(() => null);
      throw new Error(`no active cinematic appeared while selecting Zone 3: ${JSON.stringify(state)}; ${error.message}`);
    }
    const overlayState = await page.evaluate(() => {
      const overlay = document.getElementById('boss-cinematic');
      return {
        showing: overlay?.classList.contains('show') === true,
        zoneKey: overlay?.dataset.zoneKey || null,
        failed: document.documentElement.dataset.zone3PresentationFailsafe === 'reached',
      };
    });
    if (overlayState.failed || (overlayState.showing && overlayState.zoneKey === ZONE3_KEY)) return;
    await dismissUnrelatedCinematic(page);
  }
  throw new Error('Zone 3 entry overlay did not become the active cinematic');
}

async function openReplay(page) {
  await selectZone3(page);
  const replay = page.locator('#e9-world-stage-details-replay:visible, [data-e10-zone-replay]:visible').first();
  await replay.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
  requireValue(await replay.isEnabled(), 'Zone 3 replay control is disabled');
  await replay.click();
  await waitForActiveCinematic(page);
}

async function dismissCinematic(page) {
  for (let index = 0; index < MAX_DISMISS_CLICKS; index += 1) {
    if (!(await page.locator('#boss-cinematic.show').count())) break;
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
    throw new Error('cinematic is showing but has no visible dismissal control');
  }
  await page.waitForFunction(() => !document.getElementById('boss-cinematic')?.classList.contains('show'), { timeout: PAGE_TIMEOUT_MS });
}

async function stateFingerprint(page) {
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

async function cleanupSnapshot(page) {
  return page.evaluate(() => {
    const internal = window.eval(`({
      filmTimers: typeof _introFilmTimers !== 'undefined' ? _introFilmTimers.length : null,
      speechTimers: typeof _introSpeechTimers !== 'undefined' ? _introSpeechTimers.length : null,
      replayAdvance: typeof _zoneCinematicAdvanceSegment === 'function',
      presentationOnly: typeof _zoneCinematicPresentationOnly !== 'undefined' ? _zoneCinematicPresentationOnly : null,
      introFilmRunId: typeof _introFilmRunId !== 'undefined' ? _introFilmRunId : null,
    })`);
    const activeAudio = Array.from(document.querySelectorAll('audio')).filter((audio) => !audio.paused && !audio.muted && audio.volume > 0).length;
    const runtime = window.__GO_ZONE3_PRESENTATION_RUNTIME__ || {};
    return {
      activePresentationOwnerCount: internal.presentationOnly ? 1 : 0,
      orphanAudioCount: activeAudio,
      orphanTimerCount: (internal.filmTimers || 0) + (internal.speechTimers || 0),
      orphanAnimationFrameCount: runtime.fx || runtime.audio ? 1 : 0,
      staleEventHandlerCount: document.querySelector('#e9-world-stage-slot [data-zone]') ? 1 : 0,
      internal,
    };
  });
}

async function runCase(browser, spec, viewport, dimensions) {
  const context = await browser.newContext({
    viewport: dimensions,
    reducedMotion: spec.id === 'reduced_motion' ? 'reduce' : 'no-preference',
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  await page.addInitScript((zoneKey) => {
    const state = {
      entryVisible: false,
      entryActiveShot: false,
      entryCompleted: false,
    };
    window.__w103Zone3EntryObservation = state;
    const inspect = () => {
      const overlay = document.getElementById('boss-cinematic');
      if (!overlay || overlay.dataset.zoneKey !== zoneKey) return;
      if (overlay.dataset.zone3EntryFlow === 'true'
          && overlay.getAttribute('aria-hidden') === 'false') {
        state.entryVisible = true;
      }
      if (overlay.dataset.zone3EntryCompleted === 'true') {
        state.entryCompleted = true;
      }
      if (document.querySelectorAll('#intro-film-stage .film-shot.active').length === 1) {
        state.entryActiveShot = true;
      }
    };
    new MutationObserver(inspect).observe(document, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['class', 'aria-hidden', 'data-zone-key', 'data-zone3-entry-flow', 'data-zone3-entry-completed'],
    });
    inspect();
  }, ZONE3_KEY);
  const errors = [];
  browserErrors(page, errors);
  let missingAssetHits = 0;
  if (spec.id === 'presentation_failure_noop') {
    const cdp = await context.newCDPSession(page);
    await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
    await context.route('**/*', async (route) => {
      const requestUrl = new URL(route.request().url());
      if (ZONE3_IMAGE_PATTERN.test(requestUrl.pathname)) {
        missingAssetHits += 1;
        await route.fulfill({ status: 404, body: 'intentional Wave 1 presentation negative control' });
        return;
      }
      await route.continue();
    });
  }
  try {
    await loginAndOpen(page, spec.account, spec.locale);
    if (spec.id === 'first_entry_zh_TW' || spec.id === 'first_entry_en_US') {
      await selectZone3(page);
      let activeWaitError = null;
      try {
        await waitForActiveCinematic(page);
      } catch (error) {
        activeWaitError = String(error?.message || error);
      }
      const cinematic = await page.evaluate(() => ({
        visible: document.getElementById('boss-cinematic')?.classList.contains('show') === true,
        zoneKey: document.getElementById('boss-cinematic')?.dataset.zoneKey || null,
        ariaHidden: document.getElementById('boss-cinematic')?.getAttribute('aria-hidden') || null,
        activeShots: document.querySelectorAll('#intro-film-stage .film-shot.active').length,
        entryCompleted: document.getElementById('boss-cinematic')?.dataset.zone3EntryCompleted || null,
        observed: window.__w103Zone3EntryObservation || null,
      }));
      requireValue(cinematic.observed?.entryVisible === true
        && (cinematic.observed.entryActiveShot === true || cinematic.observed.entryCompleted === true),
      `first-entry cinematic invalid: ${JSON.stringify({ cinematic, activeWaitError })}`);
      return { cinematic, activeWaitError };
    }
    if (spec.id === 'locale_switch') {
      const initial = await page.evaluate(() => document.documentElement.lang);
      const en = page.locator('#lang-switcher-index [data-lang="en"]').first();
      const zh = page.locator('#lang-switcher-index [data-lang="zh"]').first();
      await en.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
      await en.click();
      await page.waitForFunction(() => document.documentElement.lang === 'en', { timeout: PAGE_TIMEOUT_MS });
      const afterEnglish = await page.evaluate(() => document.documentElement.lang);
      await zh.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
      await zh.click();
      await page.waitForFunction(() => document.documentElement.lang === 'zh-TW', { timeout: PAGE_TIMEOUT_MS });
      const afterChinese = await page.evaluate(() => document.documentElement.lang);
      requireValue(initial === 'zh-TW' && afterEnglish === 'en' && afterChinese === 'zh-TW', `locale switch did not round-trip: ${initial}/${afterEnglish}/${afterChinese}`);
      return { initial, afterEnglish, afterChinese };
    }
    if (spec.id === 'reduced_motion') {
      const motion = await page.evaluate(() => ({
        prefersReducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        documentScrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
        stageTransition: getComputedStyle(document.getElementById('adventure-stage') || document.body).transitionDuration,
        stageAnimation: getComputedStyle(document.getElementById('adventure-stage') || document.body).animationDuration,
      }));
      requireValue(motion.prefersReducedMotion && motion.documentScrollBehavior !== 'smooth', `reduced-motion contract invalid: ${JSON.stringify(motion)}`);
      return motion;
    }
    if (spec.id === 'global_mute') {
      let settings = page.locator('[data-e10-command="settings"]:visible, [data-e10-nav-key="settings"]:visible').first();
      if (!(await settings.count())) {
        const more = page.locator('[data-e10-vs1f-nav="more"]:visible, .e10-more-trigger:visible').first();
        await more.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
        await more.click();
        settings = page.locator('#e10-all-features-overlay [data-e10-command="settings"]:visible, #e10-all-features-overlay [data-e10-nav-key="settings"]:visible').first();
      }
      await settings.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
      await settings.click();
      await page.locator('#e10-settings-overlay').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
      const sound = page.locator('#e10-settings-sound');
      await sound.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
      if (!(await sound.isChecked())) await sound.check();
      await sound.uncheck();
      const muted = await page.evaluate(() => ({
        muted: !!window.SFX?.muted,
        checked: !!document.getElementById('e10-settings-sound')?.checked,
      }));
      requireValue(muted.muted && muted.checked === false, `global mute did not reach SFX authority: ${JSON.stringify(muted)}`);
      return muted;
    }
    if (spec.id === 'cinematic_lifecycle') {
      await selectZone3(page);
      let activeWaitError = null;
      try {
        await waitForActiveCinematic(page);
      } catch (error) {
        activeWaitError = String(error?.message || error);
      }
      const started = await page.evaluate(() => ({
        visible: document.getElementById('boss-cinematic')?.classList.contains('show') === true,
        activeShots: document.querySelectorAll('#intro-film-stage .film-shot.active').length,
        observed: window.__w103Zone3EntryObservation || null,
      }));
      requireValue(started.observed?.entryVisible === true
        && (started.observed.entryActiveShot === true || started.observed.entryCompleted === true),
      `cinematic lifecycle did not observe Zone 3 presentation: ${JSON.stringify({ started, activeWaitError })}`);
      if (started.visible) await dismissCinematic(page);
      else await page.waitForFunction(() => !document.getElementById('boss-cinematic')?.classList.contains('show'), { timeout: PAGE_TIMEOUT_MS });
      const after = await page.evaluate(() => ({
        visible: document.getElementById('boss-cinematic')?.classList.contains('show') === true,
        ariaHidden: document.getElementById('boss-cinematic')?.getAttribute('aria-hidden') || null,
      }));
      requireValue(!after.visible && after.ariaHidden === 'true', `cinematic lifecycle invalid: ${JSON.stringify({ started, after, activeWaitError })}`);
      return { started, after, activeWaitError };
    }
    if (spec.id === 'presentation_failure_noop') {
      await selectZone3(page);
      await waitForZone3EntryOverlay(page);
      try {
        await page.waitForFunction(() => {
          const overlay = document.getElementById('boss-cinematic');
          const button = document.getElementById('boss-cinematic-btn');
          const activeShots = document.querySelectorAll('#intro-film-stage .film-shot.active').length;
          return document.documentElement.dataset.zone3PresentationFailsafe === 'reached'
            || (overlay?.classList.contains('show')
              && overlay.dataset.zoneKey === 'k16_20'
              && (activeShots === 1 || (button && !button.disabled && button.getClientRects().length > 0)));
        }, { timeout: PAGE_TIMEOUT_MS });
      } catch (error) {
        const state = await page.evaluate(() => {
          const overlay = document.getElementById('boss-cinematic');
          const button = document.getElementById('boss-cinematic-btn');
          return {
            overlay: overlay ? { className: overlay.className, dataset: { ...overlay.dataset } } : null,
            button: button ? { disabled: button.disabled, rects: button.getClientRects().length, text: button.textContent || null } : null,
            activeShots: document.querySelectorAll('#intro-film-stage .film-shot.active').length,
            failsafe: document.documentElement.dataset.zone3PresentationFailsafe || null,
          };
        }).catch(() => null);
        throw new Error(`Zone 3 negative control did not reach an active or failed presentation state: ${JSON.stringify(state)}; ${error.message}`);
      }
      const alreadyFailed = await page.evaluate(() => document.documentElement.dataset.zone3PresentationFailsafe === 'reached');
      if (!alreadyFailed && await page.locator('#intro-film-stage .film-shot.active').count() === 0) {
        const gesture = page.locator('#boss-cinematic-btn:visible').first();
        requireValue(await gesture.isEnabled(), 'Zone 3 presentation gesture control is disabled');
        await gesture.click();
      }
      try {
        await page.waitForFunction(() => document.documentElement.dataset.zone3PresentationFailsafe === 'reached', { timeout: PAGE_TIMEOUT_MS });
      } catch (error) {
        const state = await page.evaluate(() => {
          const overlay = document.getElementById('boss-cinematic');
          const root = document.getElementById('e9-world-stage-slot');
          return {
            path: location.pathname,
            overlayShowing: overlay?.classList.contains('show') === true,
            overlayDataset: overlay ? { ...overlay.dataset } : null,
            selectedZoneKey: root?.__e9WorldStageState?.selectedZoneKey || null,
            activeShots: document.querySelectorAll('#intro-film-stage .film-shot.active').length,
            images: Array.from(document.querySelectorAll('#intro-film-stage img')).map((image) => ({ src: image.getAttribute('src'), complete: image.complete, naturalWidth: image.naturalWidth })),
            zone3Resources: performance.getEntriesByType('resource').map((entry) => entry.name).filter((name) => name.includes('/assets/e10/art/zone3/')),
            internals: window.eval(`({
              introAudioUnlocked: typeof _introAudioUnlocked !== 'undefined' ? _introAudioUnlocked : null,
              introAudioUnlockPromise: typeof _introAudioUnlockPromise !== 'undefined' ? Boolean(_introAudioUnlockPromise) : null,
              introFilmRunId: typeof _introFilmRunId !== 'undefined' ? _introFilmRunId : null,
            })`),
          };
        }).catch(() => null);
        throw new Error(`presentation fail-safe did not settle (intercepted=${missingAssetHits}): ${JSON.stringify(state)}; ${error.message}`);
      }
      const result = await page.evaluate(() => ({
        overlayShowing: document.getElementById('boss-cinematic')?.classList.contains('show') === true,
        path: location.pathname,
        assetStatus: document.getElementById('boss-cinematic')?.dataset.assetStatus || null,
      }));
      requireValue(missingAssetHits > 0, 'presentation negative control intercepted no Zone 3 runtime image');
      requireValue(!result.overlayShowing && result.path === '/', `presentation failure did not fail closed: ${JSON.stringify(result)}`);
      return { missingAssetHits, ...result };
    }
    await openReplay(page);
    const before = await stateFingerprint(page);
    if (spec.id === 'route_exit_cleanup') {
      await page.evaluate(() => {
        if (!window.E9 || typeof window.E9.destroyShell !== 'function') throw new Error('E9 destroyShell unavailable');
        window.E9.destroyShell();
      });
      await page.waitForFunction(() => window.E9?.getActiveShell?.() === 'legacy' && !document.getElementById('boss-cinematic')?.classList.contains('show') && !document.querySelector('#e9-world-stage-slot [data-zone]'), { timeout: PAGE_TIMEOUT_MS });
      const cleanup = await cleanupSnapshot(page);
      requireValue(cleanup.activePresentationOwnerCount === 0 && cleanup.orphanAudioCount === 0 && cleanup.orphanTimerCount === 0 && cleanup.orphanAnimationFrameCount === 0 && cleanup.staleEventHandlerCount === 0, `route exit cleanup failed: ${JSON.stringify(cleanup)}`);
      return cleanup;
    }
    await dismissCinematic(page);
    const after = await stateFingerprint(page);
    requireValue(before === after, 'presentation replay changed authoritative progression fingerprint');
    const state = await page.evaluate((key) => ({
      overlayShowing: document.getElementById('boss-cinematic')?.classList.contains('show') === true,
      selectedZoneKey: document.getElementById('e9-world-stage-slot')?.__e9WorldStageState?.selectedZoneKey || null,
      zoneCardReachable: !!document.querySelector(`#e9-world-stage-slot [data-zone="${key}"]`),
    }), ZONE3_KEY);
    requireValue(!state.overlayShowing && state.selectedZoneKey === ZONE3_KEY && state.zoneCardReachable, `final state was not restored: ${JSON.stringify(state)}`);
    return { ...state, fingerprintUnchanged: true };
  } finally {
    await context.close();
  }
}

async function main() {
  const base = origin();
  const availableCases = INCLUDE_PREVIOUSLY_PASSING
    ? [...CASES, ...PREVIOUSLY_PASSING_CASES]
    : CASES;
  const selectedCases = CASE_FILTER
    ? availableCases.filter((spec) => CASE_FILTER.has(spec.id))
    : availableCases;
  const selectedViewports = Object.entries(VIEWPORTS)
    .filter(([viewport]) => !VIEWPORT_FILTER || VIEWPORT_FILTER.has(viewport));
  const report = {
    contract: 'w1_03_zone3_final_qa_blocker_repair_012',
    base_url: base,
    zone_key: ZONE3_KEY,
    cases: [],
    skipped: 0,
    physical_device_acceptance: 'NOT_PERFORMED',
  };
  [...new Set(selectedCases.map((spec) => spec.account))].forEach(credentials);
  const browser = await chromium.launch({ headless: true, executablePath: chromePath() });
  try {
    for (const spec of selectedCases) {
      for (const [viewport, dimensions] of selectedViewports) {
        const row = { case: spec.id, viewport, width: dimensions.width, height: dimensions.height, locale: spec.locale, status: 'FAIL' };
        try {
          row.evidence = await runCase(browser, spec, viewport, dimensions);
          row.status = 'PASS';
        } catch (error) {
          row.error = String(error?.stack || error);
        }
        report.cases.push(row);
        console.error(`[w1-03-012] ${spec.id}/${viewport}: ${row.status}`);
      }
    }
  } finally {
    await browser.close();
  }
  report.tests_collected = report.cases.length;
  report.tests_passed = report.cases.filter((row) => row.status === 'PASS').length;
  report.tests_failed = report.cases.filter((row) => row.status === 'FAIL').length;
  report.tests_skipped = 0;
  const expectedCount = selectedCases.length * selectedViewports.length;
  report.status = report.tests_collected === expectedCount && report.tests_passed === expectedCount ? 'PASS' : 'FAIL';
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = report.status === 'PASS' ? 0 : 1;
}

main().catch((error) => {
  console.error(error?.stack || String(error));
  process.exitCode = 1;
});
