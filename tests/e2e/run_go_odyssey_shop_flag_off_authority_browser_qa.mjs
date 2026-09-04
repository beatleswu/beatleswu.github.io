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
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error('No Chrome/Edge executable found. Set CHROME_BIN to run Shop browser QA.');
}

function contentTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
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
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[ext] || 'application/octet-stream';
}

async function startStaticServer(rootDir) {
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://127.0.0.1');
      const requested = decodeURIComponent(url.pathname);
      const relative = requested === '/' ? 'index.html' : requested.replace(/^\/+/, '');
      const filePath = path.resolve(rootDir, relative);
      const relativeCheck = path.relative(rootDir, filePath);
      if (relativeCheck.startsWith('..') || path.isAbsolute(relativeCheck)) {
        res.writeHead(404);
        res.end('not found');
        return;
      }
      const stat = await fsp.stat(filePath).catch(() => null);
      if (!stat?.isFile()) {
        res.writeHead(404);
        res.end('not found');
        return;
      }
      res.writeHead(200, {
        'Content-Type': contentTypeFor(filePath),
        'Cache-Control': 'no-store',
      });
      fs.createReadStream(filePath).pipe(res);
    } catch (error) {
      res.writeHead(500);
      res.end(String(error));
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  return { server, origin: `http://127.0.0.1:${address.port}` };
}

const OFF_CATALOG = {
  coins: 1000,
  earned_today: 0,
  daily_cap: 500,
  items: [],
  daily_items: [],
  weekly_items: [],
  monthly_items: [],
  inventory: {},
  equipment_offers: [],
  equipment_ownership: {},
  products: [],
  gacha: { pity_count: 0, pity: 30 },
  gacha_collection: { owned: 0, total: 0, percent: 0 },
};

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
    description: 'Server-described browser QA offer.',
    description_en: 'Server-described browser QA offer.',
    icon,
  },
}));

function canonicalCatalog(purchased) {
  return {
    ...OFF_CATALOG,
    coins: purchased ? 700 : 1000,
    equipment_offers: EQUIPMENT_OFFERS,
    equipment_ownership: purchased
      ? { wooden_sword: { owned_quantity: 1, ownership_state: 'OWNED' } }
      : { wooden_sword: { owned_quantity: 0, ownership_state: 'NOT_OWNED' } },
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

function jsonResponse(body, status = 200) {
  return {
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  };
}

async function runViewport(browser, origin, name, viewport, mode) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  const apiRequests = [];
  const browserErrors = [];
  let purchased = false;

  page.on('pageerror', error => browserErrors.push(`pageerror:${error.message}`));
  page.on('console', message => {
    // Chromium reports the intentionally rejected direct OFF probe as a
    // resource-level 409 console error.  It is an expected contract signal,
    // not an unhandled Shop/runtime error.  The static fixture also has no
    // Socket.IO upgrade endpoint; its exact handshake warning is outside the
    // Shop surface under test.  All other console errors remain failures.
    if (message.type() === 'error'
        && !(mode === 'OFF' && message.text() === 'Failed to load resource: the server responded with a status of 409 (Conflict)')
        && !(message.text().includes('WebSocket connection')
          && message.text().includes('/socket.io/')
          && message.text().includes('404'))) {
      browserErrors.push(`console:${message.text()}`);
    }
  });

  await page.route('**/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    apiRequests.push({ method: request.method(), pathname, postData: request.postData() });

    if (pathname === '/api/shop/catalog') {
      await route.fulfill(jsonResponse(mode === 'ON' ? canonicalCatalog(purchased) : OFF_CATALOG));
      return;
    }
    if (pathname === '/api/shop/buy' && request.method() === 'POST') {
      if (mode === 'OFF') {
        await route.fulfill(jsonResponse({ error: 'shop_offer_unavailable', code: 'SHOP_PURCHASE_DISABLED' }, 409));
        return;
      }
      purchased = true;
      const body = JSON.parse(request.postData() || '{}');
      await route.fulfill(jsonResponse(canonicalPurchaseResponse(body.purchase_operation_id)));
      return;
    }
    if ((pathname === '/api/shop/buy_appearance' || pathname === '/api/cosmetic-commerce/purchase')
        && request.method() === 'POST' && mode === 'OFF') {
      await route.fulfill(jsonResponse({ error: 'shop_offer_unavailable', code: 'SHOP_PURCHASE_DISABLED' }, 409));
      return;
    }
    if (pathname === '/api/auth/me') {
      await route.fulfill(jsonResponse({
        logged_in: true,
        user_id: 9001,
        username: 'shop-browser-qa',
        display_name: 'Shop Browser QA',
        nickname: 'Shop Browser QA',
        is_premium: false,
      }));
      return;
    }
    if (pathname === '/api/cosmetic-commerce/catalog') {
      await route.fulfill(jsonResponse({ products: [], presentation_candidates: [] }));
      return;
    }
    if (pathname === '/api/premium/v1/offer') {
      await route.fulfill(jsonResponse({ error: 'premium_disabled' }));
      return;
    }
    if (pathname === '/api/pet/status') {
      await route.fulfill(jsonResponse({ pet: null, inventory: [] }));
      return;
    }
    await route.fulfill(jsonResponse({}));
  });

  try {
    await page.goto(`${origin}/shop.html`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => {
      const balance = document.querySelector('#coin-bal');
      return balance?.dataset?.c044BalanceState === 'authoritative';
    });

    const initial = await page.evaluate(() => ({
      equipmentPanelHidden: document.querySelector('[data-c053-option-b-surface="equipment"]')?.hidden,
      cosmeticPanelHidden: document.querySelector('[data-c053-option-b-surface="cosmetics"]')?.hidden,
      offerCards: document.querySelectorAll('[data-equipment-offer-id]').length,
      visibleBuyButtons: [...document.querySelectorAll('button[data-equipment-purchase]')]
        .filter(button => !button.hidden && !button.closest('[hidden]') && button.getBoundingClientRect().width > 0).length,
      legacyVisible: [...document.querySelectorAll('[data-c053-option-b-retired]')]
        .some(element => !element.hidden && !element.closest('[hidden]')),
      balance: document.querySelector('#coin-bal')?.textContent,
    }));

    assert.equal(initial.equipmentPanelHidden, mode === 'OFF', `${name}: canonical equipment panel state`);
    assert.equal(initial.cosmeticPanelHidden, mode === 'OFF', `${name}: canonical cosmetics panel state`);
    assert.equal(initial.offerCards, mode === 'ON' ? 3 : 0, `${name}: canonical offer cards`);
    assert.equal(mode === 'ON' ? initial.visibleBuyButtons >= 3 : initial.visibleBuyButtons === 0, true, `${name}: visible Buy controls`);
    assert.equal(initial.legacyVisible, false, `${name}: retired Shop surfaces remain contained`);
    assert.equal(initial.balance, '1,000', `${name}: authoritative Coins display`);

    if (mode === 'OFF') {
      const direct = await page.evaluate(async () => {
        const response = await fetch('/api/shop/buy', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item_id: 'wooden_sword', purchase_operation_id: 'browser-off-direct-1' }),
        });
        return { status: response.status, body: await response.json() };
      });
      assert.equal(direct.status, 409, `${name}: direct OFF mutation status`);
      assert.deepEqual(direct.body, {
        error: 'shop_offer_unavailable',
        code: 'SHOP_PURCHASE_DISABLED',
      }, `${name}: direct OFF mutation contract`);
      assert.equal(
        apiRequests.filter(request => request.pathname === '/api/shop/buy').length,
        1,
        `${name}: one direct rejected mutation request`,
      );
    } else {
      const buy = page.locator('button[data-equipment-purchase="browser-wooden-sword"]').first();
      await buy.click();
      await page.waitForFunction(() => document.querySelector('#equipment-purchase-feedback')?.dataset?.state === 'success');
      const afterPurchase = await page.evaluate(() => ({
        feedbackState: document.querySelector('#equipment-purchase-feedback')?.dataset?.state,
        ownedButtons: [...document.querySelectorAll('button[data-equipment-purchase]')]
          .filter(button => button.dataset.c044Ownership === 'owned').length,
        balance: document.querySelector('#coin-bal')?.textContent,
      }));
      assert.equal(afterPurchase.feedbackState, 'success', `${name}: purchase success feedback`);
      assert.ok(afterPurchase.ownedButtons >= 1, `${name}: ownership refresh is visible`);
      assert.equal(afterPurchase.balance, '700', `${name}: purchase response/catalog balance refresh`);
      assert.equal(
        apiRequests.filter(request => request.pathname === '/api/shop/buy').length,
        1,
        `${name}: one canonical purchase request`,
      );
      assert.equal(
        apiRequests.filter(request => request.pathname.includes('/equip')).length,
        0,
        `${name}: purchase does not auto-equip`,
      );
    }

    assert.deepEqual(browserErrors, [], `${name}: no browser runtime errors`);
    return {
      name,
      mode,
      viewport,
      initial,
      apiRequests: apiRequests.map(request => ({ method: request.method, pathname: request.pathname })),
    };
  } finally {
    await page.close();
  }
}

async function main() {
  const { server, origin } = await startStaticServer(repoRoot);
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  const viewports = [
    ['desktop', { width: 1440, height: 900 }],
    ['ipad-landscape', { width: 1024, height: 768 }],
    ['ipad-portrait', { width: 768, height: 1024 }],
    ['mobile-portrait', { width: 390, height: 844 }],
  ];
  const cases = [];
  try {
    for (const [name, viewport] of viewports) {
      cases.push(await runViewport(browser, origin, name, viewport, 'OFF'));
      cases.push(await runViewport(browser, origin, name, viewport, 'ON'));
    }
    console.log(JSON.stringify({
      ok: true,
      cases: cases.map(({ name, mode, viewport, initial }) => ({ name, mode, viewport, initial })),
      physical_device_acceptance: 'NOT_PERFORMED',
    }, null, 2));
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
