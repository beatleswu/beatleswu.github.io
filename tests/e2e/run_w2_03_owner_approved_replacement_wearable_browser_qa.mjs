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
  cloth: ['cloth_robe'],
  fox: ['fox_pelt'],
  full_cloth: ['wooden_sword', 'cloth_robe', 'lucky_stone'],
  full_fox: ['wooden_sword', 'fox_pelt', 'lucky_stone'],
};
const expectedByState = {
  none: '',
  cloth: 'cloth_robe',
  fox: 'fox_pelt',
  full_cloth: 'wooden_sword,cloth_robe,lucky_stone',
  full_fox: 'wooden_sword,fox_pelt,lucky_stone',
};
const characterKeys = [
  'apprentice', 'mage', 'paladin', 'trail_apprentice', 'night_runner',
  'constellation_apprentice',
];
const viewports = [
  ['desktop', 1440, 1000],
  ['ipad-landscape', 1180, 820],
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
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

function cookieValue(request, name) {
  const header = request.headers.cookie || '';
  const pair = header.split(';').map(value => value.trim()).find(value => value.startsWith(`${name}=`));
  return pair ? decodeURIComponent(pair.slice(name.length + 1)) : '';
}

function item(itemId, inventoryId) {
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
    equipped: true,
    functional_equipment: true,
    active_effect_details: [{
      key: `fixture_${itemId}`,
      label: '測試效果',
      label_en: 'Fixture effect',
      value_label: '+1',
      value_label_en: '+1',
    }],
    unsupported_effects: [],
    comparison_summary: { state: 'CURRENTLY_EQUIPPED' },
    where_to_obtain: '測試伺服器裝備快照',
    where_to_obtain_en: 'Fixture server equipment snapshot',
    source: 'w2-03-owner-approved-replacement-browser-fixture',
    presentation: {
      mode: 'FULL_BODY_OVERLAY',
      full_body_required: true,
      asset: meta.asset,
      layer: meta.layer,
    },
  };
}

function inventoryForState(state) {
  return selectedByState[state].map((itemId, index) => item(itemId, 500 + index));
}

function jsonBody(value) {
  return Buffer.from(JSON.stringify(value));
}

function evidenceRelativePath(filePath) {
  return path.relative(repoRoot, filePath).split(path.sep).join('/');
}

async function startFixtureServer() {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url || '/', 'http://127.0.0.1');
      const character = characterKeys.includes(cookieValue(request, 'w2_03_character'))
        ? cookieValue(request, 'w2_03_character')
        : 'apprentice';
      let body;
      let type = 'application/json; charset=utf-8';
      if (url.pathname === '/api/auth/me') {
        body = {
          logged_in: true,
          user_id: 3204,
          username: 'w203-owner-approved-browser',
          display_name: 'W2-03 Owner Approved Browser',
          is_premium: false,
          tour_done: true,
        };
      } else if (url.pathname === '/api/player/appearance') {
        body = {
          character_key: character,
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
      } else if (url.pathname === '/api/skills/profile') {
        body = {
          display_name: 'W2-03 Owner Approved Browser',
          username: 'w203-owner-approved-browser',
          nickname: 'W2-03 Owner Approved Browser',
          character_key: character,
          rank_level: 2,
          go_rank: '20k',
          xp: 40,
          xp_next: 100,
          total_xp: 40,
          wardrobe: [],
          functional_equipment: [],
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
        body = Buffer.from(
          'window.io=function(){return {on:function(){},emit:function(){},disconnect:function(){}}};',
        );
        type = 'application/javascript; charset=utf-8';
      } else {
        const routeFiles = new Map([
          ['/hero', 'hero.html'],
          ['/hero.html', 'hero.html'],
        ]);
        const relative = routeFiles.get(url.pathname)
          || decodeURIComponent(url.pathname).replace(/^\/+/, '');
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

async function inspectProjection(page) {
  return page.evaluate(() => {
    const stage = document.querySelector('#char-functional-wearable-stage');
    const images = [...(stage?.querySelectorAll('img') || [])];
    const image = suffix => images.find(node => node.src.endsWith(suffix));
    const base = images.find(node => node.classList.contains('character-base'));
    const weapon = image('/wooden_sword.png');
    const cloth = image('/cloth_robe.png');
    const fox = image('/fox_pelt.png');
    const accessory = image('/lucky_stone.png');
    return {
      character: stage?.dataset.character || '',
      equipped: stage?.dataset.equippedIds || '',
      replacement: stage?.dataset.replacementIds || '',
      authority: stage?.dataset.authority || '',
      gameplayAuthority: stage?.dataset.gameplayAuthority || '',
      stageState: stage?.dataset.presentationState || '',
      images: images.map(node => node.getAttribute('src')),
      baseIndex: base ? images.indexOf(base) : -1,
      weaponIndex: weapon ? images.indexOf(weapon) : -1,
      clothIndex: cloth ? images.indexOf(cloth) : -1,
      foxIndex: fox ? images.indexOf(fox) : -1,
      accessoryIndex: accessory ? images.indexOf(accessory) : -1,
      clothLayer: cloth?.dataset.presentationLayer || '',
      foxLayer: fox?.dataset.presentationLayer || '',
      clothNaturalWidth: cloth?.naturalWidth || 0,
      foxNaturalWidth: fox?.naturalWidth || 0,
    };
  });
}

async function prepareEvidenceCamera(page) {
  await page.locator('.char-panel').evaluate(element => {
    element.style.overflow = 'visible';
    element.style.position = 'relative';
    element.style.zIndex = '20';
  });
  await page.locator('.char-avatar-wrap').evaluate(element => {
    element.style.width = '320px';
    element.style.height = '427px';
    element.style.margin = '0 auto';
  });
  const avatar = page.locator('#char-avatar');
  await avatar.evaluate(element => {
    element.style.width = '320px';
    element.style.height = '427px';
    element.style.margin = '0 auto';
    element.style.background = '#f4fafc';
    element.style.overflow = 'visible';
    element.style.position = 'relative';
    element.style.zIndex = '50';
    element.style.isolation = 'isolate';
  });
  return avatar;
}

async function run() {
  const evidenceDir = path.resolve(
    process.env.W2_03_REPLACEMENT_EVIDENCE_DIR
      || path.join(process.env.TEMP || process.cwd(), 'go-odyssey-w2-03-owner-approved-replacements'),
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
      let activeCharacter = 'apprentice';
      await context.route('**/api/player/appearance', async route => {
        await route.fulfill({
          status: 200,
          headers: {
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': 'no-store',
          },
          body: JSON.stringify({
            character_key: activeCharacter,
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
          }),
        });
      });
      await context.route('**/api/skills/profile', async route => {
        await route.fulfill({
          status: 200,
          headers: {
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': 'no-store',
          },
          body: JSON.stringify({
            display_name: 'W2-03 Owner Approved Browser',
            username: 'w203-owner-approved-browser',
            nickname: 'W2-03 Owner Approved Browser',
            character_key: activeCharacter,
            rank_level: 2,
            go_rank: '20k',
            xp: 40,
            xp_next: 100,
            total_xp: 40,
            wardrobe: [],
            functional_equipment: [],
            combat_stats: {
              attack_bonus_pct: 0,
              damage_reduction_pct: 0,
              crit_multiplier: 1,
              counter_negated: false,
              combo_multiplier_double: false,
            },
            active_effects: { xp_bonus: 0, drop_bonus: 0 },
          }),
        });
      });
      await context.route('**/api/player/inventory', async route => {
        await route.fulfill({
          status: 200,
          headers: {
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': 'no-store',
          },
          body: JSON.stringify(inventoryForState(activeState)),
        });
      });
      const pageErrors = [];
      page.on('pageerror', error => pageErrors.push(error.message));

      for (const character of characterKeys) {
        // The public Hero page intentionally exposes only the server-owned
        // selectable character keys.  Keep that authoritative page fixture
        // on the default character, then invoke the shared presentation
        // renderer directly for the six registry frames below; this tests
        // shared-frame compatibility without widening character authority.
        activeCharacter = 'apprentice';
        for (const state of Object.keys(selectedByState)) {
          activeState = state;
          await page.goto(`${origin}/hero?tab=equipment&fixture=${state}&character=${character}`, {
            waitUntil: 'domcontentloaded',
          });
          await page.waitForFunction(
            ({ expected, characterKey }) => {
              const stage = document.querySelector('#char-functional-wearable-stage');
              return stage?.dataset.equippedIds === expected
                && stage?.dataset.character === characterKey
                && stage?.dataset.presentationState === 'ready';
            },
            { expected: expectedByState[state], characterKey: activeCharacter },
            { timeout: 15000 },
          );
          if (character !== 'apprentice') {
            const result = await page.evaluate(async ({ characterKey, baseAsset, maskAsset, itemIds }) => {
              const stage = document.querySelector('#char-functional-wearable-stage');
              const rendered = await window.GoOdysseyWearableRenderer.renderSafe(
                stage,
                characterKey,
                itemIds,
                { baseAsset, maskAsset },
              );
              if (stage) stage.dataset.presentationState = rendered.supported ? 'ready' : 'fallback';
              return rendered;
            }, {
              characterKey: character,
              baseAsset: registry.characters[character].base,
              maskAsset: registry.characters[character].hair_front_mask,
              itemIds: selectedByState[state],
            });
            assert.equal(result.supported, true, `${viewportName}/${character}/${state} shared renderer`);
          }
          await page.waitForFunction(
            () => [...document.querySelectorAll('#char-functional-wearable-stage img')]
              .filter(image => !image.hidden)
              .every(image => image.complete && image.naturalWidth > 0),
            null,
            { timeout: 15000 },
          );

          const data = await inspectProjection(page);
          assert.equal(data.character, character, `${viewportName}/${character}/${state} character`);
          assert.equal(data.equipped, expectedByState[state], `${viewportName}/${character}/${state} projection`);
          assert.equal(data.replacement, '', `${viewportName}/${character}/${state} replacement projection`);
          assert.equal(data.authority, 'server_equipped_projection');
          assert.equal(data.gameplayAuthority, 'none');
          assert.equal(data.stageState, 'ready');
          assert.ok(data.baseIndex >= 0, `${viewportName}/${character}/${state} base`);

          if (state === 'none') {
            assert.equal(data.clothIndex, -1);
            assert.equal(data.foxIndex, -1);
          }
          if (state === 'cloth') {
            assert.equal(data.clothLayer, 'TORSO_ARMOR');
            assert.ok(data.clothIndex > data.baseIndex);
            assert.ok(data.clothNaturalWidth > 0);
          }
          if (state === 'fox') {
            assert.equal(data.foxLayer, 'BACK_BODY');
            assert.ok(data.foxIndex >= 0 && data.foxIndex < data.baseIndex);
            assert.ok(data.foxNaturalWidth > 0);
          }
          if (state === 'full_cloth') {
            assert.ok(data.weaponIndex > data.baseIndex);
            assert.ok(data.clothIndex > data.weaponIndex);
            assert.ok(data.accessoryIndex > data.clothIndex);
            assert.equal(data.clothLayer, 'TORSO_ARMOR');
          }
          if (state === 'full_fox') {
            assert.ok(data.foxIndex >= 0 && data.foxIndex < data.baseIndex);
            assert.ok(data.weaponIndex > data.baseIndex);
            assert.ok(data.accessoryIndex > data.weaponIndex);
            assert.equal(data.foxLayer, 'BACK_BODY');
          }

          if (character === 'apprentice') {
            const avatar = await prepareEvidenceCamera(page);
            const statePath = path.join(evidenceDir, `${viewportName}-${state}.png`);
            await avatar.screenshot({ path: statePath, animations: 'disabled' });
            const record = {
              viewport: viewportName,
              character,
              state,
              data,
              statePath: evidenceRelativePath(statePath),
            };
            if (state === 'cloth' || state === 'fox') {
              const box = await avatar.boundingBox();
              assert.ok(box && box.width > 0 && box.height > 0);
              const closePath = path.join(evidenceDir, `${viewportName}-${state}-closeup.png`);
              await page.screenshot({
                path: closePath,
                animations: 'disabled',
                clip: {
                  x: box.x + box.width * 0.08,
                  y: box.y + box.height * 0.10,
                  width: box.width * 0.84,
                  height: box.height * 0.66,
                },
              });
              record.closePath = evidenceRelativePath(closePath);
            }
            results.push(record);
          }
        }
      }
      assert.deepEqual(pageErrors, [], `${viewportName} page errors`);
      await context.close();
    }
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
  await fs.writeFile(path.join(evidenceDir, 'browser-results.json'), JSON.stringify(results, null, 2));
  console.log(`W2_03_REPLACEMENT_EVIDENCE_DIR=${evidenceDir}`);
  console.log('W2_03_OWNER_APPROVED_REPLACEMENT_BROWSER_QA=PASS');
  console.log(`W2_03_REPLACEMENT_BROWSER_CASE_COUNT=${characterKeys.length * viewports.length * Object.keys(selectedByState).length}`);
  console.log('CLOTH_ROBE_6_CHARACTER_BROWSER_PASS=YES');
  console.log('FOX_PELT_6_CHARACTER_BROWSER_PASS=YES');
  console.log('DESKTOP_EVIDENCE=PASS');
  console.log('IPAD_LANDSCAPE_EVIDENCE=PASS');
  console.log('IPAD_PORTRAIT_EVIDENCE=PASS');
  console.log('MOBILE_PORTRAIT_EVIDENCE=PASS');
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
