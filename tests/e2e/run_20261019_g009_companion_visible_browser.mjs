// G009 visible-Hero Browser E2E, with REAL Flask routes and a disposable
// local SQLite-only fixture. NOT production/Test02; no API mocking.
import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import { chromium } from 'playwright-core';

const base = new URL(process.env.G009_FIXTURE_ORIGIN || 'http://127.0.0.1:5082');
assert.equal(base.protocol, 'http:', 'Only local disposable HTTP fixture is permitted');
assert(['127.0.0.1', 'localhost'].includes(base.hostname), 'Production is forbidden');
const executablePath = process.env.CHROME_BIN
  || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, serviceWorkers: 'block' });
const apiCalls = [], pageErrors = [], checks = [];
page.on('pageerror', e => pageErrors.push(String(e)));
page.on('request', request => {
  if (request.method() === 'POST' && new URL(request.url()).pathname.startsWith('/api/pet/'))
    apiCalls.push({ method: request.method(), path: new URL(request.url()).pathname,
      body: JSON.parse(request.postData() || '{}') });
});
async function snapshot() {
  return page.evaluate(async () => {
    const res = await fetch('/api/pet/status', { credentials: 'include', cache: 'no-store' });
    if (!res.ok) throw new Error('status HTTP ' + res.status);
    const value = await res.json();
    return {
      active: value.spirit_projection?.active_spirit_id,
      pet: value.pet,
      inventory: value.inventory,
    };
  });
}
const count = path => apiCalls.filter(x => x.path === path).length;
async function record(name, callback) {
  await callback();
  checks.push({ name, verdict: 'PASS' });
}
let output;
try {
  await page.goto(new URL('/__d037_login?next=%2Fhero%3Ftab%3Dpet', base).toString(), {
    waitUntil: 'domcontentloaded', timeout: 15000,
  });
  await record('g009_visible_pet_tab_and_real_button', async () => {
    await page.locator('[data-g009-select-spirit="starpath_antlerling"]')
      .waitFor({ state: 'visible', timeout: 10000 });
    assert.equal(await page.locator('[data-g009-pet-action="pet"]').isVisible(), true);
    assert.equal(await page.locator('[data-g009-pet-action="feed"][data-g009-food-key="go_spirit_candy"]').isVisible(), true);
    assert.equal(await page.locator('[data-g009-pet-action="feed"][data-g009-food-key="starfruit"]').isDisabled(), true);
  });

  const before = await snapshot();
  await record('switch_click_single_server_mutation_and_active_ui', async () => {
    assert.equal(before.active, 'ink_drop_kelpie');
    const old = count('/api/pet/switch');
    await page.locator('[data-g009-select-spirit="starpath_antlerling"]').click({ timeout: 7000 });
    await page.locator('#g009-companion-active .g009-companion-card[data-pet-key="starpath_antlerling"]')
      .waitFor({ timeout: 10000 });
    const after = await snapshot();
    assert.equal(after.active, 'starpath_antlerling');
    assert.equal(count('/api/pet/switch'), old + 1, 'one click must produce one switch POST');
    assert.equal(await page.locator('[data-g009-select-spirit="starpath_antlerling"]').count(), 0,
      'active companion must cease being a switch button');
  });

  await record('pat_click_invokes_real_authoritative_interaction', async () => {
    const old = count('/api/pet/interact');
    const beforePat = await snapshot();
    await page.locator('[data-g009-pet-action="pet"]').click({ timeout: 7000 });
    await page.waitForFunction(() => {
      const x = document.querySelector('[data-g009-pet-action="pet"]');
      return !!x && !x.disabled;
    }, null, { timeout: 10000 });
    const afterPat = await snapshot();
    assert.equal(count('/api/pet/interact'), old + 1);
    assert(afterPat.pet.affection >= beforePat.pet.affection,
      'pat must never reduce affection; cooldown state remains authoritative');
  });

  await record('food_double_click_is_one_POST_and_one_consumption', async () => {
    const old = count('/api/pet/feed');
    const first = await snapshot();
    const food = first.inventory.find(x => x.key === 'go_spirit_candy');
    assert.equal(food.qty, 2, 'fresh disposable fixture starts with 2 foods');
    await page.evaluate(() => {
      const button = document.querySelector('[data-g009-pet-action="feed"][data-g009-food-key="go_spirit_candy"]');
      button.click(); button.click();
    });
    await page.waitForFunction(() => {
      const button = document.querySelector('[data-g009-pet-action="feed"][data-g009-food-key="go_spirit_candy"]');
      return !!button && !button.disabled && button.textContent.includes('× 1');
    }, null, { timeout: 10000 });
    const last = await snapshot();
    assert.equal(count('/api/pet/feed'), old + 1, 'one burst cannot send two feed operations');
    assert.equal(last.inventory.find(x => x.key === 'go_spirit_candy').qty, 1,
      'server must consume exactly one inventory item');
    assert.match(apiCalls.filter(x => x.path === '/api/pet/feed').at(-1).body.operation_id,
      /^companion:feed:/);
  });

  await record('committed_feed_lost_response_retries_at_zero_inventory_once', async () => {
    const initial = await snapshot();
    assert.equal(initial.inventory.find(x => x.key === 'go_spirit_candy').qty, 1);
    const before = count('/api/pet/feed');
    let withheld = 0;
    await page.route('**/api/pet/feed', async route => {
      withheld += 1;
      if (withheld === 1) {
        // Real Flask mutates the disposable database, then its response is lost.
        const committed = await route.fetch();
        assert.equal(committed.status(), 200);
      }
      if (withheld <= 2) await route.abort('failed');
      else await route.continue();
    });
    const selector = '[data-g009-pet-action="feed"][data-g009-food-key="go_spirit_candy"]';
    await page.locator(selector).click({ timeout: 7000 });
    await page.waitForFunction(() =>
      typeof _petFeedPending !== 'undefined' && !!_petFeedPending &&
      !!document.querySelector('[data-g009-pet-action="feed"][data-g009-food-key="go_spirit_candy"]:not(:disabled)'),
      null, { timeout: 10000 });
    assert.equal(withheld, 2, 'two failed responses must not start a third automatic mutation');
    const interrupted = apiCalls.filter(x => x.path === '/api/pet/feed').slice(-2);
    assert.equal(interrupted.length, 2);
    assert.equal(interrupted[0].body.operation_id, interrupted[1].body.operation_id);
    await page.evaluate(() => loadPetStatus());
    assert.equal((await snapshot()).inventory.find(x => x.key === 'go_spirit_candy').qty, 0);
    assert.equal(await page.locator(selector).isEnabled(), true,
      'the pending idempotent confirmation must remain available at zero quantity');
    assert.match(await page.locator(selector).innerText(), /Confirm previous feed|確認上次餵食/);
    await page.unroute('**/api/pet/feed');
    await page.locator(selector).click({ timeout: 7000 });
    await page.waitForFunction(() =>
      typeof _petFeedPending !== 'undefined' && !_petFeedPending, null, { timeout: 10000 });
    const final = await snapshot();
    assert.equal(final.inventory.find(x => x.key === 'go_spirit_candy').qty, 0);
    const requests = apiCalls.filter(x => x.path === '/api/pet/feed').slice(-3);
    assert.equal(requests.length, 3);
    assert(requests.every(x => x.body.operation_id === requests[0].body.operation_id),
      'the final confirmation must never use a new operation identity');
    assert.equal(count('/api/pet/feed'), before + 3);
  });

  await record('refresh_preserves_active_and_food_inventory', async () => {
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.locator('#g009-companion-active .g009-companion-card[data-pet-key="starpath_antlerling"]')
      .waitFor({ timeout: 10000 });
    const state = await snapshot();
    assert.equal(state.active, 'starpath_antlerling');
    assert.equal(state.inventory.find(x => x.key === 'go_spirit_candy').qty, 0);
    assert.equal(await page.locator('[data-g009-select-spirit="ink_drop_kelpie"]').isVisible(), true);
    assert.equal(await page.locator('[data-g009-pet-action="pet"]').isVisible(), true);
  });

  await record('chrome_tablet_touch_emulation_switch_not_real_iPad', async () => {
    // Emulator only: still requires Owner Real iPad touch UAT before release.
    const tablet = await browser.newPage({
      viewport: { width: 820, height: 1180 },
      deviceScaleFactor: 2,
      hasTouch: true,
      isMobile: true,
      serviceWorkers: 'block',
    });
    tablet.on('pageerror', e => pageErrors.push(String(e)));
    try {
      await tablet.goto(new URL('/__d037_login?next=%2Fhero%3Ftab%3Dpet', base).toString(),
        { waitUntil: 'domcontentloaded', timeout: 15000 });
      await tablet.locator('[data-g009-select-spirit="ink_drop_kelpie"]')
        .waitFor({ state: 'visible', timeout: 10000 });
      await tablet.locator('[data-g009-select-spirit="ink_drop_kelpie"]').tap({ timeout: 9000 });
      await tablet.locator('#g009-companion-active .g009-companion-card[data-pet-key="ink_drop_kelpie"]')
        .waitFor({ timeout: 10000 });
    } finally {
      await tablet.close();
    }
  });

  await record('no_browser_script_exceptions', async () => {
    assert.deepEqual(pageErrors, []);
  });
  output = { schema: 'G009_COMPANION_VISIBLE_REAL_LOCAL_E2E_20261019_R1',
    verdict: 'LOCAL_REAL_BROWSER_FLASK_SQLITE_PASS_NOT_TEST02_PRODUCTION',
    checks, total: checks.length, passed: checks.length, pageErrors, apiCalls,
    user_id: 'ISOLATED_FIXTURE_37037', production_session_used: false,
    real_prod_Test02_pass: false, real_iPad_UAT_pass: false };
  console.log(JSON.stringify(output, null, 2));
  if (process.env.G009_EVIDENCE_PATH)
    writeFileSync(process.env.G009_EVIDENCE_PATH, JSON.stringify(output, null, 2) + '\n', { flag: 'wx' });
} catch (e) {
  console.error('LOCAL_BROWSER_E2E_FAILED', e.stack || String(e));
  process.exitCode = 1;
} finally {
  await browser.close();
}
