'use strict';

import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const PORT = Number(process.env.F025_BROWSER_PORT || 41725);
const screenshotDir = process.env.F025_SCREENSHOT_DIR ? path.resolve(process.env.F025_SCREENSHOT_DIR) : null;
const browserExecutable = process.env.F025_CHROMIUM_EXECUTABLE || null;

if (screenshotDir) fs.mkdirSync(screenshotDir, { recursive: true });

function serve(root) {
  const server = http.createServer((request, response) => {
    const urlPath = decodeURIComponent((request.url || '/').split('?')[0]);
    const relative = urlPath === '/' ? 'tests/e2e/fixtures/f025_battlefield_boss_reward_presentation.html' : urlPath.replace(/^\/+/, '');
    const filePath = path.resolve(root, relative);
    if (!filePath.startsWith(root + path.sep) || !fs.existsSync(filePath)) {
      response.writeHead(404); response.end('not found'); return;
    }
    const contentType = filePath.endsWith('.css') ? 'text/css' : filePath.endsWith('.js') ? 'text/javascript' : 'text/html';
    response.writeHead(200, { 'content-type': contentType });
    fs.createReadStream(filePath).pipe(response);
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(PORT, '127.0.0.1', () => resolve(server));
  });
}

const server = await serve(ROOT);
let browser;
const results = [];
try {
  browser = await chromium.launch({
    headless: true,
    ...(browserExecutable ? { executablePath: browserExecutable } : {}),
  });

  async function runViewport(label, viewport) {
    const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
    await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'load' });
    await page.waitForSelector('#battlefield-boss-reward-result:not([hidden])');

    async function check(name, expected) {
      await page.locator(`[data-case="${name}"]`).click();
      const state = await page.locator('#battlefield-boss-reward-result').evaluate((node) => ({
        status: node.dataset.f025Status,
        replayed: node.dataset.f025Replayed,
        text: node.textContent,
        cosmeticId: node.querySelector('[data-cosmetic-id]')?.dataset.cosmeticId || node.firstElementChild?.dataset.cosmeticId || null,
        rewardIdVisible: !!node.querySelector('.battlefield-boss-reward-card__reward-id'),
        compensationVisible: /coins|refund|replacement cosmetic|reroll/i.test(node.textContent),
        powerCopy: /equip now|power \+|increase(?:d)? combat/i.test(node.textContent),
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        cardFitsViewport: node.getBoundingClientRect().width <= window.innerWidth + 1,
      }));
      assert.equal(state.status, expected.status);
      assert.equal(state.replayed, expected.replayed);
      assert.equal(state.rewardIdVisible, expected.rewardIdVisible);
      assert.equal(state.compensationVisible, false);
      assert.equal(state.powerCopy, false);
      assert.equal(state.horizontalOverflow, false);
      assert.equal(state.cardFitsViewport, true);
      if (expected.text) assert.match(state.text, expected.text);
      if (screenshotDir) {
        await page.screenshot({
          path: path.join(screenshotDir, `${label}-${name}.png`),
          fullPage: true,
        });
      }
      results.push({ viewport: label, name, ...state });
    }

    await check('new', { status: 'FIRST_CLEAR_NEW_COSMETIC', replayed: 'false', rewardIdVisible: true, text: /robe_dragon/ });
    await check('owned', { status: 'FIRST_CLEAR_ALREADY_OWNED_NO_OP', replayed: 'false', rewardIdVisible: true, text: /already in your wardrobe/i });
    await check('not-first', { status: 'NOT_FIRST_CLEAR', replayed: 'true', rewardIdVisible: false, text: /No first-clear reward/i });

    const bad = await page.evaluate(() => {
      const target = window.__F025_FIXTURE__.target;
      const payload = { ...window.__F025_FIXTURE__.payloads.new, zone_clear: true };
      return window.BattlefieldBossRewardPresentationV1.renderResult(target, payload);
    });
    assert.equal(bad.ok, false);
    assert.equal(bad.error, 'unknown_payload_field');
    assert.equal(await page.locator('#battlefield-boss-reward-result').isHidden(), true);

    const malformed = await page.evaluate(() => {
      const target = window.__F025_FIXTURE__.target;
      const payload = { ...window.__F025_FIXTURE__.payloads.new };
      delete payload.status;
      return window.BattlefieldBossRewardPresentationV1.renderResult(target, payload);
    });
    assert.equal(malformed.ok, false);
    assert.equal(malformed.error, 'missing_payload_field');
    assert.equal(await page.locator('#battlefield-boss-reward-result').isHidden(), true);
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
