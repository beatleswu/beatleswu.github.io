'use strict';

import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const PORT = Number(process.env.F026_BROWSER_PORT || 41726);
const screenshotDir = process.env.F026_SCREENSHOT_DIR ? path.resolve(process.env.F026_SCREENSHOT_DIR) : null;
const browserExecutable = process.env.F026_CHROMIUM_EXECUTABLE || process.env.F025_CHROMIUM_EXECUTABLE || null;
const fixture = 'tests/e2e/fixtures/f026_battlefield_boss_mapping_a_presentation.html';
if (screenshotDir) fs.mkdirSync(screenshotDir, { recursive: true });

function serve(root) {
  const server = http.createServer((request, response) => {
    const urlPath = decodeURIComponent((request.url || '/').split('?')[0]);
    const relative = urlPath === '/' ? fixture : urlPath.replace(/^\/+/, '');
    const filePath = path.resolve(root, relative);
    if (!filePath.startsWith(root + path.sep) || !fs.existsSync(filePath)) {
      response.writeHead(404); response.end('not found'); return;
    }
    const contentType = filePath.endsWith('.css') ? 'text/css'
      : filePath.endsWith('.js') ? 'text/javascript'
      : filePath.endsWith('.webp') ? 'image/webp'
      : filePath.endsWith('.svg') ? 'image/svg+xml'
      : 'text/html';
    response.writeHead(200, { 'content-type': contentType });
    fs.createReadStream(filePath).pipe(response);
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(PORT, '127.0.0.1', () => resolve(server));
  });
}

const expected = [
  ['zone-01', 'zone_01', 'back_pack', '棋具布包', 'back', '/assets/hero/items/fullbody/back_pack.webp'],
  ['zone-02', 'zone_02', 'hat_cloth', '布巾', 'hat', '/assets/hero/items/hat_cloth.svg'],
  ['zone-03', 'zone_03', 'hat_bamboo', '竹笠', 'hat', '/assets/hero/items/hat_bamboo.svg'],
  ['zone-04', 'zone_04', 'robe_crane', '仙鶴袍', 'outfit', '/assets/hero/items/fullbody/robe_crane.webp'],
  ['zone-05', 'zone_05', 'hat_onihorns', '鬼角盔', 'hat', '/assets/hero/items/hat_onihorns.svg'],
  ['zone-06', 'zone_06', 'robe_dragon', '龍紋袍', 'outfit', '/assets/hero/items/fullbody/robe_dragon.webp'],
  ['zone-07', 'zone_07', 'acc_dragon_pendant', '龍形玉佩', 'accessory', '/assets/hero/items/fullbody/acc_dragon_pendant.webp'],
  ['zone-08', 'zone_08', 'back_cloak', '星紋斗篷', 'back', '/assets/hero/items/fullbody/back_cloak.webp'],
  ['zone-09', 'zone_09', 'hat_dragon_horn', '龍角冠', 'hat', '/assets/hero/items/hat_dragon_horn.svg'],
  ['zone-10', 'zone_10', 'hat_celestial_crown', '天龍金冠', 'hat', '/assets/hero/items/hat_celestial_crown.svg'],
];

const server = await serve(ROOT);
let browser;
const results = [];
try {
  browser = await chromium.launch({ headless: true, ...(browserExecutable ? { executablePath: browserExecutable } : {}) });

  async function runViewport(label, viewport) {
    const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
    await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'load' });
    await page.waitForSelector('#battlefield-boss-reward-result:not([hidden])');

    async function checkCase(name, expectedStatus, expectedId, expectedZone, shouldShowReward, screenshot) {
      await page.locator(`[data-case="${name}"]`).click();
      const state = await page.locator('#battlefield-boss-reward-result').evaluate((node) => {
        const card = node.querySelector('.battlefield-boss-reward-card');
        return ({
        status: node.dataset.f025Status,
        zone: node.querySelector('.battlefield-boss-reward-card__facts dd')?.textContent || null,
        cardId: card?.dataset.cosmeticId || null,
        canonicalId: node.querySelector('[data-canonical-cosmetic-id]')?.dataset.canonicalCosmeticId || null,
        displayName: node.querySelector('.battlefield-boss-reward-card__display-name')?.textContent || null,
        category: node.querySelector('.battlefield-boss-reward-card__reward-category')?.textContent || null,
        asset: node.querySelector('[data-canonical-cosmetic-asset]')?.dataset.canonicalCosmeticAsset || null,
        assetState: node.querySelector('[data-canonical-cosmetic-asset]')?.dataset.assetState || null,
        rewardVisible: !!node.querySelector('.battlefield-boss-reward-card__reward-id'),
        falseCompensation: /coins|refund|bonus reward|reroll|replacement cosmetic/i.test(node.textContent),
        powerCopy: /equip now|power \+|stat upgrade|increase combat/i.test(node.textContent),
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        cardFitsViewport: node.getBoundingClientRect().width <= window.innerWidth + 1,
        });
      });
      assert.equal(state.status, expectedStatus);
      assert.equal(state.cardId, expectedId);
      assert.equal(state.zone, expectedZone);
      assert.equal(state.rewardVisible, shouldShowReward);
      assert.equal(state.falseCompensation, false);
      assert.equal(state.powerCopy, false);
      assert.equal(state.horizontalOverflow, false);
      assert.equal(state.cardFitsViewport, true);
      if (shouldShowReward) {
        assert.equal(state.canonicalId, expectedId);
        assert.equal(state.asset, screenshot.asset);
        assert.equal(state.assetState, 'canonical');
        assert.match(state.displayName || '', new RegExp(screenshot.displayName));
        assert.equal(state.category, screenshot.category);
      } else {
        assert.equal(state.canonicalId, null);
        assert.equal(state.asset, null);
      }
      if (screenshot.save && screenshotDir) {
        await page.screenshot({ path: path.join(screenshotDir, `${label}-${screenshot.save}.png`), fullPage: true });
      }
      results.push({ viewport: label, name, ...state });
    }

    for (const row of expected) {
      const [name, zone, id, displayName, category, asset] = row;
      const selected = { displayName, category, asset, save: ['zone-01', 'zone-06', 'zone-10'].includes(name) ? name : null };
      await checkCase(name, 'FIRST_CLEAR_NEW_COSMETIC', id, zone, true, selected);
    }
    await checkCase('owned', 'FIRST_CLEAR_ALREADY_OWNED_NO_OP', 'robe_crane', 'zone_04', true, {
      displayName: '仙鶴袍', category: 'outfit', asset: '/assets/hero/items/fullbody/robe_crane.webp', save: 'owned',
    });
    await checkCase('not-first', 'NOT_FIRST_CLEAR', 'hat_celestial_crown', 'zone_10', false, {
      displayName: '天龍金冠', category: 'hat', asset: '/assets/hero/items/hat_celestial_crown.svg', save: 'not-first',
    });

    const unknown = await page.evaluate(() => {
      const target = window.__F026_FIXTURE__.target;
      const payload = { ...window.__F026_FIXTURE__.payloads['zone-01'], mapped_cosmetic_id: 'not_a_canonical_cosmetic' };
      return window.BattlefieldBossRewardPresentationV1.renderResult(target, payload);
    });
    assert.equal(unknown.ok, false);
    assert.equal(unknown.error, 'unknown_cosmetic');
    assert.equal(await page.locator('#battlefield-boss-reward-result').isHidden(), true);

    const missingAsset = await page.evaluate(() => {
      const target = window.__F026_FIXTURE__.target;
      const resolver = window.BattlefieldBossCosmeticDisplayV1;
      window.BattlefieldBossCosmeticDisplayV1 = {
        resolve: function () {
          return { canonical_cosmetic_id: 'back_pack', display_name: '棋具布包', display_asset: '', display_category: 'back' };
        },
      };
      const result = window.BattlefieldBossRewardPresentationV1.renderResult(target, window.__F026_FIXTURE__.payloads['zone-01']);
      window.BattlefieldBossCosmeticDisplayV1 = resolver;
      return {
        result: result,
        fallback: target.querySelector('[data-canonical-cosmetic-asset]')?.dataset.assetState || null,
        name: target.querySelector('.battlefield-boss-reward-card__display-name')?.textContent || null,
      };
    });
    assert.equal(missingAsset.result.ok, true);
    assert.equal(missingAsset.fallback, 'fallback');
    assert.equal(missingAsset.name, '棋具布包');
    await page.close();
  }

  await runViewport('desktop', { width: 1280, height: 820 });
  await runViewport('tablet', { width: 834, height: 1112 });
  await runViewport('mobile', { width: 390, height: 844 });
  console.log(JSON.stringify({ ok: true, screenshotDir, results }, null, 2));
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
