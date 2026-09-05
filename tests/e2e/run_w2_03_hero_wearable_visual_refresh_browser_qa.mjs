import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_CORE_PATH || 'playwright-core');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const registryPath = path.join(
  repoRoot, 'assets', 'hero', 'equipment', 'wearables', 'wearable_registry.json',
);
const registry = JSON.parse(await fs.readFile(registryPath, 'utf8'));

const selectedByState = {
  none: [],
  weapon: ['wooden_sword'],
  cloth_robe: ['cloth_robe'],
  accessory: ['lucky_stone'],
  full: ['wooden_sword', 'dragon_scale', 'lucky_stone'],
};
const expectedByState = {
  none: { equipped: '', replacement: '' },
  weapon: { equipped: 'wooden_sword', replacement: '' },
  cloth_robe: { equipped: '', replacement: 'cloth_robe' },
  accessory: { equipped: 'lucky_stone', replacement: '' },
  full: { equipped: 'wooden_sword,dragon_scale,lucky_stone', replacement: '' },
};
const viewports = [
  ['desktop', 1440, 1000],
  ['ipad-portrait', 820, 1180],
  ['mobile-portrait', 430, 932],
];

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const executable = candidates.find(candidate => fssync.existsSync(candidate));
  if (!executable) throw new Error('No Chrome/Edge executable found. Set CHROME_BIN.');
  return executable;
}

function contentTypeFor(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

function item(itemId, inventoryId, equipped) {
  const meta = registry.equipment[itemId];
  return {
    inv_id: inventoryId,
    inventory_id: inventoryId,
    item_id: itemId,
    id: itemId,
    slot: meta.slot,
    name: itemId,
    name_en: itemId,
    display_name: itemId,
    display_name_en: itemId,
    icon: `/assets/hero/equipment/functional/${itemId}.svg`,
    icon_alt: itemId,
    owned_quantity: 1,
    owned: true,
    equipped,
    functional_equipment: true,
    active_effect_details: equipped ? [{
      key: `fixture_${itemId}`,
      label: '測試效果',
      label_en: 'Fixture effect',
      value_label: '+1',
      value_label_en: '+1',
    }] : [],
    unsupported_effects: [],
    comparison_summary: { state: equipped ? 'CURRENTLY_EQUIPPED' : 'BASELINE' },
    where_to_obtain: '測試伺服器裝備快照',
    where_to_obtain_en: 'Fixture server equipment snapshot',
    source: 'w2-03-hero-wearable-refresh-browser-fixture',
    presentation: {
      mode: 'FULL_BODY_OVERLAY',
      full_body_required: true,
      asset: meta.asset,
      layer: meta.layer,
    },
  };
}

function inventoryForState(state) {
  return selectedByState[state].map((itemId, index) => item(itemId, 200 + index, true));
}

function jsonBody(value) {
  return Buffer.from(JSON.stringify(value));
}

async function startFixtureServer() {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://127.0.0.1');
      const state = selectedByState[url.searchParams.get('fixture')] ? url.searchParams.get('fixture') : 'none';
      let body;
      let type = 'application/json; charset=utf-8';
      if (url.pathname === '/api/auth/me') {
        body = {
          logged_in: true,
          user_id: 3203,
          username: 'w203-browser',
          display_name: 'W2-03 Browser',
          is_premium: false,
          tour_done: true,
        };
      } else if (url.pathname === '/api/player/appearance') {
        body = {
          character_key: 'apprentice',
          wardrobe: [],
          equipped: {},
          combat_armor: 'none',
          combat_weapon: 'none',
          combat_cape: 'none',
          combat_offhand: 'none',
          combat_hat: 'none',
          combat_pet: 'none',
          combat_aura: 'none',
          combat_acc: 'none',
        };
      } else if (url.pathname === '/api/player/inventory') {
        body = inventoryForState(state);
      } else if (url.pathname === '/api/skills/profile') {
        body = {
          display_name: 'W2-03 Browser',
          username: 'w203-browser',
          nickname: 'W2-03 Browser',
          character_key: 'apprentice',
          rank_level: 2,
          go_rank: '20k',
          xp: 40,
          xp_next: 100,
          total_xp: 40,
          wardrobe: [],
          functional_equipment: inventoryForState(state),
          combat_stats: {
            attack_bonus_pct: 0,
            damage_reduction_pct: 0,
            crit_multiplier: 1,
            counter_negated: false,
            combo_multiplier_double: false,
          },
          active_effects: { xp_bonus: 0, drop_bonus: 0 },
        };
      } else if (url.pathname === '/api/pet/status') {
        body = { pet: null, inventory: [] };
      } else if (url.pathname === '/api/user/coins') {
        body = { coins: 0 };
      } else if (url.pathname === '/api/dm/unread_count') {
        body = { count: 0 };
      } else if (url.pathname === '/api/class/profile') {
        body = {};
      } else if (url.pathname === '/api/subscription/status') {
        body = { is_premium: false, remaining: 20, daily_limit: 20 };
      } else if (url.pathname.startsWith('/api/')) {
        body = {};
      } else if (url.pathname.startsWith('/socket.io/')) {
        body = Buffer.from('window.io=function(){return {on:function(){},emit:function(){},disconnect:function(){}}};');
        type = 'application/javascript; charset=utf-8';
      } else {
        const routeFiles = new Map([
          ['/hero', 'hero.html'],
          ['/hero.html', 'hero.html'],
          ['/inventory', 'inventory.html'],
          ['/profile', 'profile.html'],
        ]);
        const relative = routeFiles.get(url.pathname) || decodeURIComponent(url.pathname).replace(/^\/+/, '');
        const absolute = path.resolve(repoRoot, relative);
        if (absolute !== repoRoot && !absolute.startsWith(`${repoRoot}${path.sep}`)) {
          response.writeHead(403);
          response.end('forbidden');
          return;
        }
        const stat = await fs.stat(absolute).catch(() => null);
        if (!stat?.isFile()) {
          response.writeHead(404);
          response.end('not found');
          return;
        }
        body = await fs.readFile(absolute);
        type = contentTypeFor(absolute);
      }
      if (!(body instanceof Buffer)) body = jsonBody(body);
      response.writeHead(200, {
        'Content-Type': type,
        'Cache-Control': 'no-store',
        'Content-Length': body.length,
      });
      response.end(body);
    } catch (error) {
      response.writeHead(500);
      response.end(String(error));
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

async function run() {
  const evidenceDir = path.resolve(
    process.env.W2_03_EVIDENCE_DIR
      || path.join(process.env.TEMP || process.cwd(), 'go-odyssey-w2-03-hero-wearable-refresh'),
  );
  await fs.mkdir(evidenceDir, { recursive: true });
  const { server, origin } = await startFixtureServer();
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  const results = [];
  try {
    for (const [viewportName, width, height] of viewports) {
      const context = await browser.newContext({
        viewport: { width, height },
        deviceScaleFactor: 3,
        locale: 'zh-TW',
        serviceWorkers: 'block',
      });
      const page = await context.newPage();
      let activeState = 'none';
      await context.route('**/api/player/inventory', async route => {
        await route.fulfill({
          status: 200,
          headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
          body: JSON.stringify(inventoryForState(activeState)),
        });
      });
      const pageErrors = [];
      page.on('pageerror', error => pageErrors.push(error.message));
      for (const state of Object.keys(selectedByState)) {
        activeState = state;
        const expected = expectedByState[state];
        await page.goto(`${origin}/hero?tab=equipment&fixture=${state}`, { waitUntil: 'domcontentloaded' });
        await page.waitForFunction(({ equipped, replacement }) => {
          const stage = document.querySelector('#char-functional-wearable-stage');
          return stage?.dataset.equippedIds === equipped
            && stage?.dataset.replacementIds === replacement;
        }, expected, { timeout: 15000 });
        await page.waitForTimeout(350);
        const data = await page.evaluate(() => ({
          equipped: document.querySelector('#char-functional-wearable-stage')?.dataset.equippedIds || '',
          replacement: document.querySelector('#char-functional-wearable-stage')?.dataset.replacementIds || '',
          authority: document.querySelector('#char-functional-wearable-stage')?.dataset.authority || '',
          gameplayAuthority: document.querySelector('#char-functional-wearable-stage')?.dataset.gameplayAuthority || '',
          layers: [...document.querySelectorAll('#char-functional-wearable-stage img')].map(image => image.getAttribute('src')),
          replacementCards: [...new Set([...document.querySelectorAll('[data-functional-item-id]')]
            .filter(element => element.dataset.presentationState === 'art-replacement-required')
            .map(element => element.dataset.functionalItemId))],
        }));
        assert.equal(data.equipped, expected.equipped, `${viewportName}/${state} equipped projection`);
        assert.equal(data.replacement, expected.replacement, `${viewportName}/${state} replacement projection`);
        assert.equal(data.authority, 'server_equipped_projection');
        assert.equal(data.gameplayAuthority, 'none');
        assert.equal(data.layers.some(source => source?.includes('/cloth_robe.png')), false);
        assert.equal(data.layers.some(source => source?.includes('/fox_pelt.png')), false);
        if (state === 'cloth_robe') assert.deepEqual(data.replacementCards, ['cloth_robe']);
        if (state !== 'cloth_robe') assert.deepEqual(data.replacementCards, []);

        const avatar = page.locator('#char-avatar');
        await avatar.evaluate(element => {
          element.style.width = '280px';
          element.style.height = '374px';
          element.style.margin = '0 auto';
        });
        const evidencePath = path.join(evidenceDir, `after-${viewportName}-${state}.png`);
        await avatar.screenshot({ path: evidencePath, animations: 'disabled' });
        results.push({ viewport: viewportName, state, data, evidencePath });
      }
      assert.deepEqual(pageErrors, [], `${viewportName} page errors`);
      await context.close();
    }
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
  await fs.writeFile(path.join(evidenceDir, 'browser-results.json'), JSON.stringify(results, null, 2));
  console.log(`W2_03_BROWSER_EVIDENCE_DIR=${evidenceDir}`);
  console.log('W2_03_BROWSER_QA=PASS');
  console.log(`W2_03_BROWSER_CASE_COUNT=${results.length}`);
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
