import assert from 'node:assert/strict';
import fssync from 'node:fs';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const FIXTURE_PATH = '/tests/e2e/fixtures/w2_03_equipment_loadout_visual_slice.html';

const VIEWPORTS = Object.freeze({
  DESKTOP: { width: 1440, height: 900 },
  IPAD_LANDSCAPE: { width: 1024, height: 768 },
  IPAD_PORTRAIT: { width: 768, height: 1024 },
  MOBILE_PORTRAIT: { width: 390, height: 844 },
});

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

function contentType(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

async function startStaticServer() {
  const server = http.createServer(async (request, response) => {
    try {
      let pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
      if (pathname === '/') pathname = FIXTURE_PATH;
      const absolute = path.resolve(REPO_ROOT, `.${pathname}`);
      if (!absolute.startsWith(REPO_ROOT)) {
        response.writeHead(403);
        response.end('forbidden');
        return;
      }
      const body = await fs.readFile(absolute);
      response.writeHead(200, { 'content-type': contentType(absolute), 'cache-control': 'no-store' });
      response.end(body);
    } catch (_) {
      response.writeHead(404);
      response.end('not found');
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  return { server, origin: `http://127.0.0.1:${port}` };
}

function row({ id, invId, slot, equipped = false, equippable = true, asset = '' }) {
  return {
    item_id: id,
    id,
    inv_id: invId,
    display_name: id.replaceAll('_', ' '),
    display_name_en: id.replaceAll('_', ' '),
    name: id.replaceAll('_', ' '),
    name_en: id.replaceAll('_', ' '),
    slot,
    canonical_slot: equippable ? slot : null,
    rarity: 'common',
    icon: '/assets/hero/equipment/functional/wooden_sword.svg',
    equipped,
    canonical_equippable: equippable,
    presentation: asset
      ? { mode: 'FULL_BODY_OVERLAY', asset, presentation_only: true }
      : { mode: 'ICON_ONLY', presentation_only: true },
    active_effect_details: equippable
      ? [{ label: 'Server effect', label_en: 'Server effect', value_label: '+5%', value_label_en: '+5%' }]
      : [],
  };
}

function snapshot(loadoutEnabled) {
  return {
    capability: { equipment_loadout_enabled: loadoutEnabled },
    appearance: { character_key: 'apprentice' },
    inventory: [
      row({
        id: 'wooden_sword',
        invId: 101,
        slot: 'weapon',
        equipped: true,
        asset: '/assets/hero/equipment/wearables/overlays/wooden_sword.png',
      }),
      row({
        id: 'iron_sword',
        invId: 102,
        slot: 'weapon',
        asset: '/assets/hero/equipment/wearables/overlays/iron_sword.png',
      }),
      row({
        id: 'cloth_robe',
        invId: 103,
        slot: 'armor',
        asset: '/assets/hero/equipment/wearables/overlays/cloth_robe.png',
      }),
      row({ id: 'xp_amulet', invId: 104, slot: 'accessory', equippable: false }),
    ],
  };
}

async function mountSnapshot(page, value, { canonicalMutation = false } = {}) {
  await page.evaluate(({ value, canonicalMutation }) => {
    window.__w2FixtureSnapshot = structuredClone(value);
    window.__w2FixturePosts = [];
    if (window.__w2FixtureController) window.__w2FixtureController.destroy();
    const options = {
      snapshotLoader: async () => structuredClone(window.__w2FixtureSnapshot),
    };
    if (canonicalMutation) {
      options.fetchImpl = async (url, init) => {
        const payload = JSON.parse(init.body);
        window.__w2FixturePosts.push({ url, payload });
        const rows = window.__w2FixtureSnapshot.inventory;
        const target = rows.find((item) => String(item.inv_id) === String(payload.inv_id));
        if (target && payload.action === 'equip') {
          rows.filter((item) => item.canonical_slot === target.canonical_slot)
            .forEach((item) => { item.equipped = false; });
          target.equipped = true;
        } else if (target && payload.action === 'unequip') {
          target.equipped = false;
        }
        return new Response(JSON.stringify({ ok: true, item_id: target?.item_id || null }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      };
    }
    window.__w2FixtureController = window.GoOdysseyEquipmentLoadoutVisualSlice.create(
      document.querySelector('#w2-03-fixture-root'),
      options,
    );
  }, { value, canonicalMutation });
  await page.evaluate(() => window.__w2FixtureController.load());
  await page.waitForFunction(() => document.querySelector('[data-w2-status]')?.dataset.state === 'ready');
  await page.waitForFunction(() => document.querySelector('[data-w2-paper-stage]')?.dataset.supported === 'true');
}

async function readPageState(page) {
  return page.evaluate(() => ({
    root: Boolean(document.querySelector('[data-w2-03-equipment-slice]')),
    cards: document.querySelectorAll('[data-w2-item-key]').length,
    capability: document.querySelector('[data-w2-capability]')?.dataset.state || '',
    actions: document.querySelectorAll('[data-w2-mutation]').length,
    overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    stageLayers: document.querySelector('[data-w2-paper-stage]')?.dataset.paperDollLayerCount || '',
    stageSupported: document.querySelector('[data-w2-paper-stage]')?.dataset.supported || '',
    renderedLayers: document.querySelectorAll('[data-w2-paper-stage] img.rpg-wearable-layer').length,
  }));
}

async function assertViewport(browser, label, viewport) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  try {
    await page.goto(`${globalThis.__W2_ORIGIN__}${FIXTURE_PATH}`, { waitUntil: 'networkidle' });
    await mountSnapshot(page, snapshot(false));
    const state = await readPageState(page);
    assert.equal(state.root, true, `${label}: fixture root`);
    assert.equal(state.cards, 4, `${label}: cards`);
    assert.equal(state.capability, 'disabled', `${label}: Loadout OFF`);
    assert.equal(state.actions, 0, `${label}: no action when Loadout OFF`);
    assert.equal(state.overflow, false, `${label}: no horizontal overflow`);
    assert.equal(state.stageLayers, '8', `${label}: Paper Doll layer contract`);
    assert.equal(state.stageSupported, 'true', `${label}: Paper Doll supported`);
    assert.ok(state.renderedLayers >= 1, `${label}: Paper Doll rendered layers`);
    assert.deepEqual(errors, [], `${label}: browser errors`);
  } finally {
    await context.close();
  }
}

async function main() {
  const { server, origin } = await startStaticServer();
  globalThis.__W2_ORIGIN__ = origin;
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  const results = {};
  try {
    for (const [label, viewport] of Object.entries(VIEWPORTS)) {
      await assertViewport(browser, label, viewport);
      results[label] = 'PASS';
    }

    const context = await browser.newContext({ viewport: VIEWPORTS.DESKTOP });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`${origin}${FIXTURE_PATH}`, { waitUntil: 'networkidle' });

    // Loadout OFF: the projection remains readable, but no functional action
    // is exposed and selecting an item never creates a mutation.
    await mountSnapshot(page, snapshot(false));
    await page.locator('[data-w2-item-key$="::102"]').click();
    assert.equal(await page.locator('[data-w2-mutation]').count(), 0, 'OFF: no Equip action');
    assert.equal((await page.evaluate(() => window.__w2FixturePosts)).length, 0, 'OFF: no mutation');
    await page.locator('[data-w2-item-key$="::104"]').click();
    assert.match(await page.locator('[data-w2-detail-card]').innerText(), /not equippable/i, 'not-equippable state');
    assert.equal(await page.locator('[data-w2-mutation]').count(), 0, 'not-equippable: no action');

    // Loadout ON: the default mutation adapter posts only the ownership row
    // reference and action to the canonical endpoint, then re-reads state.
    await mountSnapshot(page, snapshot(true), { canonicalMutation: true });
    assert.equal(await page.locator('[data-w2-mutation]').count(), 1, 'ON: initial equipped item exposes Unequip');
    await page.locator('[data-w2-item-key$="::102"]').click();
    assert.match(await page.locator('[data-w2-detail-card]').innerText(), /replace the current/i, 'replacement affordance');
    assert.equal(await page.locator('[data-w2-mutation="equip"]').count(), 1, 'ON: Equip action');
    assert.equal((await page.evaluate(() => window.__w2FixturePosts)).length, 0, 'ON: no auto-equip');
    await page.locator('[data-w2-mutation="equip"]').click();
    await page.waitForFunction(() => document.querySelector('[data-w2-status]')?.dataset.state === 'success');
    const equipResult = await page.evaluate(() => ({
      posts: window.__w2FixturePosts,
      iron: document.querySelector('[data-w2-item-key$="::102"]')?.dataset.equipped,
      wooden: document.querySelector('[data-w2-item-key$="::101"]')?.dataset.equipped,
    }));
    assert.equal(equipResult.posts[0].url, '/api/player/inventory/equip', 'canonical mutation endpoint');
    assert.deepEqual(equipResult.posts[0].payload, { inv_id: '102', action: 'equip' }, 'canonical equip payload');
    assert.equal(equipResult.iron, 'true', 'replacement comes from fresh server projection');
    assert.equal(equipResult.wooden, 'false', 'old same-slot item is no longer equipped');

    // Unequip is also explicit and server round-tripped.
    await page.locator('[data-w2-mutation="unequip"]').click();
    await page.waitForFunction(() => document.querySelector('[data-w2-status]')?.dataset.state === 'success');
    const unequipResult = await page.evaluate(() => ({
      posts: window.__w2FixturePosts,
      iron: document.querySelector('[data-w2-item-key$="::102"]')?.dataset.equipped,
    }));
    assert.deepEqual(unequipResult.posts[1].payload, { inv_id: '102', action: 'unequip' }, 'canonical unequip payload');
    assert.equal(unequipResult.iron, 'false', 'unequip comes from fresh server projection');

    // A reload keeps the server-projected state and adds no local mutation.
    await page.evaluate(() => window.__w2FixtureController.refresh());
    await page.waitForFunction(() => document.querySelector('[data-w2-status]')?.dataset.state === 'ready');
    assert.equal(await page.locator('[data-w2-item-key$="::102"]').getAttribute('data-equipped'), 'false', 'reload persistence');
    assert.equal((await page.evaluate(() => window.__w2FixturePosts)).length, 2, 'reload does not auto-equip');

    // Change the synthetic server projection to a second player and remount;
    // no previous player's selection or ownership may leak into the surface.
    const secondPlayer = snapshot(false);
    secondPlayer.inventory = [row({ id: 'dragon_scale', invId: 201, slot: 'armor', equippable: true })];
    await mountSnapshot(page, secondPlayer);
    assert.equal(await page.locator('[data-w2-item-key$="::201"]').count(), 1, 'second player item present');
    assert.equal(await page.locator('[data-w2-item-key$="::101"]').count(), 0, 'cross-player state isolated');

    // Reduced-motion coverage is evaluated by Chromium, not by string-only
    // inspection.  It keeps the same information and suppresses motion.
    await context.close();
    const reducedContext = await browser.newContext({ viewport: VIEWPORTS.MOBILE_PORTRAIT, reducedMotion: 'reduce' });
    const reducedPage = await reducedContext.newPage();
    const reducedErrors = [];
    reducedPage.on('pageerror', (error) => reducedErrors.push(error.message));
    await reducedPage.goto(`${origin}${FIXTURE_PATH}`, { waitUntil: 'networkidle' });
    await mountSnapshot(reducedPage, snapshot(true), { canonicalMutation: true });
    const reduced = await reducedPage.evaluate(() => ({
      media: matchMedia('(prefers-reduced-motion: reduce)').matches,
      transition: getComputedStyle(document.querySelector('.w2-03-item-card')).transitionDuration,
      cards: document.querySelectorAll('[data-w2-item-key]').length,
    }));
    assert.equal(reduced.media, true, 'reduced-motion media query');
    assert.equal(reduced.transition, '0s', 'reduced-motion suppresses transitions');
    assert.equal(reduced.cards, 4, 'reduced-motion keeps content');
    assert.deepEqual(reducedErrors, [], 'reduced-motion browser errors');
    await reducedContext.close();

    // Destroy removes the task-owned DOM and its delegated listener.
    const cleanupContext = await browser.newContext({ viewport: VIEWPORTS.MOBILE_PORTRAIT });
    const cleanupPage = await cleanupContext.newPage();
    await cleanupPage.goto(`${origin}${FIXTURE_PATH}`, { waitUntil: 'networkidle' });
    await mountSnapshot(cleanupPage, snapshot(false));
    await cleanupPage.evaluate(() => window.__w2FixtureController.destroy());
    const cleanup = await cleanupPage.evaluate(() => ({
      children: document.querySelector('#w2-03-fixture-root')?.children.length,
      mounted: document.querySelector('#w2-03-fixture-root')?.dataset.w2Mounted || '',
    }));
    assert.deepEqual(cleanup, { children: 0, mounted: '' }, 'destroy cleanup');
    await cleanupContext.close();
    assert.deepEqual(errors, [], 'functional browser errors');
    results.FUNCTIONAL_PROJECTION = 'PASS';
    results.REDUCED_MOTION = 'PASS';
    results.CLEANUP = 'PASS';
    results.TESTS_PASSED = 4 + 10;
    results.TESTS_FAILED = 0;
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
  console.log(JSON.stringify({
    task: 'W2_03_EQUIPMENT_LOADOUT_VISUAL_SYSTEM_VERTICAL_SLICE_001',
    viewports: VIEWPORTS,
    results,
    physical_device_acceptance: 'REQUIRED_LATER',
  }, null, 2));
}

await main();
