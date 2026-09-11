import assert from 'node:assert/strict';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import http from 'node:http';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const require = createRequire(import.meta.url);
const playwrightCoreRoot = process.env.SHOP_PLAYWRIGHT_CORE
  || path.resolve(repoRoot, '..', '..', 'go-website', 'node_modules', 'playwright-core');
const { chromium } = require(playwrightCoreRoot);

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const executable = candidates.find(candidate => fs.existsSync(candidate));
  if (!executable) throw new Error('No Chrome/Edge executable found. Set CHROME_BIN for Shop-C browser QA.');
  return executable;
}

function jsonResponse(body, status = 200) {
  return {
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  };
}

function contentTypeFor(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

async function startStaticServer(rootDir) {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://127.0.0.1');
      const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '') || 'index.html';
      const filePath = path.resolve(rootDir, relative);
      const relativePath = path.relative(rootDir, filePath);
      if (relativePath.startsWith('..') || path.isAbsolute(relativePath)) {
        response.writeHead(404);
        response.end('not found');
        return;
      }
      const stat = await fsp.stat(filePath).catch(() => null);
      if (!stat?.isFile()) {
        response.writeHead(404);
        response.end('not found');
        return;
      }
      response.writeHead(200, { 'Content-Type': contentTypeFor(filePath), 'Cache-Control': 'no-store' });
      fs.createReadStream(filePath).pipe(response);
    } catch (error) {
      response.writeHead(500);
      response.end(String(error));
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

const CONSUMABLES = [
  ['hint_ticket', 'Hint Ticket', 30, 'training'],
  ['ai_explain_ticket', 'AI Analysis Ticket', 50, 'training'],
  ['extra_questions_small', 'Small Training Pass', 60, 'training'],
  ['extra_questions', 'Extra Questions Ticket', 100, 'training'],
  ['grand_training_pass', 'Grand Training Pass', 180, 'training'],
  ['small_xp_potion', 'Small XP Potion', 70, 'growth'],
  ['xp_potion', 'XP Potion', 120, 'growth'],
  ['grand_xp_potion', 'Grand XP Potion', 220, 'growth'],
  ['streak_shield', 'Streak Shield', 80, 'guard'],
  ['double_streak_shield', 'Double Streak Shield', 150, 'guard'],
].map(([key, name, price, category]) => ({
  key,
  name,
  name_en: name,
  price,
  category,
  usable: ['extra_questions_small', 'extra_questions', 'grand_training_pass', 'small_xp_potion', 'xp_potion', 'grand_xp_potion', 'streak_shield', 'double_streak_shield'].includes(key) ? 'activate' : 'instant',
  effect: ['extra_questions_small', 'extra_questions', 'grand_training_pass', 'small_xp_potion', 'xp_potion', 'grand_xp_potion', 'streak_shield', 'double_streak_shield'].includes(key) ? { key } : undefined,
}));

const EQUIPMENT_OFFERS = [
  ['browser-wooden-sword', 'wooden_sword', 'WEAPON', 300, '🗡️'],
  ['browser-cloth-robe', 'cloth_robe', 'ARMOR', 250, '🛡️'],
  ['browser-lucky-stone', 'lucky_stone', 'ACCESSORY', 150, '💎'],
].map(([offer_id, item_id, acquisition_class, price, icon]) => ({
  offer_id,
  item_id,
  quantity: 1,
  currency_type: 'COINS',
  price,
  destination: 'player_inventory',
  acquisition_class,
  status: 'ACTIVE',
  duplicate_policy: 'REJECT_IF_OWNED',
  presentation_metadata: {
    name: item_id,
    name_en: item_id.replaceAll('_', ' '),
    description: 'Server-described R1 equipment offer.',
    description_en: 'Server-described R1 equipment offer.',
    icon,
  },
}));

const COSMETICS = [
  ['cosmetic.r1.outfit.one', 'r1_outfit_one', 'R1 Outfit One', 200, false],
  ['cosmetic.r1.outfit.two', 'r1_outfit_two', 'R1 Outfit Two', 250, true],
  ['cosmetic.r1.outfit.three', 'r1_outfit_three', 'R1 Outfit Three', 300, false],
  ['cosmetic.r1.back.one', 'r1_back_one', 'R1 Back One', 350, false],
  ['cosmetic.r1.back.two', 'r1_back_two', 'R1 Back Two', 400, false],
  ['cosmetic.r1.accessory.one', 'r1_accessory_one', 'R1 Accessory One', 450, false],
].map(([product_id, cosmetic_id, name, price, owned]) => ({
  product_id,
  cosmetic_id,
  category: 'outfit',
  name,
  name_en: name,
  flavor: 'Server-described R1 cosmetic.',
  flavor_en: 'Server-described R1 cosmetic.',
  rarity: 'common',
  unlock_type: 'coins',
  currency: 'coins',
  price,
  ownership: { owned },
  equipped_state: { equipped: false },
  preview_asset: { canonical_art_available: false, fallback_emoji: '🎽', fallback_color: '#233' },
}));

function catalogFor({ purchaseEnabled, includePurchaseField = true, purchased = false }) {
  return {
    ...(includePurchaseField ? { purchase_enabled: purchaseEnabled } : {}),
    coins: purchased ? 700 : 1000,
    earned_today: 0,
    daily_cap: 500,
    items: CONSUMABLES,
    daily_items: CONSUMABLES,
    weekly_items: [],
    monthly_items: [],
    inventory: { xp_potion: 3 },
    equipment_offers: EQUIPMENT_OFFERS,
    equipment_ownership: {
      wooden_sword: { owned_quantity: purchased ? 1 : 0, ownership_state: purchased ? 'OWNED' : 'NOT_OWNED' },
      cloth_robe: { owned_quantity: 0, ownership_state: 'NOT_OWNED' },
      lucky_stone: { owned_quantity: 0, ownership_state: 'NOT_OWNED' },
    },
    daily_slots: [],
    daily_slots_visible: 3,
    gacha: { cost: 150, pity: 30, pity_count: 0, rates: {} },
    gacha_collection: { owned: 0, total: 0, percent: 0, rarity_owned: {}, rarity_totals: {} },
    shop_product_grant_registry: [],
  };
}

function canonicalPurchaseResponse(operationId) {
  return {
    ok: true,
    source_operation_id: operationId,
    ownership_reference: 'player_inventory:9001',
    coins_spent: 300,
    coins_after: 700,
    canonical_acquisition_result: {
      source_type: 'SHOP_COIN_PURCHASE',
      source_operation_id: operationId,
      source_reference: 'browser-wooden-sword',
      destination: 'PLAYER_INVENTORY',
      ownership_authority: 'player_inventory',
      ownership_reference: 'player_inventory:9001',
      item_id: 'wooden_sword',
      quantity: 1,
      can_equip: true,
      can_wear: true,
      is_new: true,
      replayed: false,
    },
  };
}

async function runCase(browser, origin, { name, purchaseEnabled, includePurchaseField, language = 'zh' }) {
  const page = await browser.newPage({ viewport: { width: 1024, height: 768 } });
  const requests = [];
  let purchased = false;
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    requests.push({ method: request.method(), pathname });
    if (pathname === '/api/shop/catalog') {
      await route.fulfill(jsonResponse(catalogFor({ purchaseEnabled, includePurchaseField, purchased })));
      return;
    }
    if (pathname === '/api/cosmetic-commerce/catalog') {
      await route.fulfill(jsonResponse({ products: COSMETICS, presentation_candidates: [] }));
      return;
    }
    if (pathname === '/api/shop/buy' && request.method() === 'POST') {
      if (!purchaseEnabled) {
        await route.fulfill(jsonResponse({ error: 'shop_offer_unavailable', code: 'SHOP_PURCHASE_DISABLED' }, 409));
        return;
      }
      purchased = true;
      const body = JSON.parse(request.postData() || '{}');
      await route.fulfill(jsonResponse(canonicalPurchaseResponse(body.purchase_operation_id)));
      return;
    }
    if (pathname === '/api/cosmetic-commerce/purchase' && request.method() === 'POST') {
      await route.fulfill(jsonResponse({ ok: true, status: 'purchased', coins_after: 900 }));
      return;
    }
    if (pathname === '/api/auth/me') {
      await route.fulfill(jsonResponse({ logged_in: true, user_id: 9001, username: 'shop-c', is_premium: false }));
      return;
    }
    if (pathname === '/api/pet/status') {
      await route.fulfill(jsonResponse({ pet: null, inventory: [] }));
      return;
    }
    await route.fulfill(jsonResponse({}));
  });

  try {
    await page.goto(`${origin}/shop.html?lang=${language}`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.querySelector('#coin-bal')?.dataset?.c044BalanceState === 'authoritative');
    const state = await page.evaluate(() => ({
      bannerHidden: document.querySelector('#shop-purchase-state')?.hidden,
      bannerState: document.querySelector('#shop-purchase-state')?.dataset?.shopPurchaseState,
      source: document.querySelector('#shop-purchase-state')?.dataset?.purchaseEnabledSource,
      equipmentBuyDisabled: document.querySelector('button[data-equipment-purchase]')?.disabled,
      equipmentBuyLabel: document.querySelector('button[data-equipment-purchase]')?.textContent,
      consumableCount: document.querySelectorAll('#shop-r1-consumables-grid [data-item-key]').length,
      consumableBuyDisabled: document.querySelector('#shop-r1-consumables-grid [data-shop-purchase-control]')?.disabled,
      cosmeticCount: document.querySelectorAll('[data-cosmetic-product]').length,
      ownedCosmeticCount: document.querySelectorAll('[data-cosmetic-state="owned"]').length,
      ownedCosmeticPurchaseButtons: document.querySelectorAll('[data-cosmetic-state="owned"] [data-cosmetic-purchase]').length,
      width: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
      errors: [
        'shop_offer_unavailable', 'SHOP_PURCHASE_DISABLED', 'LEGACY_PURCHASE_RETIRED',
        'insufficient_coins', 'already_owned', 'purchase_operation_in_progress',
        'purchase_operation_conflict', 'purchase_failed', 'unknown_shop_failure',
      ].map(code => [code, errorMessage(code)]),
    }));
    assert.deepEqual(errors, [], `${name}: no browser page errors`);
    assert.equal(state.bannerState, purchaseEnabled === true ? 'open' : 'closed', `${name}: closed/open state`);
    assert.equal(state.bannerHidden, purchaseEnabled === true, `${name}: banner visibility`);
    assert.equal(state.source, includePurchaseField ? 'server' : 'missing', `${name}: field source`);
    assert.equal(state.consumableCount, 10, `${name}: exact ten server consumables render`);
    assert.equal(state.cosmeticCount, 6, `${name}: all six server cosmetics render`);
    assert.equal(state.ownedCosmeticCount, 1, `${name}: owned cosmetic state renders`);
    assert.equal(state.ownedCosmeticPurchaseButtons, 0, `${name}: owned cosmetic has no purchase action`);
    assert.ok(state.width <= state.viewport + 1, `${name}: no horizontal overflow`);
    for (const [code, message] of state.errors) {
      assert.notEqual(message, code, `${name}: raw error code ${code} is not visible`);
      if (code === 'unknown_shop_failure') assert.ok(message.length > 0);
    }

    if (purchaseEnabled !== true) {
      assert.equal(state.consumableBuyDisabled, true, `${name}: consumable Buy is disabled while closed`);
      await page.evaluate(() => document.querySelector('#shop-r1-consumables-grid [data-shop-purchase-control]')?.click());
      await new Promise(resolve => setTimeout(resolve, 80));
      assert.equal(
        requests.filter(request => request.pathname === '/api/shop/buy' && request.method === 'POST').length,
        0,
        `${name}: disabled Buy does not issue a purchase request`,
      );
      return { name, state, purchaseRequests: 0 };
    }

    const itemState = await page.evaluate(() => {
      renderR1Consumables(catalog);
      const potion = document.querySelector('#shop-r1-consumables-grid [data-item-key="xp_potion"]');
      return {
        itemCount: document.querySelectorAll('#shop-r1-consumables-grid .item-card').length,
        potionBuyDisabled: potion?.querySelector('button')?.disabled,
        useCopy: potion?.querySelector('[data-shop-purchase-use]')?.textContent || '',
      };
    });
    assert.equal(itemState.itemCount, 10, `${name}: exact ten consumables render`);
    assert.equal(itemState.potionBuyDisabled, false, `${name}: repeatable consumable stays buyable with quantity`);
    assert.match(itemState.useCopy, /Added to Backpack/i, `${name}: Buy copy is inventory delivery`);
    assert.match(itemState.useCopy, /Activate it later from Backpack/i, `${name}: Use copy is deferred activation`);

    await page.locator('button[data-equipment-purchase="browser-wooden-sword"]').first().click();
    await page.waitForFunction(() => document.querySelector('#equipment-purchase-feedback')?.dataset?.state === 'success');
    const after = await page.evaluate(() => ({
      balance: document.querySelector('#coin-bal')?.textContent,
      ownedButtons: [...document.querySelectorAll('button[data-equipment-purchase]')]
        .filter(button => button.dataset.c044Ownership === 'owned').length,
    }));
    assert.equal(after.balance, '700', `${name}: balance refreshes after purchase`);
    assert.ok(after.ownedButtons >= 1, `${name}: ownership/catalog refreshes after purchase`);
    assert.equal(
      requests.filter(request => request.pathname === '/api/shop/buy' && request.method === 'POST').length,
      1,
      `${name}: one purchase request`,
    );
    return { name, state, itemState, after, purchaseRequests: 1 };
  } finally {
    await page.close();
  }
}

async function main() {
  const { server, origin } = await startStaticServer(repoRoot);
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  try {
    const cases = [];
    cases.push(await runCase(browser, origin, { name: 'desktop-closed', purchaseEnabled: false, includePurchaseField: true }));
    cases.push(await runCase(browser, origin, { name: 'desktop-missing', purchaseEnabled: undefined, includePurchaseField: false }));
    cases.push(await runCase(browser, origin, { name: 'desktop-open', purchaseEnabled: true, includePurchaseField: true, language: 'en' }));
    for (const [name, width, height] of [['mobile-closed', 390, 844], ['desktop-open-layout', 1440, 900]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      await page.route('**/api/**', async route => {
        const pathname = new URL(route.request().url()).pathname;
        if (pathname === '/api/shop/catalog') return route.fulfill(jsonResponse(catalogFor({ purchaseEnabled: false, includePurchaseField: true })));
        if (pathname === '/api/cosmetic-commerce/catalog') return route.fulfill(jsonResponse({ products: COSMETICS, presentation_candidates: [] }));
        if (pathname === '/api/auth/me') return route.fulfill(jsonResponse({ logged_in: true, user_id: 9001, username: 'shop-c', is_premium: false }));
        return route.fulfill(jsonResponse({}));
      });
      await page.goto(`${origin}/shop.html?lang=zh`, { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => document.querySelector('#coin-bal')?.dataset?.c044BalanceState === 'authoritative');
      const layout = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth, statusRole: document.querySelector('#shop-purchase-state')?.getAttribute('role'), statusLive: document.querySelector('#shop-purchase-state')?.getAttribute('aria-live') }));
      assert.ok(layout.width <= layout.viewport + 1, `${name}: responsive layout has no horizontal overflow`);
      assert.equal(layout.statusRole, 'status', `${name}: purchase state is announced`);
      assert.equal(layout.statusLive, 'polite', `${name}: purchase state has polite live announcement`);
      await page.close();
    }
    console.log(JSON.stringify({ ok: true, cases, responsive: ['mobile-closed', 'desktop-open-layout'], physical_device_acceptance: 'NOT_PERFORMED' }, null, 2));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
